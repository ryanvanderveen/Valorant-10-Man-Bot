import discord
from discord.ext import commands

class InfoCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def info(self, ctx):
        """Displays bot info"""
        embed = discord.Embed(
            title="🅿🅿 Bot Info", 
            description="The one and only PP measuring bot, with extra fun!", 
            color=discord.Color.purple()
        )
        embed.add_field(
            name="Creator", 
            value="Built by ryanvanderveen", 
            inline=False
        )
        embed.add_field(
            name="Library", 
            value=f"discord.py {discord.__version__}", 
            inline=True
        )
        embed.add_field(
            name="Servers", 
            value=f"{len(self.bot.guilds)}", 
            inline=True
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(InfoCommands(bot))
