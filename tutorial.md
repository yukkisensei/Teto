Huong dan lay bien ENV cho Teto Bot

Muc tieu
1. Biet bien nao bat buoc, bien nao tuy chon.
2. Biet cach lay gia tri cho tung bien.
3. Dien vao file `/opt/teto/.env` dung cach.

Buoc 1. Mo file ENV
```bash
cd /opt/teto
nano .env
```

Buoc 2. Bien bat buoc de bot chay

1. `DISCORD_TOKEN`
- Vao `https://discord.com/developers/applications`
- Tao app moi hoac mo app hien tai
- Vao tab Bot
- Bam Reset Token
- Copy token vao `DISCORD_TOKEN`

2. `OWNER_ID`
- Mo Discord desktop
- Vao Settings > Advanced > bat Developer Mode
- Quay lai profile cua ban, bam chuot phai vao ten tai khoan, chon Copy User ID
- Dan vao `OWNER_ID`

3. `LAVALINK_HOST`, `LAVALINK_PORT`, `LAVALINK_PASSWORD`, `LAVALINK_SECURE`
- Dat trung voi config Lavalink dang chay
- Neu bot va Lavalink cung may, dung:
  - `LAVALINK_HOST=127.0.0.1`
  - `LAVALINK_PORT=2333`
  - `LAVALINK_SECURE=0`
- `LAVALINK_PASSWORD` phai giong password ben Lavalink

Buoc 3. Bien cho tinh nang AI

1. `GROQ_API_KEY`
- Vao `https://console.groq.com/keys`
- Tao API key moi
- Dan vao `.env`

2. `GROQ_MODEL`, `GROQ_BASE_URL`
- Co the giu mac dinh:
  - `GROQ_MODEL=llama-3.1-8b-instant`
  - `GROQ_BASE_URL=https://api.groq.com/openai/v1`

Buoc 4. Bien cho nhac chat luong cao

1. Chat luong thuc te tren Discord
- Discord re-encode am thanh sang Opus.
- Chat luong con phu thuoc bitrate cua voice channel.
- Muon nghe on hon, dung kenh co bitrate cao (thuong 128 kbps tro len).
- Bot da duoc cau hinh de uu tien chat luong cao va do on dinh tren Lavalink.

Buoc 5. Bien co the giu mac dinh
- `PRESENCE_STATUS`, `PRESENCE_ACTIVITY_TYPE`, `PRESENCE_ACTIVITY_TEXT`
- `DATA_DIR`, `CACHE_DIR`, `DB_PATH`
- `LOG_LEVEL`, `DEFAULT_LOCALE`
- `MUSIC_QUALITY`, `MUSIC_MAX_QUEUE`
- Nhom anti spam, anti raid, leveling, economy

Buoc 6. Mau ENV toi thieu de chay
```env
DISCORD_TOKEN=
OWNER_ID=
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
GROQ_BASE_URL=https://api.groq.com/openai/v1

LAVALINK_HOST=127.0.0.1
LAVALINK_PORT=2333
LAVALINK_PASSWORD=youshallnotpass
LAVALINK_SECURE=0
```

Buoc 7. Kiem tra nhanh sau khi sua ENV
```bash
systemctl is-active lavalink
systemctl is-active teto
```

Neu doi `.env`, restart dich vu:
```bash
systemctl restart lavalink
systemctl restart teto
```

Luu y bao mat
- Khong commit file `.env` len git.
- Neu token da lo, reset token va thay token moi ngay.

For licensing or permission to use this project, contact: support@yukki.site
