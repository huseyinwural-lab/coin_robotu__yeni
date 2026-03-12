from datetime import datetime, timezone


def detect_extreme_volatility(metrics: dict) -> dict:
    atr_ratio = float(metrics.get("atr_ratio") or 0.0)
    price_delta_pct = float(metrics.get("price_delta_pct") or 0.0)
    volatility_percentile = float(metrics.get("volatility_percentile") or 0.0)

    reasons: list[str] = []
    if atr_ratio >= 2.2:
        reasons.append("ATR_EXPLOSION")
    if abs(price_delta_pct) >= 2.8:
        reasons.append("PRICE_DELTA_ANOMALY")
    if volatility_percentile >= 0.92:
        reasons.append("VOLATILITY_PERCENTILE_SPIKE")

    active = len(reasons) >= 2
    severity = "HIGH" if len(reasons) >= 3 else ("MEDIUM" if active else "INFO")
    frequency_multiplier = 0.5 if active else 1.0
    size_multiplier = 0.6 if active else 1.0

    event = None
    if active:
        event = {
            "event": "EXTREME_VOLATILITY_ALERT",
            "severity": severity,
            "reason": reasons,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": {
                "trade_frequency_multiplier": frequency_multiplier,
                "position_size_multiplier": size_multiplier,
            },
        }

    return {
        "active": active,
        "severity": severity,
        "reason": reasons,
        "trade_frequency_multiplier": frequency_multiplier,
        "position_size_multiplier": size_multiplier,
        "event": event,
    }
