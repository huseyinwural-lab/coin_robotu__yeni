from datetime import datetime, timezone


def evaluate_cluster_risk(
    *,
    cluster_exposures: list[dict],
    cluster_exposure_limit: float = 0.35,
    cluster_position_limit: int = 3,
    cluster_direction_limit: float = 0.85,
) -> dict:
    alerts: list[dict] = []

    for row in cluster_exposures:
        reasons: list[str] = []
        exposure_ratio = float(row.get("cluster_exposure") or 0.0)
        position_count = int(row.get("cluster_position_count") or 0)
        direction = str(row.get("cluster_direction") or "NEUTRAL")
        cluster_notional = float(row.get("cluster_exposure_notional") or 0.0)

        if exposure_ratio > cluster_exposure_limit:
            reasons.append("CLUSTER_EXPOSURE_LIMIT")
        if position_count > cluster_position_limit:
            reasons.append("CLUSTER_POSITION_LIMIT")
        if direction in {"LONG", "SHORT"} and exposure_ratio > cluster_direction_limit:
            reasons.append("CLUSTER_DIRECTION_LIMIT")

        risk_state = "NORMAL"
        if reasons:
            risk_state = "LIMIT_HIT"
            alerts.append(
                {
                    "cluster_id": row.get("cluster_id"),
                    "event": "CLUSTER_RISK_LIMIT_HIT",
                    "symbols": row.get("symbols") or [],
                    "cluster_exposure": exposure_ratio,
                    "cluster_direction": direction,
                    "cluster_position_count": position_count,
                    "cluster_exposure_notional": cluster_notional,
                    "reason": reasons,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        row["risk_state"] = risk_state

    return {
        "cluster_limits": {
            "cluster_exposure_limit": cluster_exposure_limit,
            "cluster_position_limit": cluster_position_limit,
            "cluster_direction_limit": cluster_direction_limit,
        },
        "cluster_risk_alerts": alerts,
        "risk_state": "ALERT" if alerts else "NORMAL",
        "cluster_exposures": cluster_exposures,
    }
