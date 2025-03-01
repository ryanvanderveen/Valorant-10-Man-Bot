import discord
import random
from discord.ext import commands

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def pp(self, ctx, user: discord.Member = None):
        """Random PP size"""
        user = user or ctx.author
        size = "=" * random.randint(0, 20)
        await ctx.send(f"{user.mention}'s pp is 8{size}D, length: {len(size)} inches")

    @commands.command()
    async def rizz(self, ctx, user: discord.Member = None):
        """Rates user's rizz"""
        user = user or ctx.author
        score = random.randint(0, 10)
        await ctx.send(f"{user.mention} has {score}/10 rizz! 💯")

    @commands.command()
    async def roast(self, ctx, user: discord.Member = None):
        """Roasts a user"""
        roasts = [
            "You're slower than my grandma’s WiFi.",
            "You're proof that even mistakes can be successful.",
            "Your brain has more lag than a 2004 Dell laptop."
        ]
        user = user or ctx.author
        await ctx.send(f"{user.mention}, {random.choice(roasts)}")

    @commands.command()
    async def love(self, ctx, user: discord.Member = None):
        """Love compatibility"""
        if not user:
            await ctx.send("You need someone to love! 💔")
            return
        score = random.randint(0, 100)
        await ctx.send(f"💖 {ctx.author.mention} and {user.mention} have {score}% compatibility!")

def setup(bot):
    bot.add_cog(Fun(bot))
