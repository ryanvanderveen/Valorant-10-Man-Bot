import os
import asyncpg
import discord
import random
import pytz  # ✅ Timezone handling for ET
import asyncio
from discord.ext import commands, tasks
from datetime import datetime, timedelta

class PPLeaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.DATABASE_URL = os.getenv("DATABASE_URL")
        self.db = None  # ✅ Database pool
        self.ET_TIMEZONE = pytz.timezone("America/New_York")  # ✅ Eastern Time
        self.bot.loop.create_task(self.initialize_db())  # ✅ Initialize DB on startup
        self.reset_leaderboard.start()  # ✅ Start weekly reset task

    async def initialize_db(self):
        """Creates database connection pool and ensures the table exists."""
        if not self.DATABASE_URL:
            print("❌ ERROR: DATABASE_URL is not set! Check your environment variables.")
            return

        # ✅ Fix asyncpg issue: Convert postgresql:// → postgres://
        if self.DATABASE_URL.startswith("postgresql://"):
            self.DATABASE_URL = self.DATABASE_URL.replace("postgresql://", "postgres://", 1)

        try:
            self.db = await asyncpg.create_pool(self.DATABASE_URL)
            print("✅ Successfully connected to PostgreSQL!")

            async with self.db.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS pp_sizes (
                        user_id BIGINT PRIMARY KEY,
                        size INTEGER,
                        last_used TIMESTAMP DEFAULT NULL
                    )
                """)
            print("✅ PostgreSQL database initialized!")

        except Exception as e:
            print(f"❌ ERROR: Unable to connect to PostgreSQL: {e}")
            exit(1)

    @commands.command()
    async def pp(self, ctx, user: discord.Member = None):
        """Generate a random PP size with a 1-hour cooldown"""
        print(f"🔍 {ctx.author} triggered 'pls pp'")

        user = user or ctx.author
        user_id = user.id
        size = random.randint(0, 20)
        now = datetime.utcnow()

        try:
            async with self.db.acquire() as conn:
                row = await conn.fetchrow("SELECT size, last_used FROM pp_sizes WHERE user_id = $1", user_id)

                if row:
                    last_used = row["last_used"]
                    elapsed_time = (now - last_used).total_seconds() if last_used else 3601
                    if elapsed_time < 3600:
                        remaining_time = 3600 - elapsed_time
                        minutes, seconds = divmod(int(remaining_time), 60)
                        print(f"🕒 Cooldown Active: {minutes}m {seconds}s remaining")
                        await ctx.send(f"⏳ {user.mention}, you need to wait **{minutes}m {seconds}s** before checking your PP size again! 🍆")
                        return

                await conn.execute(
                    "INSERT INTO pp_sizes (user_id, size, last_used) VALUES ($1, $2, NOW()) "
                    "ON CONFLICT(user_id) DO UPDATE SET size = EXCLUDED.size, last_used = NOW()",
                    user_id, size
                )

                print(f"✅ Updated PP size for {user.name}: {size} inches")
                await ctx.send(f"{user.mention}'s new pp size: 8{'=' * size}D! (**{size} inches**) 🎉")

        except Exception as e:
            print(f"❌ Database error: {e}")
            await ctx.send(f"❌ Database error: {e}")

    @commands.command()
    async def leaderboard(self, ctx):
        """Displays the top 5 users with the biggest PP sizes"""
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
        now_et = now_utc.replace(tzinfo=pytz.utc).astimezone(self.ET_TIMEZONE)  # Convert UTC to ET

        print(f"🔍 Checking reset time... Current ET: {now_et.strftime('%Y-%m-%d %H:%M:%S')}")

        if now_et.weekday() == 6 and now_et.hour == 0:  # ✅ Sunday at midnight ET
            async with self.db.acquire() as conn:
                await conn.execute("DELETE FROM pp_sizes")  # ✅ Clears the table
            print("🔄 PP Leaderboard has been reset for the new week!")

    @reset_leaderboard.before_loop
    async def before_reset_leaderboard(self):
        """Wait until next Sunday at midnight ET before starting the reset task"""
        await self.bot.wait_until_ready()

        now_utc = datetime.utcnow()
        now_et = now_utc.replace(tzinfo=pytz.utc).astimezone(self.ET_TIMEZONE)  # Convert UTC to ET

        # Check if today is Sunday and past midnight ET
        if now_et.weekday() == 6 and now_et.hour >= 0:
            # If it's already Sunday after midnight, schedule for next week
            next_reset = now_et + timedelta(days=7)
        else:
            # Schedule for this upcoming Sunday
            next_reset = now_et + timedelta(days=(6 - now_et.weekday()))

        next_reset = next_reset.replace(hour=0, minute=0, second=0, microsecond=0)

        delay = (next_reset - now_et).total_seconds()
        print(f"⏳ Next leaderboard reset scheduled in {delay / 3600:.2f} hours (ET).")

        await asyncio.sleep(delay)  # ✅ Wait until next Sunday midnight ET


async def setup(bot):
    await bot.add_cog(PPLeaderboard(bot))
