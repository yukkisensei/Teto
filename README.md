# Teto Discord Bot

All-in-one Discord bot themed around Kasane Teto. Built with Python + discord.py.

## Features
- Quick setup presets (Small / Medium / Gaming / Fanclub)
- Moderation: warnings, timeout, anti-spam, anti-raid, blocked words, invite filter
- Music: SoundCloud + direct URL playback (queue, loop, skip)
- AI chat (Kasane Teto persona) via Groq API
- Leveling + daily tasks + badges
- Tickets, role menus, auto-role
- Reminders, events, birthdays
- Polls with buttons
- Mini-games (fishing, Pokemon, trivia, typing)
- Profile card + economy shop

## Setup
1) Install Python 3.11+
2) Install ffmpeg and make sure `ffmpeg` is in PATH
3) Install dependencies:
   - `pip install -r requirements.txt`
4) Create a `.env` file and fill in values (see below)
5) In Discord Developer Portal, enable **Message Content Intent** and **Server Members Intent**
6) Run:
   - `python main.py`

## .env template
```
DISCORD_TOKEN=
OWNER_ID=
GOD_MODE_ENABLED=1
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
GROQ_BASE_URL=https://api.groq.com/openai/v1
SOUNDCLOUD_CLIENT_ID=
SOUNDCLOUD_CLIENT_SECRET=
SOUNDCLOUD_API_BASE=https://api.soundcloud.com
SOUNDCLOUD_OAUTH_URL=https://secure.soundcloud.com/oauth/token

PRESENCE_STATUS=dnd
PRESENCE_ACTIVITY_TYPE=playing
PRESENCE_ACTIVITY_TEXT=Kasane Teto is singing
PRESENCE_STREAM_URL=
PRESENCE_ROTATION_ENABLED=1
PRESENCE_ROTATION_INTERVAL=30

DATA_DIR=C:\Teto\data
CACHE_DIR=C:\Teto\data\cache
DB_PATH=C:\Teto\data\bot.db

LOG_LEVEL=INFO
DEFAULT_LOCALE=en

CACHE_TTL_MINUTES=1440
CACHE_MAX_GB=10
MUSIC_QUALITY=bestaudio
MUSIC_MAX_QUEUE=100
FFMPEG_PATH=ffmpeg

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

## Notes
- SoundCloud playback requires API credentials (client id/secret). Set them in `.env`.
- The AI persona is locked to Kasane Teto. Edit `utils/ai_client.py` if you want to adjust style.

## Commands (high level)
- `/setup preset`, `/setup channels`, `/setup language`, `/setup summary`
- `/warn`, `/warnings`, `/timeout`, `/kick`, `/ban`, `/purge`
- `/play`, `/queue`, `/skip`, `/loop`
- `/ai`
- `/rank`, `/leaderboard`, `/profile`
- `/daily`, `/balance`, `/shop`, `/buy`
- `/ticket`, `/ticket_close`
- `/rolemenu`, `/autorole`
- `/remind`, `/event_create`, `/event_list`, `/birthday`
- `/poll`
- `/links`
