import discord
import random
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
    async def fuck(self, ctx, user: discord.Member = None):
        """Generates a random 'how long you last' result"""
        if user is None:
            await ctx.send("You need a partner first 😏")
            return
        duration = random.randint(1, 60)
        unit = "seconds" if duration < 10 else "minutes"
        await ctx.send(f"{ctx.author.mention} lasted **{duration} {unit}** with {user.mention}. 🍑🔥")

    @commands.command()
    async def eightball(self, ctx, *, question: str):
        """Answers a yes/no question"""
        responses = [
            "Yes, definitely! ✅", "No way. ❌", "Ask again later. 🤔",
            "I'm not sure... 🤷", "Absolutely! 🎯", "I wouldn't count on it. 🙅‍♂️"
        ]
        await ctx.send(f"🎱 **Question:** {question}\n**Answer:** {random.choice(responses)}")

async def setup(bot):
    print("✅ Loading fun cog...")  # ✅ Debugging
    await bot.add_cog(Fun(bot))
    print("✅ Fun cog successfully loaded!")  # ✅ Debugging
