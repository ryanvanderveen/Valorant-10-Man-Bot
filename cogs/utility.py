import discord
from discord.ext import commands

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Command to display help information
    @commands.command(name='help')
    async def bothelp(self, ctx):
        """Displays dynamically generated help information"""
        prefix = "pls " # Assuming 'pls ' is the primary prefix
        
        embed = discord.Embed(
            title="🅿🅿 Bot Help", 
            description="Here are the available commands:", 
            color=discord.Color.purple()
        )

        # PP Core
        embed.add_field(
            name="📏 PP Core & Profile", 
            value=f"`{prefix}pp` - Roll for your PP size (resets top of the hour, highest daily wins Hog Daddy!).\n"
                  f"`{prefix}profile [@user]` - Show your (or someone else's) PP profile, stats, and achievements.\n"
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

    # Command to display bot info
    @commands.command()
    async def info(self, ctx):
        """Displays bot info"""
        embed = discord.Embed(title="🅿🅿 Bot Info", description="The one and only PP measuring bot, with extra fun!", color=discord.Color.purple())
        embed.add_field(name="<:peepoSmile:1105687381285158972> Creator", value="Built by ryanvanderveen", inline=False) # Feel free to change this!
        embed.add_field(name="<:python:1230960341111668736> Library", value=f"discord.py {discord.__version__}", inline=True)
        embed.add_field(name="<:member:1105687397014466651> Servers", value=f"{len(self.bot.guilds)}", inline=True)
        # Add a link to your repo if you have one!
        # embed.add_field(name="Source Code", value="[GitHub Repo](YOUR_REPO_LINK_HERE)", inline=False)
        await ctx.send(embed=embed)

# ✅ Fix: Correctly define setup function for bot
async def setup(bot):
    await bot.add_cog(Utility(bot))
