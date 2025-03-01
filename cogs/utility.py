import discord
from discord.ext import commands

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="bothelp")
    async def bothelp(self, ctx):
        """Displays dynamically generated help information"""
        embed = discord.Embed(title="📜 Bot Commands", description="Here's what I can do:", color=discord.Color.blue())

        # Get all commands grouped by category (cog name)
        command_categories = {}
        for command in self.bot.commands:
            if command.cog_name not in command_categories:
                command_categories[command.cog_name] = []
            command_categories[command.cog_name].append(f"`pls {command.name}`")

        # Add each category and its commands to the embed
        for category, commands in command_categories.items():
            embed.add_field(name=f"**{category} Commands**", value=", ".join(commands), inline=False)

        embed.set_footer(text="Use pls <command> to run a command!")
    
        await ctx.send(embed=embed)

    @commands.command()
    async def info(self, ctx):
        """Displays bot info"""
        embed = discord.Embed(title="Bot Info", description="PP Bot", color=discord.Color.green())
        embed.set_footer(text=f"Requested by {ctx.author.name}")
        await ctx.send(embed=embed)

# ✅ Fix: Correctly define setup function for bot
async def setup(bot):
    await bot.add_cog(Utility(bot))
