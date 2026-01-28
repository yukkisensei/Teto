from __future__ import annotations

import time
from typing import Dict, List

import discord
from discord import app_commands
from discord.ext import commands

from config import MAX_AI_HISTORY, AI_COOLDOWN_SECONDS
from db import get_guild_config
from utils.guards import bot_ratio_exceeded, module_enabled


class AICog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.history: Dict[int, Dict[int, List[Dict[str, str]]]] = {}
        self.cooldowns: Dict[int, float] = {}

    def _get_history(self, guild_id: int, user_id: int) -> List[Dict[str, str]]:
        if guild_id not in self.history:
            self.history[guild_id] = {}
        if user_id not in self.history[guild_id]:
            self.history[guild_id][user_id] = []
        return self.history[guild_id][user_id]

    def _cooldown_ok(self, user_id: int) -> bool:
        now = time.time()
        last = self.cooldowns.get(user_id, 0)
        if now - last < AI_COOLDOWN_SECONDS:
            return False
        self.cooldowns[user_id] = now
        return True

    @app_commands.command(name="ai", description="Chat with Kasane Teto.")
    async def ai(self, interaction: discord.Interaction, prompt: str) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "ai_enabled", interaction.user.id):
            await interaction.response.send_message("AI module is disabled.", ephemeral=True)
            return
        if bot_ratio_exceeded(interaction.guild, cfg, interaction.user.id):
            await interaction.response.send_message("AI is disabled due to bot ratio guard.", ephemeral=True)
            return
        if not self.bot.ai_client.enabled():
            await interaction.response.send_message("AI is not configured.", ephemeral=True)
            return
        if not self._cooldown_ok(interaction.user.id):
            await interaction.response.send_message("Please wait before using AI again.", ephemeral=True)
            return
        history = self._get_history(interaction.guild.id, interaction.user.id)
        history.append({"role": "user", "content": prompt})
        history[:] = history[-MAX_AI_HISTORY:]
        await interaction.response.defer()
        try:
            reply = await self.bot.ai_client.generate(history, interaction.user.id)
        except Exception as exc:
            await interaction.followup.send(f"AI error: {exc}")
            return
        history.append({"role": "assistant", "content": reply})
        history[:] = history[-MAX_AI_HISTORY:]
        if len(reply) <= 1900:
            await interaction.followup.send(reply)
        else:
            for idx in range(0, len(reply), 1900):
                await interaction.followup.send(reply[idx:idx + 1900])

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        cfg = await get_guild_config(message.guild.id)
        ai_channel_id = cfg.get("ai_channel_id")
        if not cfg.get("ai_enabled") or not ai_channel_id:
            return
        if message.channel.id != int(ai_channel_id):
            return
        if bot_ratio_exceeded(message.guild, cfg):
            return
        if not self.bot.ai_client.enabled():
            return
        if not self._cooldown_ok(message.author.id):
            return
        history = self._get_history(message.guild.id, message.author.id)
        history.append({"role": "user", "content": message.content})
        history[:] = history[-MAX_AI_HISTORY:]
        try:
            reply = await self.bot.ai_client.generate(history, message.author.id)
        except Exception:
            return
        history.append({"role": "assistant", "content": reply})
        history[:] = history[-MAX_AI_HISTORY:]
        if len(reply) <= 1900:
            await message.reply(reply, mention_author=False)
        else:
            for idx in range(0, len(reply), 1900):
                await message.channel.send(reply[idx:idx + 1900])


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AICog(bot))
