from __future__ import annotations

import random
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from config import FISH_REWARD, POKEMON_REWARD
from db import (
    add_inventory_item,
    add_pokemon,
    update_balance,
    get_guild_config,
    update_daily_progress,
    get_daily_tasks,
    upsert_daily_task,
)
from utils.guards import bot_ratio_exceeded, module_enabled


FISH_ITEMS = ["Tiny Fish", "Golden Fish", "Old Boot", "Mystic Koi", "Teto Bass"]
POKEMON_LIST = ["Pikachu", "Eevee", "Bulbasaur", "Charmander", "Squirtle", "Jigglypuff"]
TRIVIA = [
    ("What is Kasane Teto's signature instrument?", "UTAU"),
    ("Which year was Kasane Teto first released?", "2008"),
    ("What color is Kasane Teto's hair?", "Red"),
]
TYPING_PHRASES = [
    "Kasane Teto is the cutest!",
    "Red hair, twin drills, unstoppable!",
    "UTAU vibes, Teto time!",
]


class GamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _ensure_daily_tasks(self, guild_id: int, user_id: int) -> None:
        date = datetime.utcnow().strftime("%Y-%m-%d")
        tasks = await get_daily_tasks(guild_id, user_id, date)
        if tasks:
            return
        await upsert_daily_task(guild_id, user_id, date, "messages", 30, 0, 0)
        await upsert_daily_task(guild_id, user_id, date, "voice_minutes", 15, 0, 0)
        await upsert_daily_task(guild_id, user_id, date, "games", 2, 0, 0)

    async def _module_ok(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "games_enabled", interaction.user.id):
            await interaction.response.send_message("Games module is disabled.", ephemeral=True)
            return False
        if bot_ratio_exceeded(interaction.guild, cfg, interaction.user.id):
            await interaction.response.send_message("Games are disabled due to bot ratio guard.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="fish", description="Go fishing.")
    async def fish(self, interaction: discord.Interaction) -> None:
        if not await self._module_ok(interaction):
            return
        await self._ensure_daily_tasks(interaction.guild.id, interaction.user.id)
        item = random.choice(FISH_ITEMS)
        await add_inventory_item(interaction.guild.id, interaction.user.id, item, 1)
        await update_balance(interaction.guild.id, interaction.user.id, FISH_REWARD)
        await update_daily_progress(interaction.guild.id, interaction.user.id, datetime.utcnow().strftime("%Y-%m-%d"), "games", 1)
        await interaction.response.send_message(f"You caught **{item}** and earned {FISH_REWARD} coins!", ephemeral=True)

    @app_commands.command(name="pokemon", description="Catch a random Pokémon.")
    async def pokemon(self, interaction: discord.Interaction) -> None:
        if not await self._module_ok(interaction):
            return
        await self._ensure_daily_tasks(interaction.guild.id, interaction.user.id)
        poke = random.choice(POKEMON_LIST)
        await add_pokemon(interaction.guild.id, interaction.user.id, poke, 1)
        await update_balance(interaction.guild.id, interaction.user.id, POKEMON_REWARD)
        await update_daily_progress(interaction.guild.id, interaction.user.id, datetime.utcnow().strftime("%Y-%m-%d"), "games", 1)
        await interaction.response.send_message(f"You caught **{poke}** and earned {POKEMON_REWARD} coins!", ephemeral=True)

    @app_commands.command(name="quiz", description="Answer a Vocaloid trivia question.")
    async def quiz(self, interaction: discord.Interaction) -> None:
        if not await self._module_ok(interaction):
            return
        question, answer = random.choice(TRIVIA)
        await interaction.response.send_message(f"Trivia: **{question}** (You have 15s)")

        def check(msg: discord.Message) -> bool:
            return msg.author == interaction.user and msg.channel == interaction.channel

        try:
            msg = await self.bot.wait_for("message", timeout=15.0, check=check)
        except Exception:
            await interaction.followup.send(f"Time's up! Answer: **{answer}**")
            return
        if msg.content.strip().lower() == answer.lower():
            await update_balance(interaction.guild.id, interaction.user.id, 50)
            await interaction.followup.send("Correct! +50 coins.")
        else:
            await interaction.followup.send(f"Wrong! Answer: **{answer}**")

    @app_commands.command(name="typing", description="Typing speed mini-game.")
    async def typing(self, interaction: discord.Interaction) -> None:
        if not await self._module_ok(interaction):
            return
        phrase = random.choice(TYPING_PHRASES)
        await interaction.response.send_message(f"Type this within 20s:\n`{phrase}`")

        def check(msg: discord.Message) -> bool:
            return msg.author == interaction.user and msg.channel == interaction.channel and msg.content.strip() == phrase

        try:
            await self.bot.wait_for("message", timeout=20.0, check=check)
        except Exception:
            await interaction.followup.send("No win this time!")
            return
        await update_balance(interaction.guild.id, interaction.user.id, 40)
        await interaction.followup.send("Nice typing! +40 coins.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GamesCog(bot))
