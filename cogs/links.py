from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


TETO_CODE_URL = "https://github.com/yukkisensei/Teto"
TETOREA_URL = "https://discord.gg/35P2xNnemF"


class LinksCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="links", description="Show official Teto links.")
    async def links(self, interaction: discord.Interaction) -> None:
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Visit Teto code", url=TETO_CODE_URL))
        view.add_item(discord.ui.Button(label="Visit South Tetorea", url=TETOREA_URL))
        embed = discord.Embed(
            title="Teto Links",
            description="Useful links for Teto.",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LinksCog(bot))
