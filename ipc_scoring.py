def score_ipc_signal(c: dict) -> int:
    """
    Skoring IPC (0 - 130)

    4 WAJIB (harus True):
    - trend_1h_bullish
    - struct_15m_bullish
    - pullback_healthy
    - anti_fake_break

    3 OPSIONAL (penguat):
    - impulse_strong
    - continuation_break
    - volume_strong
    """

    score = 0

    # ===== WAJIB (bobot besar) =====
    if c.get("trend_1h_bullish"):
        score += 30
    if c.get("struct_15m_bullish"):
        score += 30
    if c.get("pullback_healthy"):
        score += 30
    if c.get("anti_fake_break"):
        score += 20

    # ===== OPSIONAL (penguat) =====
    if c.get("impulse_strong"):
        score += 5
    if c.get("continuation_break"):
        score += 5
    if c.get("volume_strong"):
        score += 10

    return score


def tier_from_score(score: int) -> str:
    """
    Mapping score → Tier
    - A+ : >= 115
    - A  : 95–114
    - B  : 80–94
    - NONE : < 80
    """
    if score >= 115:
        return "A+"
    elif score >= 95:
        return "A"
    elif score >= 80:
        return "B"
    else:
        return "NONE"


def should_send_tier(tier: str, min_tier: str = "A") -> bool:
    """
    Hanya kirim sinyal minimal Tier tertentu (default A).
    Urutan: NONE < B < A < A+
    """
    order = {"NONE": 0, "B": 1, "A": 2, "A+": 3}
    return order.get(tier, 0) >= order.get(min_tier, 2)
