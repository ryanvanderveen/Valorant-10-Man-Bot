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
bot = Bot(command, options["scheme"], options["maps"], options["sides"], blacklist)

length = '============'

def get_pp_size():
  return ''.join(random.choice(length) for i in range(random.randint(0, 20)))
  
@bot.event
async def on_ready():
  await bot.change_presence(status=discord.Status.online, activity=discord.Game('with TJ\'s heart'))
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
async def rizz(ctx, user: discord.Member = None):
  rizz = random.randint(0, 10)
  if (user == None):
    await ctx.send("{0} your rizz is {1}/10.".format(ctx.author.mention, rizz))
  else:
    await ctx.send("{0}'s rizz is {1}/10.".format(user.mention, rizz))

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
async def p(ctx, map_name : str):
    await pick(ctx, map_name)
    
@bot.command()
async def pick(ctx, map_name : str):
    embed = await bot.pick_map(map_name, ctx.author)
    await ctx.send(embed=embed)
    
@bot.command()
async def s(ctx, side_name : str):
    await side(ctx, side_name)
    
@bot.command()
async def side(ctx, side_name : str):
    embed = await bot.pick_side(side_name, ctx.author)
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
    a_channel = next((i for i in ctx.guild.voice_channels if i.name == options['team_a']), None)
    b_channel = next((i for i in ctx.guild.voice_channels if i.name == options['team_b']), None)
    players = lobby_channel.members
    await bot.new_game(players)
    await bot.set_captain(cap1,"A",a_channel)
    await bot.set_captain(cap2,"B",b_channel)
    embed = discord.Embed(title="Valorant 10 Man Bot",
            description="The captains are {} and {}".format(get_member_name(cap1,lower=False),get_member_name(cap2,lower=False)))
    await ctx.send(embed=embed)

@bot.command()
async def new(ctx):
    lobby_channel = next((i for i in ctx.guild.voice_channels if i.name == options['lobby']), None)
    
    players = lobby_channel.members
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
