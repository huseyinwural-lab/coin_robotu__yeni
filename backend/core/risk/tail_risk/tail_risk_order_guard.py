from datetime import datetime, timezone


def evaluate_tail_risk_order_guard(
    *,
    strategy_id: str,
    global_risk_score: float,
    risk_state: str,
    active_alerts: list[dict],
) -> dict:
    state = str(risk_state or "NORMAL").upper()
    score = float(global_risk_score or 0.0)
    reasons = [str(item.get("event") or "UNKNOWN") for item in (active_alerts or [])]

    if state == "PAUSE":
        event = {
            "event": "TAIL_RISK_TRADE_REJECTED",
            "strategy_id": strategy_id,
            "risk_score": round(score, 2),
            "reason": reasons or ["TRADE_ENGINE_PAUSED"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return {
            "action": "REJECT",
            "size_multiplier": 0.0,
            "pause_strategy": True,
            "event": event,
        }

    if state == "THROTTLE":
        return {
            "action": "REDUCE_SIZE",
            "size_multiplier": 0.45,
            "pause_strategy": False,
            "event": None,
        }

    if state == "DOWNSHIFT":
        return {
            "action": "REDUCE_SIZE",
            "size_multiplier": 0.7,
            "pause_strategy": False,
            "event": None,
        }

    return {
        "action": "ALLOW",
        "size_multiplier": 1.0,
        "pause_strategy": False,
        "event": None,
    }
