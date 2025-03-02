# This example requires the 'message_content' privileged intents

import os
import discord
import yaml
import random
import asyncio
from discord.ext import commands
from utils import get_member_name
from converters import Player
from dotenv import load_dotenv

load_dotenv()  # ✅ Load environment variables
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL is not set! Please check Railway environment variables.")
    exit(1)

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
intents.message_content = True  # ✅ Ensures bot can read messages
def custom_prefix(bot, message):
    return commands.when_mentioned_or("pls ", "Pls ", "PLS ", "pLS ", "pLs ", "plS ")(bot, message)

bot = commands.Bot(command_prefix=custom_prefix, intents=intents, help_command=None)


async def load_cogs():
    """Loads all cogs asynchronously."""
    COGS = ["pp_leaderboard", "utility", "fun"]  # ✅ Ensure the correct cog names
    for cog in COGS:
        try:
            await bot.load_extension(f"cogs.{cog}")
            print(f"✅ Loaded {cog} cog")
        except Exception as e:
            print(f"❌ Failed to load {cog}: {e}")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

async def main():
    async with bot:
        await load_cogs()
        await bot.start(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())