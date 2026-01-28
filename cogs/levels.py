from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Dict

import discord
from discord import app_commands
from discord.ext import commands

from config import XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX, XP_COOLDOWN_SECONDS, VOICE_XP_PER_MIN
from db import (
    get_guild_config,
    get_leveling,
    set_leveling,
    get_leaderboard,
    increment_message_count,
    increment_voice_seconds,
    add_badge,
    get_badges,
    get_daily_tasks,
    upsert_daily_task,
    update_daily_progress,
)
from utils.leveling_utils import level_from_xp, progress_to_next_level
from utils.guards import bot_ratio_exceeded, module_enabled


def _date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class LevelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.last_xp: Dict[int, Dict[int, float]] = {}
        self.voice_sessions: Dict[int, Dict[int, float]] = {}

    def _cooldown_ok(self, guild_id: int, user_id: int) -> bool:
        if guild_id not in self.last_xp:
            self.last_xp[guild_id] = {}
        now = datetime.now(timezone.utc).timestamp()
        last = self.last_xp[guild_id].get(user_id, 0.0)
        if now - last < XP_COOLDOWN_SECONDS:
            return False
        self.last_xp[guild_id][user_id] = now
        return True

    async def _ensure_daily_tasks(self, guild_id: int, user_id: int) -> None:
        date = _date_str()
        tasks = await get_daily_tasks(guild_id, user_id, date)
        if tasks:
            return
        msg_target = random.randint(20, 50)
        voice_target = random.randint(10, 30)
        game_target = random.randint(1, 3)
        await upsert_daily_task(guild_id, user_id, date, "messages", msg_target, 0, 0)
        await upsert_daily_task(guild_id, user_id, date, "voice_minutes", voice_target, 0, 0)
        await upsert_daily_task(guild_id, user_id, date, "games", game_target, 0, 0)

    async def _check_badges(self, guild_id: int, user_id: int, level: int) -> None:
        milestones = {5: "Rising Star", 10: "Teto Fan", 20: "Kasaner", 30: "Diva"} 
        if level in milestones:
            await add_badge(guild_id, user_id, milestones[level])

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        cfg = await get_guild_config(message.guild.id)
        if not module_enabled(cfg, "leveling_enabled", message.author.id):
            return
        if bot_ratio_exceeded(message.guild, cfg, message.author.id):
            return
        await increment_message_count(message.guild.id, message.author.id, 1)
        await self._ensure_daily_tasks(message.guild.id, message.author.id)
        await update_daily_progress(message.guild.id, message.author.id, _date_str(), "messages", 1)
        if not self._cooldown_ok(message.guild.id, message.author.id):
            return
        data = await get_leveling(message.guild.id, message.author.id)
        xp_gain = random.randint(XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX)
        new_xp = int(data["xp"]) + xp_gain
        new_level = level_from_xp(new_xp)
        await set_leveling(message.guild.id, message.author.id, new_xp, new_level, datetime.now(timezone.utc).isoformat())
        if new_level > int(data["level"]):
            await self._check_badges(message.guild.id, message.author.id, new_level)
            try:
                await message.channel.send(f"{message.author.mention} reached level {new_level}!")
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if not member.guild or member.bot:
            return
        cfg = await get_guild_config(member.guild.id)
        if not module_enabled(cfg, "leveling_enabled", member.id):
            return
        if bot_ratio_exceeded(member.guild, cfg, member.id):
            return
        guild_id = member.guild.id
        if guild_id not in self.voice_sessions:
            self.voice_sessions[guild_id] = {}
        if before.channel is None and after.channel is not None:
            self.voice_sessions[guild_id][member.id] = datetime.now(timezone.utc).timestamp()
            return
        if before.channel is not None and after.channel is None:
            start = self.voice_sessions[guild_id].pop(member.id, None)
            if not start:
                return
            seconds = int(datetime.now(timezone.utc).timestamp() - start)
            if seconds <= 0:
                return
            await increment_voice_seconds(guild_id, member.id, seconds)
            await self._ensure_daily_tasks(guild_id, member.id)
            minutes = max(1, seconds // 60)
            await update_daily_progress(guild_id, member.id, _date_str(), "voice_minutes", minutes)
            data = await get_leveling(guild_id, member.id)
            new_xp = int(data["xp"]) + minutes * VOICE_XP_PER_MIN
            new_level = level_from_xp(new_xp)
            await set_leveling(guild_id, member.id, new_xp, new_level, datetime.now(timezone.utc).isoformat())
        if before.channel is not None and after.channel is not None and before.channel != after.channel:
            start = self.voice_sessions[guild_id].get(member.id)
            if start:
                seconds = int(datetime.now(timezone.utc).timestamp() - start)
                if seconds > 0:
                    await increment_voice_seconds(guild_id, member.id, seconds)
            self.voice_sessions[guild_id][member.id] = datetime.now(timezone.utc).timestamp()

    @app_commands.command(name="rank", description="Show your rank.")
    async def rank(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        if not interaction.guild:
            return
        target = member or interaction.user
        data = await get_leveling(interaction.guild.id, target.id)
        progress, required = progress_to_next_level(int(data["xp"]))
        badges = await get_badges(interaction.guild.id, target.id)
        embed = discord.Embed(title=f"{target.display_name}'s Rank", color=discord.Color.red())
        embed.add_field(name="Level", value=str(data["level"]), inline=True)
        embed.add_field(name="XP", value=f"{data['xp']} ({progress}/{required})", inline=True)
        embed.add_field(name="Badges", value=", ".join(badges) if badges else "None", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="leaderboard", description="Show the XP leaderboard.")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        leaders = await get_leaderboard(interaction.guild.id, 10)
        lines = []
        for idx, entry in enumerate(leaders, start=1):
            user = interaction.guild.get_member(int(entry["user_id"]))
            name = user.display_name if user else str(entry["user_id"])
            lines.append(f"{idx}. {name} - L{entry['level']} ({entry['xp']} XP)")
        if not lines:
            await interaction.response.send_message("No data yet.", ephemeral=True)
            return
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LevelsCog(bot))
