# This example requires the 'message_content' privileged intents

import os
import discord
import yaml
import random
import asyncio
from discord.ext import commands
from utils import get_member_name
from converters import Player

# Load config
config_path = "config.yaml"
if os.path.exists(config_path):
    with open(config_path, "r") as file:
        config = yaml.safe_load(file)
else:
    print("⚠️ config.yaml not found! Using default settings.")
    config = {"prefix": "pls "}  # Default settings

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True  # ✅ Fix: Enable privileged intent
bot = commands.Bot(command_prefix=config["prefix"], intents=intents)

async def load_cogs():
    """Loads all cogs asynchronously."""
    COGS = ["fun", "utility"]  # Add all cogs here
    for cog in COGS:
        try:
            await bot.load_extension(f"cogs.{cog}")
            print(f"✅ Loaded {cog} cog")
        except Exception as e:
            print(f"❌ Failed to load {cog}: {e}")


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# ✅ Fix: Properly await cog loading
async def main():
    async with bot:
        await load_cogs()  # ✅ Fix: Now properly awaited
        await bot.start(os.getenv("DISCORD_TOKEN"))

# ✅ Fix: Use asyncio.run() correctly
if __name__ == "__main__":
    asyncio.run(main())
