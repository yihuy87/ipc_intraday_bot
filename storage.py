import os
from datetime import datetime, timedelta
from typing import Dict, Any

from config import FREE_SIGNAL_LIMIT, VIP_DURATION_DAYS, SIGNAL_COOLDOWN_SECONDS
from utils import load_json, save_json, get_today_str, ensure_dir

DATA_DIR = "data"
SUBSCRIBERS_FILE = os.path.join(DATA_DIR, "subscribers.json")
COOLDOWN_FILE = os.path.join(DATA_DIR, "cooldown.json")


# ============ SUBSCRIBERS / VIP ============

def load_subscribers() -> Dict[str, Any]:
    """
    Return dict: { chat_id(str): { active, is_vip, vip_expiry, signals_today, last_day } }
    """
    ensure_dir(SUBSCRIBERS_FILE)
    return load_json(SUBSCRIBERS_FILE, {})


def save_subscribers(data: Dict[str, Any]) -> None:
    save_json(SUBSCRIBERS_FILE, data)


def ensure_user(subs: Dict[str, Any], chat_id: int) -> None:
    """
    Pastikan user sudah ada di subscribers.
    Sekaligus reset signals_today jika ganti hari.
    """
    key = str(chat_id)
    today = get_today_str()

    if key not in subs:
        subs[key] = {
            "active": True,          # ON/OFF sinyal
            "is_vip": False,
            "vip_expiry": None,      # "YYYY-MM-DD" atau None
            "signals_today": 0,
            "last_day": today,
        }
    else:
        # Reset harian jika tanggal berubah
        if subs[key].get("last_day") != today:
            subs[key]["last_day"] = today
            subs[key]["signals_today"] = 0


def is_vip(user: Dict[str, Any]) -> bool:
    """
    Cek apakah user VIP & belum expired.
    """
    if not user.get("is_vip"):
        return False
    expiry = user.get("vip_expiry")
    if not expiry:
        return False
    try:
        exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
    except Exception:
        return False
    return exp_date >= datetime.utcnow().date()


def grant_vip(subs: Dict[str, Any], chat_id: int, days: int = None) -> None:
    """
    Beri VIP ke user selama X hari (default VIP_DURATION_DAYS).
    """
    if days is None:
        days = VIP_DURATION_DAYS
    ensure_user(subs, chat_id)
    key = str(chat_id)

    today = datetime.utcnow().date()
    new_exp = today + timedelta(days=days)

    subs[key]["is_vip"] = True
    subs[key]["vip_expiry"] = new_exp.strftime("%Y-%m-%d")


def revoke_vip(subs: Dict[str, Any], chat_id: int) -> None:
    """
    Hapus status VIP user (jadi free).
    """
    ensure_user(subs, chat_id)
    key = str(chat_id)

    subs[key]["is_vip"] = False
    subs[key]["vip_expiry"] = None


def can_receive_signal(user: Dict[str, Any]) -> bool:
    """
    Cek apakah user berhak menerima sinyal saat ini.
    - Harus active == True
    - Jika VIP -> unlimited
    - Jika free -> <= FREE_SIGNAL_LIMIT per hari
    """
    if not user.get("active", True):
        return False

    if is_vip(user):
        return True

    return user.get("signals_today", 0) < FREE_SIGNAL_LIMIT


def mark_signal_sent(user: Dict[str, Any]) -> None:
    """
    Tambah counter sinyal harian untuk FREE user.
    VIP tidak dibatasi, tetapi fungsi ini tetap aman dipanggil.
    """
    if not is_vip(user):
        user["signals_today"] = user.get("signals_today", 0) + 1


# ============ COOLDOWN ============

def load_cooldown_config() -> Dict[str, Any]:
    """
    Simpan konfigurasi cooldown global, misal:
    { "cooldown_seconds": 300 }
    """
    ensure_dir(COOLDOWN_FILE)
    data = load_json(COOLDOWN_FILE, {})
    if "cooldown_seconds" not in data:
        data["cooldown_seconds"] = SIGNAL_COOLDOWN_SECONDS
    return data


def save_cooldown_config(data: Dict[str, Any]) -> None:
    save_json(COOLDOWN_FILE, data)


def get_cooldown_seconds() -> int:
    data = load_cooldown_config()
    return int(data.get("cooldown_seconds", SIGNAL_COOLDOWN_SECONDS))


def set_cooldown_seconds(seconds: int) -> None:
    data = load_cooldown_config()
    data["cooldown_seconds"] = int(seconds)
    save_cooldown_config(data)
