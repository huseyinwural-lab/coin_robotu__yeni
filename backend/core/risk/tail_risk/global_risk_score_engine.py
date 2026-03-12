from datetime import datetime, timezone


def _cluster_score(cluster_risk_state: str) -> float:
    state = str(cluster_risk_state or "NORMAL").upper()
    if state == "ALERT":
        return 78.0
    return 22.0


def _capital_score(capital_drift_state: str) -> float:
    state = str(capital_drift_state or "NORMAL").upper()
    if state == "ALERT":
        return 82.0
    return 24.0


def compute_global_risk_score(
    *,
    strategy_health_score: float,
    cluster_risk_state: str,
    capital_drift_state: str,
    tail_risk_score: float,
    weights: dict | None = None,
) -> dict:
    weights = weights or {
        "strategy": 0.25,
        "cluster": 0.25,
        "capital": 0.20,
        "tail_risk": 0.30,
    }

    strategy_risk_component = max(0.0, min(100.0, 100 - float(strategy_health_score or 0.0)))
    cluster_component = _cluster_score(cluster_risk_state)
    capital_component = _capital_score(capital_drift_state)
    tail_component = max(0.0, min(100.0, float(tail_risk_score or 0.0)))

    global_score = (
        strategy_risk_component * float(weights.get("strategy", 0.25))
        + cluster_component * float(weights.get("cluster", 0.25))
        + capital_component * float(weights.get("capital", 0.20))
        + tail_component * float(weights.get("tail_risk", 0.30))
    )

    risk_state = "NORMAL"
    events: list[dict] = []
    if global_score > 90:
        risk_state = "PAUSE"
        events.append({"event": "TRADE_ENGINE_PAUSED", "timestamp": datetime.now(timezone.utc).isoformat()})
    elif global_score > 80:
        risk_state = "THROTTLE"
        events.append({"event": "GLOBAL_RISK_THROTTLE", "timestamp": datetime.now(timezone.utc).isoformat()})
    elif global_score > 60:
        risk_state = "DOWNSHIFT"
        events.append({"event": "GLOBAL_RISK_ALERT", "timestamp": datetime.now(timezone.utc).isoformat()})

    return {
        "global_risk_score": round(global_score, 2),
        "risk_state": risk_state,
        "weights": weights,
        "components": {
            "strategy_risk_component": round(strategy_risk_component, 2),
            "cluster_risk_component": round(cluster_component, 2),
            "capital_risk_component": round(capital_component, 2),
            "tail_risk_component": round(tail_component, 2),
        },
        "active_events": events,
    }
