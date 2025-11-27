import json
import os
from datetime import datetime
from typing import Any


def ensure_dir(path: str) -> None:
    """
    Pastikan folder untuk path ada.
    Contoh: logs/runtime.log -> buat folder logs jika belum ada.
    """
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def load_json(path: str, default: Any):
    """
    Baca file JSON. Jika tidak ada / error -> return default.
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data: Any) -> None:
    """
    Simpan dict/list ke file JSON dengan indent rapi.
    """
    ensure_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_today_str() -> str:
    """
    Return tanggal UTC hari ini dalam format YYYY-MM-DD.
    """
    return datetime.utcnow().strftime("%Y-%m-%d")
