import discord
import random
import json
import os
from discord.ext import commands, tasks
from datetime import datetime

# File to store PP sizes
DATA_FILE = "pp_leaderboard.json"
COOLDOWN_TIME = 3600  # 1 hour in seconds

class PPLeaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_data()
        self.reset_leaderboard.start()  # Start the weekly reset task

    def load_data(self):
        """Loads the leaderboard data from a file."""
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                self.leaderboard = json.load(f)
        else:
            self.leaderboard = {}

    def save_data(self):
        """Saves the leaderboard data to a file."""
        with open(DATA_FILE, "w") as f:
            json.dump(self.leaderboard, f, indent=4)

    @commands.command()
    @commands.cooldown(1, COOLDOWN_TIME, commands.BucketType.user)  # ✅ Built-in cooldown
    async def pp(self, ctx, user: discord.Member = None):
        """Random PP size with cooldown"""
        user = user or ctx.author
        user_id = str(user.id)

        # Generate new PP size (fix: use an integer instead of a string)
        size = random.randint(0, 20)  # ✅ Now it's an integer
        current_size = self.leaderboard.get(user_id, 0)

        if size > current_size:
            self.leaderboard[user_id] = size
            self.save_data()
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
        """Displays the top 5 users with the biggest pp sizes"""
        if not self.leaderboard:
            await ctx.send("No pp sizes recorded yet! Use `pls pp` to start.")
            return

        sorted_leaderboard = sorted(self.leaderboard.items(), key=lambda x: x[1], reverse=True)
        top_users = sorted_leaderboard[:5]

        embed = discord.Embed(title="🍆 PP Leaderboard - Biggest of the Week", color=discord.Color.purple())
        for rank, (user_id, size) in enumerate(top_users, start=1):
            user = self.bot.get_user(int(user_id))
            username = user.name if user else f"User {user_id}"
            embed.add_field(name=f"#{rank}: {username}", value=f"Size: 8{'=' * size}D (**{size} inches**)", inline=False)

        await ctx.send(embed=embed)

    @tasks.loop(hours=24)
    async def reset_leaderboard(self):
        """Resets the leaderboard every Sunday at midnight"""
        now = datetime.utcnow()
        if now.weekday() == 6 and now.hour == 0:  # Sunday midnight UTC
            self.leaderboard.clear()
            self.save_data()
            print("🔄 PP Leaderboard has been reset for the new week!")

    @reset_leaderboard.before_loop
    async def before_reset_leaderboard(self):
        """Wait until bot is ready before starting reset task"""
        await self.bot.wait_until_ready()

# ✅ Setup function to load cog
async def setup(bot):
    await bot.add_cog(PPLeaderboard(bot))
