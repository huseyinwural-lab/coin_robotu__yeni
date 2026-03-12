def detect_deviation_signal(*, latest_price: float, range_mean: float, atr: float, range_state: str) -> dict:
    price = float(latest_price or 0.0)
    mean = float(range_mean or 0.0)
    atr_value = max(float(atr or 0.0), 0.00001)
    state = (range_state or "TRENDING").upper()

    if mean <= 0:
        return {
            "mean_reversion_signal": "NONE",
            "confidence": 0.0,
            "normalized_distance": 0.0,
        }

    distance = (price - mean) / mean
    normalized_distance = abs(distance) / atr_value
    if state != "RANGING" and normalized_distance < 1.2:
        return {
            "mean_reversion_signal": "NONE",
            "confidence": 0.0,
            "normalized_distance": round(normalized_distance, 4),
        }

    if distance >= 0.007 and normalized_distance >= 1.0:
        side = "SHORT"
    elif distance <= -0.007 and normalized_distance >= 1.0:
        side = "LONG"
    else:
        side = "NONE"

    confidence = 0.0 if side == "NONE" else min(0.95, 0.45 + normalized_distance * 0.22)
    return {
        "mean_reversion_signal": side,
        "confidence": round(confidence, 4),
        "normalized_distance": round(normalized_distance, 4),
    }
