import discord
import os
import yaml
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
bot = commands.Bot(command_prefix=config["prefix"], intents=intents, help_command=None)  # ✅ Disables default help

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
