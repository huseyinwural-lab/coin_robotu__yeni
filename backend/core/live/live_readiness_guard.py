from datetime import datetime, timezone


def evaluate_live_readiness_guard(readiness_payload: dict) -> dict:
    state = str(readiness_payload.get("readiness_state") or "UNKNOWN")
    score = float(readiness_payload.get("readiness_confidence_score") or 0.0)

    if state != "READY":
        return {
            "action": "BLOCK",
            "reject_trade": True,
            "pause_engine": True,
            "size_multiplier": 0.0,
            "event": {
                "event": "LIVE_READINESS_BLOCK",
                "readiness_score": round(score, 2),
                "readiness_state": state,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    return {
        "action": "ALLOW",
        "reject_trade": False,
        "pause_engine": False,
        "size_multiplier": 1.0,
        "event": None,
    }
