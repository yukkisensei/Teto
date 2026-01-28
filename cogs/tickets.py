from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from config import TICKET_CATEGORY_NAME
from db import create_ticket, close_ticket, get_guild_config
from utils.checks import is_moderator
from utils.guards import module_enabled


class TicketModal(discord.ui.Modal, title="Support Ticket"):
    issue = discord.ui.TextInput(label="Describe your issue", style=discord.TextStyle.paragraph, max_length=1000)

    def __init__(self, bot: commands.Bot, interaction: discord.Interaction) -> None:
        super().__init__()
        self.bot = bot
        self.interaction = interaction

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not guild:
            return
        cfg = await get_guild_config(guild.id)
        if not module_enabled(cfg, "tickets_enabled", interaction.user.id):
            await interaction.response.send_message("Tickets are disabled.", ephemeral=True)
            return
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(TICKET_CATEGORY_NAME)
        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}".lower(),
            category=category,
            topic=f"Ticket by {interaction.user.id}",
        )
        await channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
        mod_role_id = cfg.get("mod_role_id")
        if mod_role_id:
            role = guild.get_role(int(mod_role_id))
            if role:
                await channel.set_permissions(role, read_messages=True, send_messages=True)
        await create_ticket(guild.id, channel.id, interaction.user.id)
        await channel.send(f"New ticket from {interaction.user.mention}\nIssue: {self.issue.value}")
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)


class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ticket", description="Open a support ticket.")
    async def ticket(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "tickets_enabled", interaction.user.id):
            await interaction.response.send_message("Tickets are disabled.", ephemeral=True)
            return
        modal = TicketModal(self.bot, interaction)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="ticket_close", description="Close the current ticket.")
    async def ticket_close(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        if not await is_moderator(interaction.user):
            await interaction.response.send_message("No permission.", ephemeral=True)
            return
        await close_ticket(interaction.channel_id)
        await interaction.response.send_message("Ticket closed.", ephemeral=True)
        try:
            await interaction.channel.delete()
        except Exception:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TicketsCog(bot))
