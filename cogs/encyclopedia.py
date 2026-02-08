from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_VERSION


TETO_INFO = (
    "Kasane Teto is a popular UTAU character known for her red twin-drill hair "
    "and playful personality. She debuted in 2008 and became a fan-favorite vocal synth."
)

VOCALOID_TRIVIA = [
    "Vocaloid is a singing voice synthesizer software.",
    "UTAU is a free singing synthesizer created by Ameya/Ayame.",
    "Many fan-made voicebanks exist for both Vocaloid and UTAU.",
]

TETO_QUOTES = [
    "Let's sing together!",
    "Hehe, ready for another take?",
    "Teto time!",
]


class EncyclopediaCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="teto", description="Show info about Kasane Teto.")
    async def teto(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="Kasane Teto", description=TETO_INFO, color=discord.Color.red())
        embed.set_footer(text=f"version: {BOT_VERSION}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="vocaloid", description="Random Vocaloid trivia.")
    async def vocaloid(self, interaction: discord.Interaction) -> None:
        trivia = random.choice(VOCALOID_TRIVIA)
        await interaction.response.send_message(trivia, ephemeral=True)

    @app_commands.command(name="quote", description="Random Teto quote.")
    async def quote(self, interaction: discord.Interaction) -> None:
        quote = random.choice(TETO_QUOTES)
        await interaction.response.send_message(quote, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EncyclopediaCog(bot))
