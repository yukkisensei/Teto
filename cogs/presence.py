from __future__ import annotations

import discord
from discord.ext import commands, tasks

from config import (
    PRESENCE_STATUS,
    PRESENCE_ACTIVITY_TYPE,
    PRESENCE_ACTIVITY_TEXT,
    PRESENCE_STREAM_URL,
    PRESENCE_ROTATION_ENABLED,
    PRESENCE_ROTATION_INTERVAL,
)


STATUS_MESSAGES = [
    "Teto is making Baguette....",
    "Teto is playing with Yuu...",
    "Teto is Pear!",
    "Teto is tuning her voicebank.",
    "Teto is practicing drills.",
    "Teto is humming UTAU melodies.",
    "Teto is baking red velvet.",
    "Teto is chasing a golden note.",
    "Teto is guarding the twin tails.",
    "Teto is cheering your server.",
]


def _status_from_config() -> discord.Status:
    mapping = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "invisible": discord.Status.invisible,
    }
    return mapping.get(PRESENCE_STATUS, discord.Status.dnd)


def _static_activity() -> discord.BaseActivity | None:
    if not PRESENCE_ACTIVITY_TEXT:
        return None
    if PRESENCE_ACTIVITY_TYPE == "streaming" and PRESENCE_STREAM_URL:
        return discord.Streaming(name=PRESENCE_ACTIVITY_TEXT, url=PRESENCE_STREAM_URL)
    type_map = {
        "playing": discord.ActivityType.playing,
        "listening": discord.ActivityType.listening,
        "watching": discord.ActivityType.watching,
        "competing": discord.ActivityType.competing,
        "custom": discord.ActivityType.custom,
    }
    activity_type = type_map.get(PRESENCE_ACTIVITY_TYPE, discord.ActivityType.playing)
    if activity_type == discord.ActivityType.custom:
        return discord.CustomActivity(name=PRESENCE_ACTIVITY_TEXT)
    return discord.Activity(type=activity_type, name=PRESENCE_ACTIVITY_TEXT)


class PresenceCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._index = 0

    async def cog_load(self) -> None:
        if PRESENCE_ROTATION_ENABLED:
            self.rotate_status.start()
        else:
            await self._set_static_presence()

    async def cog_unload(self) -> None:
        if PRESENCE_ROTATION_ENABLED:
            self.rotate_status.cancel()

    async def _set_static_presence(self) -> None:
        await self.bot.wait_until_ready()
        try:
            await self.bot.change_presence(status=_status_from_config(), activity=_static_activity())
        except Exception:
            pass

    @tasks.loop(seconds=PRESENCE_ROTATION_INTERVAL)
    async def rotate_status(self) -> None:
        await self.bot.wait_until_ready()
        message = STATUS_MESSAGES[self._index % len(STATUS_MESSAGES)]
        self._index += 1
        status = _status_from_config()
        try:
            activity = discord.CustomActivity(name=message)
            await self.bot.change_presence(status=status, activity=activity)
        except Exception:
            try:
                activity = discord.Activity(type=discord.ActivityType.playing, name=message)
                await self.bot.change_presence(status=status, activity=activity)
            except Exception:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PresenceCog(bot))
