from __future__ import annotations

import discord
from typing import Optional

from db import get_guild_config
from utils.superusers import is_superuser


def is_owner(user_id: int) -> bool:
    return is_superuser(user_id)


async def is_moderator(member: discord.Member) -> bool:
    if is_owner(member.id):
        return True
    if member.guild_permissions.manage_guild or member.guild_permissions.administrator:
        return True
    config = await get_guild_config(member.guild.id)
    mod_role_id = config.get("mod_role_id")
    if mod_role_id:
        role = member.guild.get_role(int(mod_role_id))
        if role and role in member.roles:
            return True
    return False


async def get_log_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    config = await get_guild_config(guild.id)
    channel_id = config.get("log_channel_id")
    if not channel_id:
        return None
    channel = guild.get_channel(int(channel_id))
    if isinstance(channel, discord.TextChannel):
        return channel
    return None
