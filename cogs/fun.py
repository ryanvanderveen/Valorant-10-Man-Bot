import discord
import random
import aiohttp  # For fetching memes
from discord.ext import commands

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def pp(self, ctx, user: discord.Member = None):
        """Random PP size"""
        user = user or ctx.author
        size = "=" * random.randint(0, 20)
        await ctx.send(f"{user.mention}'s pp is 8{size}D, length: {len(size)} inches.")

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
    async def bless(self, ctx, user: discord.Member = None):
        """Compliments a user"""
        compliments = [
            "You're amazing just the way you are! ✨",
            "Your presence lights up the server! 🔥",
            "You're proof that kindness still exists. ❤️"
        ]
        user = user or ctx.author
        await ctx.send(f"{user.mention}, {random.choice(compliments)}")

    @commands.command()
    async def love(self, ctx, user: discord.Member = None):
        """Love compatibility"""
        if not user:
            await ctx.send("You need someone to love! 💔")
            return
        score = random.randint(0, 100)
        await ctx.send(f"💖 {ctx.author.mention} and {user.mention} have {score}% compatibility!")

    @commands.command()
    async def fight(self, ctx, user: discord.Member = None):
        """Fights another user"""
        if not user:
            await ctx.send("You need an opponent to fight! 🥊")
            return
        winner = random.choice([ctx.author, user])
        await ctx.send(f"🥊 {ctx.author.mention} and {user.mention} fought... and **{winner.mention}** won!")

    @commands.command()
    async def simp(self, ctx, user: discord.Member = None):
        """Rates how much of a simp someone is"""
        user = user or ctx.author
        simp_score = random.randint(0, 100)
        await ctx.send(f"💗 {user.mention} is **{simp_score}%** a simp!")

    @commands.command()
    async def eightball(self, ctx, *, question: str):
        """Answers a yes/no question"""
        responses = [
            "Yes, definitely! ✅", "No way. ❌", "Ask again later. 🤔",
            "I'm not sure... 🤷", "Absolutely! 🎯", "I wouldn't count on it. 🙅‍♂️"
        ]
        await ctx.send(f"🎱 **Question:** {question}\n**Answer:** {random.choice(responses)}")

    @commands.command()
    async def meme(self, ctx):
        """Fetches a random meme from an API"""
        async with aiohttp.ClientSession() as session:
            async with session.get("https://meme-api.com/gimme") as response:
                if response.status == 200:
                    data = await response.json()
                    meme_url = data["url"]
                    title = data["title"]
                    embed = discord.Embed(title=title, color=discord.Color.random())
                    embed.set_image(url=meme_url)
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("Couldn't fetch a meme. Try again later!")

# ✅ Fix: Correctly define setup function for bot
async def setup(bot):
    await bot.add_cog(Fun(bot))
