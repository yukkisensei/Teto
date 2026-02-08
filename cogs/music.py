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


def _clamp_text(value: str, size: int = 100) -> str:
    if len(value) <= size:
        return value
    return value[: size - 3] + "..."


def _format_track_length(length_ms: object) -> str:
    if not isinstance(length_ms, int) or length_ms <= 0:
        return "Live"
    total_seconds = length_ms // 1000
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class TrackPicker(discord.ui.Select):
    def __init__(self, view: "TrackPickerView") -> None:
        options: list[discord.SelectOption] = []
        for idx, track in enumerate(view.tracks):
            title = _clamp_text(getattr(track, "title", "Unknown title"), 100)
            author = getattr(track, "author", None) or "Unknown artist"
            length = _format_track_length(getattr(track, "length", None))
            description = _clamp_text(f"{author} - {length}", 100)
            options.append(discord.SelectOption(label=title, description=description, value=str(idx)))
        super().__init__(placeholder="Select a track to play", min_values=1, max_values=1, options=options)
        self.picker_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.picker_view.cog._queue_size(self.picker_view.player) >= MUSIC_MAX_QUEUE:
            await interaction.response.edit_message(content="Queue is full.", view=None)
            self.picker_view.stop()
            return
        index = int(self.values[0])
        track = self.picker_view.tracks[index]
        await self.picker_view.cog._queue_track(self.picker_view.player, track)
        await interaction.response.edit_message(content=f"Queued: {track.title}", view=None)
        self.picker_view.stop()


class TrackPickerView(discord.ui.View):
    def __init__(
        self,
        cog: "MusicCog",
        player: wavelink.Player,
        tracks: list[wavelink.Playable],
        requester_id: int,
    ) -> None:
        super().__init__(timeout=45)
        self.cog = cog
        self.player = player
        self.tracks = tracks
        self.requester_id = requester_id
        self.message: Optional[discord.Message] = None
        self.add_item(TrackPicker(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message("Only the command user can choose a track.", ephemeral=True)
        return False

    async def on_timeout(self) -> None:
        if self.message is None:
            return
        try:
            await self.message.edit(content="Selection timed out. Run /play again.", view=None)
        except Exception:
            pass


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.loop_enabled: dict[int, bool] = {}
        self.quality_warning_sent: set[int] = set()
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
        queue_empty_type = getattr(getattr(wavelink, "exceptions", None), "QueueEmpty", None)
        try:
            result = getter()
        except Exception as exc:
            if queue_empty_type and isinstance(exc, queue_empty_type):
                return None
            return None
        if inspect.isawaitable(result):
            try:
                return await result
            except Exception as exc:
                if queue_empty_type and isinstance(exc, queue_empty_type):
                    return None
                return None
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

    async def _enforce_self_deaf(
        self,
        guild: discord.Guild,
        channel: Optional[discord.abc.Connectable],
    ) -> None:
        if channel is None:
            return
        changer = getattr(guild, "change_voice_state", None)
        if changer is None:
            return
        try:
            await changer(channel=channel, self_deaf=True, self_mute=False)
        except Exception:
            return

    async def _maybe_warn_low_bitrate(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.abc.Connectable],
    ) -> None:
        if not interaction.guild or channel is None:
            return
        guild_id = interaction.guild.id
        if guild_id in self.quality_warning_sent:
            return
        bitrate = getattr(channel, "bitrate", None)
        if not isinstance(bitrate, int) or bitrate <= 0 or bitrate >= 128000:
            return
        self.quality_warning_sent.add(guild_id)
        kbps = bitrate // 1000
        try:
            await interaction.followup.send(
                (
                    f"Voice channel bitrate is only {kbps}kbps. Discord always re-encodes to Opus "
                    "and caps quality by channel bitrate. Use 128kbps+ for cleaner audio."
                ),
                ephemeral=True,
            )
        except Exception:
            return

    def _disable_autoplay(self, player: wavelink.Player) -> None:
        mode_enum = getattr(wavelink, "AutoPlayMode", None)
        if mode_enum is None:
            return
        disabled_value = getattr(mode_enum, "disabled", None)
        if disabled_value is None:
            return
        try:
            player.autoplay = disabled_value
        except Exception:
            pass

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
            self._disable_autoplay(existing)
            if existing.channel != voice_state.channel:
                mover = getattr(existing, "move_to", None)
                if mover:
                    await self._maybe_await(mover(voice_state.channel))
            await self._enforce_self_deaf(interaction.guild, existing.channel or voice_state.channel)
            return existing
        player = await voice_state.channel.connect(
            cls=wavelink.Player,
            self_deaf=True,
            self_mute=False,
        )
        if isinstance(player, wavelink.Player):
            self._disable_autoplay(player)
            await self._enforce_self_deaf(interaction.guild, player.channel)
        return player

    async def _search(
        self,
        query: str,
        preferred_source: str = "youtube",
    ) -> tuple[Optional[wavelink.Playlist], List[wavelink.Playable]]:
        normalized = query.strip()
        if not normalized:
            return None, []
        is_url = self._is_url_query(normalized)
        requested_source = None
        explicit_source = False
        source_enum = getattr(wavelink, "TrackSource", None)
        if not is_url:
            lowered = normalized.lower()
            if lowered.startswith("ytsearch:"):
                normalized = normalized[len("ytsearch:") :].strip()
                requested_source = getattr(source_enum, "YouTube", None)
                explicit_source = True
            elif lowered.startswith("ytmsearch:"):
                normalized = normalized[len("ytmsearch:") :].strip()
                requested_source = getattr(source_enum, "YouTubeMusic", None)
                explicit_source = True
            elif lowered.startswith("scsearch:"):
                normalized = normalized[len("scsearch:") :].strip()
                requested_source = getattr(source_enum, "SoundCloud", None)
                explicit_source = True
        if not normalized:
            return None, []
        attempts: list[tuple[str, object | None]] = []
        youtube_source = getattr(source_enum, "YouTube", None)
        youtube_music_source = getattr(source_enum, "YouTubeMusic", None)
        soundcloud_source = getattr(source_enum, "SoundCloud", None)

        def _append_attempt(search_query: str, search_source: object | None) -> None:
            candidate = (search_query, search_source)
            if candidate not in attempts:
                attempts.append(candidate)

        if is_url:
            _append_attempt(normalized, None)
        elif explicit_source:
            _append_attempt(normalized, requested_source)
        else:
            selected = preferred_source.strip().lower()
            if selected == "soundcloud":
                if soundcloud_source is not None:
                    _append_attempt(normalized, soundcloud_source)
                else:
                    _append_attempt(normalized, "scsearch")
                if youtube_source is not None:
                    _append_attempt(normalized, youtube_source)
                if youtube_music_source is not None:
                    _append_attempt(normalized, youtube_music_source)
            else:
                if youtube_source is not None:
                    _append_attempt(normalized, youtube_source)
                if youtube_music_source is not None:
                    _append_attempt(normalized, youtube_music_source)
                if soundcloud_source is not None:
                    _append_attempt(normalized, soundcloud_source)
                else:
                    _append_attempt(normalized, "scsearch")
                if not attempts:
                    _append_attempt(normalized, None)
        last_error: Optional[Exception] = None
        for search_query, search_source in attempts:
            try:
                if hasattr(wavelink, "Playable"):
                    if search_source is None:
                        results = await wavelink.Playable.search(search_query)
                    else:
                        results = await wavelink.Playable.search(search_query, source=search_source)
                elif hasattr(wavelink, "YouTubeTrack"):
                    results = await wavelink.YouTubeTrack.search(query=search_query)
                else:
                    results = []
            except Exception as exc:
                last_error = exc
                continue
            if hasattr(wavelink, "Playlist") and isinstance(results, wavelink.Playlist):
                tracks = list(results.tracks)
                if tracks:
                    return results, tracks
                continue
            if isinstance(results, list):
                if results:
                    return None, results
                continue
            try:
                tracks = list(results)
            except Exception:
                tracks = []
            if tracks:
                return None, tracks
        if last_error is not None:
            logging.exception("Search failed: %s", last_error)
        return None, []

    async def _queue_track(self, player: wavelink.Player, track: wavelink.Playable) -> None:
        self._disable_autoplay(player)
        self._queue_put(player, track)
        if self._is_playing(player):
            return
        next_track = await self._queue_get(player)
        if next_track:
            await self._maybe_await(player.play(next_track))

    def _is_url_query(self, query: str) -> bool:
        lowered = query.strip().lower()
        return lowered.startswith("http://") or lowered.startswith("https://")

    async def _play_internal(
        self,
        interaction: discord.Interaction,
        query: str,
        direct_only: bool,
        preferred_source: str = "youtube",
    ) -> None:
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
        await self._maybe_warn_low_bitrate(interaction, player.channel if isinstance(player, wavelink.Player) else None)
        playlist, tracks = await self._search(query, preferred_source=preferred_source)
        if not tracks:
            await interaction.followup.send("No results found.", ephemeral=True)
            return
        available = MUSIC_MAX_QUEUE - self._queue_size(player)
        if available <= 0:
            await interaction.followup.send("Queue is full.", ephemeral=True)
            return
        if playlist:
            added = 0
            for track in tracks[:available]:
                self._queue_put(player, track)
                added += 1
            if not self._is_playing(player):
                next_track = await self._queue_get(player)
                if next_track:
                    await self._maybe_await(player.play(next_track))
            await interaction.followup.send(f"Queued playlist {playlist.name} with {added} tracks.")
            return
        if direct_only or self._is_url_query(query):
            track = tracks[0]
            await self._queue_track(player, track)
            await interaction.followup.send(f"Queued: {track.title}")
            return
        options = tracks[:5]
        view = TrackPickerView(self, player, options, interaction.user.id)
        sent_message = await interaction.followup.send("Top 5 results. Choose one track:", view=view)
        view.message = sent_message

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: object) -> None:
        player = getattr(payload, "player", None)
        track = getattr(payload, "track", None)
        if not isinstance(player, wavelink.Player):
            return
        self._disable_autoplay(player)
        guild = getattr(player, "guild", None)
        if not guild:
            return
        reason = str(getattr(payload, "reason", "") or "").lower()
        if self.loop_enabled.get(guild.id) and track is not None:
            if reason == "loadfailed":
                self.loop_enabled[guild.id] = False
            elif reason not in {"stopped", "replaced", "cleanup"}:
                await self._maybe_await(player.play(track))
                return
        next_track = await self._queue_get(player)
        if next_track is None:
            return
        await self._maybe_await(player.play(next_track))

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: object) -> None:
        player = getattr(payload, "player", None)
        if not isinstance(player, wavelink.Player):
            return
        self._disable_autoplay(player)
        guild = getattr(player, "guild", None)
        if guild and self.loop_enabled.get(guild.id):
            self.loop_enabled[guild.id] = False
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
    @app_commands.describe(source="Search source")
    @app_commands.choices(
        source=[
            app_commands.Choice(name="Youtube", value="youtube"),
            app_commands.Choice(name="Soundcloud", value="soundcloud"),
        ]
    )
    async def play(
        self,
        interaction: discord.Interaction,
        query: str,
        source: app_commands.Choice[str] | None = None,
    ) -> None:
        selected = source.value if source is not None else "youtube"
        await self._play_internal(interaction, query, direct_only=False, preferred_source=selected)

    @app_commands.command(name="playurl", description="Play music from a direct URL.")
    async def playurl(self, interaction: discord.Interaction, url: str) -> None:
        await self._play_internal(interaction, url, direct_only=True)

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
