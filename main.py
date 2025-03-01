# This example requires the 'message_content' privileged intents

import os
import discord
import yaml
import random
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
intents.messages = True
bot = commands.Bot(command_prefix=config["prefix"], intents=intents)

async def load_cogs():
    """Loads all cogs asynchronously."""
    COGS = ["fun", "utility"]  # Add more cogs if needed
    for cog in COGS:
        await bot.load_extension(f"cogs.{cog}")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# Run the bot
async def main():
    await load_cogs()  # ✅ Fix: Now awaited
    await bot.start(os.environ["DISCORD_TOKEN"])

import asyncio
asyncio.run(main())  # ✅ Fix: Use asyncio to run async function
