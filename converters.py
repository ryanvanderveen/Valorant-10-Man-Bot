from discord.ext import commands
from discord.ext.commands import BadArgument
import discord
import re
from utils import get_member_name

def _get_from_guilds(bot, method, argument):
    """Helper to get member from all guilds the bot is in"""
    for guild in bot.guilds:
        result = getattr(guild, method)(argument)
        if result:
            return result
    return None

class Player(commands.MemberConverter):
    async def convert(self, ctx, argument):
        bot = ctx.bot
        match = self._get_id_match(argument) or re.match(r'<@!?([0-9]+)>$', argument)
        guild = ctx.guild
        result = None
        if match is None:
            # not a mention...
            if guild:
                result = guild.get_member_named(argument)
                if not result:
                    result = guild.get_member_named(argument.lower())
            else:
                result = _get_from_guilds(bot, 'get_member_named', argument)
                if not result:
                    result = _get_from_guilds(bot, 'get_member_named', argument.lower())
        else:
            user_id = int(match.group(1))
            if guild:
                result = guild.get_member(user_id) or discord.utils.get(ctx.message.mentions, id=user_id)
            else:
                result = _get_from_guilds(bot, 'get_member', user_id)

        if not result:
            members = guild.members
            for m in members:
                if get_member_name(m) == get_member_name(argument):
                    return m
        if result is None:
            raise BadArgument('Member "{}" not found'.format(argument))

        return result
