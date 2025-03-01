import discord
import random
import aiohttp  # For fetching memes
from discord.ext import commands

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def rizz(self, ctx, user: discord.Member = None):
        """Attempts to rizz someone up"""
        rizz = random.randint(0, 10)
        if user is None:
            await ctx.send(f"{ctx.author.mention}, your rizz is **{rizz}/10**.")
        else:
            if rizz > 5:
                await ctx.send(f"{ctx.author.mention} successfully rizzed {user.mention}. Their rizz was **{rizz}/10**! 🕺🔥")
            else:
                await ctx.send(f"{ctx.author.mention} failed to rizz {user.mention}. Their rizz was only **{rizz}/10**. 💀")

    @commands.command()
    async def smash(self, ctx, user: discord.Member = None):
        """Rates if you'd smash or pass"""
        user = user or ctx.author
        smash_chance = random.randint(0, 100)
        if smash_chance > 50:
            await ctx.send(f"{user.mention}, I'd **definitely smash**! 😏🔥 (**{smash_chance}% smash chance**)")
        else:
            await ctx.send(f"{user.mention}, it's a **pass** for me. ❌ (**{smash_chance}% smash chance**)")

    @commands.command()
    async def suck(self, ctx, user: discord.Member = None):
        """Simulates sucking something 😏"""
        user = user or ctx.author
        await ctx.send(f"{user.mention} is sucking on something real good... 🍭😏")

    @commands.command()
    async def moan(self, ctx):
        """Sends a random moan"""
        moans = [
            "*Ahnn~* 😫",
            "*Ohhh daddyyy~* 😩",
            "*Uhhh~* 😍",
            "*Ahhh~* 🔥",
            "*Mmmm~* 😏"
        ]
        await ctx.send(random.choice(moans))

    @commands.command()
    async def fuck(self, ctx, user: discord.Member = None):
        """Generates a random 'how long you last' result"""
        if user is None:
            await ctx.send("You need a partner first 😏")
            return
        duration = random.randint(1, 60)
        unit = "seconds" if duration < 10 else "minutes"
        await ctx.send(f"{ctx.author.mention} lasted **{duration} {unit}** with {user.mention}. 🍑🔥")

    @commands.command()
    async def daddy(self, ctx, user: discord.Member = None):
        """Calls someone daddy"""
        user = user or ctx.author
        responses = [
            f"{user.mention} is the ultimate daddy. 😩",
            f"{user.mention} is **not** daddy material. 🚫",
            f"{user.mention}, do you like being called daddy? 👀"
        ]
        await ctx.send(random.choice(responses))

    @commands.command()
    async def eightball(self, ctx, *, question: str):
        """Answers a yes/no question"""
        responses = [
            "Yes, definitely! ✅", "No way. ❌", "Ask again later. 🤔",
            "I'm not sure... 🤷", "Absolutely! 🎯", "I wouldn't count on it. 🙅‍♂️"
        ]
        await ctx.send(f"🎱 **Question:** {question}\n**Answer:** {random.choice(responses)}")

# ✅ Fix: Correctly define setup function for bot
async def setup(bot):
    await bot.add_cog(Fun(bot))
