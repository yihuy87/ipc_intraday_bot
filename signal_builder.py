from typing import Dict


def _mark(flag: bool) -> str:
    return "✅" if flag else "❌"


def build_ipc_signal_message(
    symbol: str,
    levels: Dict[str, float],
    conditions: Dict[str, bool],
    score: int,
    tier: str,
) -> str:
    """
    Bangun teks sinyal IPC sesuai format yang kamu mau.
    """

    entry = levels.get("entry", 0.0)
    sl = levels.get("sl", 0.0)
    tp1 = levels.get("tp1", 0.0)
    tp2 = levels.get("tp2", 0.0)
    tp3 = levels.get("tp3", 0.0)

    text = f"""🟦 IPC INTRADAY CONTINUATION SIGNAL — {symbol.upper()}

IPC SCORE: {score}/130 — Tier {tier}

💰 Harga
• Entry : {entry:.6f}
• SL    : {sl:.6f}
• TP1   : {tp1:.6f}
• TP2   : {tp2:.6f}
• TP3   : {tp3:.6f}

📌 Checklist Wajib
• Trend 1H          : {_mark(conditions.get("trend_1h_bullish", False))}
• Struktur 15m      : {_mark(conditions.get("struct_15m_bullish", False))}
• Pullback sehat    : {_mark(conditions.get("pullback_healthy", False))}
• Anti-fake break   : {_mark(conditions.get("anti_fake_break", False))}

📌 Checklist Penguat
• Impulse kuat      : {_mark(conditions.get("impulse_strong", False))}
• Break lanjut      : {_mark(conditions.get("continuation_break", False))}
• Volume kuat       : {_mark(conditions.get("volume_strong", False))}

📝 Catatan
Free: maksimal 2 sinyal/hari. VIP: Unlimited sinyal.
"""
    return text
