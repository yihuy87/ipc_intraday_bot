# telegram_bot.py

import asyncio
from typing import Any, Dict

import requests

from config import TELEGRAM_TOKEN, TELEGRAM_ADMIN_ID, TELEGRAM_ADMIN_USERNAME
from storage import (
    load_subscribers_dict,
    save_subscribers_dict,
    ensure_user,
    is_vip,
    grant_vip_days,
    revoke_vip,
    get_cooldown_seconds,
    set_cooldown_seconds,
    can_receive_signal,
    clear_pause,
    set_pause_24h,
    load_stats,
)


def is_admin(chat_id: int) -> bool:
    return TELEGRAM_ADMIN_ID and int(chat_id) == int(TELEGRAM_ADMIN_ID)


# ============ SEND MESSAGE ============

def send_message(chat_id: int, text: str, reply_keyboard: Dict[str, Any] | None = None) -> None:
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN belum di-set.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if reply_keyboard:
        payload["reply_markup"] = reply_keyboard

    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok:
            print("Gagal kirim Telegram:", r.text)
    except Exception as e:
        print("Error kirim Telegram:", e)


# ============ KEYBOARD ============

def build_user_keyboard() -> Dict[str, Any]:
    return {
        "keyboard": [
            [
                {"text": "🏠 Home"},
                {"text": "📊 Status Saya"},
            ],
            [
                {"text": "🔔 Aktifkan Sinyal"},
                {"text": "🔕 Nonaktifkan Sinyal"},
            ],
            [
                {"text": "⏱ Pause 24 Jam"},
                {"text": "⭐ Upgrade VIP"},
            ],
            [
                {"text": "❓ Bantuan"},
            ],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


def build_admin_keyboard() -> Dict[str, Any]:
    return {
        "keyboard": [
            [
                {"text": "🏠 Home"},
                {"text": "▶️ Start Scan"},
                {"text": "⏸️ Pause Scan"},
            ],
            [
                {"text": "⛔ Stop Scan"},
                {"text": "📊 Status Bot"},
                {"text": "⚙️ Mode Tier"},
            ],
            [
                {"text": "⏲️ Cooldown"},
                {"text": "⭐ VIP Control"},
                {"text": "🔄 Restart Bot"},
            ],
            [
                {"text": "❓ Help Admin"},
            ],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


# ============ TELEGRAM LOOP (GET UPDATES) ============

async def telegram_command_loop(state) -> None:
    """
    state:
      - scanning_enabled: bool
      - paused: bool
      - request_soft_restart: bool
      - request_hard_restart: bool
      - awaiting_cooldown_input: bool
      - min_tier: str
      - last_update_id: int | None
    """
    if not TELEGRAM_TOKEN:
        print("Tidak ada TELEGRAM_TOKEN, telegram_command_loop dilewati.")
        return

    print("Telegram command loop start...")
    base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    get_updates_url = f"{base_url}/getUpdates"

    # sync awal: skip pesan lama
    try:
        r = requests.get(get_updates_url, timeout=20)
        if r.ok:
            data = r.json()
            results = data.get("result", [])
            if results:
                state.last_update_id = results[-1]["update_id"]
                print(f"Sync Telegram: skip {len(results)} pesan lama.")
    except Exception as e:
        print("Error sync awal Telegram:", e)

    if not hasattr(state, "awaiting_cooldown_input"):
        state.awaiting_cooldown_input = False
    if not hasattr(state, "min_tier"):
        state.min_tier = "A"

    while True:
        try:
            params = {}
            if state.last_update_id is not None:
                params["offset"] = state.last_update_id + 1

            r = requests.get(get_updates_url, params=params, timeout=35)
            if not r.ok:
                print("Error getUpdates:", r.text)
                await asyncio.sleep(2)
                continue

            data = r.json()

            for upd in data.get("result", []):
                state.last_update_id = upd["update_id"]

                # MESSAGE
                msg = upd.get("message")
                if msg:
                    chat_id = msg["chat"]["id"]
                    text = (msg.get("text") or "").strip()
                    subs = load_subscribers_dict()
                    ensure_user(subs, chat_id)
                    user = subs[str(chat_id)]

                    # admin?
                    admin_flag = is_admin(chat_id)

                    # COOLDOWN INPUT (ADMIN)
                    if admin_flag and state.awaiting_cooldown_input and text and text[0].isdigit():
                        try:
                            sec = int(text)
                            if sec <= 0:
                                raise ValueError
                            set_cooldown_seconds(sec)
                            state.awaiting_cooldown_input = False
                            send_message(
                                chat_id,
                                f"⏲️ Cooldown diatur menjadi *{sec} detik*.",
                                reply_keyboard=build_admin_keyboard(),
                            )
                        except Exception:
                            send_message(
                                chat_id,
                                "Format tidak valid. Kirim angka detik, misal `300`.",
                                reply_keyboard=build_admin_keyboard(),
                            )
                        save_subscribers_dict(subs)
                        continue

                    # ========== ADMIN ==========
                    if admin_flag:
                        # tombol "Home" atau /start
                        if text.startswith("/start") or text == "🏠 Home":
                            stats = load_stats()
                            scan_status = "AKTIF" if state.scanning_enabled else "STANDBY"
                            mode = "PAUSE" if state.paused else "RUNNING"
                            send_message(
                                chat_id,
                                "👑 *IPC INTRADAY — ADMIN PANEL*\n\n"
                                f"• Scan   : *{scan_status}* ({mode})\n"
                                f"• MinTier: *{state.min_tier}*\n"
                                f"• Today  : *{stats.get('signals_today_total', 0)}* sinyal\n"
                                f"• Total  : *{stats.get('total_signals', 0)}* sinyal\n"
                                f"• Last   : `{stats.get('last_symbol')}`\n",
                                reply_keyboard=build_admin_keyboard(),
                            )
                        elif text == "▶️ Start Scan" or text.startswith("/startscan"):
                            if not state.scanning_enabled:
                                state.scanning_enabled = True
                                state.paused = False
                                send_message(
                                    chat_id,
                                    "▶️ Scan market *dimulai*. Bot mulai memantau sinyal IPC.",
                                    reply_keyboard=build_admin_keyboard(),
                                )
                            elif state.paused:
                                state.paused = False
                                send_message(
                                    chat_id,
                                    "▶️ Scan *dilanjutkan* dari mode pause.",
                                    reply_keyboard=build_admin_keyboard(),
                                )
                            else:
                                send_message(
                                    chat_id,
                                    "ℹ️ Scan sudah *AKTIF*. Tidak ada perubahan.",
                                    reply_keyboard=build_admin_keyboard(),
                                )
                        elif text == "⏸️ Pause Scan" or text.startswith("/pausescan"):
                            if not state.scanning_enabled:
                                send_message(
                                    chat_id,
                                    "ℹ️ Scan belum aktif, tidak ada yang perlu dijeda.",
                                    reply_keyboard=build_admin_keyboard(),
                                )
                            elif state.paused:
                                send_message(
                                    chat_id,
                                    "ℹ️ Scan sudah dalam mode *PAUSE*.",
                                    reply_keyboard=build_admin_keyboard(),
                                )
                            else:
                                state.paused = True
                                send_message(
                                    chat_id,
                                    "⏸️ Scan market *dijeda* (bot tetap online).",
                                    reply_keyboard=build_admin_keyboard(),
                                )
                        elif text == "⛔ Stop Scan" or text.startswith("/stopscan"):
                            if not state.scanning_enabled and not state.paused:
                                send_message(
                                    chat_id,
                                    "ℹ️ Scan sudah *NON-AKTIF*.",
                                    reply_keyboard=build_admin_keyboard(),
                                )
                            else:
                                state.scanning_enabled = False
                                state.paused = False
                                send_message(
                                    chat_id,
                                    "⛔ Scan *dihentikan total.* Bot masuk mode standby.",
                                    reply_keyboard=build_admin_keyboard(),
                                )
                        elif text == "📊 Status Bot" or text.startswith("/status"):
                            cooldown = get_cooldown_seconds()
                            stats = load_stats()
                            total_users = len(subs)
                            vip_users = sum(1 for u in subs.values() if is_vip(u))
                            scan_status = "AKTIF" if state.scanning_enabled else "STANDBY"
                            mode = "PAUSE" if state.paused else "RUNNING"
                            send_message(
                                chat_id,
                                "📊 *STATUS BOT IPC*\n\n"
                                f"• Scan      : *{scan_status}* ({mode})\n"
                                f"• Min Tier  : *{state.min_tier}*\n"
                                f"• Cooldown  : *{cooldown} detik*\n"
                                f"• Users     : *{total_users}*\n"
                                f"• VIP Users : *{vip_users}*\n\n"
                                f"• Today     : *{stats.get('signals_today_total', 0)}* sinyal\n"
                                f"• Total     : *{stats.get('total_signals', 0)}* sinyal\n"
                                f"• Last pair : `{stats.get('last_symbol')}`\n"
                                f"• Last time : `{stats.get('last_signal_time')}`",
                                reply_keyboard=build_admin_keyboard(),
                            )
                        elif text == "⚙️ Mode Tier" or text.startswith("/mode"):
                            # toggle A <-> A+
                            current = state.min_tier
                            if current == "A":
                                new_tier = "A+"
                            else:
                                new_tier = "A"
                            state.min_tier = new_tier
                            send_message(
                                chat_id,
                                f"⚙️ Min Tier diubah menjadi *{new_tier}*.\n"
                                "Hanya sinyal dengan tier >= ini yang dikirim.",
                                reply_keyboard=build_admin_keyboard(),
                            )
                        elif text == "⏲️ Cooldown" or text.startswith("/cooldown"):
                            current = get_cooldown_seconds()
                            send_message(
                                chat_id,
                                f"⏲️ Cooldown saat ini: *{current} detik*.\n"
                                "Kirim angka baru dalam detik (contoh: `300`).",
                                reply_keyboard=build_admin_keyboard(),
                            )
                            state.awaiting_cooldown_input = True
                        elif text == "⭐ VIP Control":
                            total_users = len(subs)
                            vip_ids = [cid for cid, u in subs.items() if is_vip(u)]
                            vip_count = len(vip_ids)
                            preview = ", ".join(vip_ids[:5]) if vip_ids else "-"
                            send_message(
                                chat_id,
                                "⭐ *VIP CONTROL*\n\n"
                                f"• Total user : *{total_users}*\n"
                                f"• Total VIP  : *{vip_count}*\n"
                                f"• Contoh VIP : `{preview}`\n\n"
                                "Perintah:\n"
                                "`/addvip <chat_id> [hari]`\n"
                                "`/removevip <chat_id>`",
                                reply_keyboard=build_admin_keyboard(),
                            )
                        elif text == "🔄 Restart Bot":
                            send_message(
                                chat_id,
                                "🔄 Soft restart diminta.\n"
                                "Bot akan reconnect & melanjutkan scan dengan pengaturan sekarang.",
                                reply_keyboard=build_admin_keyboard(),
                            )
                            state.request_soft_restart = True
                        elif text == "❓ Help Admin" or text.startswith("/helpadmin"):
                            send_message(
                                chat_id,
                                "📖 *BANTUAN ADMIN*\n\n"
                                "▶️ Start Scan  — mulai / lanjut scan\n"
                                "⏸️ Pause Scan  — jeda scan sementara\n"
                                "⛔ Stop Scan   — stop scan total\n"
                                "📊 Status Bot  — lihat status & statistik\n"
                                "⚙️ Mode Tier   — toggle A / A+\n"
                                "⏲️ Cooldown    — atur jarak sinyal\n"
                                "⭐ VIP Control  — kelola VIP\n"
                                "🔄 Restart Bot — soft restart engine\n",
                                reply_keyboard=build_admin_keyboard(),
                            )
                        elif text.startswith("/addvip"):
                            parts = text.split()
                            if len(parts) < 2:
                                send_message(
                                    chat_id,
                                    "Gunakan: `/addvip <chat_id> [hari]`",
                                    reply_keyboard=build_admin_keyboard(),
                                )
                            else:
                                try:
                                    target = int(parts[1])
                                    days = int(parts[2]) if len(parts) > 2 else 30
                                    grant_vip_days(subs, target, days)
                                    save_subscribers_dict(subs)
                                    send_message(
                                        chat_id,
                                        f"⭐ VIP diaktifkan untuk `{target}` selama {days} hari.",
                                        reply_keyboard=build_admin_keyboard(),
                                    )
                                    send_message(
                                        target,
                                        f"🎉 VIP kamu diaktifkan selama {days} hari.\n"
                                        "Sinyal kamu sekarang *unlimited* per hari.",
                                    )
                                except Exception:
                                    send_message(
                                        chat_id,
                                        "Format salah. Contoh: `/addvip 123456789 30`",
                                        reply_keyboard=build_admin_keyboard(),
                                    )
                        elif text.startswith("/removevip"):
                            parts = text.split()
                            if len(parts) < 2:
                                send_message(
                                    chat_id,
                                    "Gunakan: `/removevip <chat_id>`",
                                    reply_keyboard=build_admin_keyboard(),
                                )
                            else:
                                try:
                                    target = int(parts[1])
                                    revoke_vip(subs, target)
                                    save_subscribers_dict(subs)
                                    send_message(
                                        chat_id,
                                        f"VIP user `{target}` dihapus.",
                                        reply_keyboard=build_admin_keyboard(),
                                    )
                                    send_message(
                                        target,
                                        "VIP kamu telah dinonaktifkan. Kembali ke paket FREE.",
                                    )
                                except Exception:
                                    send_message(
                                        chat_id,
                                        "Format salah. Contoh: `/removevip 123456789`",
                                        reply_keyboard=build_admin_keyboard(),
                                    )

                        save_subscribers_dict(subs)
                        continue  # admin done, lanjut update berikutnya

                    # ========== USER (NON ADMIN) ==========

                    # /start atau Home
                    if text.startswith("/start") or text == "🏠 Home":
                        user["active"] = True
                        clear_pause(user)
                        save_subscribers_dict(subs)
                        pkg = "VIP" if is_vip(user) else "FREE"
                        limit = "Unlimited" if is_vip(user) else "2 sinyal/hari"
                        send_message(
                            chat_id,
                            "🟦 *IPC INTRADAY SIGNAL BOT*\n\n"
                            "Bot ini mengirim sinyal *intraday continuation* berbasis model IPC "
                            "(1H Bias, 15m Structure, 5m Trigger).\n\n"
                            f"Status akun:\n"
                            f"• Paket : *{pkg}*\n"
                            f"• Limit : *{limit}*\n\n"
                            "Gunakan tombol di bawah untuk mengelola sinyal.",
                            reply_keyboard=build_user_keyboard(),
                        )
                    elif text == "🔔 Aktifkan Sinyal" or text.startswith("/activate"):
                        if user.get("active", True) and not user.get("pause_until"):
                            send_message(
                                chat_id,
                                "ℹ️ Sinyal sudah *AKTIF* untuk akun ini.",
                                reply_keyboard=build_user_keyboard(),
                            )
                        else:
                            user["active"] = True
                            clear_pause(user)
                            save_subscribers_dict(subs)
                            send_message(
                                chat_id,
                                "🔔 Sinyal *diaktifkan* untuk akun ini.",
                                reply_keyboard=build_user_keyboard(),
                            )
                    elif text == "🔕 Nonaktifkan Sinyal" or text.startswith("/deactivate"):
                        if not user.get("active", True):
                            send_message(
                                chat_id,
                                "ℹ️ Sinyal sudah *NON-AKTIF* untuk akun ini.",
                                reply_keyboard=build_user_keyboard(),
                            )
                        else:
                            user["active"] = False
                            clear_pause(user)
                            save_subscribers_dict(subs)
                            send_message(
                                chat_id,
                                "🔕 Sinyal *dinonaktifkan* untuk akun ini.",
                                reply_keyboard=build_user_keyboard(),
                            )
                    elif text == "⏱ Pause 24 Jam":
                        set_pause_24h(user)
                        user["active"] = True
                        save_subscribers_dict(subs)
                        send_message(
                            chat_id,
                            "⏱ Sinyal *dijeda 24 jam*.\n"
                            "Setelah itu, sinyal akan aktif otomatis.",
                            reply_keyboard=build_user_keyboard(),
                        )
                    elif text == "📊 Status Saya" or text.startswith("/status"):
                        vip_flag = is_vip(user)
                        mode = "VIP" if vip_flag else "FREE"
                        signals_today = user.get("signals_today", 0)
                        vip_exp = user.get("vip_expiry") or "-"
                        pause_until = user.get("pause_until")
                        if pause_until:
                            pause_info = f"PAUSE sampai `{pause_until}`"
                        else:
                            pause_info = "Tidak ada pause aktif."

                        active_text = "AKTIF" if user.get("active", True) and not pause_until else "NON-AKTIF/PAUSE"

                        send_message(
                            chat_id,
                            "📊 *STATUS AKUN*\n\n"
                            f"• Mode      : *{mode}*\n"
                            f"• Sinyal    : *{active_text}*\n"
                            f"• Today     : *{signals_today}* sinyal\n"
                            f"• VIP Expiry: `{vip_exp}`\n"
                            f"• Pause     : {pause_info}\n"
                            f"• User ID   : `{chat_id}`",
                            reply_keyboard=build_user_keyboard(),
                        )
                    elif text == "⭐ Upgrade VIP":
                        send_message(
                            chat_id,
                            "⭐ *UPGRADE KE VIP*\n\n"
                            "Paket VIP memberikan:\n"
                            "• Sinyal *unlimited* setiap hari\n"
                            "• Fokus pada tier tinggi\n\n"
                            "Hubungi admin untuk upgrade:\n"
                            f"`{TELEGRAM_ADMIN_USERNAME}` (kirim /status untuk info akun).",
                            reply_keyboard=build_user_keyboard(),
                        )
                    elif text == "❓ Bantuan" or text.startswith("/help"):
                        send_message(
                            chat_id,
                            "📖 *BANTUAN USER IPC*\n\n"
                            "🔔 Aktifkan Sinyal — hidupkan sinyal.\n"
                            "🔕 Nonaktifkan Sinyal — matikan sinyal.\n"
                            "⏱ Pause 24 Jam — jeda sinyal sementara.\n"
                            "📊 Status Saya — lihat paket & limit.\n"
                            "⭐ Upgrade VIP — info upgrade.\n",
                            reply_keyboard=build_user_keyboard(),
                        )

                    save_subscribers_dict(subs)

            await asyncio.sleep(0.5)

        except Exception as e:
            print("Error di telegram_command_loop:", e)
            await asyncio.sleep(2)
