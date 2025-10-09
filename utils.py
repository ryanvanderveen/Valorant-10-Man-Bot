import discord

def get_member_name(member, lower=True):
    """Returns a member's display name (nickname or username)"""
    if type(member) == str:
        if lower:
            return member.lower()
        return member
    if member.nick:
        if lower:
            return member.nick.lower()
        return member.nick
    if lower:
        return member.name.lower()
    return member.name

def prettify(s: str):
    """Capitalizes first letter of a string"""
    if not s:
        return s
    return s[0].upper() + s[1:].lower()
