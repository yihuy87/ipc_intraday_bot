# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# === TELEGRAM ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

# Admin ID (bisa dari MAIN_ADMIN_ID atau TELEGRAM_ADMIN_ID)
_admin_id_raw = os.getenv("MAIN_ADMIN_ID") or os.getenv("TELEGRAM_ADMIN_ID") or "0"
try:
    TELEGRAM_ADMIN_ID = int(_admin_id_raw)
except ValueError:
    TELEGRAM_ADMIN_ID = 0

# Username admin (untuk info upgrade VIP ke user)
TELEGRAM_ADMIN_USERNAME = os.getenv("TELEGRAM_ADMIN_USERNAME", "")

# === BINANCE ===
BINANCE_REST_URL = "https://api.binance.com"
BINANCE_STREAM_URL = "wss://stream.binance.com:9443/stream"

# === FILTER PAIR & SCAN ===

# Minimal volume (USDT) 24 jam supaya pair masuk daftar scan
MIN_VOLUME_USDT = float(os.getenv("MIN_VOLUME_USDT", "6000000"))

# Max jumlah pair USDT yang discan
MAX_USDT_PAIRS = int(os.getenv("MAX_USDT_PAIRS", "500"))

# Interval refresh daftar pair (jam)
REFRESH_PAIR_INTERVAL_HOURS = float(os.getenv("REFRESH_PAIR_INTERVAL_HOURS", "24"))

# === TIER & COOLDOWN ===

# Tier minimum untuk kirim sinyal: "A+", "A", "B"
MIN_TIER_TO_SEND = os.getenv("MIN_TIER_TO_SEND", "A")

# Cooldown default antar sinyal per pair (detik)
SIGNAL_COOLDOWN_SECONDS = int(os.getenv("SIGNAL_COOLDOWN_SECONDS", "900"))  # 15 menit

# === KLINES LIMIT (KOMPATIBEL DENGAN ipc_logic LAMA) ===

# Digunakan oleh ipc_logic.py: berapa candle terakhir yang diambil dari REST
LIMIT_KLINES = int(os.getenv("LIMIT_KLINES", "300"))
