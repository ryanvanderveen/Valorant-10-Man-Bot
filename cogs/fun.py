import random
import discord
from discord.ext import commands
from converters import Player

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _pair_names(self, ctx, target):
        author = ctx.author.mention
        other = target.mention if target else "someone"
        return author, other

    def _is_bot_target(self, target):
        return target and getattr(target, "bot", False)

    @commands.command(name="kiss")
    async def kiss(self, ctx, target: Player):
        if self._is_bot_target(target):
            await ctx.send("I blush in binary, but I can't kiss.")
            return
        a, b = self._pair_names(ctx, target)
        lines = [
            f"{a} pulls {b} in for a slow, consensual kiss.",
            f"{a} and {b} trade a teasing kiss that lingers.",
            f"{a} kisses {b} like they've been waiting all night.",
            f"{a} plants a kiss on {b} and smirks.",
        ]
        await ctx.send(random.choice(lines))

    @commands.command(name="fuck")
    async def fuck(self, ctx, target: Player):
        if self._is_bot_target(target):
            await ctx.send("Error 69: bots are not equipped for that.")
            return
        a, b = self._pair_names(ctx, target)
        lines = [
            f"{a} and {b} vanish for a very consensual, very loud break.",
            f"{a} and {b} lock the door. The rest is private and enthusiastic.",
            f"{a} and {b} disappear behind closed doors with mutual consent.",
            f"{a} and {b} heat things up with a wild, consensual night.",
        ]
        await ctx.send(random.choice(lines))

    @commands.command(name="bang")
    async def bang(self, ctx, target: Player):
        if self._is_bot_target(target):
            await ctx.send("I only bang out code.")
            return
        a, b = self._pair_names(ctx, target)
        lines = [
            f"{a} and {b} agree on a spicy rendezvous.",
            f"{a} and {b} make the couch regret its life choices.",
            f"{a} and {b} share a shameless, consensual bang session.",
            f"{a} and {b} turn the heat up to maximum.",
        ]
        await ctx.send(random.choice(lines))

    @commands.command(name="tease")
    async def tease(self, ctx, target: Player):
        if self._is_bot_target(target):
            await ctx.send("I only respond to /ping.")
            return
        a, b = self._pair_names(ctx, target)
        lines = [
            f"{a} teases {b} slowly, then walks away grinning.",
            f"{a} leans into {b}'s ear and whispers something filthy.",
            f"{a} drags a finger along {b}'s chin and dares them to react.",
            f"{a} gives {b} that look that says 'later.'",
        ]
        await ctx.send(random.choice(lines))

    @commands.command(name="dirtyrate")
    async def dirtyrate(self, ctx, target: Player = None):
        target = target or ctx.author
        score = random.randint(0, 100)
        labels = [
            "angelic",
            "sweet but spicy",
            "lowkey naughty",
            "dangerously horny",
            "absolutely feral",
        ]
        label = labels[min(score // 20, 4)]
        await ctx.send(f"Dirty rating for {target.mention}: {score}/100 - {label}.")

    @commands.command(name="smash")
    async def smash(self, ctx, target: Player):
        if self._is_bot_target(target):
            await ctx.send("Smash the like button instead.")
            return
        a, b = self._pair_names(ctx, target)
        lines = [
            f"{a}: Smash. No hesitation. {b} knows why.",
            f"{a}: Smash. {b} can come over.",
            f"{a}: Smash. The verdict is in.",
            f"{a}: Smash. That tension is mutual.",
        ]
        await ctx.send(random.choice(lines))

    @commands.command(name="pass")
    async def pass_cmd(self, ctx, target: Player):
        if self._is_bot_target(target):
            await ctx.send("I can't take it personally, I'm code.")
            return
        a, b = self._pair_names(ctx, target)
        lines = [
            f"{a}: Pass. {b} stays on read.",
            f"{a}: Pass. Not tonight.",
            f"{a}: Pass. The vibe isn't there.",
            f"{a}: Pass. Keeping it chill.",
        ]
        await ctx.send(random.choice(lines))

    @commands.command(name="top")
    async def top(self, ctx):
        lines = [
            f"{ctx.author.mention} is top energy.",
            f"{ctx.author.mention} is definitely top tonight.",
            f"{ctx.author.mention} radiates top vibes.",
        ]
        await ctx.send(random.choice(lines))

    @commands.command(name="bottom")
    async def bottom(self, ctx):
        lines = [
            f"{ctx.author.mention} is bottom energy.",
            f"{ctx.author.mention} is definitely bottom tonight.",
            f"{ctx.author.mention} radiates bottom vibes.",
        ]
        await ctx.send(random.choice(lines))

    @commands.command(name="kink")
    async def kink(self, ctx):
        prompts = [
            "Blindfold + whispering orders.",
            "Ice cubes and slow teasing.",
            "Praise kink, say it like you mean it.",
            "Roleplay: strangers at a bar.",
            "Mirror play and eye contact.",
            "Hands only, no mouths.",
            "Shower session with zero rush.",
            "Silk rope and soft control.",
        ]
        await ctx.send(f"Kink prompt: {random.choice(prompts)}")

    @commands.command(name="moan")
    async def moan(self, ctx):
        lines = [
            "mmh~",
            "ahh... yeah.",
            "ngh~ don't stop.",
            "mmm... harder.",
            "h-hah~",
        ]
        await ctx.send(random.choice(lines))

async def setup(bot):
    print("Loading fun cog...")  # Debugging
    await bot.add_cog(Fun(bot))
    print("Fun cog successfully loaded!")  # Debugging
