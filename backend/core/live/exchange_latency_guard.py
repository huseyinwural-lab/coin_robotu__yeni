from datetime import datetime, timezone


def evaluate_exchange_latency(metrics: dict) -> dict:
    order_ack_latency = float(metrics.get("order_ack_latency") or 0.0)
    api_response_latency = float(metrics.get("api_response_latency") or 0.0)
    websocket_delay = float(metrics.get("websocket_delay") or 0.0)
    heartbeat_gap = float(metrics.get("heartbeat_gap") or 0.0)

    reasons: list[str] = []
    if order_ack_latency > 1200:
        reasons.append("ORDER_ACK_LATENCY")
    if api_response_latency > 1000:
        reasons.append("API_RESPONSE_LATENCY")
    if websocket_delay > 800:
        reasons.append("WEBSOCKET_DELAY")
    if heartbeat_gap > 20:
        reasons.append("HEARTBEAT_GAP")

    state = "NORMAL"
    if len(reasons) >= 3:
        state = "ALERT"
    elif len(reasons) >= 1:
        state = "ELEVATED"

    event = None
    if state != "NORMAL":
        event = {
            "event": "EXCHANGE_LATENCY_ALERT",
            "state": state,
            "reason": reasons,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": {
                "trade_frequency_throttle": state in {"ELEVATED", "ALERT"},
                "order_submission_delay": state == "ALERT",
            },
        }

    return {
        "exchange_latency_state": state,
        "latency_metrics": {
            "order_ack_latency": order_ack_latency,
            "api_response_latency": api_response_latency,
            "websocket_delay": websocket_delay,
            "heartbeat_gap": heartbeat_gap,
        },
        "event": event,
    }
