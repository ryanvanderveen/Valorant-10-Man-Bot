import discord
import random
import asyncpg  # ✅ Use PostgreSQL instead of SQLite
import os
from discord.ext import commands, tasks
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")  # ✅ Get Railway PostgreSQL URL
COOLDOWN_TIME = 3600  # 1 hour in seconds

class PPLeaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.initialize_db())  # ✅ Initialize database on startup
        self.reset_leaderboard.start()  # Start the weekly reset task

    async def initialize_db(self):
        """Creates the database and table if they don't exist."""
        try:
            self.db = await asyncpg.connect(DATABASE_URL, ssl="require")  # ✅ Ensure secure connection
            print("✅ Successfully connected to PostgreSQL!")
        except Exception as e:
            print(f"❌ ERROR: Unable to connect to PostgreSQL: {e}")
            exit(1)
        await self.db.execute(
            """CREATE TABLE IF NOT EXISTS pp_sizes (
                user_id BIGINT PRIMARY KEY, 
                size INTEGER
            )"""
        )

    @commands.command()
    @commands.cooldown(1, COOLDOWN_TIME, commands.BucketType.user)  # ✅ 1 use per hour per user
    async def pp(self, ctx, user: discord.Member = None):
        """Random PP size with cooldown (now stored in PostgreSQL)"""
        user = user or ctx.author
        user_id = user.id
        size = random.randint(0, 20)  # ✅ Generate new PP size

        async with self.db.acquire() as conn:
            current_size = await conn.fetchval("SELECT size FROM pp_sizes WHERE user_id = $1", user_id) or 0

            if size > current_size:
                await conn.execute(
                    "INSERT INTO pp_sizes (user_id, size) VALUES ($1, $2) "
                    "ON CONFLICT(user_id) DO UPDATE SET size = EXCLUDED.size",
                    user_id, size
                )
                await ctx.send(f"{user.mention} got a **record-breaking** pp size: 8{'=' * size}D! (**{size} inches**) 🎉")
            else:
                await ctx.send(f"{user.mention}'s pp is 8{'=' * size}D (**{size} inches**), but it's not a new record. 😢")

        print(f"✅ {user.name} ({user_id}) used pls pp - Size: {size} - Cooldown applied!")  # Debugging

    @pp.error
    async def pp_error(self, ctx, error):
        """Handles cooldown errors for pp command"""
        if isinstance(error, commands.CommandOnCooldown):
            time_remaining = int(error.retry_after)
            minutes = time_remaining // 60
            seconds = time_remaining % 60
            await ctx.send(f"⏳ {ctx.author.mention}, you need to wait **{minutes}m {seconds}s** before checking your PP size again! 🍆")


    @commands.command()
    async def leaderboard(self, ctx):
        """Displays the top 5 users with the biggest pp sizes (from PostgreSQL)"""
        top_users = await self.db.fetch("SELECT user_id, size FROM pp_sizes ORDER BY size DESC LIMIT 5")

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
        """Resets the leaderboard every Sunday at midnight UTC"""
        now = datetime.utcnow()
        print(f"Checking for leaderboard reset... (Current UTC time: {now})")

        if now.weekday() == 6 and now.hour == 0:  # ✅ Sunday at midnight UTC
            await self.db.execute("DELETE FROM pp_sizes")  # ✅ Clears the table
            print("🔄 PP Leaderboard has been reset for the new week!")

    @reset_leaderboard.before_loop
    async def before_reset_leaderboard(self):
        """Wait until next Sunday midnight UTC before starting the reset task"""
        await self.bot.wait_until_ready()
    
    async def cog_unload(self):
        """Closes the database connection when the cog is unloaded"""
        await self.db.close()

# ✅ Setup function to load cog
async def setup(bot):
    await bot.add_cog(PPLeaderboard(bot))
