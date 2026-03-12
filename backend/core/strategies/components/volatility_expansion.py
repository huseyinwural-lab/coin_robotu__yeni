def detect_volatility_expansion(*, atr_current: float, atr_baseline: float, compression_state: float) -> dict:
    current = max(float(atr_current or 0.0), 0.00001)
    baseline = max(float(atr_baseline or 0.0), 0.00001)
    compression = max(0.0, min(1.0, float(compression_state or 0.0)))

    expansion_ratio = current / baseline
    expansion_score = min(1.0, (expansion_ratio - 1.0) * 0.7 + compression * 0.4)

    if expansion_score >= 0.72:
        state = "EXPANSION_CONFIRMED"
    elif expansion_score >= 0.5:
        state = "EXPANSION_BUILDING"
    else:
        state = "NO_EXPANSION"

    return {
        "expansion_state": state,
        "expansion_ratio": round(expansion_ratio, 4),
        "expansion_score": round(expansion_score, 4),
    }
