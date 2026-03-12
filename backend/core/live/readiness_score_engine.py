from datetime import datetime, timezone


STATE_SCORE_MAP = {
    "position_sync_state": {"SYNCED": 100, "DRIFT": 45, "UNVERIFIED": 55},
    "order_reconciliation_state": {"RECONCILED": 100, "ERROR": 45, "UNVERIFIED": 55},
    "balance_integrity_state": {"INTACT": 100, "ALERT": 40, "UNVERIFIED": 55},
    "exchange_latency_state": {"NORMAL": 100, "ELEVATED": 70, "ALERT": 40},
}


def compute_readiness_score(*, position_sync_state: str, order_reconciliation_state: str, balance_integrity_state: str, exchange_latency_state: str) -> dict:
    component_scores = {
        "position_sync_state": STATE_SCORE_MAP["position_sync_state"].get(position_sync_state, 50),
        "order_reconciliation_state": STATE_SCORE_MAP["order_reconciliation_state"].get(order_reconciliation_state, 50),
        "balance_integrity_state": STATE_SCORE_MAP["balance_integrity_state"].get(balance_integrity_state, 50),
        "exchange_latency_state": STATE_SCORE_MAP["exchange_latency_state"].get(exchange_latency_state, 50),
    }

    weights = {
        "position_sync_state": 0.25,
        "order_reconciliation_state": 0.25,
        "balance_integrity_state": 0.25,
        "exchange_latency_state": 0.25,
    }

    score = sum(component_scores[key] * weights[key] for key in component_scores)
    readiness_state = "READY"
    if score < 70:
        readiness_state = "BLOCKED"
    elif score < 85:
        readiness_state = "WARNING"

    event = None
    if readiness_state != "READY":
        event = {
            "event": "LIVE_READINESS_ALERT",
            "readiness_confidence_score": round(score, 2),
            "readiness_state": readiness_state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "readiness_confidence_score": round(score, 2),
        "readiness_state": readiness_state,
        "component_scores": component_scores,
        "weights": weights,
        "event": event,
    }
