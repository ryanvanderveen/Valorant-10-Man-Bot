import discord
from discord.ext import commands
import traceback

class PPProfile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_db(self):
        """Get database pool from PPDB cog"""
        db_cog = self.bot.get_cog('PPDB')
        if not db_cog:
            raise RuntimeError("PPDB cog not loaded!")
        return await db_cog.get_db()

    @commands.command(aliases=['prof'])
    async def profile(self, ctx, *, member: discord.Member = None):
        """Shows a user's PP profile and stats."""
        target_user = member or ctx.author
        print(f" {ctx.author} triggered 'pls profile' for {target_user.name}")

        db = await self._get_db()

        try:
            async with db.acquire() as conn:
                # --- Fetch Data ---
                # Get current PP size (from pp_core's table)
                current_pp = await conn.fetchrow(
                    "SELECT size FROM pp_sizes WHERE user_id = $1",
                    target_user.id
                )
                current_size = current_pp['size'] if current_pp else 0 # Default to 0 if no record

                # Get stats from user_stats, defaulting to 0 if no record exists
                stats = await conn.fetchrow("""
                    SELECT 
                        COALESCE(trivia_wins, 0) as trivia_wins,
                        COALESCE(duel_wins, 0) as duel_wins,
                        COALESCE(total_rolls, 0) as total_rolls,
                        COALESCE(zero_rolls, 0) as zero_rolls,
                        COALESCE(twenty_rolls, 0) as twenty_rolls
                    FROM user_stats 
                    WHERE user_id = $1
                    """, target_user.id)
                
                # Handle case where user has no stats record at all
                if not stats:
                    stats = {'trivia_wins': 0, 'duel_wins': 0, 'total_rolls': 0, 'zero_rolls': 0, 'twenty_rolls': 0}

                # Get earned achievements
                earned_achievements_raw = await conn.fetch("""
                    SELECT a.name, a.description
                    FROM user_achievements ua
                    JOIN achievements a ON ua.achievement_id = a.achievement_id
                    WHERE ua.user_id = $1
                    ORDER BY ua.earned_at ASC
                    """, target_user.id)

                # --- Create Embed ---
                embed = discord.Embed(
                    title=f"{target_user.display_name}'s PP Profile",
                    color=target_user.color # Use member's role color
                )
                embed.set_thumbnail(url=target_user.display_avatar.url)

                embed.add_field(name="Current PP Size", value=f"8{'=' * current_size}D (**{current_size} inches**)", inline=False)

                # Add Stats Fields
                stats_text = (
                    f"**Trivia Wins:** {stats['trivia_wins']}\n"
                    f"**Duel Wins:** {stats['duel_wins']}\n"
                    f"**Total Rolls:** {stats['total_rolls']}\n"
                    f"**Zero Rolls:** {stats['zero_rolls']}\n"
                    f"**Twenty Rolls:** {stats['twenty_rolls']}"
                )
                embed.add_field(name="📈 Statistics", value=stats_text, inline=True)

                # Add Achievements Field
                if earned_achievements_raw:
                    achievements_text = "\n".join([f"🏆 **{ach['name']}**: {ach['description']}" for ach in earned_achievements_raw])
                    embed.add_field(name="🏅 Achievements", value=achievements_text, inline=True)
                else:
                    embed.add_field(name="🏅 Achievements", value="None earned yet!", inline=True)

                embed.set_footer(text=f"User ID: {target_user.id}")

            await ctx.send(embed=embed)

        except Exception as e:
            print(f" Error creating profile for {target_user.name}: {e}")
            traceback.print_exc()
            await ctx.send(f"Could not fetch profile data for {target_user.mention}. Please try again.")

    async def _grant_achievement(self, user: discord.Member, achievement_id: str, ctx: commands.Context = None):
        """Checks if user has achievement, grants if not, handles rewards. Sends public message if ctx provided."""
        granted_new = False # Flag to track if we actually granted it now
        if not user: # Cannot grant to user not in server
            return False
            
        db = await self._get_db()
        async with db.acquire() as conn:
            async with conn.transaction(): # Ensure atomicity
                # Check if user already has this achievement
                exists = await conn.fetchval("SELECT 1 FROM user_achievements WHERE user_id = $1 AND achievement_id = $2", user.id, achievement_id)
                if exists:
                    # print(f"[Achievement] User {user.id} already has '{achievement_id}'.")
                    return False # Already has it

                # Get achievement details (including potential reward role)
                achievement_details = await conn.fetchrow("SELECT name, description, reward_role_name FROM achievements WHERE achievement_id = $1", achievement_id)
                if not achievement_details:
                    print(f"⚠️ [Achievement] Definition for '{achievement_id}' not found in DB.")
                    return False

                # Grant the achievement
                await conn.execute("INSERT INTO user_achievements (user_id, achievement_id) VALUES ($1, $2)", user.id, achievement_id)
                granted_new = True # Mark as newly granted
                print(f"[Achievement] Granted '{achievement_id}' to user {user.name} ({user.id}).")

                # Handle Role Reward
                reward_role_name = achievement_details['reward_role_name']
                if reward_role_name:
                    role = discord.utils.get(user.guild.roles, name=reward_role_name)
                    if role:
                        if role not in user.roles:
                            try:
                                await user.add_roles(role, reason=f"Earned achievement: {achievement_details['name']}")
                                print(f"[Achievement] Granted role '{role.name}' to {user.name} for '{achievement_id}'.")
                            except discord.Forbidden:
                                print(f"⚠️ [Achievement] Bot lacks permission to grant role '{role.name}' for achievement '{achievement_id}'.")
                            except Exception as e:
                                print(f"⚠️ [Achievement] Error granting role '{role.name}' for '{achievement_id}': {e}")
                        else:
                            print(f"[Achievement] User {user.name} already had role '{role.name}'.")
                    else:
                         print(f"⚠️ [Achievement] Reward role '{reward_role_name}' for '{achievement_id}' not found in guild {user.guild.name}.")

                # --- DM Notification Removed ---
                # try:
                #     await user.send(f"🏆 **Achievement Unlocked!** 🏆\nYou earned: **{achievement_details['name']}** ({achievement_details['description']})")
                # except discord.Forbidden:
                #     print(f"[Achievement] Could not DM user {user.name} about achievement '{achievement_id}'.")
                # except Exception as e:
                #     print(f"[Achievement] Error DMing user {user.name}: {e}")
        
        # Send public notification if newly granted and ctx is available
        if granted_new and achievement_details: # Send regardless of ctx now, but need details
            announcement_channel_id = 934181022659129444
            channel = self.bot.get_channel(announcement_channel_id)
            if channel:
                try:
                    await channel.send(f"🎉 **Achievement Unlocked!** {user.mention} just earned **{achievement_details['name']}**! ({achievement_details['description']}) 🎉")
                except discord.Forbidden:
                    print(f"⚠️ [Achievement] Bot lacks permission to send message in announcement channel {announcement_channel_id}.")
                except Exception as e:
                    print(f"[Achievement] Error sending public notification to channel {announcement_channel_id}: {e}")
            else:
                print(f"⚠️ [Achievement] Could not find announcement channel with ID {announcement_channel_id}.")
        
        return granted_new # Return whether it was newly granted


async def setup(bot):
    await bot.add_cog(PPProfile(bot))
    print("✅ PPProfile Cog loaded")
