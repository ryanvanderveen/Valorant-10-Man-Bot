import discord
from discord.ext import commands

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Command to check bot latency
    @commands.command()
    async def ping(self, ctx):
        """Checks the bot's latency"""
        latency_ms = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! Latency: **{latency_ms}ms**")

# ✅ Fix: Correctly define setup function for bot
async def setup(bot):
    await bot.add_cog(Utility(bot))
