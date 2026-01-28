from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from db import (
    get_guild_config,
    create_reminder,
    get_due_reminders,
    delete_reminder,
    set_birthday,
    list_birthdays_for_date,
    create_event,
    list_upcoming_events,
    delete_event,
)
from utils.time_utils import parse_duration, format_duration
from utils.checks import is_moderator
from utils.guards import module_enabled


class UtilityCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.reminder_loop.start()
        self.birthday_loop.start()
        self._last_birthday_date: Optional[str] = None

    async def cog_unload(self) -> None:
        self.reminder_loop.cancel()
        self.birthday_loop.cancel()

    @tasks.loop(seconds=30)
    async def reminder_loop(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        due = await get_due_reminders(now_iso)
        for reminder in due:
            channel = self.bot.get_channel(int(reminder["channel_id"]))
            if not isinstance(channel, discord.TextChannel):
                await delete_reminder(reminder["id"])
                continue
            try:
                await channel.send(f"<@{reminder['user_id']}> Reminder: {reminder['message']}")
            except Exception:
                pass
            await delete_reminder(reminder["id"])

    @tasks.loop(minutes=60)
    async def birthday_loop(self) -> None:
        today = datetime.now(timezone.utc).strftime("%m-%d")
        if self._last_birthday_date == today:
            return
        self._last_birthday_date = today
        month = int(today.split("-")[0])
        day = int(today.split("-")[1])
        for guild in self.bot.guilds:
            cfg = await get_guild_config(guild.id)
            channel_id = cfg.get("welcome_channel_id") or cfg.get("log_channel_id")
            if not channel_id:
                continue
            channel = guild.get_channel(int(channel_id))
            if not isinstance(channel, discord.TextChannel):
                continue
            users = await list_birthdays_for_date(guild.id, month, day)
            for user_id in users:
                await channel.send(f"Happy birthday <@{user_id}>! 🎉")

    @app_commands.command(name="remind", description="Set a reminder (e.g. 10m, 2h, 1d).")
    async def remind(self, interaction: discord.Interaction, duration: str, message: str) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "reminders_enabled", interaction.user.id):
            await interaction.response.send_message("Reminders are disabled.", ephemeral=True)
            return
        try:
            seconds = parse_duration(duration)
        except Exception:
            await interaction.response.send_message("Invalid duration.", ephemeral=True)
            return
        remind_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        await create_reminder(interaction.user.id, interaction.guild.id, interaction.channel_id, message, remind_at.isoformat())
        await interaction.response.send_message(f"Reminder set for {format_duration(seconds)}.", ephemeral=True)

    @app_commands.command(name="birthday", description="Set your birthday (MM-DD).")
    async def birthday(self, interaction: discord.Interaction, date: str) -> None:
        if not interaction.guild:
            return
        try:
            month, day = date.split("-")
            month_i = int(month)
            day_i = int(day)
        except Exception:
            await interaction.response.send_message("Use MM-DD format.", ephemeral=True)
            return
        await set_birthday(interaction.guild.id, interaction.user.id, month_i, day_i)
        await interaction.response.send_message("Birthday saved.", ephemeral=True)

    @app_commands.command(name="event_create", description="Create an event (YYYY-MM-DD HH:MM UTC).")
    async def event_create(self, interaction: discord.Interaction, name: str, when: str) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "reminders_enabled", interaction.user.id):
            await interaction.response.send_message("Events are disabled.", ephemeral=True)
            return
        if not isinstance(interaction.user, discord.Member) or not await is_moderator(interaction.user):
            await interaction.response.send_message("No permission.", ephemeral=True)
            return
        try:
            event_time = datetime.strptime(when, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except Exception:
            await interaction.response.send_message("Invalid date format.", ephemeral=True)
            return
        event_id = await create_event(interaction.guild.id, interaction.channel_id, name, event_time.isoformat(), interaction.user.id)
        await interaction.response.send_message(f"Event created with ID {event_id}.", ephemeral=True)

    @app_commands.command(name="event_list", description="List upcoming events.")
    async def event_list(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "reminders_enabled", interaction.user.id):
            await interaction.response.send_message("Events are disabled.", ephemeral=True)
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        events = await list_upcoming_events(interaction.guild.id, now_iso, 10)
        if not events:
            await interaction.response.send_message("No upcoming events.", ephemeral=True)
            return
        lines = [f"{e['id']} - {e['name']} at {e['event_time']}" for e in events]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="event_delete", description="Delete an event by ID.")
    async def event_delete(self, interaction: discord.Interaction, event_id: int) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "reminders_enabled", interaction.user.id):
            await interaction.response.send_message("Events are disabled.", ephemeral=True)
            return
        if not isinstance(interaction.user, discord.Member) or not await is_moderator(interaction.user):
            await interaction.response.send_message("No permission.", ephemeral=True)
            return
        await delete_event(event_id)
        await interaction.response.send_message("Event deleted.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UtilityCog(bot))
