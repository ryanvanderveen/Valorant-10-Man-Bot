import discord
from discord.ext import commands

class HelpCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='help')
    async def bothelp(self, ctx):
        """Displays dynamically generated help information"""
        prefix = "pls "  # Assuming 'pls ' is the primary prefix
        
        embed = discord.Embed(
            title="🅿🅿 Bot Help", 
            description="Here are the available commands:", 
            color=discord.Color.purple()
        )

        # PP Core
        embed.add_field(
            name="📏 PP Core", 
            value=f"`{prefix}pp` - Roll for your PP size (once per hour).\n"
                  f"`{prefix}leaderboard [global]` - Show the server (or global) PP leaderboard.", 
            inline=False
        )

        # Items
        embed.add_field(
            name="🎒 Items",
            value=f"`{prefix}inventory` or `{prefix}inv` - View your item inventory.\n"
                  f"`{prefix}use <item_name>` - Use an item from your inventory.",
            inline=False
        )
        
        # Mini-Games
        embed.add_field(
            name="🎮 Mini-Games",
            value=f"`{prefix}trivia` - Start a trivia question. First correct answer (A-D) wins!\n"
                  f"`{prefix}duel <@user>` - Challenge another user to a PP duel.\n"
                  f"`{prefix}accept <@user>` - Accept a pending duel challenge.\n"
                  f"`{prefix}ppoff [minutes]` - Start a timed PP Off event (default 1 min). Highest roll wins!",
            inline=False
        )

        # Utility
        embed.add_field(
            name="⚙️ Utility", 
            value=f"`{prefix}help` - Shows this help message.\n"
                  f"`{prefix}info` - Shows bot information.\n"
                  f"`{prefix}ping` - Checks the bot's latency.",
            inline=False
        )

        embed.set_footer(text="Remember to use the prefix 'pls ' before commands!")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCommands(bot))
