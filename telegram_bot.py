# telegram_bot.py

import asyncio
from typing import Any, Dict

import requests

from config import TELEGRAM_TOKEN, MAIN_ADMIN_ID
from storage import (
    load_subscribers,
    save_subscribers,
    ensure_user,
    is_vip,
    grant_vip,
    revoke_vip,
    get_cooldown_seconds,
    set_cooldown_seconds,
)


# ============ SEND MESSAGE ============

def send_message(chat_id: int, text: str, reply_keyboard: Dict[str, Any] | None = None) -> None:
    """
    Kirim pesan Telegram dengan optional reply keyboard.
    """
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN belum diset. Tidak bisa kirim pesan Telegram.")
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


# ============ REPLY KEYBOARDS ============

def build_user_keyboard() -> Dict[str, Any]:
    """
    Reply keyboard untuk USER.
    """
    return {
        "keyboard": [
            [{"text": "🏠 Home"}, {"text": "📊 Status Saya"}],
            [{"text": "🔔 Aktifkan Sinyal"}, {"text": "🔕 Nonaktifkan Sinyal"}],
            [{"text": "⭐ Upgrade VIP"}, {"text": "❓ Bantuan"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


def build_admin_keyboard() -> Dict[str, Any]:
    """
    Reply keyboard untuk ADMIN (versi lengkap).
    Susunan:
    🏠 Home   ▶ Start Scan   ⏸ Pause Scan
    ⛔ Stop Scan  📊 Status Bot  ⚙ Mode Tier
    🧭 Cooldown   ⭐ VIP Control  🔄 Restart Bot
    ❓ Help Admin
    """
    return {
        "keyboard": [
            [
                {"text": "🏠 Home"},
                {"text": "▶ Start Scan"},
                {"text": "⏸ Pause Scan"},
            ],
            [
                {"text": "⛔ Stop Scan"},
                {"text": "📊 Status Bot"},
                {"text": "⚙ Mode Tier"},
            ],
            [
                {"text": "🧭 Cooldown"},
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


# ============ TELEGRAM COMMAND LOOP ============

async def telegram_command_loop(state) -> None:
    """
    Loop utama untuk menangani perintah Telegram (admin & user) via getUpdates.

    Parameter:
        state: object sederhana (dari main.py) yang punya:
            - scanning_enabled: bool
            - paused: bool
            - request_soft_restart: bool
            - request_hard_restart: bool
            - awaiting_cooldown_input: bool
            - min_tier: str ("A" / "A+")
    """
    if not TELEGRAM_TOKEN:
        print("Telegram token tidak di-set, lewati telegram_command_loop.")
        return

    print("Telegram command loop start...")

    offset = 0
    # flags
    if not hasattr(state, "awaiting_cooldown_input"):
        state.awaiting_cooldown_input = False
    if not hasattr(state, "min_tier"):
        state.min_tier = "A"  # default kirim Tier A & A+

    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {
                "timeout": 30,
                "offset": offset + 1,
            }
            r = requests.get(url, params=params, timeout=35)
            if not r.ok:
                await asyncio.sleep(2)
                continue

            data = r.json()
            if not data.get("ok"):
                await asyncio.sleep(2)
                continue

            for update in data.get("result", []):
                offset = update["update_id"]

                # ---- message biasa ----
                if "message" in update:
                    msg = update["message"]
                    chat_id = msg["chat"]["id"]
                    text = (msg.get("text") or "").strip()
                    is_admin = (chat_id == MAIN_ADMIN_ID)

                    # load subscribers setiap update
                    subs = load_subscribers()
                    ensure_user(subs, chat_id)
                    user = subs[str(chat_id)]

                    # cek input cooldown (admin only)
                    if is_admin and state.awaiting_cooldown_input and text and text[0].isdigit():
                        try:
                            seconds = int(text)
                            if seconds <= 0:
                                raise ValueError
                            set_cooldown_seconds(seconds)
                            state.awaiting_cooldown_input = False
                            send_message(
                                chat_id,
                                f"🧭 Cooldown berhasil diatur ke *{seconds} detik*.",
                                reply_keyboard=build_admin_keyboard(),
                            )
                        except Exception:
                            send_message(
                                chat_id,
                                "Format tidak valid. Kirim angka dalam *detik*, misal: `300`",
                                reply_keyboard=build_admin_keyboard(),
                            )
                        save_subscribers(subs)
                        continue

                    # ========== ADMIN COMMANDS ==========
                    if is_admin:
                        # /start atau Home
                        if text.startswith("/start") or text == "🏠 Home":
                            send_message(
                                chat_id,
                                "👑 *IPC Intraday — ADMIN PANEL*\n\n"
                                "Bot siap. Gunakan menu di bawah untuk kontrol penuh.",
                                reply_keyboard=build_admin_keyboard(),
                            )

                        elif text.startswith("/helpadmin") or text == "❓ Help Admin" or text.startswith("/help"):
                            send_message(
                                chat_id,
                                "📘 *Help Admin*\n\n"
                                "- `▶ Start Scan` / /startscan  → mulai scan sinyal\n"
                                "- `⏸ Pause Scan` / /pausescan   → jeda kirim sinyal\n"
                                "- `⛔ Stop Scan` / /stopscan    → hentikan scan\n"
                                "- `🔄 Restart Bot` / /restart   → soft restart & reconnect\n"
                                "- `/hardrestart`               → hard restart + refresh pairs\n"
                                "- `🧭 Cooldown` / /cooldown    → ubah cooldown sinyal per pair\n"
                                "- `⚙ Mode Tier`               → toggle tier minimal (A / A+)\n"
                                "- `⭐ VIP Control`             → info /setvip & /unsetvip\n"
                                "- `📊 Status Bot` / /status    → lihat status bot & user\n",
                                reply_keyboard=build_admin_keyboard(),
                            )

                        elif text.startswith("/startscan") or text == "▶ Start Scan":
                            state.scanning_enabled = True
                            state.paused = False
                            send_message(
                                chat_id,
                                "▶ Scan dimulai. Bot memantau market untuk sinyal IPC.",
                                reply_keyboard=build_admin_keyboard(),
                            )

                        elif text.startswith("/pausescan") or text == "⏸ Pause Scan":
                            state.paused = True
                            send_message(
                                chat_id,
                                "⏸ Scan dijeda. Bot tidak akan mengirim sinyal sementara.",
                                reply_keyboard=build_admin_keyboard(),
                            )

                        elif text.startswith("/stopscan") or text == "⛔ Stop Scan":
                            state.scanning_enabled = False
                            state.paused = False
                            send_message(
                                chat_id,
                                "⛔ Scan dihentikan. Bot dalam mode siaga.",
                                reply_keyboard=build_admin_keyboard(),
                            )

                        elif text.startswith("/restart") or text == "🔄 Restart Bot":
                            state.request_soft_restart = True
                            send_message(
                                chat_id,
                                "🔄 Soft restart diminta. Bot akan reconnect & reset cooldown.",
                                reply_keyboard=build_admin_keyboard(),
                            )

                        elif text.startswith("/hardrestart"):
                            state.request_hard_restart = True
                            send_message(
                                chat_id,
                                "💥 Hard restart diminta. Bot akan refresh daftar pair & memulai ulang scan.",
                                reply_keyboard=build_admin_keyboard(),
                            )

                        elif text.startswith("/cooldown") or text == "🧭 Cooldown":
                            current_cd = get_cooldown_seconds()
                            send_message(
                                chat_id,
                                f"🧭 Cooldown saat ini: *{current_cd} detik*.\n"
                                "Kirim angka baru dalam *detik*, misal: `300`",
                                reply_keyboard=build_admin_keyboard(),
                            )
                            state.awaiting_cooldown_input = True

                        elif text.startswith("/status") or text == "📊 Status Bot":
                            scan_status = "AKTIF" if state.scanning_enabled else "NON-AKTIF"
                            mode = "PAUSE" if state.paused else "RUNNING"
                            cooldown_sec = get_cooldown_seconds()
                            total_users = len(subs)
                            vip_users = sum(1 for u in subs.values() if is_vip(u))
                            min_tier = getattr(state, "min_tier", "A")

                            send_message(
                                chat_id,
                                f"📊 *STATUS BOT IPC*\n\n"
                                f"- Scan      : *{scan_status}*\n"
                                f"- Mode      : *{mode}*\n"
                                f"- Min Tier  : *{min_tier}*\n"
                                f"- Cooldown  : *{cooldown_sec} detik*\n"
                                f"- Users     : *{total_users}*\n"
                                f"- VIP Users : *{vip_users}*",
                                reply_keyboard=build_admin_keyboard(),
                            )

                        elif text == "⚙ Mode Tier":
                            # toggle antara "A" dan "A+"
                            current = getattr(state, "min_tier", "A")
                            new_tier = "A+" if current == "A" else "A"
                            state.min_tier = new_tier
                            send_message(
                                chat_id,
                                f"⚙ Mode tier minimum diubah menjadi: *{new_tier}*.\n"
                                "Bot hanya akan mengirim sinyal dengan tier >= mode ini.",
                                reply_keyboard=build_admin_keyboard(),
                            )

                        elif text == "⭐ VIP Control":
                            total_users = len(subs)
                            vip_users = [cid for cid, u in subs.items() if is_vip(u)]
                            vip_count = len(vip_users)
                            vip_list_preview = ", ".join(vip_users[:5]) if vip_users else "-"

                            send_message(
                                chat_id,
                                "⭐ *VIP Control*\n\n"
                                f"- Total user   : *{total_users}*\n"
                                f"- Total VIP    : *{vip_count}*\n"
                                f"- Contoh VIP   : `{vip_list_preview}`\n\n"
                                "Perintah manual:\n"
                                "- `/setvip <chat_id>`   → aktifkan VIP\n"
                                "- `/unsetvip <chat_id>` → hapus VIP\n",
                                reply_keyboard=build_admin_keyboard(),
                            )

                        elif text.startswith("/setvip"):
                            parts = text.split()
                            if len(parts) < 2:
                                send_message(
                                    chat_id,
                                    "Usage: `/setvip <chat_id>`",
                                    reply_keyboard=build_admin_keyboard(),
                                )
                            else:
                                try:
                                    target_id = int(parts[1])
                                    grant_vip(subs, target_id)
                                    save_subscribers(subs)
                                    send_message(
                                        chat_id,
                                        f"⭐ VIP diaktifkan untuk user `{target_id}`.",
                                        reply_keyboard=build_admin_keyboard(),
                                    )
                                except Exception:
                                    send_message(
                                        chat_id,
                                        "Gagal set VIP. Pastikan chat_id berupa angka.",
                                        reply_keyboard=build_admin_keyboard(),
                                    )

                        elif text.startswith("/unsetvip"):
                            parts = text.split()
                            if len(parts) < 2:
                                send_message(
                                    chat_id,
                                    "Usage: `/unsetvip <chat_id>`",
                                    reply_keyboard=build_admin_keyboard(),
                                )
                            else:
                                try:
                                    target_id = int(parts[1])
                                    revoke_vip(subs, target_id)
                                    save_subscribers(subs)
                                    send_message(
                                        chat_id,
                                        f"⭐ VIP dihapus untuk user `{target_id}`.",
                                        reply_keyboard=build_admin_keyboard(),
                                    )
                                except Exception:
                                    send_message(
                                        chat_id,
                                        "Gagal unset VIP. Pastikan chat_id berupa angka.",
                                        reply_keyboard=build_admin_keyboard(),
                                    )

                        # simpan perubahan subscribers (jika ada)
                        save_subscribers(subs)
                        continue  # selesai handle admin, lanjut update berikutnya

                    # ========== USER COMMANDS (NON-ADMIN) ==========

                    # /start atau Home
                    if text.startswith("/start") or text == "🏠 Home":
                        user["active"] = True
                        save_subscribers(subs)
                        send_message(
                            chat_id,
                            "👋 *Selamat datang di IPC Intraday Signal Bot!*\n\n"
                            "Bot ini mengirim sinyal *lanjutan tren (continuation)* berbasis IPC.\n\n"
                            "- Mode Free  : max 2 sinyal/hari\n"
                            "- Mode VIP   : Unlimited sinyal (diatur admin)\n\n"
                            "Gunakan tombol di bawah untuk mengaktifkan / menonaktifkan sinyal.",
                            reply_keyboard=build_user_keyboard(),
                        )

                    elif text.startswith("/help") or text == "❓ Bantuan":
                        send_message(
                            chat_id,
                            "📘 *Bantuan User*\n\n"
                            "- `🔔 Aktifkan Sinyal`   : mulai menerima sinyal\n"
                            "- `🔕 Nonaktifkan Sinyal`: stop sinyal sementara\n"
                            "- `📊 Status Saya`       : lihat status akun (FREE/VIP, limit harian)\n"
                            "- `⭐ Upgrade VIP`        : info cara upgrade ke VIP\n\n"
                            "Free: 2 sinyal/hari. VIP: unlimited.",
                            reply_keyboard=build_user_keyboard(),
                        )

                    elif text.startswith("/activate") or text == "🔔 Aktifkan Sinyal":
                        user["active"] = True
                        save_subscribers(subs)
                        send_message(
                            chat_id,
                            "🔔 Sinyal *DI AKTIFKAN* untuk akun ini.",
                            reply_keyboard=build_user_keyboard(),
                        )

                    elif text.startswith("/deactivate") or text == "🔕 Nonaktifkan Sinyal":
                        user["active"] = False
                        save_subscribers(subs)
                        send_message(
                            chat_id,
                            "🔕 Sinyal *DI NONAKTIFKAN* untuk akun ini.",
                            reply_keyboard=build_user_keyboard(),
                        )

                    elif text.startswith("/status") or text == "📊 Status Saya":
                        vip_flag = is_vip(user)
                        mode = "VIP" if vip_flag else "FREE"
                        active = "AKTIF" if user.get("active", True) else "NON-AKTIF"
                        signals_today = user.get("signals_today", 0)
                        vip_exp = user.get("vip_expiry") or "-"

                        send_message(
                            chat_id,
                            f"📊 *STATUS AKUN*\n\n"
                            f"- Mode      : *{mode}*\n"
                            f"- Sinyal    : *{active}*\n"
                            f"- Hari ini  : *{signals_today}* sinyal\n"
                            f"- VIP Expiry: `{vip_exp}`",
                            reply_keyboard=build_user_keyboard(),
                        )

                    elif text == "⭐ Upgrade VIP":
                        send_message(
                            chat_id,
                            "⭐ *Upgrade VIP*\n\n"
                            "Untuk upgrade ke VIP (unlimited sinyal):\n"
                            "1. Hubungi admin bot.\n"
                            "2. Setelah pembayaran/konfirmasi, admin akan mengaktifkan VIP untuk akun Anda.\n\n"
                            "VIP cocok untuk trader yang ingin memantau lebih banyak pair & peluang.",
                            reply_keyboard=build_user_keyboard(),
                        )

                    # simpan perubahan user
                    save_subscribers(subs)

            await asyncio.sleep(0.5)

        except Exception as e:
            print("Error di telegram_command_loop:", e)
            await asyncio.sleep(2)
