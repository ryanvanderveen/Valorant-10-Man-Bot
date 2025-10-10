# This example requires the 'message_content' privileged intents

import os
import discord
import yaml
import random
import asyncio
from discord.ext import commands
from utils import get_member_name
from converters import Player

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL is not set! Please check Railway environment variables.")
    exit(1)
else:
    print(f"✅ DATABASE_URL is set: {DATABASE_URL}")  # Debugging

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
intents.messages = True  # ✅ Enable message intent
intents.guilds = True
intents.message_content = True  # ✅ Required for commands
intents.members = True # ✅ Required for member cache/fetching

def custom_prefix(bot, message):
    return commands.when_mentioned_or("pls ", "Pls ", "PLS ", "pLS ", "pLs ", "plS ")(bot, message)

bot = commands.Bot(command_prefix=custom_prefix, intents=intents, help_command=None)


async def load_cogs():
    """Loads all cogs asynchronously."""
    COGS = [
        "pp_db",         # Database initialization and shared functions
        "pp_core",       # Core PP functionality
        "pp_events",     # Event system
        "pp_items",      # Item and inventory system
        "pp_minigames",  # Mini-games (trivia, duels, pp-off)
        "pp_profile",    # Profile command
        "help_cog",      # Help command
        "info_cog",      # Bot information
        "utility",       # Utility commands (ping)
        "utility_core",  # Core utility functions (placeholder)
        "fun"            # Fun commands (placeholder)
    ]
    for cog in COGS:
        try:
            await bot.load_extension(f"cogs.{cog}")
            print(f"✅ Loaded {cog} cog")
        except Exception as e:
            print(f"❌ Failed to load {cog}: {e}")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_command_error(ctx, error):
    """Global error handler to catch command errors"""
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore command not found
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: {error.param.name}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Bad argument: {error}")
    elif isinstance(error, commands.CommandInvokeError):
        print(f"❌ Command error in {ctx.command}: {error.original}")
        import traceback
        traceback.print_exception(type(error), error, error.__traceback__)
        await ctx.send(f"❌ An error occurred: {error.original}")
    else:
        print(f"❌ Unhandled error in {ctx.command}: {error}")
        import traceback
        traceback.print_exception(type(error), error, error.__traceback__)

async def main():
    async with bot:
        await load_cogs()
        await bot.start(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())