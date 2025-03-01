# This example requires the 'message_content' privileged intents

import os
import discord
import yaml
import random
from discord.ext import commands
from utils import get_member_name
from converters import Player

command = {'pls ', 'PLS ', 'PlS ', 'PLs ', 'pLs ', 'pLS ', 'plS ', 'Pls '}
intents = discord.Intents.default()
bot = commands.Bot(command_prefix=config[command], intents=intents)

# Load all cogs (command files)
COGS = ["fun", "utility"]  # Add more as needed

for cog in COGS:
    bot.load_extension(f"cogs.{cog}")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# Run the bot
bot.run(os.environ["DISCORD_TOKEN"])
