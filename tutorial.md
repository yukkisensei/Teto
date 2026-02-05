**Huong dan cai dat Teto Bot tren Ubuntu VPS**

**Muc tieu**
1. Cai bot bang Python tren Ubuntu VPS
2. Cai Lavalink va ket noi bot qua bien moi truong
3. Chay tu dong bang systemd

**Yeu cau**
1. Ubuntu 22.04 hoac 24.04
2. Token bot tu Discord Developer Portal
3. Quyen sudo tren VPS

**Buoc 1: Cap nhat he thong va cong cu co ban**
```bash
sudo apt update
sudo apt install -y git curl software-properties-common
```

**Buoc 2: Cai Python 3.11**
```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
python3.11 --version
```

**Buoc 3: Tai ma nguon bot**
```bash
sudo mkdir -p /opt/teto
sudo chown $USER:$USER /opt/teto
cd /opt
git clone REPO_URL teto
cd /opt/teto
```

**Buoc 4: Tao venv va cai dependency**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

**Buoc 5: Tao file .env**
```bash
cd /opt/teto
nano .env
```

Noi dung goi y cho .env
```
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

**Buoc 6: Cai Java 17 va Lavalink**
```bash
sudo apt install -y openjdk-17-jre-headless
java -version
```

Tao thu muc Lavalink
```bash
sudo mkdir -p /opt/lavalink
sudo chown $USER:$USER /opt/lavalink
cd /opt/lavalink
```

Tai Lavalink.jar tu trang releases chinh thuc
```bash
https://github.com/lavalink-devs/Lavalink/releases
```

Sau khi copy link jar tren trang releases, tai bang curl
```bash
LAVALINK_JAR_URL=PASTE_DIRECT_JAR_URL_HERE
curl -L -o /opt/lavalink/Lavalink.jar "$LAVALINK_JAR_URL"
```

Tao file application.yml toi thieu
```bash
cat > /opt/lavalink/application.yml << 'EOF'
server:
  port: 2333
  address: 0.0.0.0
  http2:
    enabled: false
EOF
```

**Buoc 7: Chay Lavalink bang systemd**
Chinh lai User thanh username dang dung tren VPS
```bash
sudo tee /etc/systemd/system/lavalink.service > /dev/null << 'EOF'
[Unit]
Description=Lavalink
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/lavalink
ExecStart=/usr/bin/java -jar /opt/lavalink/Lavalink.jar
Restart=on-failure
RestartSec=5
Environment=SERVER_PORT=2333
Environment=SERVER_ADDRESS=0.0.0.0
Environment=LAVALINK_SERVER_PASSWORD=youshallnotpass

[Install]
WantedBy=multi-user.target
EOF
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable lavalink
sudo systemctl start lavalink
sudo systemctl status lavalink
```

Neu bot va Lavalink khac VPS, mo cong 2333
```bash
sudo ufw allow 2333/tcp
```

Neu bot va Lavalink cung VPS, nen de LAVALINK_HOST=127.0.0.1 va SERVER_ADDRESS=127.0.0.1 de an toan

**Buoc 8: Chay bot thu cong lan dau**
```bash
cd /opt/teto
source .venv/bin/activate
python main.py
```

**Buoc 9: Tu dong chay bot bang systemd**
Chinh lai User thanh username dang dung tren VPS
```bash
sudo tee /etc/systemd/system/teto-bot.service > /dev/null << 'EOF'
[Unit]
Description=Teto Discord Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/teto
EnvironmentFile=/opt/teto/.env
ExecStart=/opt/teto/.venv/bin/python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable teto-bot
sudo systemctl start teto-bot
sudo systemctl status teto-bot
```

**Buoc 10: Setup trong Discord**
1. Moi bot vao server, cap quyen Applications Commands va quyen can thiet
2. Dung lenh slash
3. Tao verify bang /setup verify
4. Tao giveaway bang /setup giveaway

**Goi y kiem tra nhanh**
1. Slash lenh hoat dong, thu /ping
2. Thu /join va /play de kiem tra Lavalink
3. Thu /verify sau khi bam nut Verify
