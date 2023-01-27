# This example requires the 'message_content' privileged intents

import os
import discord
import yaml
import random
from discord.ext import commands
from bot import Bot
from utils import get_member_name
from converters import Player

with open("config.yaml","r") as file:
    options = yaml.safe_load(file)
blacklist = open("blacklist.txt","r").readlines()
command = {'pls ', 'PLS ', 'PlS ', 'PLs ', 'pLs ', 'pLS ', 'plS ', 'Pls '}
bot = Bot(command, options["scheme"], options["maps"], blacklist)

length = '============'

def get_pp_size():
  return ''.join(random.choice(length) for i in range(random.randint(0, 20)))
  
@bot.event
async def on_ready():
  await bot.change_presence(status=discord.Status.online, activity=discord.Game('with Dana\'s pussy'))
  print('We have logged in as {0.user}'.format(bot))
  
@bot.command()
async def pp(ctx, user: discord.Member = None):
  pp_size = get_pp_size()
  pp_num_size = len(pp_size)
  if (user == None):
    await ctx.send("{0}'s penis is 8{1}D, a total of {2} inches long".format(ctx.author.mention, pp_size, pp_num_size))
  else:
    await ctx.send("{0}'s penis is 8{1}D, a total of {2} inches long".format(user.mention, pp_size, pp_num_size))

@bot.command()
async def fuck(ctx, user: discord.Member = None, *, reason = '', type = 'anal'):
  pp_size = get_pp_size()
  pp_num_size = len(pp_size)
  asshole = pp_num_size / 2.5
  reason = 'dick, 8{0}D. Which is a total of a {1} inches long!'.format(pp_size, pp_num_size)
  await ctx.send('{0} just had {2} sex with {3}\'s {1} {3} expanded {0}\'s asshole by {4} inches'.format(user.mention, reason, type, ctx.author.mention, asshole))

@bot.command()
async def newcaps(ctx):
    lobby_channel = next((i for i in ctx.guild.voice_channels if i.name == options['lobby']), None)
    a_channel = next((i for i in ctx.guild.voice_channels if i.name == options['team_a']), None)
    b_channel = next((i for i in ctx.guild.voice_channels if i.name == options['team_b']), None)
    players = lobby_channel.members
    await bot.new_game(players)
    await ctx.send(embed=await bot.generate_captains(a_channel,b_channel))

@bot.command()
async def b(ctx, map_name : str):
    await ban(ctx, map_name)

@bot.command()
async def ban(ctx, map_name : str):
    embed = await bot.ban_map(map_name, ctx.author)
    await ctx.send(embed=embed)

@bot.command()
async def nc(ctx):
    await newcaps(ctx)

@bot.command()
async def d(ctx, player_name : Player):
    await draft(ctx, player_name)

@bot.command()
async def draft(ctx,player_name : Player):
    temp_dict = {i.name : i for i in ctx.guild.voice_channels}
    channel_dict = {"A":temp_dict[options["team_a"]],"B":temp_dict[options["team_b"]]}
    await ctx.send(embed=await bot.draft_player(ctx.author,player_name,channel_dict))

@bot.command()
async def draft_for_bot(ctx,bot_name : Player, player_name : Player):
    temp_dict = {i.name : i for i in ctx.guild.voice_channels}
    channel_dict = {"A":temp_dict[options["team_a"]],"B":temp_dict[options["team_b"]]}
    await ctx.send(embed=await bot.draft_player(bot_name,player_name,channel_dict))

@bot.command()
async def setcaps(ctx,cap1 : Player, cap2 : Player):
    lobby_channel = next((i for i in ctx.guild.voice_channels if i.name == options['lobby']), None)
    players = lobby_channel.members
    await bot.new_game(players)
    await bot.set_captain(cap1,"A")
    await bot.set_captain(cap2,"B")
    embed = discord.Embed(title="Valorant 10 Man Bot",
            description="The captains are {} and {}".format(get_member_name(cap1,lower=False),get_member_name(cap2,lower=False)))
    await ctx.send(embed=embed)

@bot.command()
async def new(ctx):
    embed = discord.Embed(title="Valorant 10 Man Bot",
            description="How many players are playing?")
    await ctx.send(embed=embed)

    # This will make sure that the response will only be registered if the following
    # conditions are met:
    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel and int(msg.content) in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    msg = await bot.wait_for("message", check=check)
    
    if int(msg.content) != lobby_channel.members:
        embed = discord.Embed(title="Valorant 10 Man Bot",
        description="Please get the right amount of people to join.")
        await ctx.send(embed=embed)
    players = int(msg.content)
    lobby_channel = next((i for i in ctx.guild.voice_channels if i.name == options['lobby']), None)
    embed = await bot.new_game(players)
    await ctx.send(embed=embed)

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="Valorant 10 Man Bot",
            description="The following commands are available\n\n :one: pls nc : selects captains for current game\n\
                         :two: pls d <player name> : drafts player to your team (you must be captain)\n\
                         :three: pls setcaps <captain1> <captain2> : manually set the captains \n\
                         :four: pls new : starts a new game (does not set captains)\n\
                         :five: pls ban <map_name> : bans a map (must be captain)")
    await ctx.send(embed=embed)
    
bot.run(os.environ["DISCORD_TOKEN"])
