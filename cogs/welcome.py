from __future__ import annotations

import discord
from discord.ext import commands

from db import get_guild_config


class WelcomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = await get_guild_config(member.guild.id)
        if not cfg.get("welcome_enabled"):
            return
        channel_id = cfg.get("welcome_channel_id")
        if not channel_id:
            return
        channel = member.guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return
        msg = (cfg.get("welcome_message") or "Welcome {user} to {server}!").format(
            user=member.mention, server=member.guild.name
        )
        await channel.send(msg)

        auto_role_id = cfg.get("auto_role_id")
        if auto_role_id:
            role = member.guild.get_role(int(auto_role_id))
            if role:
                try:
                    await member.add_roles(role, reason="Auto role")
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        cfg = await get_guild_config(member.guild.id)
        if not cfg.get("goodbye_enabled"):
            return
        channel_id = cfg.get("goodbye_channel_id")
        if not channel_id:
            return
        channel = member.guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return
        msg = (cfg.get("goodbye_message") or "Goodbye {user}.").format(
            user=member.name, server=member.guild.name
        )
        await channel.send(msg)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.premium_since == after.premium_since or after.premium_since is None:
            return
        cfg = await get_guild_config(after.guild.id)
        if not cfg.get("boost_enabled"):
            return
        channel_id = cfg.get("welcome_channel_id") or cfg.get("log_channel_id")
        if not channel_id:
            return
        channel = after.guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return
        msg = (cfg.get("boost_message") or "Thanks for boosting the server, {user}!").format(
            user=after.mention, server=after.guild.name
        )
        await channel.send(msg)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
