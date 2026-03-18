from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import SystemAlert


def compute_slo_metrics(rows: list[SystemAlert], *, sla_target_pct: float = 99.5) -> dict:
    total = len(rows)
    critical_count = sum(1 for row in rows if (row.severity or "").upper() == "CRITICAL")
    warning_count = sum(1 for row in rows if (row.severity or "").upper() == "WARNING")
    error_rate = round(((critical_count + warning_count) / total), 6) if total else 0.0

    resolved_rows = [row for row in rows if (row.status or "").lower() == "resolved"]
    mttr_minutes = 0.0
    if resolved_rows:
        mttr_minutes = round(
            sum(max((row.updated_at - row.created_at).total_seconds() / 60, 0) for row in resolved_rows)
            / len(resolved_rows),
            2,
        )

    error_rate_pct = round(error_rate * 100.0, 4)
    availability_pct = round(max(0.0, 100.0 - error_rate_pct), 4)
    error_budget_target_pct = round(max(0.0, 100.0 - float(sla_target_pct)), 4)
    error_budget_consumed_pct = (
        round((error_rate_pct / error_budget_target_pct) * 100.0, 2)
        if error_budget_target_pct > 0
        else 0.0
    )
    sla_breached = availability_pct < float(sla_target_pct)

    return {
        "total_alerts": total,
        "critical_alerts": critical_count,
        "warning_alerts": warning_count,
        "resolved_alerts": len(resolved_rows),
        "error_rate": error_rate,
        "error_rate_pct": error_rate_pct,
        "mttr_minutes": mttr_minutes,
        "availability_pct": availability_pct,
        "sla_target_pct": float(sla_target_pct),
        "sla_breached": sla_breached,
        "error_budget_target_pct": error_budget_target_pct,
        "error_budget_consumed_pct": error_budget_consumed_pct,
    }


def load_alert_rows_for_window(db: Session, *, days: int) -> list[SystemAlert]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return (
        db.query(SystemAlert)
        .filter(SystemAlert.created_at >= since)
        .order_by(SystemAlert.created_at.desc())
        .limit(10000)
        .all()
    )


def compute_slo_trend(db: Session, *, windows: list[int] | None = None) -> dict:
    now = datetime.now(timezone.utc)
    selected_windows = windows or [7, 30, 90]
    points: list[dict] = []

    for window in selected_windows:
        rows = load_alert_rows_for_window(db, days=window)
        metrics = compute_slo_metrics(rows)
        points.append(
            {
                "window_days": window,
                "availability_pct": metrics["availability_pct"],
                "error_rate": metrics["error_rate"],
                "error_rate_pct": metrics["error_rate_pct"],
                "mttr_minutes": metrics["mttr_minutes"],
                "total_alerts": metrics["total_alerts"],
                "error_budget_consumed_pct": metrics["error_budget_consumed_pct"],
            }
        )

    point_map = {point["window_days"]: point for point in points}
    p7 = point_map.get(7, {})
    p30 = point_map.get(30, {})
    p90 = point_map.get(90, {})

    baseline_30 = float(p30.get("error_rate_pct") or 0.0)
    short_7 = float(p7.get("error_rate_pct") or 0.0)
    spike_detected = baseline_30 > 0 and short_7 >= baseline_30 * 1.5 and (short_7 - baseline_30) >= 0.2
    long_shift = float(p90.get("error_rate_pct") or 0.0) > baseline_30 * 1.2 if baseline_30 > 0 else False

    anomaly_detection = {
        "spike_detected": bool(spike_detected),
        "long_term_shift": bool(long_shift),
        "signal": "SPIKE" if spike_detected else ("DRIFT" if long_shift else "NORMAL"),
        "reason": (
            "7d error_rate_pct 30d baseline'e göre belirgin yükseldi"
            if spike_detected
            else ("90d error trend yukarı kayıyor" if long_shift else "anomaly_detected_none")
        ),
    }

    return {
        "generated_at": now.isoformat(),
        "points": points,
        "window_labels": [f"{window}d" for window in selected_windows],
        "anomaly_detection": anomaly_detection,
    }
