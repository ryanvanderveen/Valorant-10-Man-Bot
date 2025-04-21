import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta

class PPItems(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_db(self):
        """Get database pool from PPDB cog"""
        db_cog = self.bot.get_cog('PPDB')
        if not db_cog:
            raise RuntimeError("PPDB cog not loaded!")
        return await db_cog.get_db()

    async def _add_item_to_inventory(self, user_id: int, item_id: int, quantity: int = 1):
        """Adds an item to a user's inventory or increases the quantity."""
        db = await self._get_db()
        async with db.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_inventory (user_id, item_id, quantity)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, item_id)
                DO UPDATE SET quantity = user_inventory.quantity + EXCLUDED.quantity
            """, user_id, item_id, quantity)

    async def _remove_item_from_inventory(self, user_id: int, item_id: int, quantity: int = 1) -> bool:
        """Removes an item from a user's inventory or decreases the quantity. Returns True if successful."""
        db = await self._get_db()
        async with db.acquire() as conn:
            current_quantity = await conn.fetchval(
                "SELECT quantity FROM user_inventory WHERE user_id = $1 AND item_id = $2",
                user_id, item_id
            )
            
            if not current_quantity or current_quantity < quantity:
                return False

            if current_quantity == quantity:
                await conn.execute(
                    "DELETE FROM user_inventory WHERE user_id = $1 AND item_id = $2",
                    user_id, item_id
                )
            else:
                await conn.execute(
                    "UPDATE user_inventory SET quantity = quantity - $3 WHERE user_id = $1 AND item_id = $2",
                    user_id, item_id, quantity
                )
            return True

    async def _get_item_by_name(self, item_name: str):
        """Fetches item details from the database by name (case-insensitive)."""
        db = await self._get_db()
        async with db.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM items WHERE LOWER(name) = LOWER($1)",
                item_name
            )

    async def _apply_active_effect(self, user_id: int, effect_type: str, effect_value: int, duration_minutes: int):
        """Adds or updates an active effect for a user."""
        end_time = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        db = await self._get_db()
        async with db.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_active_effects (user_id, effect_type, effect_value, end_time)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, effect_type)
                DO UPDATE SET effect_value = EXCLUDED.effect_value, end_time = EXCLUDED.end_time
            """, user_id, effect_type, effect_value, end_time)

    @commands.command(aliases=['inv'])
    async def inventory(self, ctx):
        """Displays your current item inventory."""
        db = await self._get_db()
        async with db.acquire() as conn:
            inventory_items = await conn.fetch("""
                SELECT i.name, i.description, inv.quantity 
                FROM user_inventory inv
                JOIN items i ON inv.item_id = i.item_id
                WHERE inv.user_id = $1 AND inv.quantity > 0
                ORDER BY i.name
            """, ctx.author.id)

        if not inventory_items:
            await ctx.send(f"{ctx.author.mention}, your inventory is empty.")
            return

        embed = discord.Embed(
            title=f"🎒 {ctx.author.display_name}'s Inventory",
            color=discord.Color.gold()
        )
        for item in inventory_items:
            embed.add_field(
                name=f"{item['name']} (x{item['quantity']})",
                value=item['description'],
                inline=False
            )
        
        embed.set_footer(text="Use 'pls use [item name]' to use an item.")
        await ctx.send(embed=embed)

    @commands.command(aliases=['consume'])
    async def use(self, ctx, *, item_name: str):
        """Uses an item from your inventory."""
        user_id = ctx.author.id
        item_name = item_name.strip()

        item = await self._get_item_by_name(item_name)
        if not item or not item['usable']:
            await ctx.send(f"{ctx.author.mention}, I couldn't find a usable item named '{item_name}'. Check your spelling or `pls inventory`.")
            return

        item_id = item['item_id']
        effect_type = item['effect_type']
        effect_value = item['effect_value']
        duration_minutes = item['duration_minutes']

        # Check and Remove from Inventory
        removed = await self._remove_item_from_inventory(user_id, item_id, 1)
        if not removed:
            await ctx.send(f"{ctx.author.mention}, you don't have any '{item['name']}' to use!")
            return

        # Apply Effect
        if duration_minutes > 0:  # Timed effect (e.g., pp_boost)
            await self._apply_active_effect(user_id, effect_type, effect_value, duration_minutes)
            await ctx.send(f"{ctx.author.mention}, you used **{item['name']}**! Its effect (`{effect_type}`: {effect_value}) will last for {duration_minutes} minutes.")
        
        elif effect_type == 'reroll':  # Instant effect flag
            await self._apply_active_effect(user_id, 'reroll_available', 1, 1)
            await ctx.send(f"{ctx.author.mention}, you used **{item['name']}**! You have a reroll available for your next `pls pp` command (within 1 min).")

        else:  # Other effects
            print(f"User {user_id} used item '{item['name']}' with unhandled effect type: {effect_type}")
            await ctx.send(f"{ctx.author.mention}, you used **{item['name']}**! Its effect will be applied when relevant.")

async def setup(bot):
    await bot.add_cog(PPItems(bot))
    print("✅ PPItems Cog loaded")
