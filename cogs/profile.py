from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from db import get_balance, get_leveling, get_badges, get_user_profile, get_user_items


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="profile", description="Show a user's profile card.")
    async def profile(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        if not interaction.guild:
            return
        target = member or interaction.user
        balance, _ = await get_balance(interaction.guild.id, target.id)
        leveling = await get_leveling(interaction.guild.id, target.id)
        badges = await get_badges(interaction.guild.id, target.id)
        profile = await get_user_profile(interaction.guild.id, target.id)
        items = await get_user_items(interaction.guild.id, target.id)
        embed = discord.Embed(title=f"{target.display_name}'s Profile", color=discord.Color.red())
        if profile.get("title"):
            embed.description = f"**Title:** {profile['title']}"
        if profile.get("frame"):
            embed.add_field(name="Frame", value=profile["frame"], inline=True)
        embed.add_field(name="Level", value=str(leveling["level"]), inline=True)
        embed.add_field(name="XP", value=str(leveling["xp"]), inline=True)
        embed.add_field(name="Coins", value=str(balance), inline=True)
        embed.add_field(name="Messages", value=str(leveling["message_count"]), inline=True)
        embed.add_field(name="Voice (min)", value=str(leveling["voice_seconds"] // 60), inline=True)
        embed.add_field(name="Badges", value=", ".join(badges) if badges else "None", inline=False)
        embed.add_field(name="Items", value=", ".join([i["item_id"] for i in items]) if items else "None", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfileCog(bot))
