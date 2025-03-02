import os
import asyncpg
import discord
from discord.ext import commands
from datetime import datetime
import random

class PPLeaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.DATABASE_URL = os.getenv("DATABASE_URL")  # ✅ Store DATABASE_URL in self
        self.db = None  # ✅ Initialize the database pool
        self.bot.loop.create_task(self.initialize_db())  # ✅ Start database setup on startup

    async def initialize_db(self):
        """Creates a database connection pool and ensures the table exists."""
        if not self.DATABASE_URL:
            print("❌ ERROR: DATABASE_URL is not set! Check your environment variables.")
            return

        # ✅ Fix asyncpg issue: Convert postgresql:// → postgres://
        if self.DATABASE_URL.startswith("postgresql://"):
            self.DATABASE_URL = self.DATABASE_URL.replace("postgresql://", "postgres://", 1)

        try:
            self.db = await asyncpg.create_pool(self.DATABASE_URL)  # ✅ Use connection pool
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

async def setup(bot):
    await bot.add_cog(PPLeaderboard(bot))
