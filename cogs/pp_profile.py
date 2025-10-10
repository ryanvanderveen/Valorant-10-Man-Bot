import discord
from discord.ext import commands
import asyncpg
import os
from datetime import datetime, timezone

ACHIEVEMENT_CHANNEL_ID = 934181022659129444 # Your achievement announcement channel

class PPProfile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_pool = None

    async def cog_load(self):
        print("Attempting to connect to the database from PPProfile...")
        try:
            self.db_pool = await asyncpg.create_pool(dsn=os.getenv('DATABASE_URL'))
            print("✅ PPProfile Database pool created successfully.")
        except Exception as e:
            print(f"❌ Failed to connect to PPProfile database: {e}")

    async def cog_unload(self):
        if self.db_pool:
            await self.db_pool.close()
            print("PPProfile Database pool closed.")

    async def _get_db(self):
        if not self.db_pool:
             # Attempt to reconnect or use the main bot pool if available
            if hasattr(self.bot, 'db_pool') and self.bot.db_pool:
                self.db_pool = self.bot.db_pool
            else:
                try: # Last resort: create a new pool just for this cog
                    print("PPProfile trying fallback DB connection...")
                    self.db_pool = await asyncpg.create_pool(dsn=os.getenv('DATABASE_URL'))
                    print("✅ PPProfile Fallback DB pool created.")
                except Exception as e:
                    print(f"❌ PPProfile Fallback DB connection failed: {e}")
                    raise ConnectionError("Database pool is not initialized in PPProfile.")
        return self.db_pool

    @commands.command(name='coins', aliases=['balance', 'bal'], help='Check your PP coin balance.')
    async def coins(self, ctx, member: discord.Member = None):
        """Check your or someone else's PP coin balance"""
        if member is None:
            member = ctx.author

        user_id = member.id
        db = await self._get_db()

        async with db.acquire() as conn:
            coins_record = await conn.fetchrow("SELECT pp_coins FROM user_data WHERE user_id = $1", user_id)

        pp_coins = coins_record['pp_coins'] if coins_record else 0

        if member == ctx.author:
            await ctx.send(f"💰 You have **{pp_coins} PP coins**!")
        else:
            await ctx.send(f"💰 {member.display_name} has **{pp_coins} PP coins**!")

    @commands.command(name='profile', aliases=['prof'], help='Shows your PP profile and stats.')
    async def profile(self, ctx, *, member: discord.Member = None):
        if member is None:
            member = ctx.author

        user_id = member.id
        db = await self._get_db()

        async with db.acquire() as conn:
            # Fetch PP Size
            pp_record = await conn.fetchrow("SELECT size, last_roll_timestamp FROM pp_sizes WHERE user_id = $1", user_id)
            # Fetch Stats
            stats_record = await conn.fetchrow("SELECT * FROM user_stats WHERE user_id = $1", user_id)
            # Fetch PP Coins
            coins_record = await conn.fetchrow("SELECT pp_coins FROM user_data WHERE user_id = $1", user_id)
            # Fetch Achievements
            achievements_earned = await conn.fetch("""
                SELECT a.name, a.description FROM user_achievements ua
                JOIN achievements a ON ua.achievement_id = a.achievement_id
                WHERE ua.user_id = $1 ORDER BY ua.earned_at
            """, user_id)

        embed = discord.Embed(title=f"{member.display_name}'s Profile", color=member.color)
        embed.set_thumbnail(url=member.display_avatar.url)

        # PP Coins
        pp_coins = coins_record['pp_coins'] if coins_record else 0
        embed.add_field(name="💰 PP Coins", value=f"{pp_coins}", inline=True)

        # PP Info
        if pp_record:
            pp_size = pp_record['size']
            last_roll = pp_record['last_roll_timestamp']
            embed.add_field(name="Current PP Size", value=f"{pp_size} inches", inline=True)
            if last_roll:
                 embed.add_field(name="Last Measured", value=discord.utils.format_dt(last_roll, style='R'), inline=True)
            else:
                embed.add_field(name="Last Measured", value="Never", inline=True)
        else:
            embed.add_field(name="Current PP Size", value="Not measured yet", inline=True)
            embed.add_field(name="Last Measured", value="Never", inline=True)

        # Stats Info
        if stats_record:
            embed.add_field(name="Total Rolls", value=stats_record.get('total_rolls', 0), inline=True)
            embed.add_field(name="Zero Rolls", value=stats_record.get('zero_rolls', 0), inline=True)
            embed.add_field(name="Twenty Rolls", value=stats_record.get('twenty_rolls', 0), inline=True)
            embed.add_field(name="Duel Wins", value=stats_record.get('duel_wins', 0), inline=True)
            embed.add_field(name="Trivia Wins", value=stats_record.get('trivia_wins', 0), inline=True)
            embed.add_field(name="Days as Hog Daddy", value=stats_record.get('days_as_hog_daddy', 0), inline=True)
        else:
            embed.add_field(name="Stats", value="No stats recorded yet.", inline=False)

        # Achievements Info
        if achievements_earned:
            ach_text = "\n".join([f"- **{ach['name']}**: {ach['description']}" for ach in achievements_earned])
            embed.add_field(name="Achievements", value=ach_text if ach_text else "None", inline=False)
        else:
            embed.add_field(name="Achievements", value="None", inline=False)

        await ctx.send(embed=embed)

    async def _grant_achievement(self, user: discord.Member, achievement_id: str, ctx: commands.Context):
        """Grants an achievement if not already earned, updates DB, announces, and gives role."""
        db = await self._get_db()
        guild = user.guild
        
        async with db.acquire() as conn:
            async with conn.transaction():
                # Check if already earned
                already_earned = await conn.fetchval("SELECT 1 FROM user_achievements WHERE user_id = $1 AND achievement_id = $2", user.id, achievement_id)
                if already_earned:
                    return # Already has it

                # Get achievement details (including potential role reward)
                achievement_info = await conn.fetchrow("SELECT name, description, reward_role_name FROM achievements WHERE achievement_id = $1", achievement_id)
                if not achievement_info:
                    print(f"Grant Achievement Error: Achievement ID '{achievement_id}' not found in database.")
                    return

                # Add to user_achievements
                await conn.execute("INSERT INTO user_achievements (user_id, achievement_id) VALUES ($1, $2)", user.id, achievement_id)
                print(f"[Achievement] Granted '{achievement_id}' to {user.name} ({user.id})")

                # Announce in channel
                announce_channel = self.bot.get_channel(ACHIEVEMENT_CHANNEL_ID)
                if announce_channel:
                    try:
                        await announce_channel.send(f"🏆 Achievement Unlocked! {user.mention} earned **{achievement_info['name']}**! ({achievement_info['description']}) 🏆")
                    except discord.Forbidden:
                        print(f"Grant Achievement Error: Missing permissions to send to channel {ACHIEVEMENT_CHANNEL_ID}.")
                    except discord.HTTPException as e:
                        print(f"Grant Achievement Error: Failed to send announcement: {e}")
                else:
                    print(f"Grant Achievement Error: Announcement channel {ACHIEVEMENT_CHANNEL_ID} not found.")

                # Grant role reward if specified
                role_name = achievement_info['reward_role_name']
                if role_name:
                    role = discord.utils.get(guild.roles, name=role_name)
                    if role:
                        if role not in user.roles:
                            try:
                                await user.add_roles(role, reason=f"Achievement unlocked: {achievement_info['name']}")
                                print(f"[Achievement] Granted role '{role.name}' to {user.name}")
                            except discord.Forbidden:
                                print(f"Grant Achievement Error: Bot lacks permission to add role '{role.name}' to {user.name}.")
                                if ctx: await ctx.send(f"(Couldn't grant the '{role.name}' role reward due to permissions.)", delete_after=15)
                            except discord.HTTPException as e:
                                print(f"Grant Achievement Error: Failed to add role '{role.name}': {e}")
                        else:
                            print(f"[Achievement] User {user.name} already has role '{role.name}'.")
                    else:
                        print(f"Grant Achievement Error: Role '{role_name}' not found in guild '{guild.name}'.")
                        if ctx: await ctx.send(f"(Achievement role '{role_name}' not found.)", delete_after=15)
    
    async def _grant_achievement_no_ctx(self, user_id: int, achievement_id: str, announcement_channel: discord.TextChannel):
        """Grants an achievement without a command context (for tasks). Fetches user/guild info."""
        db = await self._get_db()
        guild = announcement_channel.guild
        user = guild.get_member(user_id)
        if not user:
            print(f"Grant Achievement (NoCtx) Error: User {user_id} not found in guild {guild.name}.")
            return
        
        # Re-use the main logic, passing None for ctx where needed inside the function
        async with db.acquire() as conn:
            async with conn.transaction():
                already_earned = await conn.fetchval("SELECT 1 FROM user_achievements WHERE user_id = $1 AND achievement_id = $2", user.id, achievement_id)
                if already_earned:
                    return

                achievement_info = await conn.fetchrow("SELECT name, description, reward_role_name FROM achievements WHERE achievement_id = $1", achievement_id)
                if not achievement_info:
                    print(f"Grant Achievement (NoCtx) Error: Achievement ID '{achievement_id}' not found.")
                    return

                await conn.execute("INSERT INTO user_achievements (user_id, achievement_id) VALUES ($1, $2)", user.id, achievement_id)
                print(f"[Achievement][NoCtx] Granted '{achievement_id}' to {user.name} ({user.id})")

                # Announce
                try:
                    await announcement_channel.send(f"🏆 Achievement Unlocked! {user.mention} earned **{achievement_info['name']}**! ({achievement_info['description']}) 🏆")
                except Exception as e:
                     print(f"Grant Achievement (NoCtx) Error: Failed to send announcement: {e}")

                # Grant role
                role_name = achievement_info['reward_role_name']
                if role_name:
                    role = discord.utils.get(guild.roles, name=role_name)
                    if role and role not in user.roles:
                        try:
                            await user.add_roles(role, reason=f"Achievement unlocked (Task): {achievement_info['name']}")
                            print(f"[Achievement][NoCtx] Granted role '{role.name}' to {user.name}")
                        except Exception as e:
                            print(f"Grant Achievement (NoCtx) Error: Failed to add role '{role.name}': {e}")
                    elif not role:
                         print(f"Grant Achievement (NoCtx) Error: Role '{role_name}' not found.")

async def setup(bot):
    await bot.add_cog(PPProfile(bot))
