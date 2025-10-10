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
            name="📏 PP Core & Profile",
            value=f"`{prefix}pp` - Roll for your PP size (resets top of the hour, highest daily wins Hog Daddy!). **Earn coins = your roll size!**\n"
                  f"`{prefix}coins [@user]` - Check your (or someone's) PP coin balance. 💰\n"
                  f"`{prefix}profile [@user]` - Show your (or someone's) PP profile, stats, and achievements.\n"
                  f"`{prefix}leaderboard` or `{prefix}lb` - Show the daily PP leaderboard (resets at midnight UTC).",
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
            value=f"`{prefix}trivia` - Answer a trivia question (A-D) to win items + 10 coins!\n"
                  f"`{prefix}scramble` - Unscramble a word to win an item + 10 coins!\n"
                  f"`{prefix}highlow` - Guess if the next number is higher or lower! Win 10 coins!\n"
                  f"`{prefix}mathrush` - Solve a quick math problem to win 10 coins!\n"
                  f"`{prefix}blackjack [bet]` - Play blackjack! Bet ANY amount of PP coins (default: 10). 🎰\n"
                  f"`{prefix}hit` - Draw another card in blackjack.\n"
                  f"`{prefix}stand` - Hold your hand in blackjack.\n"
                  f"`{prefix}wyr` - Answer a fun 'Would You Rather' question!\n"
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
