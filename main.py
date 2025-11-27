# main.py

import asyncio
import json
import time
from types import SimpleNamespace
from typing import List, Dict

import websockets
import requests

from config import (
    TELEGRAM_TOKEN,
    TELEGRAM_ADMIN_ID,
    BINANCE_REST_URL,
    BINANCE_STREAM_URL,
    MIN_VOLUME_USDT,
    MAX_USDT_PAIRS,
    MIN_TIER_TO_SEND,
    REFRESH_PAIR_INTERVAL_HOURS,
)

# --- Import IPC logic dengan cara fleksibel ---
import ipc_logic
try:
    analyse_symbol_ipc = ipc_logic.analyse_symbol
except AttributeError:
    # fallback kalau namanya analyse_symbol_ipc
    analyse_symbol_ipc = ipc_logic.analyse_symbol_ipc

from ipc_scoring import score_ipc_signal, tier_from_score, should_send_tier
from signal_builder import build_ipc_signal_message
from storage import (
    load_subscribers_dict,
    save_subscribers_dict,
    ensure_user,
    can_receive_signal,
    mark_signal_sent,
    bump_stats,
    get_cooldown_seconds,
)
from telegram_bot import send_message, telegram_command_loop


# ================== PAIRS FILTER (VOLUME) ==================

def get_usdt_pairs_with_volume(min_volume: float, max_pairs: int) -> List[str]:
    """
    Ambil semua pair USDT yang statusnya TRADING,
    filter hanya yang 24h quoteVolume >= min_volume (USDT),
    lalu urutkan dari volume terbesar dan batasi max_pairs.
    """
    info_url = f"{BINANCE_REST_URL}/api/v3/exchangeInfo"
    r = requests.get(info_url, timeout=10)
    r.raise_for_status()
    info = r.json()

    usdt_symbols = []
    for s in info["symbols"]:
        if s["status"] == "TRADING" and s["quoteAsset"] == "USDT":
            usdt_symbols.append(s["symbol"])

    ticker_url = f"{BINANCE_REST_URL}/api/v3/ticker/24hr"
    r2 = requests.get(ticker_url, timeout=10)
    r2.raise_for_status()
    tickers = r2.json()

    vol_map: Dict[str, float] = {}
    for t in tickers:
        sym = t.get("symbol")
        if sym in usdt_symbols:
            try:
                qv = float(t.get("quoteVolume", "0"))  # dalam USDT
            except ValueError:
                qv = 0.0
            vol_map[sym] = qv

    filtered = [s for s in usdt_symbols if vol_map.get(s, 0.0) >= min_volume]
    filtered_sorted = sorted(filtered, key=lambda s: vol_map.get(s, 0.0), reverse=True)
    if max_pairs > 0:
        filtered_sorted = filtered_sorted[:max_pairs]

    symbols_lower = [s.lower() for s in filtered_sorted]
    print(f"Filter volume >= {min_volume:,.0f} USDT → {len(symbols_lower)} pair.")
    return symbols_lower


# ================== SCAN LOOP (WEBOSCKET) ==================

async def scan_loop(state) -> None:
    """
    - Refresh daftar pair (volume filter) periodik
    - Connect WebSocket kline_5m
    - Hanya saat state.scanning_enabled & not paused sinyal diproses
    - Analisa IPC & kirim sinyal ke admin + subscribers (free/vip)
    """
    symbols: List[str] = []
    last_pairs_refresh = 0.0
    refresh_interval = REFRESH_PAIR_INTERVAL_HOURS * 3600

    last_signal_time: Dict[str, float] = {}
    last_signal_entry: Dict[str, float] = {}
    recent_signal_ts: List[float] = []

    HEARTBEAT_TIMEOUT_SEC = 120
    last_tick_time = time.time()
    heartbeat_warned = False

    while True:
        try:
            now = time.time()
            if (
                not symbols
                or (now - last_pairs_refresh) > refresh_interval
                or getattr(state, "request_hard_restart", False)
            ):
                print("Refresh daftar pair USDT berdasarkan volume...")
                try:
                    symbols = get_usdt_pairs_with_volume(MIN_VOLUME_USDT, MAX_USDT_PAIRS)
                    last_pairs_refresh = time.time()
                    state.request_hard_restart = False
                    print(f"Scan {len(symbols)} pair:", ", ".join(s.upper() for s in symbols))

                    if TELEGRAM_ADMIN_ID:
                        send_message(
                            TELEGRAM_ADMIN_ID,
                            f"🔄 Pair list diperbarui.\nTotal pair: *{len(symbols)}* (volume >= {MIN_VOLUME_USDT:,.0f} USDT).",
                        )
                except Exception as e:
                    print("Gagal refresh pair:", e)
                    await asyncio.sleep(10)
                    continue

            if not symbols:
                print("Tidak ada pair yang memenuhi volume. Tunggu 60 detik...")
                await asyncio.sleep(60)
                continue

            # Kalau scan belum aktif, jangan buang-buang WS connect
            if not state.scanning_enabled:
                await asyncio.sleep(2)
                continue

            streams = "/".join([f"{s}@kline_5m" for s in symbols])
            ws_url = f"{BINANCE_STREAM_URL}?streams={streams}"

            print("Menghubungkan ke WebSocket...")
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                print("WebSocket terhubung.")
                if state.scanning_enabled and not state.paused:
                    print("Scan AKTIF → memantau sinyal IPC.")
                else:
                    print("Scan dalam mode PAUSE / STANDBY.\n")

                last_tick_time = time.time()
                heartbeat_warned = False

                while True:
                    # Soft/hard restart dari admin
                    if state.request_soft_restart or state.request_hard_restart:
                        print("Soft/Hard restart diminta, putuskan WebSocket & reconnect...")
                        state.request_soft_restart = False
                        break

                    # Pair refresh tiap interval
                    if time.time() - last_pairs_refresh > refresh_interval:
                        print("Interval pair refresh tercapai → refresh & reconnect...")
                        break

                    # Heartbeat check
                    now = time.time()
                    if now - last_tick_time > HEARTBEAT_TIMEOUT_SEC and not heartbeat_warned:
                        if TELEGRAM_ADMIN_ID:
                            send_message(
                                TELEGRAM_ADMIN_ID,
                                f"⚠ Tidak ada data market selama {HEARTBEAT_TIMEOUT_SEC} detik.\n"
                                "Kemungkinan gangguan koneksi atau Binance.",
                            )
                        heartbeat_warned = True

                    try:
                        msg = await ws.recv()
                        last_tick_time = time.time()
                        if heartbeat_warned:
                            if TELEGRAM_ADMIN_ID:
                                send_message(
                                    TELEGRAM_ADMIN_ID,
                                    "✅ Data market kembali diterima. Koneksi normal.",
                                )
                            heartbeat_warned = False
                    except websockets.ConnectionClosed:
                        print("WebSocket terputus. Reconnect dalam 5 detik...")
                        await asyncio.sleep(5)
                        break

                    data = json.loads(msg)
                    kline = data.get("data", {}).get("k", {})
                    if not kline:
                        continue

                    is_closed = kline.get("x", False)
                    symbol = kline.get("s", "").upper()
                    if not is_closed or not symbol:
                        continue

                    if not state.scanning_enabled or state.paused:
                        continue

                    # COOLDOWN per pair
                    cooldown_sec = get_cooldown_seconds()
                    now_ts = time.time()
                    last_ts = last_signal_time.get(symbol)
                    if last_ts and now_ts - last_ts < cooldown_sec:
                        continue

                    # ANALISA IPC
                    conditions, levels = analyse_symbol_ipc(symbol)
                    if not conditions or not levels:
                        continue

                    score = score_ipc_signal(conditions)
                    tier = tier_from_score(score)

                    if not should_send_tier(tier, state.min_tier):
                        continue

                    entry = levels.get("entry")
                    if entry is None:
                        continue

                    # anti-duplikat entry (0.1%)
                    prev_entry = last_signal_entry.get(symbol)
                    if prev_entry is not None:
                        diff = abs(entry - prev_entry) / max(prev_entry, 1e-9)
                        if diff < 0.001:
                            continue

                    text = build_ipc_signal_message(symbol, levels, conditions, score, tier)

                    # UPDATE trackers
                    last_signal_time[symbol] = now_ts
                    last_signal_entry[symbol] = entry
                    bump_stats(symbol)

                    # KIRIM KE ADMIN
                    if TELEGRAM_ADMIN_ID:
                        send_message(TELEGRAM_ADMIN_ID, text)

                    # KIRIM KE USER
                    subs = load_subscribers_dict()
                    changed = False
                    for cid_str, user in subs.items():
                        chat_id = int(cid_str)
                        # skip admin agar tidak dobel
                        if TELEGRAM_ADMIN_ID and chat_id == TELEGRAM_ADMIN_ID:
                            continue
                        if not can_receive_signal(user):
                            continue
                        send_message(chat_id, text)
                        mark_signal_sent(user)
                        changed = True

                    if changed:
                        save_subscribers_dict(subs)

                    print(f"[{symbol}] Sinyal dikirim: Score {score}, Tier {tier}")

        except Exception as e:
            print("Error di scan_loop:", e)
            await asyncio.sleep(5)


# ================== MAIN ==================

async def main():
    state = SimpleNamespace()
    state.scanning_enabled = False   # mulai standby
    state.paused = False
    state.request_soft_restart = False
    state.request_hard_restart = False
    state.min_tier = MIN_TIER_TO_SEND
    state.last_update_id = None

    # Pesan startup ke admin (mirip SMC intraday)
    if TELEGRAM_ADMIN_ID:
        send_message(
            TELEGRAM_ADMIN_ID,
            "✅ *IPC Intraday Signal Bot ONLINE*\n\n"
            "- Scan : *STANDBY*\n"
            f"- Min Tier : *{state.min_tier}*\n\n"
            "Gunakan *▶️ Start Scan* di panel admin untuk mulai scan market.",
        )

    task_tg = asyncio.create_task(telegram_command_loop(state))
    task_scan = asyncio.create_task(scan_loop(state))

    await asyncio.gather(task_tg, task_scan)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot dihentikan oleh user.")
