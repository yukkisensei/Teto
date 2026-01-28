from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import FFMPEG_PATH, MUSIC_MAX_QUEUE, CACHE_TTL_MINUTES, CACHE_MAX_GB, MUSIC_QUALITY
from db import get_guild_config, list_music_cache, delete_music_cache, touch_music_cache
from utils.music_utils import Track, build_track_from_url, is_url
from utils.soundcloud_client import SoundCloudClient
from utils.guards import bot_ratio_exceeded, module_enabled, is_owner


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


@dataclass
class QueueItem:
    track: Track
    requester: int


class GuildPlayer:
    def __init__(self, bot: commands.Bot, guild_id: int) -> None:
        self.bot = bot
        self.guild_id = guild_id
        self.queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self.current: Optional[QueueItem] = None
        self.loop: bool = False
        self.voice: Optional[discord.VoiceClient] = None
        self._play_event = asyncio.Event()
        self.task = bot.loop.create_task(self.player_loop())
        self._ffmpeg_before_options = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"

    async def player_loop(self) -> None:
        while True:
            item = await self.queue.get()
            self.current = item
            if not self.voice or not self.voice.is_connected():
                self.current = None
                continue
            try:
                await touch_music_cache(item.track.video_id, MUSIC_QUALITY, datetime.now(timezone.utc).isoformat())
            except Exception:
                pass
            try:
                source = discord.FFmpegPCMAudio(
                    item.track.filepath,
                    executable=FFMPEG_PATH,
                    before_options=self._ffmpeg_before_options,
                    options="-vn",
                )
            except Exception as exc:
                logging.exception("Failed to create FFmpeg source: %s", exc)
                self.current = None
                continue
            self._play_event.clear()
            def _after_play(error: Optional[Exception]) -> None:
                if error:
                    logging.exception("Voice playback error: %s", error)
                self.bot.loop.call_soon_threadsafe(self._play_event.set)

            self.voice.play(source, after=_after_play)
            await self._play_event.wait()
            if self.loop and self.current:
                await self.queue.put(self.current)
            self.current = None

    async def ensure_voice(self, channel: discord.VoiceChannel) -> None:
        if self.voice and self.voice.is_connected():
            if self.voice.channel != channel:
                await self.voice.move_to(channel)
            return
        self.voice = await channel.connect()

    def stop(self) -> None:
        if self.voice and self.voice.is_playing():
            self.voice.stop()


class SoundCloudSelect(discord.ui.Select):
    def __init__(self, cog: "MusicCog", tracks: List[dict], requester_id: int) -> None:
        self.cog = cog
        self.tracks = tracks
        self.requester_id = requester_id
        options = []
        for idx, track in enumerate(tracks, start=1):
            title = (track.get("title") or "Untitled")[:100]
            user = track.get("user") or {}
            artist = (user.get("username") or "Unknown artist")[:100]
            options.append(
                discord.SelectOption(
                    label=f"{idx}. {title}",
                    description=artist,
                    value=str(idx - 1),
                )
            )
        super().__init__(
            placeholder="Pick a SoundCloud track...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"sc_pick:{requester_id}",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("Only the requester can pick.", ephemeral=True)
            return
        try:
            index = int(self.values[0])
        except Exception:
            await interaction.response.send_message("Invalid selection.", ephemeral=True)
            return
        if not (0 <= index < len(self.tracks)):
            await interaction.response.send_message("Invalid selection.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        await self.cog._queue_soundcloud_track(interaction, self.tracks[index])
        if isinstance(self.view, SoundCloudPickView):
            await self.view.disable_and_edit()


class SoundCloudPickView(discord.ui.View):
    def __init__(self, cog: "MusicCog", tracks: List[dict], requester_id: int) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.tracks = tracks
        self.requester_id = requester_id
        self.message: Optional[discord.Message] = None
        self.add_item(SoundCloudSelect(cog, tracks, requester_id))

    async def on_timeout(self) -> None:
        await self.disable_and_edit()

    async def disable_and_edit(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.players: Dict[int, GuildPlayer] = {}
        self.sc = SoundCloudClient()
        self.cache_cleanup.start()

    def get_player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer(self.bot, guild_id)
        return self.players[guild_id]

    async def cog_unload(self) -> None:
        self.cache_cleanup.cancel()

    @tasks.loop(minutes=30)
    async def cache_cleanup(self) -> None:
        cache_entries = await list_music_cache()
        if not cache_entries:
            return
        # Remove expired
        now = datetime.now(timezone.utc)
        to_delete: List[dict] = []
        for entry in cache_entries:
            last_played = _parse_iso(entry["last_played_at"])
            ttl_minutes = int(CACHE_TTL_MINUTES)
            if now - last_played > timedelta(minutes=ttl_minutes):
                to_delete.append(entry)
        for entry in to_delete:
            path = Path(entry["filepath"])
            if path.exists():
                try:
                    path.unlink()
                except Exception:
                    pass
            await delete_music_cache(entry["video_id"], entry["quality"])

        # Enforce size limit
        cache_entries = await list_music_cache()
        total_size = sum(int(e["size_bytes"]) for e in cache_entries)
        max_size = int(CACHE_MAX_GB * 1024 * 1024 * 1024)
        if total_size <= max_size:
            return
        sorted_entries = sorted(cache_entries, key=lambda e: e["last_played_at"])
        for entry in sorted_entries:
            if total_size <= max_size:
                break
            path = Path(entry["filepath"])
            size = int(entry["size_bytes"])
            if path.exists():
                try:
                    path.unlink()
                except Exception:
                    pass
            await delete_music_cache(entry["video_id"], entry["quality"])
            total_size -= size

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
        await interaction.response.defer(thinking=True, ephemeral=True)
        player = self.get_player(interaction.guild.id)
        await player.ensure_voice(interaction.user.voice.channel)
        await interaction.followup.send("Joined voice channel.", ephemeral=True)

    @app_commands.command(name="play", description="Play music from SoundCloud or a direct URL.")
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
        await interaction.response.defer(thinking=True)
        try:
            if is_url(query):
                host = urlparse(query).netloc.lower()
                is_soundcloud = "soundcloud.com" in host
            else:
                is_soundcloud = True
            if is_soundcloud and not is_url(query):
                if not self.sc.enabled():
                    await interaction.followup.send("SoundCloud is not configured.", ephemeral=True)
                    return
                results = await self.sc.search_tracks(query, limit=5)
                if not results:
                    await interaction.followup.send("No SoundCloud results found.", ephemeral=True)
                    return
                embed = discord.Embed(
                    title="SoundCloud results",
                    description=self._format_sc_results(results),
                    color=discord.Color.red(),
                )
                view = SoundCloudPickView(self, results, interaction.user.id)
                message = await interaction.followup.send(embed=embed, view=view, ephemeral=True, wait=True)
                view.message = message
                return

            if is_soundcloud:
                if not self.sc.enabled():
                    await interaction.followup.send("SoundCloud is not configured.", ephemeral=True)
                    return
                track_data = await self._get_soundcloud_track(query)
                await self._queue_soundcloud_track(interaction, track_data)
            else:
                await self._queue_direct_url(interaction, query)
        except Exception as exc:
            await interaction.followup.send(f"Failed to play: {exc}")

    @app_commands.command(name="playurl", description="Play music from a direct URL.")
    async def playurl(self, interaction: discord.Interaction, url: str) -> None:
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
        if not is_url(url):
            await interaction.response.send_message("Please provide a valid URL.", ephemeral=True)
            return
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            await self._queue_direct_url(interaction, url)
        except Exception as exc:
            await interaction.followup.send(f"Failed to play: {exc}")

    async def _get_soundcloud_track(self, query_or_url: str) -> dict:
        if is_url(query_or_url):
            return await self.sc.resolve_url(query_or_url)
        results = await self.sc.search_tracks(query_or_url, limit=1)
        if not results:
            raise RuntimeError("No SoundCloud results found")
        return results[0]

    async def _queue_direct_url(self, interaction: discord.Interaction, url: str) -> None:
        player = self.get_player(interaction.guild.id)
        await player.ensure_voice(interaction.user.voice.channel)
        if player.queue.qsize() >= MUSIC_MAX_QUEUE:
            await interaction.followup.send("Queue is full.", ephemeral=True)
            return
        track = build_track_from_url(url)
        await player.queue.put(QueueItem(track=track, requester=interaction.user.id))
        await interaction.followup.send(f"Queued: **{track.title}**")

    async def _queue_soundcloud_track(self, interaction: discord.Interaction, track_data: dict) -> None:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("Join a voice channel first.", ephemeral=True)
            return
        player = self.get_player(interaction.guild.id)
        await player.ensure_voice(interaction.user.voice.channel)
        if player.queue.qsize() >= MUSIC_MAX_QUEUE:
            await interaction.followup.send("Queue is full.", ephemeral=True)
            return
        track, meta = await self._build_soundcloud_track(track_data)
        await player.queue.put(QueueItem(track=track, requester=interaction.user.id))
        await interaction.followup.send(f"Queued: **{track.title}** — {meta}")

    def _format_sc_results(self, results: List[dict]) -> str:
        lines: List[str] = []
        for idx, track in enumerate(results, start=1):
            title = track.get("title") or "Untitled"
            user = track.get("user") or {}
            artist = user.get("username") or "Unknown artist"
            duration_ms = track.get("duration")
            duration = self._format_duration(duration_ms)
            lines.append(f"{idx}. **{title}** — {artist}{duration}")
        return "\n".join(lines)

    @staticmethod
    def _format_duration(duration_ms: Optional[int]) -> str:
        if not isinstance(duration_ms, (int, float)):
            return ""
        total_seconds = int(duration_ms // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        return f" ({minutes}:{seconds:02d})"

    async def _build_soundcloud_track(self, track_data: dict) -> tuple[Track, str]:
        access = track_data.get("access")
        if access and access not in ("playable", "preview"):
            raise RuntimeError("SoundCloud track is not playable")
        stream_url = await self.sc.resolve_stream_url(track_data)
        title = track_data.get("title") or "SoundCloud track"
        permalink = track_data.get("permalink_url") or ""
        user = track_data.get("user") or {}
        username = user.get("username") or "Unknown artist"
        duration_ms = track_data.get("duration")
        duration_sec = int(duration_ms / 1000) if isinstance(duration_ms, (int, float)) else None
        track = Track(
            title=title,
            url=permalink or stream_url,
            video_id=str(track_data.get("id") or track_data.get("urn") or permalink or title),
            filepath=stream_url,
            duration=duration_sec,
        )
        meta = f"{username} (SoundCloud)"
        if permalink:
            meta += f"\n{permalink}"
        return track, meta

    @app_commands.command(name="skip", description="Skip the current song.")
    async def skip(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = self.get_player(interaction.guild.id)
        player.stop()
        await interaction.response.send_message("Skipped.", ephemeral=True)

    @app_commands.command(name="pause", description="Pause playback.")
    async def pause(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = self.get_player(interaction.guild.id)
        if player.voice and player.voice.is_playing():
            player.voice.pause()
        await interaction.response.send_message("Paused.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume playback.")
    async def resume(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = self.get_player(interaction.guild.id)
        if player.voice and player.voice.is_paused():
            player.voice.resume()
        await interaction.response.send_message("Resumed.", ephemeral=True)

    @app_commands.command(name="stop", description="Stop playback and clear queue.")
    async def stop(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = self.get_player(interaction.guild.id)
        player.stop()
        while not player.queue.empty():
            try:
                player.queue.get_nowait()
            except Exception:
                break
        await interaction.response.send_message("Stopped and cleared queue.", ephemeral=True)

    @app_commands.command(name="leave", description="Disconnect from voice.")
    async def leave(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = self.get_player(interaction.guild.id)
        if player.voice and player.voice.is_connected():
            await player.voice.disconnect(force=True)
        await interaction.response.send_message("Disconnected.", ephemeral=True)

    @app_commands.command(name="queue", description="Show the queue.")
    async def queue(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = self.get_player(interaction.guild.id)
        items = list(player.queue._queue)  # noqa: SLF001
        if not items:
            await interaction.response.send_message("Queue is empty.", ephemeral=True)
            return
        lines = [f"{idx+1}. {item.track.title}" for idx, item in enumerate(items[:10])]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="nowplaying", description="Show current song.")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = self.get_player(interaction.guild.id)
        if not player.current:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await interaction.response.send_message(f"Now playing: **{player.current.track.title}**", ephemeral=True)

    @app_commands.command(name="loop", description="Toggle loop mode.")
    async def loop(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        player = self.get_player(interaction.guild.id)
        player.loop = not player.loop
        await interaction.response.send_message(f"Loop is now {'on' if player.loop else 'off'}.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
