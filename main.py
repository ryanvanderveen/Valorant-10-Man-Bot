# This example requires the 'message_content' privileged intents

import os
import discord
import yaml
import random
import asyncio
from discord.ext import commands
from utils import get_member_name
from converters import Player

# Load config.yaml
config_path = "config.yaml"
if os.path.exists(config_path):
    with open(config_path, "r") as file:
        config = yaml.safe_load(file)
else:
    print("⚠️ config.yaml not found! Using default settings.")
    config = {"prefix": "pls "}  # Default settings

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True  # ✅ Ensures the bot can read message content
bot = commands.Bot(command_prefix=config["prefix"], intents=intents)

async def load_cogs():
    """Loads all cogs asynchronously."""
    COGS = ["pp_leaderboard", "utility", "fun"]  # ✅ Ensure the correct cog name is used
    for cog in COGS:
        try:
            await bot.load_extension(f"cogs.{cog}")
            print(f"✅ Loaded {cog} cog")
        except Exception as e:
            print(f"❌ Failed to load {cog}: {e}")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# ✅ Ensure cooldowns are properly applied
@bot.before_invoke
async def before_command(ctx):
    """Ensure cooldowns are being applied"""
    bucket = bot.get_cog("PPLeaderboard").pp._buckets
    retry_after = bucket.get_retry_after(ctx.message)
    if retry_after > 0:
        raise commands.CommandOnCooldown(bucket, retry_after)

async def main():
    async with bot:
        await load_cogs()
        await bot.start(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())# ✅ Fix: Properly await cog loading
