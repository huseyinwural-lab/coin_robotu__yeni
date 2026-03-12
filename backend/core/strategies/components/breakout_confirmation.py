def confirm_breakout(
    *,
    latest_price: float,
    range_high: float,
    range_low: float,
    volume_spike_ratio: float,
    microstructure_suitable: bool,
) -> dict:
    price = float(latest_price or 0.0)
    high = float(range_high or 0.0)
    low = float(range_low or 0.0)
    volume_ratio = float(volume_spike_ratio or 0.0)

    side = "NONE"
    if high > 0 and price > high:
        side = "LONG"
    elif low > 0 and price < low:
        side = "SHORT"

    volume_ok = volume_ratio >= 1.15
    confirmed = side != "NONE" and volume_ok and bool(microstructure_suitable)
    confidence = 0.0
    if confirmed:
        confidence = min(0.95, 0.52 + min(volume_ratio, 2.0) * 0.18)

    return {
        "breakout_side": side,
        "volume_confirmation": volume_ok,
        "confirmed": confirmed,
        "confidence": round(confidence, 4),
    }
