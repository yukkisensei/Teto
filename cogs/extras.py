from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands


class ExtrasCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.started_at = datetime.now(timezone.utc)

    @app_commands.command(name="ping", description="Check bot latency.")
    async def ping(self, interaction: discord.Interaction) -> None:
        ms = int(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong {ms}ms", ephemeral=True)

    @app_commands.command(name="avatar", description="Show a user's avatar.")
    async def avatar(self, interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        target = member or interaction.user
        if not target:
            return
        embed = discord.Embed(title=f"Avatar for {target}", color=discord.Color.red())
        embed.set_image(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="serverinfo", description="Show server info.")
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        guild = interaction.guild
        owner = guild.owner
        embed = discord.Embed(title=guild.name, color=discord.Color.red())
        embed.add_field(name="Server ID", value=str(guild.id), inline=True)
        embed.add_field(name="Members", value=str(guild.member_count or 0), inline=True)
        embed.add_field(name="Owner", value=str(owner) if owner else "Unknown", inline=True)
        embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Boosts", value=str(guild.premium_subscription_count or 0), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="userinfo", description="Show user info.")
    async def userinfo(self, interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        if not interaction.guild:
            return
        target = member or interaction.user
        if not isinstance(target, discord.Member):
            return
        embed = discord.Embed(title=str(target), color=discord.Color.red())
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="User ID", value=str(target.id), inline=True)
        embed.add_field(name="Joined", value=target.joined_at.strftime("%Y-%m-%d") if target.joined_at else "Unknown", inline=True)
        embed.add_field(name="Created", value=target.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Roles", value=str(len(target.roles)), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="uptime", description="Show bot uptime.")
    async def uptime(self, interaction: discord.Interaction) -> None:
        delta = datetime.now(timezone.utc) - self.started_at
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        await interaction.response.send_message(
            f"Uptime {days}d {hours}h {minutes}m {seconds}s",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ExtrasCog(bot))
