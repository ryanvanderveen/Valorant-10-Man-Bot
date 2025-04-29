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
        """Uses an item from your inventory. For shrink ray, use: pls use shrink ray @targetuser"""
        user_id = ctx.author.id
        args = item_name.strip().split()
        item_name_only = item_name.strip()
        target_member = None
        # Detect if shrink ray and has a mention
        if 'shrink' in args and 'ray' in args:
            # Try to extract mention
            if ctx.message.mentions:
                target_member = ctx.message.mentions[0]
                item_name_only = 'shrink ray'
            else:
                item_name_only = 'shrink ray'
        else:
            item_name_only = item_name.strip()

        item = await self._get_item_by_name(item_name_only)
        if not item or not item['usable']:
            await ctx.send(f"{ctx.author.mention}, I couldn't find a usable item named '{item_name_only}'. Check your spelling or `pls inventory`.")
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

        # SHRINK RAY special case: shrink another user's pp
        if effect_type == 'shrink_ray':
            if not target_member:
                await ctx.send(f"{ctx.author.mention}, please mention a user to shrink their pp! Example: `pls use shrink ray @targetuser`")
                return
            if target_member.id == ctx.author.id:
                await ctx.send(f"{ctx.author.mention}, you can't shrink your own pp with the shrink ray!")
                return
            shrink_amount = abs(effect_value) if effect_value != 0 else 1
            shrunk, old_size, new_size = await self._shrink_user_pp(target_member.id, shrink_amount)
            if shrunk:
                await ctx.send(f"{ctx.author.mention} zapped {target_member.mention} with a **Shrink Ray**! Their pp shrank by {shrink_amount} inch(es)... Now {new_size} inches (was {old_size}). 😱")
            else:
                await ctx.send(f"{ctx.author.mention}, couldn't shrink {target_member.mention}'s pp (maybe they don't have one yet?).")
            return

        # Standard: Timed effect (e.g., pp_boost)
        if duration_minutes > 0:
            await self._apply_active_effect(user_id, effect_type, effect_value, duration_minutes)
            await ctx.send(f"{ctx.author.mention}, you used **{item['name']}**! Its effect (`{effect_type}`: {effect_value}) will last for {duration_minutes} minutes.")
        # Reroll
        elif effect_type == 'reroll':
            await self._apply_active_effect(user_id, 'reroll_available', 1, 1)
            await ctx.send(f"{ctx.author.mention}, you used **{item['name']}**! You have a reroll available for your next `pls pp` command (within 1 min).")
        # Catch-all: Always confirm item use
        else:
            print(f"User {user_id} used item '{item['name']}' with unhandled effect type: {effect_type}")
            await ctx.send(f"{ctx.author.mention}, you used **{item['name']}**! Its effect will be applied when relevant.")

    async def _shrink_user_pp(self, user_id: int, amount: int):
        """Shrink a user's pp by amount. Returns (True, old_size, new_size) or (False, None, None) if not found."""
        db = await self._get_db()
        async with db.acquire() as conn:
            record = await conn.fetchrow("SELECT size FROM pp_sizes WHERE user_id = $1", user_id)
            if not record:
                return False, None, None
            old_size = record['size']
            new_size = max(0, old_size - amount)
            await conn.execute("UPDATE pp_sizes SET size = $1 WHERE user_id = $2", new_size, user_id)
            return True, old_size, new_size


async def setup(bot):
    await bot.add_cog(PPItems(bot))
    print("✅ PPItems Cog loaded")
