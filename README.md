Teto Discord Bot

All in one Discord bot themed around Kasane Teto, built with Python and discord.py.

Overview
- Quick setup presets (Small, Medium, Gaming, Fanclub)
- Moderation: warnings, timeout, anti spam, anti raid, blocked words, invite filter
- Music with Lavalink and Wavelink
- AI chat with Groq
- Verification, giveaway, leveling, profile and economy
- Tickets, role menu, utility and mini games

Music behavior
- `/play` supports source selection:
  - `Youtube` (default)
  - `Spotify`
  - `Soundcloud`
- `/playurl` plays direct URLs.
- Bot joins voice with self-deaf enabled, so it does not listen in voice channel.
- If Spotify credentials are missing, bot auto falls back to other search sources instead of hard failing.
- Spotify links can be converted to text search fallback when direct Spotify lookup is unavailable.

Audio quality notes
- Discord always re-encodes to Opus and is capped by voice channel bitrate.
- For cleaner playback, use higher bitrate voice channels.
- Source quality above 256 kbps is possible only when upstream source supports it.
- Deezer high quality path requires valid Deezer credentials in environment.

Requirements
1. Python 3.11 or newer
2. Java 17 or newer
3. Lavalink 4 server reachable by the bot
4. Discord bot token with required intents enabled

Quick start
1. Install dependencies:
   - `pip install -r requirements.txt`
2. Create `.env` in project root.
3. Start Lavalink.
4. Start bot:
   - `python main.py`

Environment template
```env
DISCORD_TOKEN=
OWNER_ID=
GOD_MODE_ENABLED=1
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
GROQ_BASE_URL=https://api.groq.com/openai/v1

LAVALINK_HOST=127.0.0.1
LAVALINK_PORT=2333
LAVALINK_PASSWORD=youshallnotpass
LAVALINK_SECURE=0

SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_COUNTRY_CODE=US
DEEZER_ENABLED=0
DEEZER_ARL=
DEEZER_MASTER_DECRYPTION_KEY=

PRESENCE_STATUS=dnd
PRESENCE_ACTIVITY_TYPE=playing
PRESENCE_ACTIVITY_TEXT=Kasane Teto is singing
PRESENCE_STREAM_URL=
PRESENCE_ROTATION_ENABLED=1
PRESENCE_ROTATION_INTERVAL=30

DATA_DIR=/opt/teto/data
CACHE_DIR=/opt/teto/data/cache
DB_PATH=/opt/teto/data/bot.db

LOG_LEVEL=INFO
DEFAULT_LOCALE=en

CACHE_TTL_MINUTES=1440
CACHE_MAX_GB=10
MUSIC_QUALITY=bestaudio
MUSIC_MAX_QUEUE=100

VERIFY_CODE_TTL_MINUTES=10

AI_COOLDOWN_SECONDS=8
MAX_AI_HISTORY=8

ANTI_SPAM_ENABLED=1
ANTI_SPAM_RATE=6
ANTI_SPAM_INTERVAL=8
MAX_MENTIONS=5
ANTI_RAID_ENABLED=1
ANTI_RAID_THRESHOLD=6
ANTI_RAID_WINDOW=10
ANTI_INVITE_ENABLED=1
ANTI_LINK_ENABLED=0
ANTI_NSFW_ENABLED=1

XP_PER_MESSAGE_MIN=10
XP_PER_MESSAGE_MAX=20
XP_COOLDOWN_SECONDS=45
DAILY_REWARD=250
FISH_REWARD=20
POKEMON_REWARD=30
VOICE_XP_PER_MIN=2

BOT_RATIO_GUARD_ENABLED=1
BOT_RATIO_MAX=0.6
```

Lavalink plugin expectations
- `youtube-plugin` enabled
- `lavasrc-plugin` enabled for Spotify and optional Deezer resolution
- If Deezer is enabled without required keys, Lavalink can fail to start

Troubleshooting
- No YouTube results:
  - Check Lavalink status and plugin load.
  - Check `/v4/info` and confirm `youtube` source manager is present.
- Spotify search fails:
  - Set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`.
  - Restart Lavalink after changing `.env`.
- Stutter or unstable audio:
  - Check host CPU and memory.
  - Check network stability to Discord voice edge.
  - Use higher bitrate voice channels.

Main command groups
- Setup: `/setup preset`, `/setup channels`, `/setup verify`, `/setup giveaway`, `/setup language`, `/setup summary`
- Moderation: `/warn`, `/warnings`, `/timeout`, `/kick`, `/ban`, `/purge`
- Music: `/join`, `/play`, `/playurl`, `/queue`, `/skip`, `/loop`, `/nowplaying`
- AI: `/ai`
- Verify: `/verify`, `/verify_resend`
- Giveaway: `/giveaway create`, `/giveaway end`, `/giveaway reroll`, `/giveaway list`
- Level and profile: `/rank`, `/leaderboard`, `/profile`
- Economy: `/daily`, `/balance`, `/shop`, `/buy`
- Tickets and roles: `/ticket`, `/ticket_close`, `/rolemenu`, `/autorole`
- Utility: `/ping`, `/avatar`, `/serverinfo`, `/userinfo`, `/uptime`, `/links`

Extra docs
- `tutorial.md` contains step by step environment variable setup guide.
