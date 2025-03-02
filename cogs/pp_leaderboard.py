import discord
import random
import asyncpg
import asyncio
import pytz  # ✅ Timezone handling
from discord.ext import commands, tasks
from datetime import datetime, timedelta

DATABASE_URL = "DATABASE_URL"  # Replace with your actual PostgreSQL URL
COOLDOWN_TIME = 3600  # 1 hour cooldown
ET_TIMEZONE = pytz.timezone("America/New_York")  # ✅ Eastern Time Zone

class PPLeaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.initialize_db())  # ✅ Initialize database on startup
        self.reset_leaderboard.start()  # ✅ Start the weekly reset task

    async def initialize_db(self):
        """Creates the database and table if they don't exist."""
        self.db = await asyncpg.connect(DATABASE_URL)

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS pp_sizes (
                user_id BIGINT PRIMARY KEY,
                size INTEGER,
                last_used TIMESTAMP DEFAULT NULL
            )
        """)

        print("✅ PostgreSQL database initialized!")

    @commands.command()
    async def pp(self, ctx, user: discord.Member = None):
        """Generate a random PP size with a 1-hour cooldown"""
        user = user or ctx.author
        user_id = user.id
        size = random.randint(0, 20)  # ✅ Generate new PP size
        now = datetime.utcnow()

        async with self.db.acquire() as conn:
            row = await conn.fetchrow("SELECT size, last_used FROM pp_sizes WHERE user_id = $1", user_id)

            if row:
                last_used = row["last_used"]
                if last_used:
                    elapsed_time = (now - last_used).total_seconds()
                    if elapsed_time < COOLDOWN_TIME:
                        remaining_time = COOLDOWN_TIME - elapsed_time
                        minutes, seconds = divmod(int(remaining_time), 60)
                        await ctx.send(f"⏳ {user.mention}, you need to wait **{minutes}m {seconds}s** before checking your PP size again! 🍆")
                        return

                current_size = row["size"]
            else:
                current_size = 0

            # If new size is larger, update the database
            if size > current_size:
                await conn.execute(
                    "INSERT INTO pp_sizes (user_id, size, last_used) VALUES ($1, $2, $3) "
                    "ON CONFLICT(user_id) DO UPDATE SET size = EXCLUDED.size, last_used = EXCLUDED.last_used",
                    user_id, size, now
                )
                await ctx.send(f"{user.mention} got a **record-breaking** pp size: 8{'=' * size}D! (**{size} inches**) 🎉")
            else:
                await conn.execute(
                    "UPDATE pp_sizes SET last_used = $1 WHERE user_id = $2",
                    now, user_id
                )
                await ctx.send(f"{user.mention}'s pp is 8{'=' * size}D (**{size} inches**), but it's not a new record. 😢")

    @commands.command()
    async def leaderboard(self, ctx):
        """Displays the top 5 users with the biggest pp sizes"""
        async with self.db.acquire() as conn:
            top_users = await conn.fetch("SELECT user_id, size FROM pp_sizes ORDER BY size DESC LIMIT 5")

        if not top_users:
            await ctx.send("No pp sizes recorded yet! Use `pls pp` to start.")
            return

        embed = discord.Embed(title="🍆 PP Leaderboard - Biggest of the Week", color=discord.Color.purple())
        for rank, record in enumerate(top_users, start=1):
            user_id, size = record["user_id"], record["size"]
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)  # ✅ Fetch username if needed
            username = user.name if user else f"Unknown User ({user_id})"
            embed.add_field(name=f"#{rank}: {username}", value=f"Size: 8{'=' * size}D (**{size} inches**)", inline=False)

        await ctx.send(embed=embed)

    @tasks.loop(hours=24)
    async def reset_leaderboard(self):
        """Resets the leaderboard every Sunday at midnight ET"""
        now_utc = datetime.utcnow()
        now_et = now_utc.replace(tzinfo=pytz.utc).astimezone(ET_TIMEZONE)  # Convert UTC to Eastern Time

        print(f"🔍 Checking reset time... Current ET: {now_et.strftime('%Y-%m-%d %H:%M:%S')}")

        if now_et.weekday() == 6 and now_et.hour == 0:  # ✅ Sunday at midnight ET
            async with self.db.acquire() as conn:
                await conn.execute("DELETE FROM pp_sizes")  # ✅ Clears the table
            print("🔄 PP Leaderboard has been reset for the new week!")

    @reset_leaderboard.before_loop
    async def before_reset_leaderboard(self):
        """Wait until next Sunday midnight ET before starting the reset task"""
        await self.bot.wait_until_ready()

        now_utc = datetime.utcnow()
        now_et = now_utc.replace(tzinfo=pytz.utc).astimezone(ET_TIMEZONE)  # Convert UTC to Eastern Time

        # Calculate time until next Sunday at midnight ET
        days_until_sunday = (6 - now_et.weekday()) % 7
        next_sunday = now_et + timedelta(days=days_until_sunday)
        next_sunday_midnight = next_sunday.replace(hour=0, minute=0, second=0, microsecond=0)

        delay = (next_sunday_midnight - now_et).total_seconds()
        print(f"⏳ Next leaderboard reset scheduled in {delay / 3600:.2f} hours (ET).")

        await asyncio.sleep(delay)  # ✅ Wait until next Sunday midnight ET

    async def cog_unload(self):
        """Closes the database connection when the cog is unloaded"""
        await self.db.close()

# ✅ Setup function to load cog
async def setup(bot):
    await bot.add_cog(PPLeaderboard(bot))
