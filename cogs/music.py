from __future__ import annotations

import inspect
import logging
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands
import wavelink

from config import LAVALINK_HOST, LAVALINK_PORT, LAVALINK_PASSWORD, LAVALINK_SECURE, MUSIC_MAX_QUEUE
from db import get_guild_config
from utils.guards import bot_ratio_exceeded, module_enabled, is_owner


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.loop_enabled: dict[int, bool] = {}
        self.node_ready = False

    async def cog_load(self) -> None:
        await self._connect_lavalink()

    async def _connect_lavalink(self) -> None:
        if self.node_ready:
            return
        uri = f"{'https' if LAVALINK_SECURE else 'http'}://{LAVALINK_HOST}:{LAVALINK_PORT}"
        connected = False
        if hasattr(wavelink, "Pool") and hasattr(wavelink, "Node"):
            try:
                node = wavelink.Node(uri=uri, password=LAVALINK_PASSWORD)
                await wavelink.Pool.connect(client=self.bot, nodes=[node])
                connected = True
            except Exception as exc:
                logging.exception("Lavalink pool connection failed: %s", exc)
        if not connected and hasattr(wavelink, "NodePool"):
            try:
                await wavelink.NodePool.create_node(
                    bot=self.bot,
                    host=LAVALINK_HOST,
                    port=LAVALINK_PORT,
                    password=LAVALINK_PASSWORD,
                    https=LAVALINK_SECURE,
                )
                connected = True
            except Exception as exc:
                logging.exception("Lavalink node connection failed: %s", exc)
        self.node_ready = connected

    def _queue_size(self, player: wavelink.Player) -> int:
        queue = getattr(player, "queue", None)
        if queue is None:
            return 0
        try:
            return len(queue)
        except Exception:
            count = getattr(queue, "count", None)
            if isinstance(count, int):
                return count
        return 0

    def _queue_items(self, player: wavelink.Player) -> List[wavelink.Playable]:
        queue = getattr(player, "queue", None)
        if queue is None:
            return []
        try:
            return list(queue)
        except Exception:
            inner = getattr(queue, "_queue", None)
            if inner:
                try:
                    return list(inner)
                except Exception:
                    return []
        return []

    async def _queue_get(self, player: wavelink.Player) -> Optional[wavelink.Playable]:
        queue = getattr(player, "queue", None)
        if queue is None:
            return None
        getter = getattr(queue, "get", None)
        if getter is None:
            return None
        result = getter()
        if inspect.isawaitable(result):
            return await result
        return result

    def _queue_put(self, player: wavelink.Player, track: wavelink.Playable) -> None:
        queue = getattr(player, "queue", None)
        if queue is None:
            return
        putter = getattr(queue, "put", None)
        if putter:
            putter(track)
            return
        put_nowait = getattr(queue, "put_nowait", None)
        if put_nowait:
            put_nowait(track)

    async def _maybe_await(self, value: object) -> None:
        if inspect.isawaitable(value):
            await value

    def _is_playing(self, player: wavelink.Player) -> bool:
        playing = getattr(player, "playing", None)
        if isinstance(playing, bool):
            return playing
        is_playing = getattr(player, "is_playing", None)
        if callable(is_playing):
            try:
                return bool(is_playing())
            except Exception:
                return False
        return False

    def _is_paused(self, player: wavelink.Player) -> bool:
        paused = getattr(player, "paused", None)
        if isinstance(paused, bool):
            return paused
        is_paused = getattr(player, "is_paused", None)
        if callable(is_paused):
            try:
                return bool(is_paused())
            except Exception:
                return False
        return False

    async def _ensure_player(self, interaction: discord.Interaction) -> Optional[wavelink.Player]:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return None
        voice_state = interaction.user.voice
        if not voice_state or not voice_state.channel:
            return None
        existing = interaction.guild.voice_client
        if existing and isinstance(existing, wavelink.Player):
            if existing.channel != voice_state.channel:
                mover = getattr(existing, "move_to", None)
                if mover:
                    await self._maybe_await(mover(voice_state.channel))
            return existing
        return await voice_state.channel.connect(cls=wavelink.Player)

    async def _search(self, query: str) -> tuple[Optional[wavelink.Playlist], List[wavelink.Playable]]:
        try:
            if hasattr(wavelink, "Playable"):
                results = await wavelink.Playable.search(query)
            elif hasattr(wavelink, "YouTubeTrack"):
                results = await wavelink.YouTubeTrack.search(query=query)
            else:
                results = []
        except Exception as exc:
            logging.exception("Search failed: %s", exc)
            return None, []
        if hasattr(wavelink, "Playlist") and isinstance(results, wavelink.Playlist):
            return results, list(results.tracks)
        if isinstance(results, list):
            return None, results
        try:
            return None, list(results)
        except Exception:
            return None, []

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: object) -> None:
        player = getattr(payload, "player", None)
        track = getattr(payload, "track", None)
        if not isinstance(player, wavelink.Player):
            return
        guild = getattr(player, "guild", None)
        if not guild:
            return
        if self.loop_enabled.get(guild.id) and track is not None:
            await self._maybe_await(player.play(track))
            return
        next_track = await self._queue_get(player)
        if next_track is None:
            return
        await self._maybe_await(player.play(next_track))

    @app_commands.command(name="join", description="Join your voice channel.")
    async def join(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "music_enabled", interaction.user.id):
            await interaction.response.send_message("Music module is disabled.", ephemeral=True)
            return
        if bot_ratio_exceeded(interaction.guild, cfg, interaction.user.id):
            await interaction.response.send_message("Music is disabled due to bot ratio guard.", ephemeral=True)
            return
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
            return
        if not self.node_ready:
            await self._connect_lavalink()
        if not self.node_ready:
            await interaction.response.send_message("Lavalink is not connected.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        player = await self._ensure_player(interaction)
        if not player:
            await interaction.followup.send("Failed to connect to voice.", ephemeral=True)
            return
        await interaction.followup.send("Joined voice channel.", ephemeral=True)

    @app_commands.command(name="play", description="Play music using Lavalink search or URL.")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        cfg = await get_guild_config(interaction.guild.id)
        if not module_enabled(cfg, "music_enabled", interaction.user.id):
            await interaction.response.send_message("Music module is disabled.", ephemeral=True)
            return
        if bot_ratio_exceeded(interaction.guild, cfg, interaction.user.id):
            await interaction.response.send_message("Music is disabled due to bot ratio guard.", ephemeral=True)
            return
        channel_id = cfg.get("music_channel_id")
        if channel_id and interaction.channel_id != int(channel_id) and not is_owner(interaction.user.id):
            await interaction.response.send_message("Use the configured music channel.", ephemeral=True)
            return
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
            return
        if not self.node_ready:
            await self._connect_lavalink()
        if not self.node_ready:
            await interaction.response.send_message("Lavalink is not connected.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        player = await self._ensure_player(interaction)
        if not player:
            await interaction.followup.send("Failed to connect to voice.")
            return
        playlist, tracks = await self._search(query)
        if not tracks:
            await interaction.followup.send("No results found.", ephemeral=True)
            return
        available = MUSIC_MAX_QUEUE - self._queue_size(player)
        if available <= 0:
            await interaction.followup.send("Queue is full.", ephemeral=True)
            return
        added = 0
        if playlist:
            for track in tracks[:available]:
                self._queue_put(player, track)
                added += 1
            if not self._is_playing(player):
                next_track = await self._queue_get(player)
                if next_track:
                    await self._maybe_await(player.play(next_track))
            await interaction.followup.send(f"Queued playlist {playlist.name} with {added} tracks.")
            return
        track = tracks[0]
        self._queue_put(player, track)
        if not self._is_playing(player):
            next_track = await self._queue_get(player)
            if next_track:
                await self._maybe_await(player.play(next_track))
        await interaction.followup.send(f"Queued: {track.title}")

    @app_commands.command(name="playurl", description="Play music from a direct URL.")
    async def playurl(self, interaction: discord.Interaction, url: str) -> None:
        await self.play(interaction, url)

    @app_commands.command(name="skip", description="Skip the current song.")
    async def skip(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = interaction.guild.voice_client
        if not isinstance(player, wavelink.Player):
            await interaction.response.send_message("Not connected.", ephemeral=True)
            return
        await self._maybe_await(player.stop())
        await interaction.response.send_message("Skipped.", ephemeral=True)

    @app_commands.command(name="pause", description="Pause playback.")
    async def pause(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = interaction.guild.voice_client
        if not isinstance(player, wavelink.Player):
            await interaction.response.send_message("Not connected.", ephemeral=True)
            return
        if not self._is_playing(player):
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        pause_method = getattr(player, "pause", None)
        if pause_method:
            await self._maybe_await(pause_method())
        await interaction.response.send_message("Paused.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume playback.")
    async def resume(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = interaction.guild.voice_client
        if not isinstance(player, wavelink.Player):
            await interaction.response.send_message("Not connected.", ephemeral=True)
            return
        if not self._is_paused(player):
            await interaction.response.send_message("Nothing is paused.", ephemeral=True)
            return
        resume_method = getattr(player, "resume", None)
        if resume_method:
            await self._maybe_await(resume_method())
        else:
            pause_method = getattr(player, "pause", None)
            if pause_method:
                try:
                    await self._maybe_await(pause_method(False))
                except Exception:
                    await self._maybe_await(pause_method())
        await interaction.response.send_message("Resumed.", ephemeral=True)

    @app_commands.command(name="stop", description="Stop playback and clear queue.")
    async def stop(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = interaction.guild.voice_client
        if not isinstance(player, wavelink.Player):
            await interaction.response.send_message("Not connected.", ephemeral=True)
            return
        await self._maybe_await(player.stop())
        queue = getattr(player, "queue", None)
        if queue is not None:
            clearer = getattr(queue, "clear", None)
            if clearer:
                clearer()
            else:
                for _ in range(self._queue_size(player)):
                    _ = await self._queue_get(player)
        await interaction.response.send_message("Stopped and cleared queue.", ephemeral=True)

    @app_commands.command(name="leave", description="Disconnect from voice.")
    async def leave(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = interaction.guild.voice_client
        if not isinstance(player, wavelink.Player):
            await interaction.response.send_message("Not connected.", ephemeral=True)
            return
        await self._maybe_await(player.disconnect())
        await interaction.response.send_message("Disconnected.", ephemeral=True)

    @app_commands.command(name="queue", description="Show the queue.")
    async def queue(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = interaction.guild.voice_client
        if not isinstance(player, wavelink.Player):
            await interaction.response.send_message("Not connected.", ephemeral=True)
            return
        items = self._queue_items(player)
        if not items:
            await interaction.response.send_message("Queue is empty.", ephemeral=True)
            return
        lines = [f"{idx + 1}. {track.title}" for idx, track in enumerate(items[:10])]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="nowplaying", description="Show current song.")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = interaction.guild.voice_client
        if not isinstance(player, wavelink.Player):
            await interaction.response.send_message("Not connected.", ephemeral=True)
            return
        current = getattr(player, "current", None)
        if not current:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await interaction.response.send_message(f"Now playing: {current.title}", ephemeral=True)

    @app_commands.command(name="loop", description="Toggle loop mode.")
    async def loop(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        enabled = not self.loop_enabled.get(interaction.guild.id, False)
        self.loop_enabled[interaction.guild.id] = enabled
        await interaction.response.send_message(f"Loop is now {'on' if enabled else 'off'}.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
