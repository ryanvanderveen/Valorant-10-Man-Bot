import discord
import random
import aiosqlite  # ✅ Async SQLite
from discord.ext import commands, tasks
from datetime import datetime

DATABASE_FILE = "pp_leaderboard.db"  # SQLite database file
COOLDOWN_TIME = 3600  # 1 hour in seconds

class PPLeaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.initialize_db())  # ✅ Initialize database on startup
        self.reset_leaderboard.start()  # Start the weekly reset task

    async def initialize_db(self):
        """Creates the database and table if they don't exist."""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS pp_sizes (
                    user_id INTEGER PRIMARY KEY, 
                    size INTEGER
                )"""
            )
            await db.commit()

    @commands.command()
    @commands.cooldown(1, COOLDOWN_TIME, commands.BucketType.user)  # ✅ 1 use per hour per user
    async def pp(self, ctx, user: discord.Member = None):
        """Random PP size with cooldown (now stored in SQL)"""
        user = user or ctx.author
        user_id = user.id
        size = random.randint(0, 20)  # ✅ Generate new PP size

        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute("SELECT size FROM pp_sizes WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                current_size = row[0] if row else 0  # Get current size, default to 0

            if size > current_size:
                await db.execute("INSERT INTO pp_sizes (user_id, size) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET size = ?", (user_id, size, size))
                await db.commit()
                await ctx.send(f"{user.mention} got a **record-breaking** pp size: 8{'=' * size}D! (**{size} inches**) 🎉")
            else:
                await ctx.send(f"{user.mention}'s pp is 8{'=' * size}D (**{size} inches**), but it's not a new record. 😢")

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
        """Displays the top 5 users with the biggest pp sizes (from SQL)"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute("SELECT user_id, size FROM pp_sizes ORDER BY size DESC LIMIT 5") as cursor:
                top_users = await cursor.fetchall()

        # ✅ Fix: Ensure leaderboard doesn't incorrectly show as empty
        if top_users is None or len(top_users) == 0:
            await ctx.send("No pp sizes recorded yet! Use `pls pp` to start.")
            return

        embed = discord.Embed(title="🍆 PP Leaderboard - Biggest of the Week", color=discord.Color.purple())
        for rank, (user_id, size) in enumerate(top_users, start=1):
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)  # ✅ Fetch username if needed
            username = user.name if user else f"Unknown User ({user_id})"
            embed.add_field(name=f"#{rank}: {username}", value=f"Size: 8{'=' * size}D (**{size} inches**)", inline=False)

        await ctx.send(embed=embed)

    @tasks.loop(hours=24)
    async def reset_leaderboard(self):
        """Resets the leaderboard every Sunday at midnight UTC"""
        now = datetime.utcnow()
        print(f"Checking for leaderboard reset... (Current UTC time: {now})")  # ✅ Debugging

        if now.weekday() == 6 and now.hour == 0:  # ✅ Sunday at midnight UTC
            async with aiosqlite.connect(DATABASE_FILE) as db:
                await db.execute("DELETE FROM pp_sizes")  # ✅ Clears the table
                await db.commit()
            print("🔄 PP Leaderboard has been reset for the new week!")

    @reset_leaderboard.before_loop
    async def before_reset_leaderboard(self):
        """Wait until next Sunday midnight UTC before starting the reset task"""
        await self.bot.wait_until_ready()

        now = datetime.utcnow()
        print(f"Current UTC time: {now}")

        # Calculate next Sunday midnight UTC
        days_until_sunday = (6 - now.weekday()) % 7  # Days until next Sunday
        if days_until_sunday == 0 and now.hour >= 0:  # If it's already past midnight on Sunday
            days_until_sunday = 7  # Schedule for the next Sunday

        next_sunday = now + timedelta(days=days_until_sunday)
        next_sunday_midnight = next_sunday.replace(hour=0, minute=0, second=0, microsecond=0)

        # Calculate delay
        delay = (next_sunday_midnight - now).total_seconds()
        print(f"✅ Next leaderboard reset scheduled in {delay / 3600:.2f} hours.")

        await asyncio.sleep(delay)  # ✅ Wait until next Sunday at 00:00 UTC

# ✅ Setup function to load cog
async def setup(bot):
    await bot.add_cog(PPLeaderboard(bot))
