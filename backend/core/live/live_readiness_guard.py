from datetime import datetime, timezone


def evaluate_live_readiness_guard(readiness_payload: dict) -> dict:
    state = str(readiness_payload.get("readiness_state") or "READY")
    score = float(readiness_payload.get("readiness_confidence_score") or 0.0)

    if state == "BLOCKED":
        return {
            "action": "BLOCK",
            "reject_trade": True,
            "pause_engine": True,
            "size_multiplier": 0.0,
            "event": {
                "event": "LIVE_READINESS_BLOCK",
                "readiness_score": round(score, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    if state == "WARNING":
        return {
            "action": "DOWNSHIFT",
            "reject_trade": False,
            "pause_engine": False,
            "size_multiplier": 0.7,
            "event": None,
        }

    return {
        "action": "ALLOW",
        "reject_trade": False,
        "pause_engine": False,
        "size_multiplier": 1.0,
        "event": None,
    }
