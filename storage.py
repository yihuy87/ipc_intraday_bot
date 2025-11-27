# storage.py

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict

from config import SIGNAL_COOLDOWN_SECONDS

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
VIP_FILE = DATA_DIR / "vip_users.json"
STATS_FILE = DATA_DIR / "stats.json"
COOLDOWN_FILE = DATA_DIR / "cooldown.json"

FREE_SIGNALS_PER_DAY = 2  # sama seperti SMC: free 2 sinyal/hari


# ============ JSON HELPERS ============

def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ============ SUBSCRIBERS ============

def load_subscribers_dict() -> Dict[str, dict]:
    """
    Format:
    {
      "123456": {
         "active": true,
         "signals_today": 0,
         "last_signal_date": "YYYY-MM-DD",
         "vip_expiry": "YYYY-MM-DD" or null,
         "pause_until": "ISO datetime" or null
      },
      ...
    }
    """
    return _load_json(SUBSCRIBERS_FILE, {})


def save_subscribers_dict(subs: Dict[str, dict]):
    _save_json(SUBSCRIBERS_FILE, subs)


def ensure_user(subs: Dict[str, dict], chat_id: int):
    cid = str(chat_id)
    if cid not in subs:
        subs[cid] = {
            "active": True,
            "signals_today": 0,
            "last_signal_date": "",
            "vip_expiry": None,
            "pause_until": None,
        }
    else:
        u = subs[cid]
        u.setdefault("active", True)
        u.setdefault("signals_today", 0)
        u.setdefault("last_signal_date", "")
        u.setdefault("vip_expiry", None)
        u.setdefault("pause_until", None)


def _today_str():
    return datetime.now(timezone.utc).date().isoformat()


def _reset_daily_if_needed(user: dict):
    today = _today_str()
    if user.get("last_signal_date") != today:
        user["last_signal_date"] = today
        user["signals_today"] = 0


# ============ VIP ============

def is_vip(user: dict) -> bool:
    exp_str = user.get("vip_expiry")
    if not exp_str:
        return False
    try:
        exp_date = datetime.fromisoformat(exp_str).date()
    except Exception:
        user["vip_expiry"] = None
        return False

    today = datetime.now(timezone.utc).date()
    if today <= exp_date:
        return True
    else:
        # expired
        user["vip_expiry"] = None
        return False


def grant_vip_days(subs: Dict[str, dict], chat_id: int, days: int = 30):
    ensure_user(subs, chat_id)
    user = subs[str(chat_id)]
    today = datetime.now(timezone.utc).date()
    exp = today + timedelta(days=days)
    user["vip_expiry"] = exp.isoformat()


def revoke_vip(subs: Dict[str, dict], chat_id: int):
    if str(chat_id) in subs:
        subs[str(chat_id)]["vip_expiry"] = None


# ============ PAUSE 24 JAM ============

def set_pause_24h(user: dict):
    now = datetime.now(timezone.utc)
    user["pause_until"] = (now + timedelta(hours=24)).isoformat()


def clear_pause(user: dict):
    user["pause_until"] = None


def is_paused(user: dict) -> bool:
    pu = user.get("pause_until")
    if not pu:
        return False
    try:
        dt = datetime.fromisoformat(pu)
    except Exception:
        user["pause_until"] = None
        return False
    return datetime.now(timezone.utc) < dt


# ============ COOLDOWN GLOBAL ============

def get_cooldown_seconds() -> int:
    data = _load_json(COOLDOWN_FILE, {})
    return int(data.get("cooldown_seconds", SIGNAL_COOLDOWN_SECONDS))


def set_cooldown_seconds(seconds: int):
    data = {"cooldown_seconds": int(seconds)}
    _save_json(COOLDOWN_FILE, data)


# ============ LIMIT HARIAN ============

def can_receive_signal(user: dict) -> bool:
    """
    - inactive → False
    - pause_until aktif → False
    - VIP → True (bypass limit harian)
    - FREE → max 2 sinyal / hari
    """
    _reset_daily_if_needed(user)

    if not user.get("active", True):
        return False
    if is_paused(user):
        return False
    if is_vip(user):
        return True

    return int(user.get("signals_today", 0)) < FREE_SIGNALS_PER_DAY


def mark_signal_sent(user: dict):
    _reset_daily_if_needed(user)
    user["signals_today"] = int(user.get("signals_today", 0)) + 1


# ============ STATS ============

def load_stats():
    stats = _load_json(STATS_FILE, {})
    today = _today_str()
    stats.setdefault("last_reset_date", today)
    stats.setdefault("signals_today_total", 0)
    stats.setdefault("total_signals", 0)
    stats.setdefault("last_symbol", None)
    stats.setdefault("last_signal_time", None)

    if stats["last_reset_date"] != today:
        stats["last_reset_date"] = today
        stats["signals_today_total"] = 0

    return stats


def save_stats(stats):
    _save_json(STATS_FILE, stats)


def bump_stats(symbol: str):
    stats = load_stats()
    stats["signals_today_total"] = int(stats.get("signals_today_total", 0)) + 1
    stats["total_signals"] = int(stats.get("total_signals", 0)) + 1
    stats["last_symbol"] = symbol
    stats["last_signal_time"] = datetime.now(timezone.utc).isoformat()
    save_stats(stats)
