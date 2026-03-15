from collections import Counter

from services.pipeline.cache_store import get_json


def _score_symbol_event(cache, symbol: str, *, position_activity: bool = False) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    candle_close = get_json(cache, f"event:candle_close:{symbol}") or {}
    if bool(candle_close.get("closed", False)):
        score += 3
        reasons.append("candle_close")

    volume_spike = get_json(cache, f"event:volume_spike:{symbol}") or {}
    if bool(volume_spike.get("active", False)):
        score += 3
        reasons.append("volume_spike")

    spread_state = get_json(cache, f"market:spread:{symbol}") or {}
    spread_bps = float(spread_state.get("spread_bps") or 0.0)
    if spread_bps >= 30:
        score += 2
        reasons.append("spread_jump")

    if position_activity:
        score += 2
        reasons.append("position_activity")

    return score, reasons


def build_event_priority_distribution(cache, symbols: list[str], *, position_activity: bool = False) -> dict:
    normalized = [str(item or "").upper().strip() for item in symbols if str(item or "").strip()]
    levels = Counter()
    rows = []

    for symbol in normalized:
        score, reasons = _score_symbol_event(cache, symbol, position_activity=position_activity)
        if score >= 6:
            level = "high"
        elif score >= 3:
            level = "medium"
        else:
            level = "low"
        levels[level] += 1
        rows.append({"symbol": symbol, "score": score, "level": level, "reasons": reasons})

    rows.sort(key=lambda item: (item["score"], item["symbol"]), reverse=True)
    return {
        "distribution": {
            "high": int(levels.get("high", 0)),
            "medium": int(levels.get("medium", 0)),
            "low": int(levels.get("low", 0)),
        },
        "top_priority_symbols": rows[:25],
    }
