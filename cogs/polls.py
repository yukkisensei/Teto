from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import List

import discord
from discord import app_commands
from discord.ext import commands, tasks

from db import (
    create_poll,
    get_poll,
    vote_poll,
    get_poll_counts,
    list_due_polls,
    list_open_polls,
    delete_poll,
    get_guild_config,
)
from utils.guards import module_enabled


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_options(raw: str) -> List[str]:
    return [opt.strip() for opt in raw.split("|") if opt.strip()]


class PollButton(discord.ui.Button):
    def __init__(self, poll_id: int, index: int, label: str) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"poll:{poll_id}:{index}")
        self.poll_id = poll_id
        self.index = index

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        poll = await get_poll(self.poll_id)
        if not poll:
            await interaction.response.send_message("Poll not found.", ephemeral=True)
            return
        await vote_poll(self.poll_id, interaction.user.id, self.index)
        options = json.loads(poll["options_json"])
        counts = await get_poll_counts(self.poll_id, len(options))
        embed = render_poll_embed(poll["question"], options, counts, poll["anonymous"])
        try:
            await interaction.message.edit(embed=embed, view=self.view)
        except Exception:
            pass
        await interaction.response.send_message("Vote recorded.", ephemeral=True)


class PollView(discord.ui.View):
    def __init__(self, poll_id: int, options: List[str]) -> None:
        super().__init__(timeout=None)
        for idx, opt in enumerate(options):
            self.add_item(PollButton(poll_id, idx, opt))


def render_poll_embed(question: str, options: List[str], counts: List[int], anonymous: int) -> discord.Embed:
    embed = discord.Embed(title=question, color=discord.Color.red())
    lines = []
    for idx, opt in enumerate(options):
        count = counts[idx] if idx < len(counts) else 0
        lines.append(f"{idx+1}. {opt} — {count} votes")
    embed.description = "\n".join(lines)
    if anonymous:
        embed.set_footer(text="Anonymous poll")
    return embed


class PollsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.poll_loop.start()

    async def cog_load(self) -> None:
        polls = await list_open_polls(_utcnow())
        for poll in polls:
            options = json.loads(poll["options_json"])
            view = PollView(poll["id"], options)
            self.bot.add_view(view)

    async def cog_unload(self) -> None:
        self.poll_loop.cancel()

    @tasks.loop(seconds=30)
    async def poll_loop(self) -> None:
        due = await list_due_polls(_utcnow())
        for poll in due:
            channel = self.bot.get_channel(int(poll["channel_id"]))
            if not isinstance(channel, discord.TextChannel):
                await delete_poll(poll["id"])
                continue
            try:
                message = await channel.fetch_message(int(poll["message_id"]))
            except Exception:
                await delete_poll(poll["id"])
                continue
            options = json.loads(poll["options_json"])
            counts = await get_poll_counts(poll["id"], len(options))
            embed = render_poll_embed(poll["question"], options, counts, poll["anonymous"])
            embed.set_footer(text="Poll closed")
            await message.edit(embed=embed, view=None)
            await delete_poll(poll["id"])

    @app_commands.command(name="poll", description="Create a poll.")
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        options: str,
        duration_minutes: int | None = None,
        anonymous: bool = False,
    ) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "polls_enabled", interaction.user.id):
            await interaction.response.send_message("Polls are disabled.", ephemeral=True)
            return
        opts = _parse_options(options)
        if len(opts) < 2:
            await interaction.response.send_message("Provide at least 2 options separated by `|`.", ephemeral=True)
            return
        if len(opts) > 5:
            await interaction.response.send_message("Maximum 5 options supported.", ephemeral=True)
            return
        ends_at = None
        if duration_minutes and duration_minutes > 0:
            ends_at = (datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)).isoformat()
        embed = render_poll_embed(question, opts, [0] * len(opts), 1 if anonymous else 0)
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        poll_id = await create_poll(
            interaction.guild.id,
            interaction.channel_id,
            message.id,
            question,
            json.dumps(opts),
            1 if anonymous else 0,
            ends_at,
            interaction.user.id,
        )
        view = PollView(poll_id, opts)
        await message.edit(view=view)
        self.bot.add_view(view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PollsCog(bot))
