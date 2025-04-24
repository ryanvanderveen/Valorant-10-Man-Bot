import discord
from discord.ext import tasks, commands
import random
from datetime import datetime, timezone, timedelta
import pytz
import asyncio

class PPCore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ET_TIMEZONE = pytz.timezone("America/New_York")
        self.weekly_reset_task.start() # Start the task loop

    def cog_unload(self):
        self.weekly_reset_task.cancel() # Stop the task when the cog unloads

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
        role_name = "Current HOG DADDY"
        print(f"[Role Update] Starting update for '{role_name}' in guild '{guild.name}' ({guild.id})")
        
        db = await self._get_db()
        async with db.acquire() as conn:
            biggest = await conn.fetchrow("SELECT user_id, size FROM pp_sizes ORDER BY size DESC, last_used ASC LIMIT 1")

            if not biggest:
                print(f"[Role Update] No PP scores found in DB for guild {guild.name}. Cannot update role.")
                # Optional: Remove role from anyone who might still have it if DB is empty?
                return

            biggest_user_id = biggest["user_id"]
            biggest_size = biggest["size"]
            print(f"[Role Update] Biggest PP user ID: {biggest_user_id} with size {biggest_size}")

            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                print(f"⚠️ [Role Update] Role '{role_name}' not found in guild {guild.name}. Please ensure it exists.")
                return

            biggest_member = guild.get_member(biggest_user_id)
            current_holder = None
            for member in guild.members:
                if role in member.roles:
                    current_holder = member
                    print(f"[Role Update] Found current role holder: {current_holder.name} ({current_holder.id})")
                    break # Assuming only one holder

            if biggest_member:
                # Check if the biggest member is already the holder
                if current_holder and current_holder.id == biggest_member.id:
                    print(f"[Role Update] {biggest_member.name} already has the '{role_name}' role. No change needed.")
                    return
                
                print(f"[Role Update] Attempting to set {biggest_member.name} as the new '{role_name}'.")
                # Remove from previous holder if there was one
                if current_holder:
                    try:
                        await current_holder.remove_roles(role, reason=f"New {role_name}: {biggest_member.name}")
                        print(f"[Role Update] Successfully removed role from previous holder: {current_holder.name}")
                    except discord.Forbidden:
                        print(f"⚠️ [Role Update] Bot lacks permissions to remove role '{role.name}' from {current_holder.name}. Check role hierarchy and permissions.")
                    except discord.HTTPException as e:
                        print(f"⚠️ [Role Update] Failed to remove role '{role.name}' from {current_holder.name}: {e}")
                    except Exception as e:
                        print(f"⚠️ [Role Update] Unexpected error removing role from {current_holder.name}: {e}")
                
                # Add to the new biggest member
                try:
                    await biggest_member.add_roles(role, reason=f"Achieved biggest PP: {biggest_size} inches")
                    print(f"[Role Update] Successfully assigned role to new holder: {biggest_member.name}")
                except discord.Forbidden:
                    print(f"⚠️ [Role Update] Bot lacks permissions to add role '{role.name}' to {biggest_member.name}. Check role hierarchy and permissions.")
                except discord.HTTPException as e:
                    print(f"⚠️ [Role Update] Failed to add role '{role.name}' to {biggest_member.name}: {e}")
                except Exception as e:
                    print(f"⚠️ [Role Update] Unexpected error adding role to {biggest_member.name}: {e}")

            else: # Biggest user is not in the guild anymore
                print(f"[Role Update] Biggest user ID {biggest_user_id} not found in guild {guild.name}. They may have left.")
                if current_holder:
                    print(f"[Role Update] Removing role from current holder {current_holder.name} as the top user left.")
                    try:
                        await current_holder.remove_roles(role, reason=f"{role_name} user left server")
                        print(f"[Role Update] Successfully removed role from {current_holder.name} (top user left).")
                    except discord.Forbidden:
                        print(f"⚠️ [Role Update] Bot lacks permissions to remove role '{role.name}' from {current_holder.name}.")
                    except discord.HTTPException as e:
                        print(f"⚠️ [Role Update] Failed to remove role '{role.name}' from {current_holder.name}: {e}")
                    except Exception as e:
                        print(f"⚠️ [Role Update] Unexpected error removing role from {current_holder.name}: {e}")

    @tasks.loop(hours=1) # Check every hour for the right time
    async def weekly_reset_task(self):
        # --- Configuration (Replace with actual IDs/settings) ---
        target_guild_id = 934160898828931143 # Replace with your Server ID
        announcement_channel_id = 934181022659129444 # Replace with your announcement Channel ID
        current_hog_role_name = "Current HOG DADDY" # Tracks the current leader
        past_hog_role_name = "HOG DADDY"           # Awarded to the weekly winner
        # --- End Configuration ---

        now_et = datetime.now(self.ET_TIMEZONE)
        # Check if it's Sunday (weekday 6) and midnight hour (0)
        # Run slightly after midnight to avoid race conditions with the exact turn
        if now_et.weekday() == 6 and now_et.hour == 0 and now_et.minute < 5: # Run in the first 5 mins of Sunday
            # Add a small random delay to prevent multiple instances hitting DB at once if scaled
            await asyncio.sleep(random.uniform(1, 10))
            print("[Weekly Reset] Triggered Sunday Midnight Reset.")
            guild = self.bot.get_guild(target_guild_id)
            channel = self.bot.get_channel(announcement_channel_id)

            if not guild:
                print(f"[Weekly Reset] Error: Guild {target_guild_id} not found.")
                return
            if not channel:
                print(f"[Weekly Reset] Error: Channel {announcement_channel_id} not found.")
                # Optionally try to find a default channel in the guild
                channel = guild.system_channel or next((ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages), None)
                if channel:
                    print(f"[Weekly Reset] Using fallback channel: {channel.name}")
                else:
                     print(f"[Weekly Reset] Error: No suitable announcement channel found in guild {guild.name}.")
                     return # Cannot proceed without channel

            db = await self._get_db()
            async with db.acquire() as conn:
                # Use a transaction to ensure atomicity
                async with conn.transaction():
                    # Find winner
                    winner_record = await conn.fetchrow(
                        "SELECT user_id, size FROM pp_sizes ORDER BY size DESC, last_used ASC LIMIT 1"
                    )

                    winner_member = None
                    winner_mention = "No one"
                    winner_size = 0

                    if winner_record:
                        winner_user_id = winner_record['user_id']
                        winner_size = winner_record['size']
                        winner_member = guild.get_member(winner_user_id)
                        if winner_member:
                             winner_mention = winner_member.mention
                        else:
                            # Try fetching if not cached
                            try:
                               winner_user = await self.bot.fetch_user(winner_user_id)
                               winner_mention = winner_user.mention + " (user not currently in server)"
                            except discord.NotFound:
                               winner_mention = f"User ID {winner_user_id} (user not found)"
                            except Exception as e:
                               winner_mention = f"User ID {winner_user_id} (error fetching: {e})"


                        # Announce winner
                        await channel.send(f"🎉 **Weekly PP Winner!** 🎉\nCongratulations to {winner_mention} for having the biggest PP this week with **{winner_size} inches**! They are the new **{past_hog_role_name}**!")

                        # --- Role Handling --- 
                        current_role = discord.utils.get(guild.roles, name=current_hog_role_name)
                        past_role = discord.utils.get(guild.roles, name=past_hog_role_name)

                        # 1. Remove 'Current HOG DADDY' from winner (if they have it)
                        if current_role and winner_member and current_role in winner_member.roles:
                            try:
                                await winner_member.remove_roles(current_role, reason="Weekly Reset - Won week")
                                print(f"[Weekly Reset] Removed '{current_hog_role_name}' from {winner_member.name}")
                            except Exception as e:
                                 print(f"⚠️ [Weekly Reset] Failed to remove role '{current_role.name}' from {winner_member.name}: {e}")
                        elif not current_role:
                             print(f"⚠️ [Weekly Reset] Role '{current_hog_role_name}' not found for removal.")

                        # 2. Handle 'HOG DADDY' role
                        if past_role:
                            previous_winner = None
                            # Find previous winner by checking who has the role
                            for member in guild.members:
                                if past_role in member.roles:
                                    previous_winner = member
                                    print(f"[Weekly Reset] Found previous '{past_hog_role_name}': {previous_winner.name}")
                                    break
                            
                            # Remove from previous winner (if different from new winner)
                            if previous_winner and previous_winner.id != winner_member.id:
                                try:
                                    await previous_winner.remove_roles(past_role, reason=f"New {past_hog_role_name}: {winner_member.name if winner_member else 'N/A'}")
                                    print(f"[Weekly Reset] Removed '{past_hog_role_name}' from previous winner {previous_winner.name}")
                                except Exception as e:
                                    print(f"⚠️ [Weekly Reset] Failed to remove role '{past_role.name}' from previous winner {previous_winner.name}: {e}")

                            # Add to the new winner (if they are in the server)
                            if winner_member and past_role not in winner_member.roles:
                                try:
                                    await winner_member.add_roles(past_role, reason="Weekly PP Winner")
                                    print(f"[Weekly Reset] Awarded '{past_hog_role_name}' to {winner_member.name}")
                                except Exception as e:
                                    print(f"⚠️ [Weekly Reset] Failed to add role '{past_role.name}' to {winner_member.name}: {e}")
                            elif winner_member and past_role in winner_member.roles:
                                print(f"[Weekly Reset] Winner {winner_member.name} already has the '{past_hog_role_name}' role.")
                                
                        else:
                             print(f"⚠️ [Weekly Reset] Role '{past_hog_role_name}' not found in the server.")
                        # --- End Role Handling ---

                    else:
                        await channel.send("🏆 The week has ended, but no one rolled their PP! Leaderboard reset. No new HOG DADDY assigned.")
                    
                    # Clear the leaderboard regardless of whether there was a winner
                    deleted_count_str = await conn.fetchval("DELETE FROM pp_sizes RETURNING count(*)") # Use fetchval for count
                    deleted_count = int(deleted_count_str) if deleted_count_str else 0
                    print(f"[Weekly Reset] Cleared {deleted_count} records from pp_sizes table.")
                    await channel.send("🔄 The weekly PP leaderboard has been reset! Good luck next week!")
            
            # Prevent running multiple times within the hour if the check passes early
            # Sleep until the next hour check. Important this is outside the transaction.
            await asyncio.sleep(3600 - (now_et.minute*60 + now_et.second)) 

    @weekly_reset_task.before_loop
    async def before_weekly_reset_task(self):
        await self.bot.wait_until_ready() # Wait for the bot to be ready before starting the loop
        
        while True: # Keep calculating sleep until the first run
            # Calculate initial delay until the next Sunday midnight ET
            now_et = datetime.now(self.ET_TIMEZONE)
            # Calculate days until next Sunday (0=Mon, 6=Sun)
            days_until_sunday = (6 - now_et.weekday() + 7) % 7 
            # Target time is next Sunday at 00:00:05 ET (slight buffer)
            next_sunday_midnight = (now_et + timedelta(days=days_until_sunday)).replace(hour=0, minute=0, second=5, microsecond=0)

            # If it's Sunday but before 5 seconds past midnight, the target is today
            # If it's Sunday *after* 5 seconds past midnight, aim for *next* Sunday
            if now_et.weekday() == 6 and now_et >= next_sunday_midnight:
                next_sunday_midnight += timedelta(days=7)
            # If it's not Sunday, days_until_sunday ensures we aim for the upcoming Sunday
                
            wait_seconds = (next_sunday_midnight - now_et).total_seconds()

            if wait_seconds <= 0: # Should not happen with the logic above, but safety check
                 wait_seconds = 5 # Wait a few seconds and recalculate
            
            print(f"[Weekly Reset] Task started. Waiting {wait_seconds:.2f} seconds until next scheduled run near Sunday Midnight ET ({next_sunday_midnight.strftime('%Y-%m-%d %H:%M:%S %Z%z')}).")
            await asyncio.sleep(wait_seconds)
            
            # Double check if it's the right time after waking up
            now_et_after_sleep = datetime.now(self.ET_TIMEZONE)
            if now_et_after_sleep.weekday() == 6 and now_et_after_sleep.hour == 0:
                 print("[Weekly Reset] Reached target time. Starting first reset cycle.")
                 break # Exit before_loop and start the main loop check
            else:
                 print("[Weekly Reset] Woke up, but not the right time yet. Recalculating sleep.")
                 # Loop continues to recalculate sleep


async def setup(bot):
    await bot.add_cog(PPCore(bot))
    print("✅ PPCore Cog loaded")
