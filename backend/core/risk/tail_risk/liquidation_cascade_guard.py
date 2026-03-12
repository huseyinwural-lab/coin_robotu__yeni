from datetime import datetime, timezone


def detect_liquidation_cascade(metrics: dict) -> dict:
    rapid_price_drop = float(metrics.get("rapid_price_drop_pct") or 0.0)
    liquidation_volume_spike = float(metrics.get("liquidation_volume_spike") or 0.0)
    funding_rate_anomaly = float(metrics.get("funding_rate_anomaly") or 0.0)

    reasons: list[str] = []
    if rapid_price_drop <= -3.0:
        reasons.append("RAPID_PRICE_DROP")
    if liquidation_volume_spike >= 2.2:
        reasons.append("LIQUIDATION_VOLUME_SPIKE")
    if abs(funding_rate_anomaly) >= 0.02:
        reasons.append("FUNDING_RATE_ANOMALY")

    active = len(reasons) >= 2
    severity = "HIGH" if len(reasons) >= 3 else ("MEDIUM" if active else "INFO")
    throttle_multiplier = 0.45 if active else 1.0

    event = None
    if active:
        event = {
            "event": "LIQUIDATION_CASCADE_ALERT",
            "severity": severity,
            "reason": reasons,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": {
                "global_risk_throttle": True,
                "position_size_multiplier": throttle_multiplier,
            },
        }

    return {
        "active": active,
        "severity": severity,
        "reason": reasons,
        "position_size_multiplier": throttle_multiplier,
        "event": event,
    }
