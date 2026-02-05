from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from db import (
    get_guild_config,
    create_giveaway,
    get_giveaway,
    get_giveaway_by_message,
    list_due_giveaways,
    list_open_giveaways,
    add_giveaway_entry,
    list_giveaway_entries,
    close_giveaway,
)
from utils.time_utils import parse_duration
from utils.checks import is_moderator
from utils.guards import module_enabled


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _timestamp(dt: datetime) -> str:
    return f"<t:{int(dt.timestamp())}:R>"


def _timestamp_full(dt: datetime) -> str:
    return f"<t:{int(dt.timestamp())}:F>"


def _build_embed(giveaway: dict, entries: int, winners: Optional[List[int]] = None) -> discord.Embed:
    title = "Giveaway"
    description = giveaway.get("prize") or "Prize"
    embed = discord.Embed(title=title, description=description, color=discord.Color.red())
    embed.add_field(name="Winner count", value=str(giveaway.get("winner_count") or 1), inline=True)
    ends_at = giveaway.get("ends_at")
    ended_at = giveaway.get("ended_at")
    if ended_at:
        try:
            ended_time = _parse_iso(ended_at)
            embed.add_field(name="Ended", value=_timestamp_full(ended_time), inline=True)
        except Exception:
            embed.add_field(name="Ended", value="Ended", inline=True)
    else:
        try:
            end_time = _parse_iso(ends_at) if ends_at else datetime.now(timezone.utc)
            embed.add_field(name="Ends", value=_timestamp(end_time), inline=True)
        except Exception:
            embed.add_field(name="Ends", value="Soon", inline=True)
    embed.add_field(name="Entries", value=str(entries), inline=True)
    if winners is not None:
        if winners:
            winner_mentions = ", ".join([f"<@{w}>" for w in winners])
            embed.add_field(name="Winners", value=winner_mentions, inline=False)
        else:
            embed.add_field(name="Winners", value="No valid entries.", inline=False)
    giveaway_id = giveaway.get("id")
    if giveaway_id:
        embed.set_footer(text=f"Giveaway ID: {giveaway_id}")
    return embed


class GiveawayJoinView(discord.ui.View):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success, emoji="🎉", custom_id="giveaway_join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        giveaway = await get_giveaway_by_message(interaction.message.id)
        if not giveaway:
            await interaction.response.send_message("Giveaway not found.", ephemeral=True)
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "giveaway_enabled", interaction.user.id):
            await interaction.response.send_message("Giveaway module is disabled.", ephemeral=True)
            return
        if giveaway.get("ended_at"):
            await interaction.response.send_message("This giveaway already ended.", ephemeral=True)
            return
        try:
            end_time = _parse_iso(giveaway.get("ends_at"))
        except Exception:
            end_time = datetime.now(timezone.utc)
        if datetime.now(timezone.utc) >= end_time:
            await interaction.response.send_message("This giveaway already ended.", ephemeral=True)
            return
        added = await add_giveaway_entry(giveaway["id"], interaction.user.id)
        entries = await list_giveaway_entries(giveaway["id"])
        try:
            embed = _build_embed(giveaway, len(entries))
            await interaction.message.edit(embed=embed, view=self)
        except Exception:
            pass
        if added:
            await interaction.response.send_message("You are entered.", ephemeral=True)
        else:
            await interaction.response.send_message("You already joined.", ephemeral=True)


class GiveawayCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.check_loop.start()

    async def cog_load(self) -> None:
        self.bot.add_view(GiveawayJoinView(self.bot))

    async def cog_unload(self) -> None:
        self.check_loop.cancel()

    @tasks.loop(seconds=30)
    async def check_loop(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        due = await list_due_giveaways(now_iso)
        for giveaway in due:
            await self._end_giveaway(giveaway)

    async def _end_giveaway(self, giveaway: dict) -> None:
        guild = self.bot.get_guild(int(giveaway["guild_id"]))
        if not guild:
            await close_giveaway(giveaway["id"], [], datetime.now(timezone.utc).isoformat())
            return
        channel = guild.get_channel(int(giveaway["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            await close_giveaway(giveaway["id"], [], datetime.now(timezone.utc).isoformat())
            return
        try:
            message = await channel.fetch_message(int(giveaway["message_id"]))
        except Exception:
            message = None
        entries = await list_giveaway_entries(giveaway["id"])
        winners: List[int] = []
        if entries:
            winner_count = int(giveaway.get("winner_count") or 1)
            winners = random.sample(entries, k=min(winner_count, len(entries)))
        ended_at = datetime.now(timezone.utc).isoformat()
        await close_giveaway(giveaway["id"], winners, ended_at)
        giveaway["ended_at"] = ended_at
        embed = _build_embed(giveaway, len(entries), winners)
        if message:
            try:
                await message.edit(embed=embed, view=None)
            except Exception:
                pass
        if winners:
            winner_mentions = ", ".join([f"<@{w}>" for w in winners])
            await channel.send(f"Giveaway ended. Winners: {winner_mentions}")
        else:
            await channel.send("Giveaway ended with no valid entries.")

    giveaway_group = app_commands.Group(name="giveaway", description="Giveaway commands")

    @giveaway_group.command(name="create", description="Create a giveaway.")
    async def create(
        self,
        interaction: discord.Interaction,
        duration: str,
        prize: str,
        winners: int,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "giveaway_enabled", interaction.user.id):
            await interaction.response.send_message("Giveaway module is disabled.", ephemeral=True)
            return
        if not await is_moderator(interaction.user):
            await interaction.response.send_message("No permission.", ephemeral=True)
            return
        try:
            seconds = parse_duration(duration)
        except Exception:
            await interaction.response.send_message("Invalid duration.", ephemeral=True)
            return
        if winners <= 0:
            await interaction.response.send_message("Winner count must be greater than 0.", ephemeral=True)
            return
        target_channel = channel
        if not target_channel:
            default_channel_id = cfg.get("giveaway_channel_id")
            if default_channel_id:
                target_channel = interaction.guild.get_channel(int(default_channel_id))
        if not isinstance(target_channel, discord.TextChannel):
            target_channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message("No valid channel.", ephemeral=True)
            return
        ends_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        embed = discord.Embed(title="Giveaway", description=prize, color=discord.Color.red())
        embed.add_field(name="Winner count", value=str(winners), inline=True)
        embed.add_field(name="Ends", value=_timestamp(ends_at), inline=True)
        embed.add_field(name="Entries", value="0", inline=True)
        await interaction.response.send_message("Giveaway created.", ephemeral=True)
        view = GiveawayJoinView(self.bot)
        message = await target_channel.send(embed=embed, view=view)
        giveaway_id = await create_giveaway(
            interaction.guild.id,
            target_channel.id,
            message.id,
            prize,
            winners,
            ends_at.isoformat(),
            interaction.user.id,
        )
        giveaway = {
            "id": giveaway_id,
            "guild_id": interaction.guild.id,
            "channel_id": target_channel.id,
            "message_id": message.id,
            "prize": prize,
            "winner_count": winners,
            "ends_at": ends_at.isoformat(),
            "created_by": interaction.user.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": None,
        }
        embed = _build_embed(giveaway, 0)
        try:
            await message.edit(embed=embed, view=view)
        except Exception:
            pass

    @giveaway_group.command(name="end", description="End a giveaway early.")
    async def end(self, interaction: discord.Interaction, giveaway_id: int) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "giveaway_enabled", interaction.user.id):
            await interaction.response.send_message("Giveaway module is disabled.", ephemeral=True)
            return
        if not await is_moderator(interaction.user):
            await interaction.response.send_message("No permission.", ephemeral=True)
            return
        giveaway = await get_giveaway(giveaway_id)
        if not giveaway:
            await interaction.response.send_message("Giveaway not found.", ephemeral=True)
            return
        if giveaway.get("ended_at"):
            await interaction.response.send_message("Giveaway already ended.", ephemeral=True)
            return
        await self._end_giveaway(giveaway)
        await interaction.response.send_message("Giveaway ended.", ephemeral=True)

    @giveaway_group.command(name="reroll", description="Reroll winners for a giveaway.")
    async def reroll(self, interaction: discord.Interaction, giveaway_id: int, winners: Optional[int] = None) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "giveaway_enabled", interaction.user.id):
            await interaction.response.send_message("Giveaway module is disabled.", ephemeral=True)
            return
        if not await is_moderator(interaction.user):
            await interaction.response.send_message("No permission.", ephemeral=True)
            return
        giveaway = await get_giveaway(giveaway_id)
        if not giveaway:
            await interaction.response.send_message("Giveaway not found.", ephemeral=True)
            return
        entries = await list_giveaway_entries(giveaway_id)
        if not entries:
            await interaction.response.send_message("No entries to reroll.", ephemeral=True)
            return
        winner_count = winners if winners is not None else int(giveaway.get("winner_count") or 1)
        if winner_count <= 0:
            await interaction.response.send_message("Winner count must be greater than 0.", ephemeral=True)
            return
        winners_list = random.sample(entries, k=min(winner_count, len(entries)))
        ended_at = datetime.now(timezone.utc).isoformat()
        await close_giveaway(giveaway_id, winners_list, ended_at)
        giveaway["ended_at"] = ended_at
        channel = interaction.guild.get_channel(int(giveaway["channel_id"]))
        if isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(int(giveaway["message_id"]))
            except Exception:
                message = None
            embed = _build_embed(giveaway, len(entries), winners_list)
            if message:
                try:
                    await message.edit(embed=embed, view=None)
                except Exception:
                    pass
            winner_mentions = ", ".join([f"<@{w}>" for w in winners_list])
            await channel.send(f"Giveaway rerolled. Winners: {winner_mentions}")
        await interaction.response.send_message("Rerolled winners.", ephemeral=True)

    @giveaway_group.command(name="list", description="List open giveaways.")
    async def list_open(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "giveaway_enabled", interaction.user.id):
            await interaction.response.send_message("Giveaway module is disabled.", ephemeral=True)
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        open_giveaways = await list_open_giveaways(now_iso)
        if not open_giveaways:
            await interaction.response.send_message("No active giveaways.", ephemeral=True)
            return
        lines = []
        for g in open_giveaways[:10]:
            try:
                ends = _parse_iso(g["ends_at"])
                ends_text = _timestamp(ends)
            except Exception:
                ends_text = "Soon"
            lines.append(f"{g['id']} | {g['prize']} | ends {ends_text}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GiveawayCog(bot))
