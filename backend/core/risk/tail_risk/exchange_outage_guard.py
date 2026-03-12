from datetime import datetime, timezone


def evaluate_exchange_health(metrics: dict) -> dict:
    api_latency_ms = float(metrics.get("api_latency_ms") or 0.0)
    ack_delay_ms = float(metrics.get("ack_delay_ms") or 0.0)
    order_reject_rate = float(metrics.get("order_reject_rate") or 0.0)
    heartbeat_age_sec = float(metrics.get("heartbeat_age_sec") or 0.0)

    reasons: list[str] = []
    if api_latency_ms >= 1200:
        reasons.append("API_LATENCY_SPIKE")
    if ack_delay_ms >= 1500:
        reasons.append("ACK_DELAY_SPIKE")
    if order_reject_rate >= 0.25:
        reasons.append("ORDER_REJECT_ANOMALY")
    if heartbeat_age_sec >= 30:
        reasons.append("HEARTBEAT_TIMEOUT")

    active = len(reasons) >= 2
    severity = "CRITICAL" if "HEARTBEAT_TIMEOUT" in reasons else ("HIGH" if active else "INFO")
    trade_pause = active

    event = None
    if active:
        event = {
            "event": "EXCHANGE_HEALTH_ALERT",
            "severity": severity,
            "reason": reasons,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": {
                "trade_pause": trade_pause,
                "order_submission_halt": trade_pause,
            },
        }

    return {
        "active": active,
        "severity": severity,
        "reason": reasons,
        "trade_pause": trade_pause,
        "event": event,
    }
