# ipc_logic.py

import requests
import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any

from config import BINANCE_REST_URL, LIMIT_KLINES


# ================== DATA FETCHING ==================


def get_klines(symbol: str, interval: str, limit: int = LIMIT_KLINES) -> pd.DataFrame:
    """
    Ambil data candlestick Binance (REST API).
    """
    url = f"{BINANCE_REST_URL}/api/v3/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}

    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ]
    df = pd.DataFrame(data, columns=cols)

    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)

    return df


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


# ================== HELPER: SWING / ATR ==================


def calc_atr_like(df: pd.DataFrame, period: int = 14) -> float:
    """
    ATR sederhana untuk melihat volatilitas rata-rata.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return float(atr.iloc[-1])


def find_recent_swing_high_low(df: pd.DataFrame, window: int = 30) -> Tuple[float, float]:
    """
    Cari high & low terbaru di jendela window terakhir.
    """
    highs = df["high"].values
    lows = df["low"].values

    if len(highs) < window:
        window = len(highs)

    recent_high = float(np.max(highs[-window:]))
    recent_low = float(np.min(lows[-window:]))

    return recent_high, recent_low


# ================== 1. TREND 1H (WAJIB) ==================


def detect_trend_1h_bullish(df_1h: pd.DataFrame) -> bool:
    """
    Trend bullish sederhana:
    - close > EMA20 > EMA50 > EMA200
    - close juga di atas EMA50
    """
    close = df_1h["close"]
    if len(close) < 200:
        return False

    ema20 = ema(close, 20)
    ema50 = ema(close, 50)
    ema200 = ema(close, 200)

    last = close.iloc[-1]
    e20 = ema20.iloc[-1]
    e50 = ema50.iloc[-1]
    e200 = ema200.iloc[-1]

    strong_bull = (last > e20 > e50 > e200)
    return bool(strong_bull)


# ================== 2. STRUKTUR 15m (WAJIB) ==================


def detect_struct_15m_bullish(df_15m: pd.DataFrame) -> bool:
    """
    Struktur bullish sederhana:
    - HL / HH terbentuk dalam beberapa candle terakhir
    - price berada di atas EMA50
    """
    closes = df_15m["close"]
    highs = df_15m["high"].values
    lows = df_15m["low"].values

    if len(closes) < 50:
        return False

    ema50 = ema(closes, 50)
    last_close = closes.iloc[-1]
    last_ema50 = ema50.iloc[-1]

    if last_close <= last_ema50:
        return False

    # cek HL / HH kasar
    # ambil 6 candle terakhir sebagai referensi
    if len(highs) < 8:
        return False

    recent_highs = highs[-8:]
    recent_lows = lows[-8:]

    # syarat: high terbaru > high beberapa candle sebelum, low terbaru > low beberapa candle sebelum
    if recent_highs[-1] > recent_highs[-4] and recent_lows[-1] > recent_lows[-4]:
        return True

    return False


# ================== 3. IMPULSE KUAT (OPSIONAL) ==================


def detect_impulse_strong_5m(df_5m: pd.DataFrame, lookback: int = 20) -> bool:
    """
    Deteksi apakah ada candle impulsif bullish baru-baru ini.
    - Candle terakhir atau sebelumnya punya body > 1.5x rata-rata body lookback
    - Close > open (bullish)
    """
    opens = df_5m["open"].values
    closes = df_5m["close"].values
    if len(opens) < lookback + 2:
        return False

    bodies = np.abs(closes - opens)
    avg_body = bodies[-(lookback + 2):-2].mean()
    if avg_body <= 0:
        return False

    # lihat 2 candle terakhir sebagai kandidat impuls
    for i in [-2, -1]:
        body = bodies[i]
        if closes[i] > opens[i] and body > avg_body * 1.5:
            return True

    return False


# ================== 4. PULLBACK SEHAT (WAJIB) ==================


def detect_pullback_healthy_5m(df_5m: pd.DataFrame, window: int = 40) -> bool:
    """
    Pullback sehat:
    - Ada rally → kemudian retrace ke zona 30-60% dari swing low->high
    - Harga saat ini tidak menembus kembali swing low
    """
    highs = df_5m["high"].values
    lows = df_5m["low"].values
    closes = df_5m["close"].values

    if len(highs) < window + 5:
        return False

    recent_high = highs[-window:].max()
    recent_low = lows[-window:].min()

    full_range = recent_high - recent_low
    if full_range <= 0:
        return False

    last_close = closes[-1]

    # posisi saat ini dalam range swing
    pos = (last_close - recent_low) / full_range  # 0 = low, 1 = high

    # pullback sehat: tidak di pucuk (0.9-1.0), tidak di dasar (<0.2)
    # ideal: 0.3 - 0.6 (discount area)
    if 0.3 <= pos <= 0.6:
        # cek tidak break swing low
        if last_close > recent_low:
            return True

    return False


# ================== 5. CONTINUATION BREAK (OPSIONAL) ==================


def detect_continuation_break_5m(df_5m: pd.DataFrame, lookback: int = 15) -> bool:
    """
    Break lanjutan (continuation):
    - close 5m terbaru menembus high beberapa candle sebelumnya
    - body cukup tegas
    """
    highs = df_5m["high"].values
    opens = df_5m["open"].values
    closes = df_5m["close"].values

    if len(highs) < lookback + 2:
        return False

    last_close = closes[-1]
    last_open = opens[-1]
    prev_highs = highs[-(lookback + 2):-2]

    if len(prev_highs) == 0:
        return False

    broke = last_close > prev_highs.max()
    if not broke:
        return False

    # pastikan bukan doji
    body = abs(last_close - last_open)
    recent_bodies = np.abs(closes[-(lookback + 2):-2] - opens[-(lookback + 2):-2])
    avg_body = recent_bodies.mean() if len(recent_bodies) > 0 else 0.0

    if avg_body <= 0:
        return False

    if body < avg_body * 0.8:
        return False

    return True


# ================== 6. ANTI FAKE BREAK (WAJIB) ==================


def detect_anti_fake_break_5m(df_5m: pd.DataFrame, lookback: int = 30) -> bool:
    """
    Anti fake break:
    - Hindari candle terbaru yang:
      * range jauh lebih besar dari rata-rata (pump/spike)
      * wick atas sangat panjang (rejection)
    """

    highs = df_5m["high"].values
    lows = df_5m["low"].values
    opens = df_5m["open"].values
    closes = df_5m["close"].values

    if len(highs) < lookback + 3:
        return False  # kalau data terlalu sedikit, anggap tidak aman

    # gunakan candle terakhir
    hi = highs[-1]
    lo = lows[-1]
    op = opens[-1]
    cl = closes[-1]

    recent_highs = highs[-(lookback + 3):-1]
    recent_lows = lows[-(lookback + 3):-1]

    ranges = recent_highs - recent_lows
    avg_range = ranges.mean()
    if avg_range <= 0:
        return False

    last_range = hi - lo

    # kalau range candle terakhir > 3x rata-rata → berpotensi spike
    if last_range > avg_range * 3.0:
        return False

    # cek wick atas
    # untuk candle bullish, wick atas = high - close
    # untuk candle bearish, wick atas = high - open (lebih konservatif)
    if cl >= op:
        upper_wick = hi - cl
        body = cl - op
    else:
        upper_wick = hi - op
        body = op - cl

    # kalau body kecil dan wick besar → fake
    if last_range > 0:
        wick_ratio = upper_wick / last_range
    else:
        wick_ratio = 0.0

    if wick_ratio > 0.6:  # wick atas >60% dari range → rejection kuat
        return False

    # kalau lolos semua filter → anti_fake_break dianggap True (aman)
    return True


# ================== 7. VOLUME KUAT (OPSIONAL) ==================


def detect_volume_strong_5m(df_5m: pd.DataFrame, lookback: int = 30) -> bool:
    """
    Volume kuat:
    - volume candle terakhir > 1.5x rata-rata volume lookback
    """
    vols = df_5m["volume"].values
    if len(vols) < lookback + 2:
        return False

    recent_vol = vols[-(lookback + 2):-2]
    avg_vol = recent_vol.mean()
    if avg_vol <= 0:
        return False

    last_vol = vols[-1]
    return bool(last_vol > avg_vol * 1.5)


# ================== LEVEL ENTRY / SL / TP ==================


def build_ipc_levels_from_5m(df_5m: pd.DataFrame, window: int = 30) -> Dict[str, float]:
    """
    Bangun level entry / SL / TP dari struktur 5m sederhana.
    - Cari swing low & high terakhir (window)
    - Entry di sekitar mid/discount
    - SL sedikit di bawah swing low
    - TP berdasarkan risk dari range swing
    """
    recent_high, recent_low = find_recent_swing_high_low(df_5m, window=window)
    closes = df_5m["close"].values

    last_close = float(closes[-1])

    full_range = recent_high - recent_low
    if full_range <= 0:
        full_range = max(1e-6, abs(last_close) * 0.001)

    # Entry dekat 50% retrace dari swing tinggi → ke bawah (discount)
    entry = recent_low + full_range * 0.5

    # SL sedikit di bawah swing low
    sl = recent_low - full_range * 0.25

    # Risk = entry - SL
    risk = entry - sl
    if risk <= 0:
        risk = full_range * 0.5

    tp1 = entry + risk * 1.0
    tp2 = entry + risk * 1.5
    tp3 = entry + risk * 2.0

    return {
        "entry": float(entry),
        "sl": float(sl),
        "tp1": float(tp1),
        "tp2": float(tp2),
        "tp3": float(tp3),
    }


# ================== MAIN ANALYZE FUNCTION ==================


def analyse_symbol_ipc(symbol: str) -> Tuple[Dict[str, Any] | None, Dict[str, float] | None]:
    """
    Analisa 1 symbol untuk model IPC:
    - Ambil data 1H, 15m, 5m
    - Hitung 4 syarat wajib:
      trend_1h_bullish, struct_15m_bullish, pullback_healthy, anti_fake_break
    - Hitung 3 syarat opsional:
      impulse_strong, continuation_break, volume_strong
    - Jika salah satu WAJIB = False -> return (None, None) agar TIDAK kirim sinyal
    - Jika semua WAJIB = True -> build levels & return
    """
    try:
        df_1h = get_klines(symbol, "1h", LIMIT_KLINES)
        df_15m = get_klines(symbol, "15m", LIMIT_KLINES)
        df_5m = get_klines(symbol, "5m", LIMIT_KLINES)
    except Exception as e:
        print(f"[{symbol}] ERROR fetching data (IPC):", e)
        return None, None

    if len(df_1h) < 200 or len(df_15m) < 60 or len(df_5m) < 60:
        # data kurang, skip
        return None, None

    # --- WAJIB ---
    trend_1h = detect_trend_1h_bullish(df_1h)
    struct_15m = detect_struct_15m_bullish(df_15m)
    pullback_ok = detect_pullback_healthy_5m(df_5m)
    anti_fake_ok = detect_anti_fake_break_5m(df_5m)

    # Jika syarat WAJIB tidak terpenuhi -> NO SIGNAL
    if not (trend_1h and struct_15m and pullback_ok and anti_fake_ok):
        return None, None

    # --- OPSIONAL ---
    impulse_ok = detect_impulse_strong_5m(df_5m)
    cont_ok = detect_continuation_break_5m(df_5m)
    vol_ok = detect_volume_strong_5m(df_5m)

    conditions = {
        "trend_1h_bullish": trend_1h,
        "struct_15m_bullish": struct_15m,
        "pullback_healthy": pullback_ok,
        "anti_fake_break": anti_fake_ok,
        "impulse_strong": impulse_ok,
        "continuation_break": cont_ok,
        "volume_strong": vol_ok,
    }

    levels = build_ipc_levels_from_5m(df_5m, window=30)

    return conditions, levels
