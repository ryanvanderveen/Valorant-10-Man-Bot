﻿import os
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

                # Check if they have the biggest PP right now
                await self.update_current_biggest(ctx.guild, user_id)

        except Exception as e:
            print(f"❌ Database error: {e}")
            await ctx.send(f"❌ Database error: {e}")

    async def update_current_biggest(self, guild, new_winner_id):
        """Assigns the 'Current HOG DADDY' role to the biggest PP holder"""
        async with self.db.acquire() as conn:
            biggest = await conn.fetchrow("SELECT user_id FROM pp_sizes ORDER BY size DESC LIMIT 1")

            if biggest:
                biggest_user_id = biggest["user_id"]
                role = discord.utils.get(guild.roles, name="Current HOG DADDY")  # 🔹 Ensure this role exists

                if role:
                    biggest_member = guild.get_member(biggest_user_id)
                    if biggest_member:
                        # Remove role from all members first
                        for member in guild.members:
                            if role in member.roles:
                                await member.remove_roles(role)

                        # Assign the role to the new biggest PP holder
                        await biggest_member.add_roles(role)
                        print(f"🏆 {biggest_member.name} now holds 'Current HOG DADDY'!")

    @tasks.loop(hours=24)
    async def reset_leaderboard(self):
        """Resets the leaderboard every Sunday at midnight ET"""
        now_utc = datetime.utcnow()
        now_et = now_utc.replace(tzinfo=pytz.utc).astimezone(self.ET_TIMEZONE)  # Convert UTC to ET

        print(f"🔍 Checking reset time... Current ET: {now_et.strftime('%Y-%m-%d %H:%M:%S')}")

        if now_et.weekday() == 6 and now_et.hour == 0:  # ✅ Sunday at midnight ET
            async with self.db.acquire() as conn:
                # Get the user with the biggest PP
                winner = await conn.fetchrow("SELECT user_id FROM pp_sizes ORDER BY size DESC LIMIT 1")

                if winner:
                    winner_id = winner["user_id"]
                    guild = self.bot.get_guild(934160898828931143)  # 🔹 Replace with your server ID
                    if guild:
                        role = discord.utils.get(guild.roles, name="HOG DADDY")  # 🔹 Ensure this role exists
                        if role:
                            winner_member = guild.get_member(winner_id)
                            if winner_member:
                                # Remove the role from all members before assigning
                                for member in guild.members:
                                    if role in member.roles:
                                        await member.remove_roles(role)
                                
                                # Assign role to the weekly winner
                                await winner_member.add_roles(role)
                                print(f"🏆 {winner_member.name} has won the 'HOG DADDY' role!")

                await conn.execute("DELETE FROM pp_sizes")  # ✅ Clears the table
            print("🔄 PP Leaderboard has been reset for the new week!")

    @reset_leaderboard.before_loop
    async def before_reset_leaderboard(self):
        """Wait until next Sunday at midnight ET before starting the reset task"""
        await self.bot.wait_until_ready()

        now_utc = datetime.utcnow()
        now_et = now_utc.replace(tzinfo=pytz.utc).astimezone(self.ET_TIMEZONE)  # Convert UTC to ET

        days_until_sunday = (6 - now_et.weekday()) % 7
        next_sunday = now_et + timedelta(days=days_until_sunday)
        next_sunday_midnight = next_sunday.replace(hour=0, minute=0, second=0, microsecond=0)

        delay = (next_sunday_midnight - now_et).total_seconds()
        print(f"⏳ Next leaderboard reset scheduled in {delay / 3600:.2f} hours (ET).")

        await asyncio.sleep(delay)  # ✅ Wait until next Sunday midnight ET

async def setup(bot):
    await bot.add_cog(PPLeaderboard(bot))
