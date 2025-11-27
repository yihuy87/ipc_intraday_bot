# main.py

import asyncio
import json
import time
from types import SimpleNamespace
from typing import Dict

import websockets

from config import (
    BINANCE_STREAM_URL,
    KLINE_TIMEFRAME,
    MIN_VOLUME_USD,
    REFRESH_PAIRS_EVERY_HOURS,
    MAIN_ADMIN_ID,
)
from ipc_logic import analyse_symbol_ipc
from ipc_scoring import score_ipc_signal, tier_from_score, should_send_tier
from signal_builder import build_ipc_signal_message
from storage import (
    load_subscribers,
    save_subscribers,
    ensure_user,
    can_receive_signal,
    mark_signal_sent,
)
from telegram_bot import send_message, telegram_command_loop
from volume_filter import get_usdt_pairs_with_volume


# ============ SCAN LOOP (WEBSOCKET) ============

async def scan_loop(state) -> None:
    """
    Loop utama untuk scan market via WebSocket Binance kline_5m.

    - Ambil daftar pair USDT yang memenuhi volume min (MIN_VOLUME_USD)
    - Connect ke stream kline_5m semua pair tersebut
    - Setiap candle 5m close -> analisa IPC
    - Kalau lolos 4 syarat wajib & skor >= tier minimal -> kirim sinyal ke admin & user
    """
    last_pairs_refresh = 0.0
    symbols: list[str] = []
    last_signal_times: Dict[str, float] = {}  # cooldown per symbol: { "btcusdt": timestamp }

    while True:
        try:
            now = time.time()

            # Refresh daftar pair jika:
            # - belum pernah ambil
            # - sudah lewat REFRESH_PAIRS_EVERY_HOURS
            # - admin minta hard restart
            if (
                not symbols
                or (now - last_pairs_refresh) > REFRESH_PAIRS_EVERY_HOURS * 3600
                or getattr(state, "request_hard_restart", False)
            ):
                print("Mengambil ulang daftar USDT pairs dengan filter volume...")
                try:
                    symbols = get_usdt_pairs_with_volume(MIN_VOLUME_USD)
                    last_pairs_refresh = time.time()
                    state.request_hard_restart = False
                    print(f"Scan {len(symbols)} pair (volume >= {MIN_VOLUME_USD} USDT):", ", ".join(s.upper() for s in symbols))

                    if MAIN_ADMIN_ID:
                        send_message(
                            MAIN_ADMIN_ID,
                            f"🔄 Pair list diperbarui.\nTotal pair: *{len(symbols)}* (volume >= {MIN_VOLUME_USD} USDT).",
                        )
                except Exception as e:
                    print("Gagal refresh pairs:", e)
                    await asyncio.sleep(10)
                    continue

            if not symbols:
                print("Tidak ada pair yang memenuhi volume. Tunggu 60 detik...")
                await asyncio.sleep(60)
                continue

            # Jika scanning tidak diaktifkan -> tunggu
            if not state.scanning_enabled:
                await asyncio.sleep(2)
                continue

            # Build multi-stream URL
            streams = "/".join([f"{s}@kline_{KLINE_TIMEFRAME}" for s in symbols])
            ws_url = f"{BINANCE_STREAM_URL}?streams={streams}"

            print("Menghubungkan ke WebSocket...")
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                print("WebSocket tersambung. Scan loop aktif.\n")

                while True:
                    # Handle restart dari admin
                    if state.request_soft_restart or state.request_hard_restart:
                        print("Soft/Hard restart diminta, putuskan WebSocket & reconnect...")
                        state.request_soft_restart = False
                        # Hard restart akan di-handle di awal loop (refresh pairs)
                        break  # keluar dari inner-while, reconnect

                    # Jika scan dimatikan sementara -> tidak memproses sinyal, tapi koneksi tetap
                    if not state.scanning_enabled:
                        await asyncio.sleep(1)
                        continue

                    if state.paused:
                        await asyncio.sleep(1)
                        continue

                    try:
                        msg = await ws.recv()
                    except websockets.ConnectionClosed:
                        print("WebSocket terputus. Reconnect dalam 5 detik...")
                        await asyncio.sleep(5)
                        break  # reconnect

                    data = json.loads(msg)

                    kline = data.get("data", {}).get("k", {})
                    if not kline:
                        continue

                    is_closed = kline.get("x", False)
                    symbol = kline.get("s", "").upper()

                    if not is_closed or not symbol:
                        continue

                    sym_lower = symbol.lower()
                    print(f"[{time.strftime('%H:%M:%S')}] 5m close: {symbol}")

                    # ====== ANALISA IPC UNTUK SYMBOL INI ======
                    conditions, levels = analyse_symbol_ipc(symbol)
                    if not conditions or not levels:
                        continue

                    # Skoring & tier
                    score = score_ipc_signal(conditions)
                    min_tier = getattr(state, "min_tier", "A")
                    tier = tier_from_score(score)

                    if not should_send_tier(tier, min_tier):
                        continue

                    # Cooldown per pair
                    from storage import get_cooldown_seconds
                    cooldown_sec = get_cooldown_seconds()
                    now_ts = time.time()
                    last_ts = last_signal_times.get(sym_lower, 0.0)
                    if now_ts - last_ts < cooldown_sec:
                        # Masih cooldown
                        continue

                    # Lolos semua filter -> siap kirim sinyal
                    from signal_builder import build_ipc_signal_message
                    text = build_ipc_signal_message(symbol, levels, conditions, score, tier)

                    # Update waktu terakhir sinyal pair ini
                    last_signal_times[sym_lower] = now_ts

                    # ====== KIRIM KE ADMIN ======
                    if MAIN_ADMIN_ID:
                        send_message(MAIN_ADMIN_ID, text)

                    # ====== KIRIM KE USER (FREE/VIP) ======
                    subs = load_subscribers()
                    changed = False

                    for cid_str, user in subs.items():
                        try:
                            chat_id = int(cid_str)
                        except Exception:
                            continue

                        # Jika mau admin tidak double terima, bisa skip di sini:
                        # if chat_id == MAIN_ADMIN_ID: continue

                        if not user.get("active", True):
                            continue

                        if not can_receive_signal(user):
                            continue

                        send_message(chat_id, text)
                        mark_signal_sent(user)
                        changed = True

                    if changed:
                        save_subscribers(subs)

        except Exception as e:
            print("Error di scan_loop:", e)
            await asyncio.sleep(5)


# ============ MAIN ENTRYPOINT ============

async def main():
    """
    Entry point:
    - buat state object
    - jalankan telegram_command_loop & scan_loop bersamaan
    """
    state = SimpleNamespace()
    state.scanning_enabled = False  # mulai dari mode siaga
    state.paused = False
    state.request_soft_restart = False
    state.request_hard_restart = False
    state.awaiting_cooldown_input = False
    state.min_tier = "A"  # minimal Tier untuk dikirim (A / A+)

    # Jalankan 2 task:
    task_telegram = asyncio.create_task(telegram_command_loop(state))
    task_scan = asyncio.create_task(scan_loop(state))

    await asyncio.gather(task_telegram, task_scan)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot dihentikan oleh user.")
