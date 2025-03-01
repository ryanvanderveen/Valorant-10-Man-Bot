import discord
from discord.ext import commands

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def help(self, ctx):
        """Displays help information"""
        embed = discord.Embed(title="Bot Commands", description="Here's what I can do:", color=discord.Color.blue())
        embed.add_field(name="Fun Commands", value="`pls pp`, `pls rizz`, `pls roast`, `pls love`", inline=False)
        embed.add_field(name="Utility Commands", value="`pls help`, `pls info`", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def info(self, ctx):
        """Displays bot info"""
        embed = discord.Embed(title="Bot Info", description="A fun Discord bot!", color=discord.Color.green())
        embed.set_footer(text=f"Requested by {ctx.author.name}")
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(Utility(bot))