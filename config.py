import os
from dotenv import load_dotenv

load_dotenv()

# ============ TELEGRAM ============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
MAIN_ADMIN_ID = int(os.getenv("MAIN_ADMIN_ID", "0") or "0")
DEFAULT_CHAT_ID = int(os.getenv("DEFAULT_CHAT_ID", "0") or "0")

# ============ BINANCE ============
BINANCE_REST_URL = os.getenv("BINANCE_REST_URL", "https://api.binance.com")
BINANCE_STREAM_URL = os.getenv("BINANCE_STREAM_URL", "wss://stream.binance.com:9443/stream")

KLINE_TIMEFRAME = os.getenv("KLINE_TIMEFRAME", "5m")
LIMIT_KLINES = int(os.getenv("LIMIT_KLINES", "200"))

MIN_VOLUME_USD = float(os.getenv("MIN_VOLUME_USD", "6000000"))
REFRESH_PAIRS_EVERY_HOURS = int(os.getenv("REFRESH_PAIRS_EVERY_HOURS", "24"))

# ============ BOT SETTINGS ============
FREE_SIGNAL_LIMIT = int(os.getenv("FREE_SIGNAL_LIMIT", "2"))
VIP_DURATION_DAYS = int(os.getenv("VIP_DURATION_DAYS", "30"))

SIGNAL_COOLDOWN_MINUTES = int(os.getenv("SIGNAL_COOLDOWN_MINUTES", "5"))
SIGNAL_COOLDOWN_SECONDS = SIGNAL_COOLDOWN_MINUTES * 60

# ============ LOGGING ============
ENABLE_LOGGING = os.getenv("ENABLE_LOGGING", "true").lower() == "true"
LOG_FILE = os.getenv("LOG_FILE", "logs/runtime.log")
