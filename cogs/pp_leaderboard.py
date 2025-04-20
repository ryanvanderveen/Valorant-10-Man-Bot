import os
import asyncpg
import discord
import random
import pytz  # Timezone handling for ET
import asyncio
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import aiohttp # For API requests
import html # For decoding HTML entities

# --- Event Definitions ---
EVENTS = [
    {"name": "Heat Wave", "effect": 2, "duration_hours": 1, "start_msg": "☀️ **Heat Wave!** Things are heating up! All pp rolls get a +2 bonus for the next hour!", "end_msg": "☀️ The Heat Wave has subsided. PP rolls are back to normal.", "color": discord.Color.orange()},
    {"name": "Cold Snap", "effect": -2, "duration_hours": 1, "start_msg": "❄️ **Cold Snap!** Brrr! It's chilly... all pp rolls get a -2 penalty for the next hour!", "end_msg": "❄️ The Cold Snap has passed. PP rolls are back to normal.", "color": discord.Color.blue()},
    {"name": "Growth Spurt", "effect": 1, "duration_hours": 2, "start_msg": "🌱 **Growth Spurt!** Favorable conditions! All pp rolls get a +1 bonus for the next 2 hours!", "end_msg": "🌱 The Growth Spurt is over. PP rolls are back to normal.", "color": discord.Color.green()},
    {"name": "Shrinkage", "effect": -1, "duration_hours": 2, "start_msg": "🥶 **Shrinkage!** Uh oh... All pp rolls get a -1 penalty for the next 2 hours!", "end_msg": "🥶 The Shrinkage effect has worn off. PP rolls are back to normal.", "color": discord.Color.light_grey()},
    # Add more potential events here
]
# ------------------------

class PPLeaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.DATABASE_URL = os.getenv("DATABASE_URL")
        self.db = None  # Database pool
        self.ET_TIMEZONE = pytz.timezone("America/New_York")  # Eastern Time
        self.bot.loop.create_task(self.initialize_db())  # Initialize DB on startup
        self.reset_leaderboard.start()  # Start weekly reset task

        # Event State
        self.current_event = None
        self.event_end_time = None
        self.event_effect = 0 # Use 0 when no event active
        self.announcement_channel = None # Will be set in before_event_task
        self.event_task.start() # Start the event cycle task

        # --- Trivia State ---
        self.current_trivia_question = None
        self.trivia_timeout = 30 # Seconds to answer trivia
        self.trivia_reward = 1 # How many inches boost for correct answer (example)

        # --- Duel State ---
        # { challenged_user_id: {'challenger': challenger_id, 'timestamp': datetime_utc} }
        self.pending_duels = {}
        self.duel_timeout_seconds = 60

        # --- PP Off State ---
        self.pp_off_active = False
        self.pp_off_end_time = None
        self.pp_off_participants = {} # {user_id: highest_score}
        self.pp_off_channel = None

    async def initialize_db(self):
        """Creates database connection pool and ensures all required tables exist."""
        if not self.DATABASE_URL:
            print(" ERROR: DATABASE_URL is not set! Check your environment variables.")
            return

        # Fix asyncpg issue: Convert postgresql:// → postgres://
        if self.DATABASE_URL.startswith("postgresql://"):
            self.DATABASE_URL = self.DATABASE_URL.replace("postgresql://", "postgres://", 1)

        try:
            self.db = await asyncpg.create_pool(self.DATABASE_URL)
            print(" Successfully connected to PostgreSQL!")

            async with self.db.acquire() as conn:
                # Ensure pp_sizes table exists
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS pp_sizes (
                        user_id BIGINT PRIMARY KEY,
                        size INTEGER,
                        last_used TIMESTAMP DEFAULT NULL
                    )
                """)
                print(" Table 'pp_sizes' checked/created.")

                # Ensure items table exists
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS items (
                        item_id SERIAL PRIMARY KEY,
                        name VARCHAR(50) UNIQUE NOT NULL,
                        description VARCHAR(255),
                        effect_type VARCHAR(50), -- e.g., 'pp_boost', 'reroll', 'cooldown_reset'
                        effect_value INTEGER, -- e.g., +2 for boost, 1 for reroll flag
                        duration_minutes INTEGER DEFAULT 0, -- 0 for instant, >0 for timed boost
                        usable BOOLEAN DEFAULT TRUE
                    )
                """)
                print(" Table 'items' checked/created.")

                # Ensure user_inventory table exists
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_inventory (
                        user_id BIGINT NOT NULL,
                        item_id INTEGER NOT NULL,
                        quantity INTEGER NOT NULL DEFAULT 1,
                        PRIMARY KEY (user_id, item_id),
                        FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE
                    )
                """)
                print(" Table 'user_inventory' checked/created.")

                # Ensure user_active_effects table exists
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_active_effects (
                        user_id BIGINT NOT NULL,
                        effect_type VARCHAR(50) NOT NULL,
                        effect_value INTEGER,
                        end_time TIMESTAMP NOT NULL,
                        PRIMARY KEY (user_id, effect_type) -- Allow only one active effect of each type per user
                    )
                """)
                print(" Table 'user_active_effects' checked/created.")

                # --- Populate Items Table (if empty) ---
                item_count = await conn.fetchval("SELECT COUNT(*) FROM items")
                if item_count == 0:
                    print(" Populating 'items' table with initial data...")
                    initial_items = [
                        ('Growth Potion', 'Temporarily increases your next pp roll.', 'pp_boost', 2, 60, True), # +2 for 60 mins
                        ('Shrink Ray', 'Temporarily decreases your next pp roll. Risky!', 'pp_boost', -2, 60, True), # -2 for 60 mins
                        ('Lucky Socks', 'Slightly increases chance of a larger roll next time.', 'luck_boost', 1, 0, True), # Placeholder effect
                        ('Reroll Token', 'Grants one reroll on your next pp command.', 'reroll', 1, 0, True),
                        # ('Cooldown Coffee', 'Instantly resets your pp command cooldown.', 'cooldown_reset', 1, 0, True) # Example for later
                    ]
                    await conn.executemany("""
                        INSERT INTO items (name, description, effect_type, effect_value, duration_minutes, usable)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """, initial_items)
                    print(f" Added {len(initial_items)} initial items.")
                # -----------------------------------------

            print(" PostgreSQL database initialization complete!")

        except Exception as e:
            print(f" ERROR: Unable to connect to PostgreSQL: {e}")
            exit(1)

    # --- Helper Functions ---
    async def _add_item_to_inventory(self, user_id: int, item_id: int, quantity: int = 1):
        """Adds an item to a user's inventory or increases the quantity."""
        async with self.db.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_inventory (user_id, item_id, quantity)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, item_id)
                DO UPDATE SET quantity = user_inventory.quantity + EXCLUDED.quantity
            """, user_id, item_id, quantity)

    async def _remove_item_from_inventory(self, user_id: int, item_id: int, quantity: int = 1) -> bool:
        """Removes an item from a user's inventory or decreases the quantity. Returns True if successful."""
        async with self.db.acquire() as conn:
            # Check current quantity first
            current_quantity = await conn.fetchval("SELECT quantity FROM user_inventory WHERE user_id = $1 AND item_id = $2", user_id, item_id)
            if not current_quantity or current_quantity < quantity:
                return False # Not enough items

            if current_quantity == quantity:
                # Delete the row if quantity becomes 0
                await conn.execute("DELETE FROM user_inventory WHERE user_id = $1 AND item_id = $2", user_id, item_id)
            else:
                # Otherwise, just decrease the quantity
                await conn.execute("UPDATE user_inventory SET quantity = quantity - $3 WHERE user_id = $1 AND item_id = $2", user_id, item_id, quantity)
            return True

    async def _get_item_by_name(self, item_name: str):
        """Fetches item details from the database by name (case-insensitive)."""
        async with self.db.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM items WHERE LOWER(name) = LOWER($1)", item_name)

    async def _apply_active_effect(self, user_id: int, effect_type: str, effect_value: int, duration_minutes: int):
        """Adds or updates an active effect for a user."""
        end_time = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        async with self.db.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_active_effects (user_id, effect_type, effect_value, end_time)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, effect_type)
                DO UPDATE SET effect_value = EXCLUDED.effect_value, end_time = EXCLUDED.end_time
            """, user_id, effect_type, effect_value, end_time)
            print(f"Applied effect '{effect_type}' ({effect_value}) to user {user_id} until {end_time.isoformat()}")

    async def _get_active_effect(self, user_id: int, effect_type: str):
        """Gets a non-expired active effect for a user."""
        async with self.db.acquire() as conn:
            return await conn.fetchrow("""
                SELECT * FROM user_active_effects 
                WHERE user_id = $1 AND effect_type = $2 AND end_time > NOW()
            """, user_id, effect_type)
            
    async def _clear_expired_effects(self, user_id: int = None):
        """Removes expired effects for a specific user or all users."""
        async with self.db.acquire() as conn:
            if user_id:
                await conn.execute("DELETE FROM user_active_effects WHERE user_id = $1 AND end_time <= NOW()", user_id)
            else:
                await conn.execute("DELETE FROM user_active_effects WHERE end_time <= NOW()")

    # --- Duel Helper Functions ---
    async def _is_user_in_duel(self, user_id: int) -> bool:
        """Check if a user is either challenging or being challenged."""
        if user_id in self.pending_duels:
            return True
        for request in self.pending_duels.values():
            if request['challenger'] == user_id:
                return True
        return False

    async def _clear_expired_duels(self):
        """Removes duel requests older than the timeout."""
        now_utc = datetime.now(timezone.utc)
        expired_keys = [
            challenged_id for challenged_id, request in self.pending_duels.items()
            if (now_utc - request['timestamp']).total_seconds() > self.duel_timeout_seconds
        ]
        for key in expired_keys:
            print(f" Duel request from {self.pending_duels[key]['challenger']} to {key} expired.")
            del self.pending_duels[key]

    # -------------------------

    @commands.command()
    async def pp(self, ctx, mentioned_user: discord.Member = None):
        """Generate a random PP size with a 1-hour cooldown, affected by server events and items."""
        print(f" {ctx.author} triggered 'pls pp'")

        # Check if another user was mentioned
        if mentioned_user is not None and mentioned_user != ctx.author:
            await ctx.send(f" Sorry {ctx.author.mention}, you can only check your own pp size!")
            return

        # If no user was mentioned or the mentioned user is the author, proceed with the author
        user = ctx.author
        user_id = user.id
        now_utc = datetime.now(timezone.utc) # Use timezone aware datetime

        # Clear any expired effects for this user first
        await self._clear_expired_effects(user_id)

        # Fetch active effects
        active_boost = await self._get_active_effect(user_id, 'pp_boost')
        reroll_available = await self._get_active_effect(user_id, 'reroll_available')

        # Define possible PP sizes and their weights
        sizes = list(range(21))  # 0 to 20 inches
        weights = [ # Example weights (adjust as needed)
            1,  2,  3,  5,  7,  10,  15,  18,  20,  25,  # 0-9
            30, 30, 25, 20, 15, 10,  7,   5,   3,   2,   # 10-19
            1  # 20
        ]

        try:
            async with self.db.acquire() as conn:
                # --- Cooldown Check ---
                row = await conn.fetchrow("SELECT size, last_used FROM pp_sizes WHERE user_id = $1", user_id)
                if row:
                    last_used = row["last_used"]
                    # Ensure last_used is timezone-aware (assuming stored as UTC)
                    if last_used and last_used.tzinfo is None:
                         last_used = last_used.replace(tzinfo=timezone.utc)

                    elapsed_time = (now_utc - last_used).total_seconds() if last_used else 3601
                    if elapsed_time < 3600:
                        remaining_time = 3600 - elapsed_time
                        minutes, seconds = divmod(int(remaining_time), 60)
                        print(f"  Cooldown Active: {minutes}m {seconds}s remaining")
                        await ctx.send(f" {user.mention}, you need to wait **{minutes}m {seconds}s** before checking your PP size again! ")
                        return
                # --------------------

                # --- Initial Roll & Effect Application ---
                initial_roll = random.choices(sizes, weights=weights, k=1)[0]
                final_size = initial_roll
                event_modifier = 0
                item_modifier = 0
                applied_effects_msg = []

                # Apply server event effect
                active_event_name = None
                if self.current_event and now_utc < self.event_end_time:
                    event_modifier = self.event_effect
                    active_event_name = self.current_event['name']
                    applied_effects_msg.append(f"{'+' if event_modifier > 0 else ''}{event_modifier} from {active_event_name}")

                # Apply item boost effect
                if active_boost:
                    item_modifier = active_boost['effect_value']
                    applied_effects_msg.append(f"{'+' if item_modifier > 0 else ''}{item_modifier} from pp_boost")
                    # Boosts are typically single-use, clear it now
                    # Or handle duration differently if they should persist
                    # await conn.execute("DELETE FROM user_active_effects WHERE user_id = $1 AND effect_type = 'pp_boost'", user_id)

                # Calculate size after effects
                final_size += (event_modifier + item_modifier)
                final_size = max(0, min(20, final_size)) # Clamp size 0-20
                # ----------------------------------------

                # --- Reroll Logic ---
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
                            # Reroll and reapply effects
                            initial_roll = random.choices(sizes, weights=weights, k=1)[0]
                            final_size = initial_roll + event_modifier + item_modifier
                            final_size = max(0, min(20, final_size)) # Clamp again
                            await ctx.send(f"{user.mention}, rerolling... Your new size is **{final_size} inches**!")
                        else:
                            await ctx.send(f"{user.mention}, okay, keeping the original roll of **{final_size} inches**.")

                    except asyncio.TimeoutError:
                         # Consume the reroll token on timeout
                        await conn.execute("DELETE FROM user_active_effects WHERE user_id = $1 AND effect_type = 'reroll_available'", user_id)
                        await ctx.send(f"{user.mention}, timed out. Keeping the original roll of **{final_size} inches**. Your Reroll Token was consumed.")
                # --------------------

                # --- Update Database and Send Final Message ---
                await conn.execute(
                    "INSERT INTO pp_sizes (user_id, size, last_used) VALUES ($1, $2, $3) "
                    "ON CONFLICT(user_id) DO UPDATE SET size = EXCLUDED.size, last_used = EXCLUDED.last_used",
                    user_id, final_size, now_utc # Store final size and timestamp
                )
                
                print(f"Updated PP size for {user.name}: {final_size} inches (Base: {initial_roll}, Event: {event_modifier}, Item: {item_modifier}, Rerolled: {performed_reroll})")

                # Construct final message if no reroll prompt occurred
                if not reroll_available:
                    message = f"{user.mention}'s new pp size: 8{'=' * final_size}D! (**{final_size} inches**)"
                    if applied_effects_msg:
                        message += f" (Effects: {', '.join(applied_effects_msg)})"
                    await ctx.send(message)

                # Update the "Current HOG DADDY" role immediately
                await self.update_current_biggest(ctx.guild)
                # ---------------------------------------------

                # --- Record score if PP Off is active ---
                if self.pp_off_active and now_utc < self.pp_off_end_time:
                    current_highest = self.pp_off_participants.get(user_id, -1) # Default to -1 if not present
                    if final_size > current_highest:
                        self.pp_off_participants[user_id] = final_size
                        print(f"  PP Off: Recorded score {final_size} for {user.name} (User ID: {user_id})")
                        # Optionally send a confirmation to the user
                        # await ctx.send(f"(Your score of {final_size} inches has been recorded for the PP Off!) ", delete_after=10)
                # --------------------------------------

        except Exception as e:
            print(f" Database/Command error in pls pp: {e}")
            # Log the traceback for more details
            import traceback
            traceback.print_exc()
            await ctx.send(f" An error occurred processing your pp command. Please try again later.")

    async def update_current_biggest(self, guild):
        """Assigns the 'Current HOG DADDY' role to the biggest PP holder immediately"""
        async with self.db.acquire() as conn:
            biggest = await conn.fetchrow("SELECT user_id FROM pp_sizes ORDER BY size DESC LIMIT 1")

            if biggest:
                biggest_user_id = biggest["user_id"]
                role = discord.utils.get(guild.roles, name="Current HOG DADDY")  # Ensure this role exists

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

    @commands.command()
    async def leaderboard(self, ctx):
        """Displays the top 5 users with the biggest PP sizes"""
        print(f" {ctx.author} triggered 'pls leaderboard'")

        async with self.db.acquire() as conn:
            top_users = await conn.fetch("SELECT user_id, size FROM pp_sizes ORDER BY size DESC LIMIT 5")

        if not top_users:
            await ctx.send("No pp sizes recorded yet! Use `pls pp` to start.")
            return

        embed = discord.Embed(title=" PP Leaderboard - Biggest of the Week", color=discord.Color.purple())

        for rank, record in enumerate(top_users, start=1):
            user_id, size = record["user_id"], record["size"]
            
            # Try fetching user from cache, otherwise fetch from API
            user = self.bot.get_user(user_id)
            if user is None:
                try:
                    user = await self.bot.fetch_user(user_id)
                except discord.NotFound:
                    user = None  # User no longer exists

            username = user.name if user else f"Unknown User ({user_id})"
            embed.add_field(name=f"#{rank}: {username}", value=f"Size: 8{'=' * size}D (**{size} inches**)", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    async def duel(self, ctx, challenged_user: discord.Member):
        """Challenges another member to a PP duel!"""
        challenger = ctx.author

        # --- Input Checks ---
        if challenger == challenged_user:
            await ctx.send(f"{challenger.mention}, you can't duel yourself! Find a worthy opponent.")
            return
        if challenged_user.bot:
            await ctx.send(f"{challenger.mention}, you can't duel a bot. They have no PP to measure!" )
            return
        
        # --- Clear Expired Duels First ---
        await self._clear_expired_duels()
        # ---------------------------------

        # --- Check Existing Duels ---
        if await self._is_user_in_duel(challenger.id):
            await ctx.send(f"{challenger.mention}, you are already involved in a duel request. Wait for it to resolve or expire.")
            return
        if await self._is_user_in_duel(challenged_user.id):
            # Check if the existing duel involves the current challenger to prevent duplicate messages
            if challenged_user.id in self.pending_duels and self.pending_duels[challenged_user.id]['challenger'] == challenger.id:
                 await ctx.send(f"{challenger.mention}, you have already challenged {challenged_user.mention}. They have {self.duel_timeout_seconds} seconds to accept.")
            else:
                await ctx.send(f"{challenger.mention}, {challenged_user.display_name} is already involved in another duel request. Wait for it to resolve or expire.")
            return
        # ---------------------------

        # --- Create Duel Request ---
        now_utc = datetime.now(timezone.utc)
        self.pending_duels[challenged_user.id] = {
            'challenger': challenger.id,
            'timestamp': now_utc
        }
        print(f"Duel request created: {challenger.name} challenges {challenged_user.name}")

        await ctx.send(f"⚔️ {challenger.mention} has challenged {challenged_user.mention} to a PP duel! ⚔️\n" 
                       f"{challenged_user.mention}, type `pls accept {challenger.mention}` within {self.duel_timeout_seconds} seconds to accept!")
        # --------------------------

    @tasks.loop(hours=24)
    async def reset_leaderboard(self):
        """Resets the leaderboard every Sunday at midnight ET"""
        now_utc = datetime.utcnow()
        now_et = now_utc.replace(tzinfo=pytz.utc).astimezone(self.ET_TIMEZONE)  # Convert UTC to ET

        print(f"  Checking reset time... Current ET: {now_et.strftime('%Y-%m-%d %H:%M:%S')}")

        if now_et.weekday() == 6 and now_et.hour == 0:  # Sunday at midnight ET
            async with self.db.acquire() as conn:
                # Get the user with the biggest PP
                winner = await conn.fetchrow("SELECT user_id FROM pp_sizes ORDER BY size DESC LIMIT 1")

                if winner:
                    winner_id = winner["user_id"]
                    guild = self.bot.get_guild(934160898828931143)  # Replace with your server ID
                    if guild:
                        role = discord.utils.get(guild.roles, name="HOG DADDY")  # Ensure this role exists
                        if role:
                            winner_member = guild.get_member(winner_id)
                            if winner_member:
                                # Remove the role from all members before assigning
                                for member in guild.members:
                                    if role in member.roles:
                                        try:
                                            await member.remove_roles(role)
                                        except discord.Forbidden:
                                            print(f"⚠️ Bot lacks permissions to remove role '{role.name}' from {member.name} (weekly reset)")
                                        except discord.HTTPException as e:
                                            print(f"⚠️ Failed to remove role '{role.name}' from {member.name} (weekly reset): {e}")
                                
                                # Assign role to the weekly winner
                                try:
                                    await winner_member.add_roles(role)
                                    print(f"🏆 {winner_member.name} has won the 'HOG DADDY' role!")
                                except discord.Forbidden:
                                    print(f"⚠️ Bot lacks permissions to add role '{role.name}' to {winner_member.name} (weekly reset)")
                                except discord.HTTPException as e:
                                    print(f"⚠️ Failed to add role '{role.name}' to {winner_member.name} (weekly reset): {e}")

                await conn.execute("DELETE FROM pp_sizes")  # Clears the table
            print("🔄 PP Leaderboard has been reset for the new week!")

    @reset_leaderboard.before_loop
    async def before_reset_leaderboard(self):
        """Wait until next Sunday at midnight ET before starting the reset task"""
        await self.bot.wait_until_ready()

        now_utc = datetime.utcnow()
        now_et = now_utc.replace(tzinfo=pytz.utc).astimezone(self.ET_TIMEZONE)  # Convert UTC to ET

        # Find the next Sunday at midnight
        days_until_sunday = (6 - now_et.weekday()) % 7  # How many days until Sunday
        next_sunday = now_et + timedelta(days=days_until_sunday)

        # Ensure the reset is scheduled for *next* Sunday if today is Sunday and past midnight
        if now_et.weekday() == 6 and now_et.hour >= 0:
            next_sunday += timedelta(days=7)

        next_reset_time = next_sunday.replace(hour=0, minute=0, second=0, microsecond=0)

        delay = (next_reset_time - now_et).total_seconds()
        if delay < 0:
            delay += 7 * 24 * 3600  # If delay is negative, move to the next Sunday

        print(f"  Next leaderboard reset scheduled in {delay / 3600:.2f} hours (ET).")

        await asyncio.sleep(delay)  # Wait until next Sunday midnight ET

    # --- Event Task Loop ---
    @tasks.loop(minutes=30) # Check roughly every 30 minutes
    async def event_task(self):
        now = datetime.now(timezone.utc)
        print(f" Running event check at {now.isoformat()}...")
        
        # Also periodically clear expired effects globally
        await self._clear_expired_effects()

        # Check if current event has ended
        if self.current_event and now >= self.event_end_time:
            print(f" Event '{self.current_event['name']}' ended.")
            if self.announcement_channel:
                embed = discord.Embed(description=self.current_event['end_msg'], color=self.current_event['color'])
                try:
                    await self.announcement_channel.send(embed=embed)
                except discord.Forbidden:
                    print(f" Error: Bot lacks permission to send messages in {self.announcement_channel.name}")
                except Exception as e:
                    print(f" Error sending event end message: {e}")
            self.current_event = None
            self.event_end_time = None
            self.event_effect = 0
            return # Don't start a new event immediately after one ends

        # If no event is active, roll dice to start one
        if not self.current_event:
            # Adjust probability as needed (e.g., 20% chance every 30 mins)
            if random.randint(1, 100) <= 20:
                self.current_event = random.choice(EVENTS)
                duration = timedelta(hours=self.current_event['duration_hours'])
                self.event_end_time = now + duration
                self.event_effect = self.current_event['effect']
                print(f" Starting event: {self.current_event['name']} for {duration}")

                if self.announcement_channel:
                    embed = discord.Embed(title=f"📢 Server Event: {self.current_event['name']}!",
                                        description=self.current_event['start_msg'],
                                        color=self.current_event['color'])
                    embed.set_footer(text=f"This event will last for {self.current_event['duration_hours']} hour(s).")
                    try:
                        await self.announcement_channel.send(embed=embed)
                    except discord.Forbidden:
                        print(f" Error: Bot lacks permission to send messages in {self.announcement_channel.name}")
                    except Exception as e:
                        print(f" Error sending event start message: {e}")
            else:
                print(" No new event started.")
        else:
             print(f" Event '{self.current_event['name']}' is still active.")

    @event_task.before_loop
    async def before_event_task(self):
        await self.bot.wait_until_ready()
        # Try to find the announcement channel
        guild_id = 934160898828931143 # Hardcoded guild ID, replace if needed
        guild = self.bot.get_guild(guild_id)
        if guild:
            # Look for 'announcements' or 'general'
            channel = discord.utils.get(guild.text_channels, name='announcements')
            if not channel:
                channel = discord.utils.get(guild.text_channels, name='general')
            
            if channel:
                self.announcement_channel = channel
                print(f" Event announcements will be sent to #{channel.name}")
            else:
                print(" Warning: Could not find 'announcements' or 'general' channel for event messages.")
        else:
            print(f" Warning: Could not find Guild ID {guild_id} for event announcements.")
            
        print(" Event Task Loop Ready.")

    # --- Trivia Command ---
    @commands.command()
    @commands.cooldown(1, 15, commands.BucketType.user) # Cooldown 15s per user
    @commands.guild_only()
    async def trivia(self, ctx):
        """Asks a trivia question from the Open Trivia Database."""
        if self.current_trivia_question:
            # Check if the existing question message still exists
            try:
                existing_msg = await self.current_trivia_question['channel'].fetch_message(self.current_trivia_question['message_id'])
                await ctx.send(f"A trivia question is already active in {self.current_trivia_question['channel'].mention}! Answer it first: {existing_msg.jump_url}")
                return
            except discord.NotFound:
                print(" Trivia: Previous question message not found, allowing new question.")
                self.current_trivia_question = None # Clear stale question
            except discord.Forbidden:
                 print(" Trivia: Bot lacks permissions to fetch previous message.")
                 # Decide how to handle - maybe just clear and proceed?
                 self.current_trivia_question = None 
            except Exception as e:
                 print(f" Trivia: Error checking existing question: {e}")
                 self.current_trivia_question = None # Clear on error

        # Categories: 11=Film, 14=TV, 15=Video Games, 32=Cartoons/Animations
        category_id = random.choice([11, 14, 15, 32])
        api_url = f"https://opentdb.com/api.php?amount=1&type=multiple&category={category_id}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        await ctx.send("Sorry, couldn't fetch a trivia question right now. The Trivia Database might be down.")
                        print(f" Trivia API Error: Status {response.status}")
                        ctx.command.reset_cooldown(ctx)
                        return
                    
                    data = await response.json()
                    
                    if data['response_code'] != 0:
                        # Response code 1: No Results. Could not return results. The API doesn't have enough questions for your query.
                        # Response code 2: Invalid Parameter. Contains an invalid parameter. Arguements passed in aren't valid.
                        # Response code 3: Token Not Found. Session Token does not exist.
                        # Response code 4: Token Empty. Session Token has returned all possible questions for the specified query. Resetting the Token is necessary.
                        await ctx.send("Sorry, couldn't get a unique trivia question from the database. Maybe try a different category or try again later.")
                        print(f" Trivia API Error: Response Code {data['response_code']}")
                        ctx.command.reset_cooldown(ctx)
                        return

                    question_data = data['results'][0]
                    question = html.unescape(question_data['question'])
                    correct_answer = html.unescape(question_data['correct_answer'])
                    incorrect_answers = [html.unescape(ans) for ans in question_data['incorrect_answers']]
                    
                    all_choices = incorrect_answers + [correct_answer]
                    random.shuffle(all_choices)
                    
                    choices_text = "\n".join([f"**{chr(65+i)}.** {choice}" for i, choice in enumerate(all_choices)])
                    
                    embed = discord.Embed(
                        title=f"🧠 Trivia Time! ({question_data['category']})",
                        description=f"**{question}**\n\n{choices_text}",
                        color=discord.Color.blue()
                    )
                    embed.set_footer(text=f"You have {self.trivia_timeout} seconds to answer with the letter (A, B, C, or D)! Requested by {ctx.author.display_name}")
                    
                    trivia_msg = await ctx.send(embed=embed)
                    
                    self.current_trivia_question = {
                        'question': question,
                        'correct_answer': correct_answer,
                        'choices': all_choices,
                        'channel': ctx.channel,
                        'message_id': trivia_msg.id,
                        'ask_time': datetime.now(timezone.utc)
                    }
                    
                    print(f" Trivia: Asked '{question}' in #{ctx.channel.name}. Correct Answer: {correct_answer}")
                    # Schedule timeout check
                    self.bot.loop.create_task(self._trivia_timeout_check(ctx.channel.id, trivia_msg.id, self.trivia_timeout))

            except aiohttp.ClientConnectorError as e:
                 await ctx.send("Sorry, couldn't connect to the Trivia Database.")
                 print(f" Trivia Network Error: {e}")
                 ctx.command.reset_cooldown(ctx)
            except Exception as e:
                await ctx.send("An unexpected error occurred while fetching trivia.")
                print(f" Trivia General Error: {e}")
                traceback.print_exc()
                ctx.command.reset_cooldown(ctx)

    async def _trivia_timeout_check(self, channel_id, message_id, delay):
        """Checks if a trivia question timed out."""
        await asyncio.sleep(delay)
        if self.current_trivia_question and \
           self.current_trivia_question['channel'].id == channel_id and \
           self.current_trivia_question['message_id'] == message_id:
            
            print(f" Trivia: Question {message_id} timed out.")
            channel = self.current_trivia_question['channel']
            correct_answer = self.current_trivia_question['correct_answer']
            self.current_trivia_question = None # Clear the question first
            try:
                await channel.send(f"⏰ Time's up! The correct answer was: **{correct_answer}**")
            except discord.NotFound:
                print(" Trivia Timeout: Channel not found.")
            except discord.Forbidden:
                 print(" Trivia Timeout: Bot lacks permission to send timeout message.")
            except Exception as e:
                 print(f" Trivia Timeout: Error sending message: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bot messages
        if message.author.bot:
            return

        # --- Check Trivia Answer ---
        if self.current_trivia_question and message.channel.id == self.current_trivia_question['channel'].id:
            content_lower = message.content.strip().lower()
            if len(content_lower) == 1 and 'a' <= content_lower <= 'd':
                # Valid answer format (A, B, C, or D)
                choice_index = ord(content_lower) - ord('a') # Calculate index (0 for a, 1 for b, etc.)
                
                # Ensure index is within bounds (should always be if A-D)
                if 0 <= choice_index < len(self.current_trivia_question['choices']):
                    chosen_answer = self.current_trivia_question['choices'][choice_index]
                    correct_answer = self.current_trivia_question['correct_answer']
                    
                    if chosen_answer == correct_answer:
                        winner = message.author
                        print(f" Trivia: Correct answer '{correct_answer}' by {winner.name} in #{message.channel.name}")
                        
                        # Store necessary info before clearing
                        question_msg_id = self.current_trivia_question['message_id']
                        # --- Clear the active question --- 
                        self.current_trivia_question = None 
                        # -------------------------------
                        
                        # Award prize (Reroll Token - item_id 4)
                        reward_item_id = 4 
                        try:
                            await self._add_item_to_inventory(winner.id, reward_item_id, 1)
                            item = await self._get_item_by_name("Reroll Token")
                            item_name = item['name'] if item else "a prize"
                            await message.channel.send(f"🎉 Correct, {winner.mention}! The answer was **{correct_answer}**. You won a **{item_name}**! 🎉")
                            # Optionally edit the original question embed to show it's answered?
                            # try:
                            #    original_msg = await message.channel.fetch_message(question_msg_id)
                            #    # Modify embed or add text
                            # except discord.NotFound:
                            #    pass # Ignore if original message deleted
                        except Exception as e:
                             print(f" Trivia: Error giving reward to {winner.id}: {e}")
                             traceback.print_exc()
                             await message.channel.send(f"🎉 Correct, {winner.mention}! The answer was **{correct_answer}**. (Error giving item reward) 🎉")
                    # else: # Incorrect answer A-D, just ignore it
                    #    pass 
            # else: # Message is not a single letter A-D, ignore
            #    pass
        # ---------------------------

    # --- Duel Commands ---
    @commands.command()
    @commands.guild_only()
    async def accept(self, ctx, challenger_user: discord.Member):
        """Accepts a pending duel challenge."""
        acceptor = ctx.author # The user running this command

        # --- Clear Expired Duels ---
        await self._clear_expired_duels()
        # ---------------------------

        # --- Validate Duel Request ---
        pending_request = self.pending_duels.get(acceptor.id)

        if not pending_request:
            await ctx.send(f"{acceptor.mention}, you don't have any pending duel requests to accept.")
            return

        if pending_request['challenger'] != challenger_user.id:
            # Find the actual challenger's name if possible
            actual_challenger = ctx.guild.get_member(pending_request['challenger'])
            actual_challenger_name = actual_challenger.mention if actual_challenger else f"User ID {pending_request['challenger']}"
            await ctx.send(f"{acceptor.mention}, you were challenged by {actual_challenger_name}, not {challenger_user.mention}. Use `pls accept {actual_challenger_name}`.")
            return
        # ---------------------------

        # --- Perform Duel ---
        challenger_id = pending_request['challenger']
        acceptor_id = acceptor.id

        # Remove the pending duel request
        del self.pending_duels[acceptor_id]
        print(f"Duel accepted: {acceptor.name} accepts challenge from {challenger_user.name}")

        # Perform rolls for both users
        challenger_roll = await self._perform_duel_roll(challenger_id)
        acceptor_roll = await self._perform_duel_roll(acceptor_id)

        # Determine winner
        result_message = f"🔥 **Duel Result!** 🔥\n" \
                         f"{challenger_user.mention} rolled: **{challenger_roll} inches**\n" \
                         f"{acceptor.mention} rolled: **{acceptor_roll} inches**\n\n"

        if challenger_roll > acceptor_roll:
            result_message += f"🏆 **{challenger_user.mention} wins the duel!** 🏆"
        elif acceptor_roll > challenger_roll:
            result_message += f"🏆 **{acceptor.mention} wins the duel!** 🏆"
        else:
            result_message += f"🤝 It's a **draw**! A rare display of equal PP prowess! 🤝"

        await ctx.send(result_message)
        # -------------------

    # --- PP Off Command ---
    async def _calculate_and_announce_ppoff_results(self):
        """Calculates PP Off results, announces winner, and resets state."""
        if not self.pp_off_active or not self.pp_off_channel:
            print(" PP Off results calculation triggered, but no active PP Off found or channel missing.")
            self.pp_off_active = False # Ensure state is reset
            return

        print(f"Calculating PP Off results for channel {self.pp_off_channel.id}...")
        channel_to_announce = self.pp_off_channel # Store before resetting

        if not self.pp_off_participants:
            await channel_to_announce.send("🏁 The PP Off has ended! Nobody participated. 🤷‍♂️")
        else:
            # Find the highest score
            max_score = -1
            for score in self.pp_off_participants.values():
                if score > max_score:
                    max_score = score
            
            # Find all winners with that score
            winners = []
            guild = channel_to_announce.guild
            for user_id, score in self.pp_off_participants.items():
                if score == max_score:
                    member = guild.get_member(user_id)
                    winners.append(member.mention if member else f"User ID {user_id}")
            
            # Announce results
            if len(winners) == 1:
                await channel_to_announce.send(f"🏁 The PP Off has ended! 🏁\n🏆 The winner is {winners[0]} with a massive **{max_score} inches**! 🏆")
            else:
                await channel_to_announce.send(f"🏁 The PP Off has ended! 🏁\n🏆 We have a tie between {', '.join(winners)} with **{max_score} inches**! 🏆")
            
            print(f" PP Off Winner(s): {winners} with score {max_score}")

        # Reset PP Off state
        self.pp_off_active = False
        self.pp_off_end_time = None
        self.pp_off_participants = {}
        self.pp_off_channel = None
        print(" PP Off state reset.")

    @commands.command(aliases=['ppoff'])
    @commands.cooldown(1, 300, commands.BucketType.guild) # Cooldown 5 mins per guild
    @commands.guild_only()
    async def ppoff(self, ctx, duration_minutes: int = 1):
        """Starts a PP Off event! Highest 'pls pp' roll in the duration wins.
        
        Usage: pls ppoff [duration_in_minutes=1]
        """
        if self.pp_off_active:
            remaining_time = self.pp_off_end_time - datetime.now(timezone.utc)
            if remaining_time.total_seconds() > 0:
                await ctx.send(f"A PP Off is already in progress in {self.pp_off_channel.mention}! It ends in {int(remaining_time.total_seconds() // 60)}m {int(remaining_time.total_seconds() % 60)}s.")
                ctx.command.reset_cooldown(ctx)
                return
            else:
                print("Warning: PP Off flag was active but end time passed. Resetting.")
                self.pp_off_active = False 
                self.pp_off_participants = {}

        if duration_minutes <= 0 or duration_minutes > 60:
            await ctx.send("Please provide a duration between 1 and 60 minutes.")
            ctx.command.reset_cooldown(ctx)
            return

        self.pp_off_active = True
        self.pp_off_end_time = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        self.pp_off_participants = {}
        self.pp_off_channel = ctx.channel
        duration_seconds = duration_minutes * 60

        print(f"PP Off started by {ctx.author.name} in #{ctx.channel.name} for {duration_minutes} minutes.")
        await ctx.send(f"**📢 PP Off Event Started! 📢**\nUse `pls pp` in the next **{duration_minutes} minute{'s' if duration_minutes != 1 else ''}** to compete! Highest roll wins bragging rights!")

        # Schedule the results announcement
        self.bot.loop.create_task(self._schedule_ppoff_end(duration_seconds))

    async def _schedule_ppoff_end(self, delay_seconds: int):
        """Waits for the duration then triggers PP Off results calculation."""
        await asyncio.sleep(delay_seconds)
        await self._calculate_and_announce_ppoff_results()

    # --- Duel Helper Functions ---
    async def _perform_duel_roll(self, user_id: int) -> int:
        """Performs a PP roll for a duel, including event/item effects."""
        # Define possible PP sizes and their weights (same as pls pp)
        sizes = list(range(21))
        weights = [
            1,  2,  3,  5,  7,  10,  15,  18,  20,  25,  # 0-9
            30, 30, 25, 20, 15, 10,  7,   5,   3,   2,   # 10-19
            1   # 20
        ]
        # TODO: Apply luck_boost modifier to weights if implemented

        base_size = random.choices(sizes, weights=weights, k=1)[0]
        final_size = base_size
        event_modifier = 0
        item_modifier = 0
        now_utc = datetime.now(timezone.utc)

        # Apply server event effect
        if self.current_event and now_utc < self.event_end_time:
            event_modifier = self.event_effect

        # Apply active pp_boost effect
        active_boost = await self._get_active_effect(user_id, 'pp_boost')
        if active_boost:
            item_modifier = active_boost['effect_value']
            # Note: We don't consume timed boosts during a duel roll

        # Calculate final size
        final_size += (event_modifier + item_modifier)
        final_size = max(0, min(20, final_size)) # Clamp size 0-20
        print(f" Duel roll for {user_id}: Base={base_size}, EventMod={event_modifier}, ItemMod={item_modifier} -> Final={final_size}")
        return final_size

    # --- Item/Inventory Commands ---
    @commands.command(aliases=['inv'])
    async def inventory(self, ctx):
        """Displays your current item inventory."""
        user_id = ctx.author.id
        async with self.db.acquire() as conn:
            inventory_items = await conn.fetch("""
                SELECT i.name, i.description, inv.quantity 
                FROM user_inventory inv
                JOIN items i ON inv.item_id = i.item_id
                WHERE inv.user_id = $1 AND inv.quantity > 0
                ORDER BY i.name
            """, user_id)

        if not inventory_items:
            await ctx.send(f"{ctx.author.mention}, your inventory is empty.")
            return

        embed = discord.Embed(title=f"🎒 {ctx.author.display_name}'s Inventory", color=discord.Color.gold())
        for item in inventory_items:
            embed.add_field(name=f"{item['name']} (x{item['quantity']})", value=item['description'], inline=False)
        
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

        # --- Check and Remove from Inventory ---
        removed = await self._remove_item_from_inventory(user_id, item_id, 1)
        if not removed:
            await ctx.send(f"{ctx.author.mention}, you don't have any '{item['name']}' to use!")
            return
        # --------------------------------------

        # --- Apply Effect ---
        if duration_minutes > 0: # Timed effect (e.g., pp_boost)
            # Check for existing effect of the same type
            existing_effect = await self._get_active_effect(user_id, effect_type)
            if existing_effect:
                 # For now, overwrite existing effect. Could change to prevent/stack later.
                 print(f"User {user_id} already had effect {effect_type}, overwriting.")
                 # Potentially refund item if overwriting isn't desired?
                 # await self._add_item_to_inventory(user_id, item_id, 1) 
                 # await ctx.send(f"{ctx.author.mention}, you already have an active '{effect_type}'. Wait for it to expire!")
                 # return
                 
            await self._apply_active_effect(user_id, effect_type, effect_value, duration_minutes)
            await ctx.send(f"{ctx.author.mention}, you used **{item['name']}**! Its effect (`{effect_type}`: {effect_value}) will last for {duration_minutes} minutes.")
        
        elif effect_type == 'reroll': # Instant effect flag (for now)
             # Mark reroll available by adding a very short duration effect
             # The 'pls pp' command will need to check for this
             await self._apply_active_effect(user_id, 'reroll_available', 1, 1) # 1 minute to use the reroll flag
             await ctx.send(f"{ctx.author.mention}, you used **{item['name']}**! You have a reroll available for your next `pls pp` command (within 1 min).")

        # Add other instant effects here (e.g., cooldown reset)
        # elif effect_type == 'cooldown_reset':
        #    async with self.db.acquire() as conn:
        #        await conn.execute("UPDATE pp_sizes SET last_used = NULL WHERE user_id = $1", user_id)
        #    await ctx.send(f"{ctx.author.mention}, you used **{item['name']}**! Your `pls pp` cooldown has been reset!")

        else: # Other unknown or non-duration effects (like luck_boost for now)
            # Could store flags or handle differently. For now, just acknowledge use.
            print(f"User {user_id} used item '{item['name']}' with unhandled instant effect type: {effect_type}")
            await ctx.send(f"{ctx.author.mention}, you used **{item['name']}**! Its effect will be applied when relevant.")

async def setup(bot):
    await bot.add_cog(PPLeaderboard(bot))
