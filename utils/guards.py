from __future__ import annotations

import discord
from typing import Any, Dict, Optional

from config import OWNER_ID, GOD_MODE_ENABLED


def is_owner(user_id: int | None) -> bool:
    return bool(GOD_MODE_ENABLED and OWNER_ID and user_id == OWNER_ID)


def bot_ratio_exceeded(guild: discord.Guild, config: Dict[str, Any], user_id: Optional[int] = None) -> bool:
    if is_owner(user_id):
        return False
    if not config.get("bot_ratio_guard_enabled"):
        return False
    humans = sum(1 for m in guild.members if not m.bot)
    bots = sum(1 for m in guild.members if m.bot)
    if humans <= 0:
        return True
    ratio = bots / max(1, humans)
    return ratio > float(config.get("bot_ratio_max") or 0.0)


def module_enabled(config: Dict[str, Any], key: str, user_id: Optional[int] = None) -> bool:
    if bool(config.get(key)):
        return True
    if is_owner(user_id):
        return True
    return False
