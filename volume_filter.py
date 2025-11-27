from typing import List

import requests

from config import BINANCE_REST_URL


def get_usdt_pairs_with_volume(min_usd: float) -> List[str]:
    """
    Ambil list symbol USDT di Binance dengan quoteVolume >= min_usd (24 jam).
    Return dalam bentuk lowercase: ['btcusdt', 'ethusdt', ...]
    """

    # 1) Ambil exchangeInfo untuk list simbol USDT
    info_url = f"{BINANCE_REST_URL}/api/v3/exchangeInfo"
    r_info = requests.get(info_url, timeout=10)
    r_info.raise_for_status()
    info = r_info.json()

    usdt_syms = set()
    for s in info["symbols"]:
        if s["status"] == "TRADING" and s["quoteAsset"] == "USDT":
            usdt_syms.add(s["symbol"])

    # 2) Ambil ticker 24 jam untuk volume
    tick_url = f"{BINANCE_REST_URL}/api/v3/ticker/24hr"
    r_tick = requests.get(tick_url, timeout=10)
    r_tick.raise_for_status()
    tickers = r_tick.json()

    result = []
    for t in tickers:
        sym = t.get("symbol", "")
        if sym not in usdt_syms:
            continue
        try:
            qv = float(t.get("quoteVolume", 0.0))
        except Exception:
            continue
        if qv >= min_usd:
            result.append(sym.lower())

    result = sorted(result)
    return result
