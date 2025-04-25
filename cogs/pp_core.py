import discord
from discord.ext import tasks, commands
import asyncpg
import random
import os
from datetime import datetime, timedelta, time, timezone
import pytz

# --- Constants ---
DAILY_HOG_DADDY_ROLE_NAME = "Daily Hog Daddy"
DAILY_RESET_HOUR_UTC = 0 # Midnight UTC
ANNOUNCEMENT_CHANNEL_ID = 934181022659129444 # Channel for reset announcements & achievement fallback
# --- End Constants ---

class LeaderboardView(discord.ui.View):
    def __init__(self, data, title="PP Leaderboard (Overall Top Rolls)", sep=10):
        super().__init__(timeout=180) # 3 minute timeout
        self.data = data
        self.total_pages = (len(data) + sep - 1) // sep
        self.sep = sep
        self.title = title
        self._update_buttons()

    def _update_buttons(self):
        self.children[0].disabled = self.current_page <= 1 # First page button
        self.children[1].disabled = self.current_page <= 1 # Previous page button
        self.children[3].disabled = self.current_page >= self.total_pages # Next page button
        self.children[4].disabled = self.current_page >= self.total_pages # Last page button
        # Update label for page number button
        page_button = next((item for item in self.children if isinstance(item, discord.ui.Button) and item.custom_id == "page_indicator"), None)
        if page_button:
            page_button.label = f"Page {self.current_page}/{self.total_pages}"

    async def show_page(self, interaction: discord.Interaction):
        start = (self.current_page - 1) * self.sep
        end = start + self.sep
        page_data = self.data[start:end]
        embed = await self.create_leaderboard_embed(page_data, interaction.guild)
        self._update_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    async def create_leaderboard_embed(self, page_data, guild):
        embed = discord.Embed(title=self.title, color=discord.Color.blue())
        description = ""
        start_rank = (self.current_page - 1) * self.sep + 1
        for i, record in enumerate(page_data):
            rank = start_rank + i
            user = guild.get_member(record['user_id']) or f"User ID: {record['user_id']}"
            user_mention = user.mention if isinstance(user, discord.Member) else user
            description += f"{rank}. {user_mention} - {record['size']} inches\n"
        embed.description = description or "No users found."
        embed.set_footer(text=f"Page {self.current_page}/{self.total_pages}")
        return embed

    @discord.ui.button(label="<<", style=discord.ButtonStyle.grey, custom_id="first_page", row=0)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 1
        await self.show_page(interaction)

    @discord.ui.button(label="<", style=discord.ButtonStyle.blurple, custom_id="prev_page", row=0)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        await self.show_page(interaction)

    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.grey, disabled=True, custom_id="page_indicator", row=0)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass # This button is just a label

    @discord.ui.button(label=">", style=discord.ButtonStyle.blurple, custom_id="next_page", row=0)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        await self.show_page(interaction)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.grey, custom_id="last_page", row=0)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = self.total_pages
        await self.show_page(interaction)


class PPCore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_pool = None
        self.current_daily_hog_daddy_id = None
        self.daily_hog_daddy_role_id = None 

    async def cog_load(self):
        print("Attempting to connect to the database...")
        try:
            self.db_pool = await asyncpg.create_pool(dsn=os.getenv('DATABASE_URL'))
            print("✅ Database pool created successfully.")
            await self._get_hog_daddy_role(self.bot.guilds[0]) 
            await self._initialize_daily_hog_daddy() # Fetch today's leader
            self.daily_reset_task.start()
            print("✅ Daily reset task started.")
        except Exception as e:
            print(f"❌ Failed to connect to database or start tasks: {e}")

    async def cog_unload(self):
        self.daily_reset_task.cancel()
        if self.db_pool:
            await self.db_pool.close()
            print("Database pool closed.")

    async def _get_db(self):
        if not self.db_pool:
            raise ConnectionError("Database pool is not initialized.")
        return self.db_pool

    async def _initialize_daily_hog_daddy(self):
        """Fetches the current daily hog daddy on startup."""
        print("Initializing Daily Hog Daddy...")
        db = await self._get_db()
        async with db.acquire() as conn:
            start_of_day_utc = datetime.now(pytz.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Find today's highest roller so far
            record = await conn.fetchrow("""
                SELECT user_id, size FROM pp_sizes
                WHERE last_roll_timestamp >= $1
                ORDER BY size DESC, last_roll_timestamp ASC
                LIMIT 1
            """, start_of_day_utc)

            if record:
                self.current_daily_hog_daddy_id = record['user_id']
                print(f"Initialized Daily Hog Daddy to User ID: {self.current_daily_hog_daddy_id} (Score: {record['size']})")
            else:
                self.current_daily_hog_daddy_id = None
                print("No Daily Hog Daddy found for today yet.")

    async def _get_hog_daddy_role(self, guild: discord.Guild) -> discord.Role | None:
        """Gets the Daily Hog Daddy role object, caching the ID."""
        if self.daily_hog_daddy_role_id:
            role = guild.get_role(self.daily_hog_daddy_role_id)
            if role:
                return role
            else: # ID was cached but role deleted/not found
                self.daily_hog_daddy_role_id = None 
        
        # Find role by name if ID not cached or role missing
        role = discord.utils.get(guild.roles, name=DAILY_HOG_DADDY_ROLE_NAME)
        if role:
            self.daily_hog_daddy_role_id = role.id # Cache the ID
            print(f"Found Daily Hog Daddy role: {role.name} (ID: {role.id})")
            return role
        else:
            print(f"Warning: Role '{DAILY_HOG_DADDY_ROLE_NAME}' not found in guild '{guild.name}'.")
            return None

    async def _update_daily_hog_daddy(self, ctx: commands.Context, user: discord.Member, new_size: int):
        """Checks if the new roll is the highest today and updates the role."""
        guild = ctx.guild
        if not guild:
            return # Should not happen in guild commands

        db = await self._get_db()
        async with db.acquire() as conn:
            start_of_day_utc = datetime.now(pytz.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Get current highest roll today
            current_highest = await conn.fetchrow("""
                SELECT user_id, size FROM pp_sizes
                WHERE last_roll_timestamp >= $1
                ORDER BY size DESC, last_roll_timestamp ASC
                LIMIT 1
            """, start_of_day_utc)

        # Determine if this user is the new highest today
        is_new_highest = False
        if not current_highest: # No rolls today yet
            is_new_highest = True
        elif new_size > current_highest['size']: # Higher score
            is_new_highest = True
        elif new_size == current_highest['size'] and current_highest['user_id'] == user.id: # Same user, same highest score
            # No change needed unless role somehow got removed
            pass
        # If new_size == current_highest['size'] but different user, the earlier roll wins for the day.

        if is_new_highest:
            print(f"New Daily Hog Daddy potential: {user.name} ({user.id}) with {new_size} inches.")
            hog_role = await self._get_hog_daddy_role(guild)
            if not hog_role:
                print("Cannot update role, Daily Hog Daddy role not found.")
                return

            previous_hog_id = self.current_daily_hog_daddy_id
            self.current_daily_hog_daddy_id = user.id # Update internal tracker

            # Remove role from previous holder (if different)
            if previous_hog_id and previous_hog_id != user.id:
                previous_member = guild.get_member(previous_hog_id)
                if previous_member and hog_role in previous_member.roles:
                    try:
                        await previous_member.remove_roles(hog_role, reason="No longer Daily Hog Daddy")
                        print(f"Removed '{hog_role.name}' from {previous_member.name}")
                    except discord.Forbidden:
                        print(f"Bot lacks permission to remove role from {previous_member.name}.")
                    except discord.HTTPException as e:
                        print(f"Failed to remove role from {previous_member.name}: {e}")

            # Add role to new holder (if they don't have it)
            if hog_role not in user.roles:
                try:
                    await user.add_roles(hog_role, reason="New Daily Hog Daddy")
                    print(f"Added '{hog_role.name}' to {user.name}")
                    await ctx.send(f"👑 {user.mention} has taken the lead for Daily Hog Daddy with **{new_size} inches**! 👑")
                except discord.Forbidden:
                    print(f"Bot lacks permission to add role to {user.name}.")
                    await ctx.send(f"👑 {user.mention} has taken the lead for Daily Hog Daddy with **{new_size} inches**! (But I couldn't assign the role.)")
                except discord.HTTPException as e:
                    print(f"Failed to add role to {user.name}: {e}")
                    await ctx.send(f"👑 {user.mention} has taken the lead for Daily Hog Daddy with **{new_size} inches**! (But there was an error assigning the role.)")

    @tasks.loop(time=time(hour=DAILY_RESET_HOUR_UTC, minute=1, tzinfo=pytz.utc)) # Run daily at 00:01 UTC
    async def daily_reset_task(self):
        """Calculates previous day's winner, updates stats, grants achievement, announces, and clears role."""
        print(f"--- Running Daily Hog Daddy Reset Task ({datetime.now(pytz.utc)}) ---")
        now_utc = datetime.now(pytz.utc)
        end_of_yesterday = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_yesterday = end_of_yesterday - timedelta(days=1)

        print(f"Checking for winner between {start_of_yesterday} and {end_of_yesterday}")

        db = await self._get_db()
        profile_cog = self.bot.get_cog('PPProfile')
        guild = self.bot.guilds[0] if self.bot.guilds else None # Assume bot is in one guild for simplicity
        if not guild:
            print("Reset Task Error: Bot is not in any guilds?")
            return
        
        hog_role = await self._get_hog_daddy_role(guild)
        if not hog_role:
            print("Reset Task Error: Daily Hog Daddy role not found.")
            # Continue without role logic? Or stop? Let's continue for stats/achievements.

        async with db.acquire() as conn:
            # Find yesterday's winner (highest score, earliest timestamp wins ties)
            winner_record = await conn.fetchrow("""
                SELECT user_id, MAX(size) as max_size
                FROM pp_sizes
                WHERE last_roll_timestamp >= $1 AND last_roll_timestamp < $2
                GROUP BY user_id
                ORDER BY max_size DESC, MIN(last_roll_timestamp) ASC
                LIMIT 1
            """, start_of_yesterday, end_of_yesterday)

            yesterdays_winner_member = None
            if winner_record:
                winner_id = winner_record['user_id']
                winner_size = winner_record['max_size']
                print(f"Yesterday's winner found: User ID {winner_id} with score {winner_size}")
                
                yesterdays_winner_member = guild.get_member(winner_id)
                winner_mention = f"<@{winner_id}>" 
                if yesterdays_winner_member:
                    winner_mention = yesterdays_winner_member.mention

                async with conn.transaction():
                    # Update stats
                    await conn.execute("""
                        INSERT INTO user_stats (user_id, days_as_hog_daddy)
                        VALUES ($1, 1)
                        ON CONFLICT (user_id) DO UPDATE SET
                            days_as_hog_daddy = user_stats.days_as_hog_daddy + 1
                    """, winner_id)
                    print(f"Incremented days_as_hog_daddy for {winner_id}")

                    # Grant achievement if needed
                    if profile_cog:
                        # We need a context-like object or channel to send the achievement message
                        # Let's try sending to a default channel (replace with your channel ID)
                        log_channel_id = ANNOUNCEMENT_CHANNEL_ID # Replace with your actual log/announcement channel ID
                        log_channel = self.bot.get_channel(log_channel_id)
                        
                        if log_channel:
                           await profile_cog._grant_achievement_no_ctx(winner_id, 'became_hog_daddy', log_channel) 
                        else:
                            print(f"Cannot grant achievement, log channel {log_channel_id} not found.")

                # Announce yesterday's winner
                announcement_channel = guild.system_channel or log_channel # Use system channel or fallback
                if announcement_channel:
                    try:
                        await announcement_channel.send(f"🏆 Congratulations to {winner_mention} for being yesterday's **Hog Daddy** with a top roll of **{winner_size} inches**! They have held the title {await conn.fetchval('SELECT days_as_hog_daddy FROM user_stats WHERE user_id = $1', winner_id)} times! 🏆")
                    except discord.Forbidden:
                         print(f"Failed to send announcement to {announcement_channel.name}: Missing permissions.")
                else:
                    print("Failed to send announcement: No suitable channel found.")

                # --- End of DB transaction ---

            else:
                print("No winner found for yesterday.")

            # Clear role from the user who held it at midnight (might be yesterday's winner or someone else if roles weren't updated perfectly)
            current_holder_id = self.current_daily_hog_daddy_id # Who held it at the end of the day
            if current_holder_id and hog_role:
                member_to_clear = guild.get_member(current_holder_id)
                if member_to_clear and hog_role in member_to_clear.roles:
                    try:
                        await member_to_clear.remove_roles(hog_role, reason="Daily reset")
                        print(f"Cleared Daily Hog Daddy role from {member_to_clear.name} for reset.")
                    except discord.Forbidden:
                         print(f"Failed to clear role from {member_to_clear.name}: Missing permissions.")
                    except discord.HTTPException as e:
                        print(f"Failed to clear role from {member_to_clear.name}: {e}")
                elif not member_to_clear:
                     print(f"Could not find member {current_holder_id} to clear role.")

            # Reset internal tracker for the new day
            self.current_daily_hog_daddy_id = None
            print("Daily Hog Daddy ID reset for the new day.")
            print("--- Daily Reset Task Finished ---")

    @daily_reset_task.before_loop
    async def before_daily_reset_task(self):
        print('Waiting for bot to be ready before starting daily reset task...')
        await self.bot.wait_until_ready()
        print('Bot ready, daily reset task loop starting.')

    @commands.command(name='pp', help='Calculates your pp size. Can be used once per hour (resets at :00). Highest roll daily wins Hog Daddy!')
    async def pp(self, ctx):
        user = ctx.author
        user_id = user.id
        db = await self._get_db()
        profile_cog = self.bot.get_cog('PPProfile')

        # Check cooldown using last_roll_timestamp
        async with db.acquire() as conn:
            last_roll_ts = await conn.fetchval(
                "SELECT last_roll_timestamp FROM pp_sizes WHERE user_id = $1",
                user_id
            )
        
        now = datetime.now(timezone.utc) # Use timezone aware datetime
        if last_roll_ts:
            # Check if the last roll was within the current calendar hour
            if (now.year == last_roll_ts.year and
                now.month == last_roll_ts.month and
                now.day == last_roll_ts.day and
                now.hour == last_roll_ts.hour):
                
                # Calculate time until the next hour begins
                next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
                retry_after = next_hour - now
                
                # Format the remaining time nicely
                minutes_left = int(retry_after.total_seconds() // 60)
                seconds_left = int(retry_after.total_seconds() % 60)
                
                wait_message = ""
                if minutes_left > 0:
                    wait_message += f"{minutes_left} minute{'s' if minutes_left > 1 else ''}"
                if seconds_left > 0:
                    if minutes_left > 0:
                        wait_message += " and "
                    wait_message += f"{seconds_left} second{'s' if seconds_left > 1 else ''}"
                    
                await ctx.send(f"⏳ Woah there, buddy! You gotta wait {wait_message} to measure again (until the top of the hour).")
                return

        base_size = random.choices(list(range(21)), weights=[1, 2, 3, 5, 7, 10, 15, 18, 20, 25, 30, 30, 25, 20, 15, 10, 7, 5, 3, 2, 1], k=1)[0]
        final_size = base_size # Apply effects later if needed
        final_size = max(0, min(20, final_size)) # Clamp result
        
        # Update database (pp_sizes and user_stats)
        async with db.acquire() as conn:
            async with conn.transaction():
                # Update pp_sizes with new size and timestamp
                await conn.execute("""
                    INSERT INTO pp_sizes (user_id, size, last_roll_timestamp)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id)
                    DO UPDATE SET size = $2, last_roll_timestamp = $3
                """, user_id, final_size, now)

                zero_increment = 1 if final_size == 0 else 0
                twenty_increment = 1 if final_size == 20 else 0
                stats = await conn.fetchrow(""" 
                    INSERT INTO user_stats (user_id, total_rolls, zero_rolls, twenty_rolls)
                    VALUES ($1, 1, $2, $3)
                    ON CONFLICT (user_id) DO UPDATE SET
                        total_rolls = user_stats.total_rolls + 1,
                        zero_rolls = user_stats.zero_rolls + $2,
                        twenty_rolls = user_stats.twenty_rolls + $3
                    RETURNING zero_rolls, twenty_rolls
                """, user_id, zero_increment, twenty_increment)

        if profile_cog:
            if final_size == 0 and stats and stats['zero_rolls'] == 1:
                await profile_cog._grant_achievement(user, 'roll_a_zero', ctx)
            elif final_size == 20 and stats and stats['twenty_rolls'] == 1:
                await profile_cog._grant_achievement(user, 'roll_a_twenty', ctx)

        measurement = f"{final_size} inches"
        await ctx.send(f"{user.mention}'s pp is {measurement}")

        if ctx.guild: # Ensure it's in a guild context
            await self._update_daily_hog_daddy(ctx, user, final_size)
        else:
            print("Cannot update Daily Hog Daddy outside of a guild.")

    @commands.command(name='leaderboard', aliases=['lb'], help='Shows the overall PP leaderboard')
    async def leaderboard(self, ctx):
        db = await self._get_db()
        async with db.acquire() as conn:
            top_users = await conn.fetch("""
                SELECT user_id, size, last_roll_timestamp FROM pp_sizes 
                ORDER BY size DESC, last_roll_timestamp ASC
                LIMIT 100 -- Limit to a reasonable number for pagination
            """)

        if not top_users:
            await ctx.send("The leaderboard is empty!")
            return

        view = LeaderboardView(top_users, title="PP Leaderboard (Overall Top Rolls)", sep=10)
        initial_embed = await view.create_leaderboard_embed(top_users[:10], ctx.guild)
        await ctx.send(embed=initial_embed, view=view)

async def setup(bot):
    await bot.add_cog(PPCore(bot))
