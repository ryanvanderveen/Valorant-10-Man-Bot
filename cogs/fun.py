import discord
from discord.ext import commands

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Minigame commands will be added here (duel, quickdraw, rpsls, trivia, wrestle, guess, etc.)
    # See enhancement plan for details.

async def setup(bot):
    print("✅ Loading fun cog...")  # Debugging
    await bot.add_cog(Fun(bot))
    print("✅ Fun cog successfully loaded!")  # Debugging
