import discord
from discord.ext import commands
import random
from datetime import datetime, timezone, timedelta
import pytz

class PPCore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ET_TIMEZONE = pytz.timezone("America/New_York")

    async def _get_db(self):
        """Get database pool from PPDB cog"""
        db_cog = self.bot.get_cog('PPDB')
        if not db_cog:
            raise RuntimeError("PPDB cog not loaded!")
        return await db_cog.get_db()

    @commands.command()
    @commands.guild_only()
    async def pp(self, ctx):
        """Generate a random PP size, usable once per clock hour."""
        print(f" {ctx.author} triggered 'pls pp'")

        user = ctx.author
        user_id = user.id
        now_utc = datetime.now(timezone.utc)

        # Get database pool
        db = await self._get_db()

        # Get event cog for active effects
        event_cog = self.bot.get_cog('PPEvents')
        minigames_cog = self.bot.get_cog('PPMinigames')

        try:
            async with db.acquire() as conn:
                # Check PP Off status if minigames cog is loaded
                is_pp_off_active_here = False
                if minigames_cog and minigames_cog.is_pp_off_active(ctx.channel.id):
                    is_pp_off_active_here = True
                    print(f"[DEBUG pp] PP Off active in this channel, bypassing time check for {ctx.author.name}")
                else:
                    # Check if user has used pp command this hour
                    last_used = await conn.fetchval(
                        "SELECT last_used FROM pp_sizes WHERE user_id = $1",
                        user_id
                    )
                    
                    if last_used:
                        last_used = last_used.replace(tzinfo=timezone.utc)  # Make timezone-aware
                        # Check if last use was in the current hour
                        if (last_used.year == now_utc.year and 
                            last_used.month == now_utc.month and 
                            last_used.day == now_utc.day and 
                            last_used.hour == now_utc.hour):
                            # Calculate time until next hour
                            next_hour = now_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                            minutes, seconds = divmod((next_hour - now_utc).total_seconds(), 60)
                            await ctx.send(
                                f"{user.mention}, you've already rolled this hour! "
                                f"Try again in **{int(minutes)}m {int(seconds)}s** (at {discord.utils.format_dt(next_hour, style='t')})"
                            )
                            return

                # Clear expired effects
                await conn.execute("DELETE FROM user_active_effects WHERE end_time <= NOW()")

                # Get active effects
                active_boost = await conn.fetchrow("""
                    SELECT * FROM user_active_effects 
                    WHERE user_id = $1 AND effect_type = 'pp_boost' AND end_time > NOW()
                """, user_id)
                reroll_available = await conn.fetchrow("""
                    SELECT * FROM user_active_effects 
                    WHERE user_id = $1 AND effect_type = 'reroll_available' AND end_time > NOW()
                """, user_id)

                # Define possible PP sizes and their weights
                sizes = list(range(21))
                weights = [
                    1,  2,  3,  5,  7,  10,  15,  18,  20,  25,  # 0-9
                    30, 30, 25, 20, 15, 10,  7,   5,   3,   2,   # 10-19
                    1   # 20
                ]

                # Initial Roll & Effect Application
                initial_roll = random.choices(sizes, weights=weights, k=1)[0]
                final_size = initial_roll
                event_modifier = 0
                item_modifier = 0
                applied_effects_msg = []

                # Apply server event effect if events cog is loaded
                if event_cog:
                    event_effect = event_cog.get_current_event_effect()
                    if event_effect:
                        event_modifier = event_effect['effect']
                        applied_effects_msg.append(f"{'+' if event_modifier > 0 else ''}{event_modifier} from {event_effect['name']}")

                # Apply item boost effect
                if active_boost:
                    item_modifier = active_boost['effect_value']
                    applied_effects_msg.append(f"{'+' if item_modifier > 0 else ''}{item_modifier} from pp_boost")

                # Calculate size after effects
                final_size += (event_modifier + item_modifier)
                final_size = max(0, min(20, final_size))

                # Reroll Logic
                performed_reroll = False
                if reroll_available:
                    initial_message = f"{user.mention}, your initial roll is **{final_size} inches**."
                    if applied_effects_msg:
                        initial_message += f" (Effects: {', '.join(applied_effects_msg)})"
                    initial_message += "\nYou have a **Reroll Token**! Would you like to reroll? Respond `yes` or `no` within 30 seconds."
                    
                    sent_msg = await ctx.send(initial_message)

                    def check(m):
                        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['yes', 'no']

                    try:
                        response_msg = await self.bot.wait_for('message', timeout=30.0, check=check)
                        
                        # Consume the reroll token regardless of answer
                        await conn.execute("DELETE FROM user_active_effects WHERE user_id = $1 AND effect_type = 'reroll_available'", user_id)

                        if response_msg.content.lower() == 'yes':
                            performed_reroll = True
                            initial_roll = random.choices(sizes, weights=weights, k=1)[0]
                            final_size = initial_roll + event_modifier + item_modifier
                            final_size = max(0, min(20, final_size))
                            await ctx.send(f"{user.mention}, rerolling... Your new size is **{final_size} inches**!")
                        else:
                            await ctx.send(f"{user.mention}, okay, keeping the original roll of **{final_size} inches**.")

                    except asyncio.TimeoutError:
                        await conn.execute("DELETE FROM user_active_effects WHERE user_id = $1 AND effect_type = 'reroll_available'", user_id)
                        await ctx.send(f"{user.mention}, timed out. Keeping the original roll of **{final_size} inches**. Your Reroll Token was consumed.")

                # Update Database
                await conn.execute(
                    "INSERT INTO pp_sizes (user_id, size, last_used) VALUES ($1, $2, $3) "
                    "ON CONFLICT(user_id) DO UPDATE SET size = EXCLUDED.size, last_used = EXCLUDED.last_used",
                    user_id, final_size, now_utc
                )

                # Send final message if no reroll prompt occurred
                if not reroll_available:
                    message = f"{user.mention}'s new pp size: 8{'=' * final_size}D! (**{final_size} inches**)"
                    if applied_effects_msg:
                        message += f" (Effects: {', '.join(applied_effects_msg)})"
                    await ctx.send(message)

                # Update roles
                await self.update_current_biggest(ctx.guild)

                # Record score if PP Off is active
                if is_pp_off_active_here and minigames_cog:
                    minigames_cog.record_pp_off_score(user_id, final_size)

        except Exception as e:
            print(f" Database/Command error in pls pp: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send(f" An error occurred processing your pp command. Please try again later.")

    @commands.command()
    async def leaderboard(self, ctx):
        """Displays the top 5 users with the biggest PP sizes"""
        print(f" {ctx.author} triggered 'pls leaderboard'")

        db = await self._get_db()
        async with db.acquire() as conn:
            top_users = await conn.fetch("SELECT user_id, size FROM pp_sizes ORDER BY size DESC LIMIT 5")

        if not top_users:
            await ctx.send("No pp sizes recorded yet! Use `pls pp` to start.")
            return

        embed = discord.Embed(title=" PP Leaderboard - Biggest of the Week", color=discord.Color.purple())

        for rank, record in enumerate(top_users, start=1):
            user_id, size = record["user_id"], record["size"]
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            username = user.name if user else f"Unknown User ({user_id})"
            embed.add_field(
                name=f"#{rank}: {username}", 
                value=f"Size: 8{'=' * size}D (**{size} inches**)", 
                inline=False
            )

        await ctx.send(embed=embed)

    async def update_current_biggest(self, guild):
        """Assigns the 'Current HOG DADDY' role to the biggest PP holder"""
        db = await self._get_db()
        async with db.acquire() as conn:
            biggest = await conn.fetchrow("SELECT user_id FROM pp_sizes ORDER BY size DESC LIMIT 1")

            if biggest:
                biggest_user_id = biggest["user_id"]
                role = discord.utils.get(guild.roles, name="Current HOG DADDY")

                if role:
                    biggest_member = guild.get_member(biggest_user_id)
                    if biggest_member:
                        # Remove role from all members first
                        for member in guild.members:
                            if role in member.roles:
                                try:
                                    await member.remove_roles(role)
                                except discord.Forbidden:
                                    print(f"⚠️ Bot lacks permissions to remove role '{role.name}' from {member.name}")
                                except discord.HTTPException as e:
                                    print(f"⚠️ Failed to remove role '{role.name}' from {member.name}: {e}")

                        # Assign the role to the new biggest PP holder
                        try:
                            await biggest_member.add_roles(role)
                            print(f"🏆 {biggest_member.name} now holds 'Current HOG DADDY'!")
                        except discord.Forbidden:
                            print(f"⚠️ Bot lacks permissions to add role '{role.name}' to {biggest_member.name}")
                        except discord.HTTPException as e:
                            print(f"⚠️ Failed to add role '{role.name}' to {biggest_member.name}: {e}")

async def setup(bot):
    await bot.add_cog(PPCore(bot))
    print("✅ PPCore Cog loaded")
