import discord

def prettify(s: str):
    """Capitalizes first letter of a string"""
    return s[0].upper() + s[1:].lower()

def get_member_name(member):
    """Returns a member's display name"""
    return member.nick or member.name