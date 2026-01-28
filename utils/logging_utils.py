from __future__ import annotations

import discord
from typing import Optional

from db import get_guild_config


async def send_log(
    bot: discord.Client,
    guild_id: int,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
) -> None:
    config = await get_guild_config(guild_id)
    channel_id = config.get("log_channel_id")
    if not channel_id:
        return
    channel = bot.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except Exception:
            return
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return
    try:
        await channel.send(content=content, embed=embed)
    except Exception:
        pass

