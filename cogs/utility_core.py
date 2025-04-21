import discord
from discord.ext import commands

class UtilityCore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    # Add future utility commands here
    # Examples might include:
    # - Server stats
    # - User info
    # - Bot status
    # - Custom prefix management
    # etc.

async def setup(bot):
    await bot.add_cog(UtilityCore(bot))
