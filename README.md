# 📈 IPC Intraday Signal Bot

Bot sinyal trading otomatis berbasis **Institutional Price Concepts (IPC)**.  
Menggunakan Binance WebSocket + Telegram Bot API untuk mendeteksi sinyal secara realtime.

---

## 🚀 Fitur Utama
- Deteksi sinyal IPC lengkap (1H Bias, 15m Struktur, PD Array, Context).
- Confluence tambahan: FVG, Breaker, Liquidity, Volume Strength, Prepump.
- Filter pair otomatis (≥ 6M volume).
- Sistem Free User (2 sinyal/hari) & VIP User (Unlimited).
- Panel Admin lengkap (Start, Pause, Stop, Cooldown, VIP Control, Restart).
- Auto-Reconnect WebSocket jika terputus.
- Auto-refresh pair setiap 24 jam.
- Format sinyal rapi + checklist IPC.

---

## 🗂 Struktur Project
```
main.py
config.py
ipc_logic.py
ipc_scoring.py
signal_builder.py
telegram_bot.py
volume_filter.py
storage.py
utils.py
data/
  ├── subscribers.json
  ├── vip.json
  ├── cooldown.json
logs/
.env
.env.example
```

---

## ⚙️ Instalasi Singkat (VPS)
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip -y

git clone <repo-link>
cd IPC-Intraday-Bot

pip3 install -r requirements.txt

cp .env.example .env
```

Edit file `.env` isi:
```
TELEGRAM_TOKEN=
MAIN_ADMIN_ID=
```

---

## ▶️ Menjalankan Bot
Normal:
```bash
python3 main.py
```

Jalan terus di background:
```bash
nohup python3 main.py &
```

Stop background (jika perlu):
```bash
pkill -f main.py
```

---

## 📱 Pengaturan Bot via BotFather
**Name:** IPC Intraday Signal Bot  
**Description:** Bot sinyal IPC realtime. Free: 2 sinyal/hari. VIP: unlimited.

### Commands untuk User
```
start - Mulai bot
status - Status akun saya
activate - Aktifkan sinyal
deactivate - Nonaktifkan sinyal
upgrade - Info VIP
help - Bantuan
```

### Commands untuk Admin
```
admin - Panel admin
startscan - Mulai scan
pausescan - Jeda scan
stopscan - Stop scan
restart - Soft restart
hardrestart - Restart penuh
cooldown - Atur jeda sinyal
setvip - Jadikan user VIP
unsetvip - Hapus VIP user
helpadmin - Bantuan admin
```

---

## ⭐ Sistem VIP
- VIP disimpan di `data/vip.json`
- Admin dapat promote/demote VIP
- VIP otomatis expired ketika waktu habis

---

## 🔐 Keamanan
- Token & API key hanya disimpan di `.env`
- `.env` sudah masuk `.gitignore` (aman)
- Jangan share folder `data/` ke publik

---

## 🎯 Catatan Penting
Bot **hanya mengirim sinyal IPC jika seluruh syarat Wajib terpenuhi**.  
Checklist non-wajib hanya memperkuat kualitas sinyal.

---

## 🧩 Lisensi
Proyek ini bebas dipakai pribadi atau komersial sesuai kebutuhan Anda.
