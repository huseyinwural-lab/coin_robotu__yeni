from datetime import datetime, timezone


def build_cluster_governance_audit_events(
    *,
    matrix_payload: dict,
    clusters_payload: dict,
    risk_payload: dict,
    order_events: list[dict],
) -> list[dict]:
    events: list[dict] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for cluster in clusters_payload.get("correlation_clusters") or []:
        events.append(
            {
                "event": "CLUSTER_CREATED",
                "cluster_id": cluster.get("cluster_id"),
                "symbols": cluster.get("symbols") or [],
                "exposure": 0.0,
                "direction": "NEUTRAL",
                "reason": ["MATRIX_BUILD"],
                "timestamp": now_iso,
            }
        )

    for alert in risk_payload.get("cluster_risk_alerts") or []:
        events.append(
            {
                "event": "CLUSTER_RISK_LIMIT_HIT",
                "cluster_id": alert.get("cluster_id"),
                "symbols": alert.get("symbols") or [],
                "exposure": alert.get("cluster_exposure", 0.0),
                "direction": alert.get("cluster_direction", "NEUTRAL"),
                "reason": alert.get("reason") or [],
                "timestamp": alert.get("timestamp") or now_iso,
            }
        )

    for event in order_events:
        events.append(
            {
                "event": "CLUSTER_TRADE_REJECTED",
                "cluster_id": event.get("cluster_id"),
                "symbols": event.get("symbols") or [],
                "exposure": event.get("exposure", 0.0),
                "direction": event.get("direction", "NEUTRAL"),
                "reason": event.get("reason") or [],
                "timestamp": event.get("timestamp") or now_iso,
            }
        )

    if matrix_payload.get("correlation_matrix"):
        events.append(
            {
                "event": "CLUSTER_UPDATED",
                "cluster_id": "ALL",
                "symbols": matrix_payload.get("symbols") or [],
                "exposure": 0.0,
                "direction": "NEUTRAL",
                "reason": ["ROLLING_MATRIX_REFRESH"],
                "timestamp": now_iso,
            }
        )

    return events
