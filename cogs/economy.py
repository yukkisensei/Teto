from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

import discord
from discord import app_commands
from discord.ext import commands

from config import DAILY_REWARD
from utils.guards import module_enabled
from db import (
    get_guild_config,
    get_balance,
    update_balance,
    get_daily_tasks,
    upsert_daily_task,
    claim_daily,
    add_user_item,
    get_user_items,
    upsert_user_profile,
    get_user_profile,
)


SHOP_ITEMS: Dict[str, Dict[str, str | int]] = {
    "teto_frame": {"name": "Teto Frame", "price": 500, "type": "frame"},
    "star_title": {"name": "Star Singer", "price": 300, "type": "title"},
    "fan_title": {"name": "Kasane Fan", "price": 300, "type": "title"},
}


def _date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="balance", description="Check your balance.")
    async def balance(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "economy_enabled", interaction.user.id):
            await interaction.response.send_message("Economy module is disabled.", ephemeral=True)
            return
        target = member or interaction.user
        balance, _ = await get_balance(interaction.guild.id, target.id)
        await interaction.response.send_message(f"{target.display_name} has {balance} coins.", ephemeral=True)

    @app_commands.command(name="daily", description="Claim daily rewards if tasks are done.")
    async def daily(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "economy_enabled", interaction.user.id):
            await interaction.response.send_message("Economy module is disabled.", ephemeral=True)
            return
        tasks = await get_daily_tasks(interaction.guild.id, interaction.user.id, _date_str())
        if not tasks:
            await upsert_daily_task(interaction.guild.id, interaction.user.id, _date_str(), "messages", 30, 0, 0)
            await upsert_daily_task(interaction.guild.id, interaction.user.id, _date_str(), "voice_minutes", 15, 0, 0)
            await upsert_daily_task(interaction.guild.id, interaction.user.id, _date_str(), "games", 2, 0, 0)
            tasks = await get_daily_tasks(interaction.guild.id, interaction.user.id, _date_str())
        all_done = all(t["progress"] >= t["target"] for t in tasks)
        already_claimed = all(t["claimed"] for t in tasks)
        if already_claimed:
            await interaction.response.send_message("Daily reward already claimed.", ephemeral=True)
            return
        if not all_done:
            lines = [f"{t['task_type']}: {t['progress']}/{t['target']}" for t in tasks]
            await interaction.response.send_message("Tasks not complete:\n" + "\n".join(lines), ephemeral=True)
            return
        await update_balance(interaction.guild.id, interaction.user.id, DAILY_REWARD)
        await claim_daily(interaction.guild.id, interaction.user.id, _date_str())
        await interaction.response.send_message(f"Daily reward claimed: {DAILY_REWARD} coins!", ephemeral=True)

    @app_commands.command(name="shop", description="Show the shop.")
    async def shop(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "economy_enabled", interaction.user.id):
            await interaction.response.send_message("Economy module is disabled.", ephemeral=True)
            return
        items = [f"{item_id} - {info['name']} ({info['price']} coins)" for item_id, info in SHOP_ITEMS.items()]
        await interaction.response.send_message("\n".join(items), ephemeral=True)

    @app_commands.command(name="buy", description="Buy an item from the shop.")
    async def buy(self, interaction: discord.Interaction, item_id: str) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "economy_enabled", interaction.user.id):
            await interaction.response.send_message("Economy module is disabled.", ephemeral=True)
            return
        if item_id not in SHOP_ITEMS:
            await interaction.response.send_message("Item not found.", ephemeral=True)
            return
        price = int(SHOP_ITEMS[item_id]["price"])
        balance, _ = await get_balance(interaction.guild.id, interaction.user.id)
        if balance < price:
            await interaction.response.send_message("Not enough coins.", ephemeral=True)
            return
        await update_balance(interaction.guild.id, interaction.user.id, -price)
        await add_user_item(interaction.guild.id, interaction.user.id, item_id, 1)
        await interaction.response.send_message(f"Purchased {SHOP_ITEMS[item_id]['name']}.", ephemeral=True)

    @app_commands.command(name="inventory", description="Show your items.")
    async def inventory(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "economy_enabled", interaction.user.id):
            await interaction.response.send_message("Economy module is disabled.", ephemeral=True)
            return
        items = await get_user_items(interaction.guild.id, interaction.user.id)
        if not items:
            await interaction.response.send_message("Inventory is empty.", ephemeral=True)
            return
        lines = [f"{i['item_id']} x{i['count']}" for i in items]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="settitle", description="Set a profile title you own.")
    async def settitle(self, interaction: discord.Interaction, item_id: str) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "economy_enabled", interaction.user.id):
            await interaction.response.send_message("Economy module is disabled.", ephemeral=True)
            return
        items = await get_user_items(interaction.guild.id, interaction.user.id)
        owned = {i["item_id"] for i in items}
        if item_id not in owned:
            await interaction.response.send_message("You don't own that item.", ephemeral=True)
            return
        item = SHOP_ITEMS.get(item_id)
        if not item or item.get("type") != "title":
            await interaction.response.send_message("That item is not a title.", ephemeral=True)
            return
        current = await get_user_profile(interaction.guild.id, interaction.user.id)
        await upsert_user_profile(interaction.guild.id, interaction.user.id, item["name"], current.get("frame"))
        await interaction.response.send_message(f"Title set to {item['name']}.", ephemeral=True)

    @app_commands.command(name="setframe", description="Set a profile frame you own.")
    async def setframe(self, interaction: discord.Interaction, item_id: str) -> None:
        if not interaction.guild:
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "economy_enabled", interaction.user.id):
            await interaction.response.send_message("Economy module is disabled.", ephemeral=True)
            return
        items = await get_user_items(interaction.guild.id, interaction.user.id)
        owned = {i["item_id"] for i in items}
        if item_id not in owned:
            await interaction.response.send_message("You don't own that item.", ephemeral=True)
            return
        item = SHOP_ITEMS.get(item_id)
        if not item or item.get("type") != "frame":
            await interaction.response.send_message("That item is not a frame.", ephemeral=True)
            return
        current = await get_user_profile(interaction.guild.id, interaction.user.id)
        await upsert_user_profile(interaction.guild.id, interaction.user.id, current.get("title"), item["name"])
        await interaction.response.send_message(f"Frame set to {item['name']}.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EconomyCog(bot))
