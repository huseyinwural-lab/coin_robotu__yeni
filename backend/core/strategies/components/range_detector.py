def detect_range_state(*, atr: float, volatility_compression: float, range_persistence: float) -> dict:
    atr_value = max(0.0, float(atr or 0.0))
    compression = max(0.0, min(1.0, float(volatility_compression or 0.0)))
    persistence = max(0.0, min(1.0, float(range_persistence or 0.0)))

    score = min(1.0, compression * 0.55 + persistence * 0.35 + (0.1 if atr_value < 0.012 else 0.0))
    if score >= 0.72:
        state = "RANGING"
    elif score >= 0.48:
        state = "MIXED"
    else:
        state = "TRENDING"

    return {
        "range_state": state,
        "range_confidence": round(score, 4),
    }
