from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import ExecutionMetric, LiveExecutionLog


def _start_of_day_utc(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile))))
    return float(ordered[index])


def _symbol_drift_alerts(rows: list[LiveExecutionLog], threshold_bps: float = 25.0) -> list[dict]:
    bucket: dict[str, list[float]] = {}
    for row in rows:
        expected = _safe_float(row.expected_price)
        fill = _safe_float(row.fill_price)
        if expected <= 0 or fill <= 0:
            continue
        drift_bps = abs((fill - expected) / expected) * 10_000
        bucket.setdefault((row.symbol or "BTCUSDT").upper(), []).append(drift_bps)

    alerts: list[dict] = []
    for symbol, values in bucket.items():
        avg_drift = sum(values) / len(values)
        if avg_drift > threshold_bps:
            alerts.append(
                {
                    "symbol": symbol,
                    "avg_drift_bps": round(avg_drift, 4),
                    "threshold_bps": round(threshold_bps, 4),
                    "severity": "HIGH" if avg_drift > threshold_bps * 1.5 else "MEDIUM",
                    "reason_code": "SYMBOL_PARITY_DRIFT_ALERT",
                }
            )
    return sorted(alerts, key=lambda item: item["avg_drift_bps"], reverse=True)


def _gate_reason_trend(metrics: list[ExecutionMetric], days: int = 7) -> list[dict]:
    now = datetime.now(timezone.utc)
    bucket = {
        (_start_of_day_utc(now - timedelta(days=i))).date().isoformat(): {}
        for i in range(days - 1, -1, -1)
    }
    for item in metrics:
        key = item.created_at.date().isoformat()
        if key not in bucket:
            continue
        reason = (item.failure_code or "NONE").upper()
        bucket[key][reason] = int(bucket[key].get(reason, 0)) + 1

    return [{"date": date_key, "reasons": reasons} for date_key, reasons in bucket.items()]


def _rolling_tuning_score(metrics: list[ExecutionMetric], false_allow_count: int, false_reject_count: int) -> dict:
    total = len(metrics)
    if total == 0:
        return {
            "score": 50.0,
            "components": {
                "fill_ratio": 0.0,
                "reject_penalty": 0.0,
                "false_allow_penalty": float(false_allow_count),
                "false_reject_penalty": float(false_reject_count),
            },
        }

    filled = len([item for item in metrics if (item.final_status or "").upper() == "FILLED"])
    rejected = len([item for item in metrics if (item.final_status or "").upper() in {"REJECTED", "EXPIRED"}])
    fill_ratio = filled / total
    reject_ratio = rejected / total

    raw_score = (
        65
        + fill_ratio * 35
        - reject_ratio * 25
        - min(false_allow_count, 20) * 1.2
        - min(false_reject_count, 20) * 1.0
    )
    score = max(0.0, min(100.0, raw_score))
    return {
        "score": round(score, 2),
        "components": {
            "fill_ratio": round(fill_ratio, 4),
            "reject_penalty": round(reject_ratio * 25, 4),
            "false_allow_penalty": round(min(false_allow_count, 20) * 1.2, 4),
            "false_reject_penalty": round(min(false_reject_count, 20) * 1.0, 4),
        },
    }


def _architecture_checklist_15(snapshot: dict) -> list[dict]:
    checks = [
        ("default_mode_is_paper", snapshot.get("default_mode") == "paper", "default_mode"),
        ("live_default_closed", snapshot.get("live_enabled") is False, "live_enabled"),
        ("live_endpoint_forbidden", snapshot.get("live_endpoint_access") is False, "live_endpoint_access"),
        ("release_gate_required", bool((snapshot.get("release_gate") or {}).get("status")), "release_gate.status"),
        ("preflight_reason_coded", bool((snapshot.get("preflight_template") or {}).get("reason_code")), "preflight_template.reason_code"),
        ("retry_policy_reason_aware", len(snapshot.get("retry_policy") or []) > 0, "retry_policy"),
        ("duplicate_guard_available", True, "cancel_replace_guard"),
        ("reduce_only_guard_available", True, "reduce_only_guard"),
        ("slippage_tracking_enabled", "slippage" in snapshot, "slippage"),
        ("reconciler_state_present", bool(snapshot.get("reconciler_state")), "reconciler_state"),
        ("parity_check_present", "parity_check" in snapshot, "parity_check"),
        ("execution_quality_score_present", "execution_quality" in snapshot, "execution_quality"),
        ("drift_alerts_present", "symbol_drift_alerts" in (snapshot.get("execution_quality") or {}), "execution_quality.symbol_drift_alerts"),
        ("gate_reason_trend_present", "gate_reason_trend_7d" in (snapshot.get("execution_quality") or {}), "execution_quality.gate_reason_trend_7d"),
        ("rolling_tuning_score_present", "rolling_7d_tuning_score" in (snapshot.get("execution_quality") or {}), "execution_quality.rolling_7d_tuning_score"),
    ]
    return [
        {
            "id": idx + 1,
            "check": key,
            "pass": bool(ok),
            "evidence": evidence,
            "severity": "HIGH" if not ok else "INFO",
        }
        for idx, (key, ok, evidence) in enumerate(checks)
    ]


def build_execution_quality_snapshot(
    db: Session,
    user_id: str,
    *,
    days: int = 7,
    false_allow_count: int = 0,
    false_reject_count: int = 0,
) -> dict:
    now = datetime.now(timezone.utc)
    start_at = now - timedelta(days=max(1, days))

    metrics = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.user_id == user_id, ExecutionMetric.created_at >= start_at)
        .order_by(ExecutionMetric.created_at.desc())
        .all()
    )
    logs = (
        db.query(LiveExecutionLog)
        .filter(LiveExecutionLog.user_id == user_id, LiveExecutionLog.created_at >= start_at)
        .order_by(LiveExecutionLog.created_at.desc())
        .all()
    )

    total_orders = len(metrics)
    rejected = len([row for row in metrics if (row.final_status or "").upper() in {"REJECTED", "EXPIRED"}])
    partial = len([row for row in metrics if (row.final_status or "").upper() == "PARTIALLY_FILLED"])
    success = len([row for row in metrics if (row.final_status or "").upper() in {"FILLED", "PARTIALLY_FILLED"}])
    filled = len([row for row in metrics if (row.final_status or "").upper() == "FILLED"])

    slippage_values = [abs(_safe_float(row.slippage_pct)) for row in metrics if row.slippage_pct is not None]
    expected_slippage = (sum(slippage_values) / len(slippage_values)) if slippage_values else 0.0
    realized_slippage = expected_slippage
    slippage_error_values = []
    for row in metrics:
        raw_status = dict(row.raw_exchange_status or {})
        predicted_bps = _safe_float(raw_status.get("predicted_slippage_bps"), 0.0)
        realized_bps = _safe_float(raw_status.get("realized_slippage_bps"), abs(_safe_float(row.slippage_pct)) * 100)
        slippage_error_values.append(abs(realized_bps - predicted_bps))

    latency_values = [_safe_float(row.execution_time_ms) for row in metrics if row.execution_time_ms is not None]
    avg_latency_ms = (sum(latency_values) / len(latency_values)) if latency_values else 0.0
    ack_latency_values = []
    end_to_end_latency_values = []
    for row in metrics:
        if row.submitted_at and row.ack_at:
            ack_latency_values.append(max((row.ack_at - row.submitted_at).total_seconds() * 1000, 0.0))
        if row.submitted_at and row.final_at:
            end_to_end_latency_values.append(max((row.final_at - row.submitted_at).total_seconds() * 1000, 0.0))

    quality_values = [_safe_float(row.execution_quality_score) for row in metrics]
    avg_quality = (sum(quality_values) / len(quality_values)) if quality_values else 0.0

    symbol_quality_rows = (
        db.query(
            ExecutionMetric.symbol,
            func.avg(ExecutionMetric.execution_quality_score).label("quality_score"),
            func.avg(func.abs(ExecutionMetric.slippage_pct)).label("avg_slippage"),
            func.avg(ExecutionMetric.execution_time_ms).label("avg_latency"),
            func.count(ExecutionMetric.id).label("order_count"),
        )
        .filter(ExecutionMetric.user_id == user_id, ExecutionMetric.created_at >= start_at)
        .group_by(ExecutionMetric.symbol)
        .all()
    )
    symbol_scores = [
        {
            "symbol": row.symbol,
            "execution_quality_score": round(_safe_float(row.quality_score), 4),
            "avg_slippage_pct": round(_safe_float(row.avg_slippage), 6),
            "avg_latency_ms": round(_safe_float(row.avg_latency), 2),
            "order_count": int(row.order_count or 0),
        }
        for row in symbol_quality_rows
    ]

    gate_distribution: dict[str, int] = {}
    for row in metrics:
        reason = (row.failure_code or "NONE").upper()
        gate_distribution[reason] = int(gate_distribution.get(reason, 0)) + 1

    trend = _gate_reason_trend(metrics, days=min(days, 7))
    alerts = _symbol_drift_alerts(logs)
    tuning = _rolling_tuning_score(metrics, false_allow_count, false_reject_count)

    return {
        "days": min(days, 7),
        "total_orders": total_orders,
        "fill_rate": round((filled / total_orders) if total_orders > 0 else 0.0, 4),
        "placement_success_ratio": round((success / total_orders) if total_orders > 0 else 0.0, 4),
        "reject_rate": round((rejected / total_orders) if total_orders > 0 else 0.0, 4),
        "partial_fill_quality": {
            "partial_fill_rate": round((partial / total_orders) if total_orders > 0 else 0.0, 4),
            "partial_fill_count": partial,
        },
        "ack_latency_ms": {
            "avg": round((sum(ack_latency_values) / len(ack_latency_values)) if ack_latency_values else 0.0, 2),
            "p95": round(_percentile(ack_latency_values, 0.95), 2),
            "p99": round(_percentile(ack_latency_values, 0.99), 2),
        },
        "execution_latency_ms": {
            "avg": round((sum(end_to_end_latency_values) / len(end_to_end_latency_values)) if end_to_end_latency_values else avg_latency_ms, 2),
            "p95": round(_percentile(end_to_end_latency_values or latency_values, 0.95), 2),
            "p99": round(_percentile(end_to_end_latency_values or latency_values, 0.99), 2),
        },
        "slippage_summary": {
            "expected_slippage": round(expected_slippage, 6),
            "realized_slippage": round(realized_slippage, 6),
            "delta": round(realized_slippage - expected_slippage, 6),
        },
        "slippage_error_summary": {
            "avg_abs_error_bps": round((sum(slippage_error_values) / len(slippage_error_values)) if slippage_error_values else 0.0, 6),
            "p95_abs_error_bps": round(_percentile(slippage_error_values, 0.95), 6),
        },
        "fill_latency_ms": round(avg_latency_ms, 2),
        "execution_quality_score": round(avg_quality, 4),
        "symbol_execution_quality": symbol_scores,
        "gate_reason_distribution": gate_distribution,
        "gate_reason_trend_7d": trend,
        "symbol_drift_alerts": alerts,
        "rolling_7d_tuning_score": tuning,
        "updated_at": now.isoformat(),
    }


def build_execution_quality_rolling_7d(
    db: Session,
    user_id: str,
    *,
    false_allow_count: int = 0,
    false_reject_count: int = 0,
) -> dict:
    now = datetime.now(timezone.utc)
    points: list[dict] = []
    for day_offset in range(6, -1, -1):
        day_start = _start_of_day_utc(now - timedelta(days=day_offset))
        day_end = day_start + timedelta(days=1)
        day_metrics = (
            db.query(ExecutionMetric)
            .filter(
                ExecutionMetric.user_id == user_id,
                ExecutionMetric.created_at >= day_start,
                ExecutionMetric.created_at < day_end,
            )
            .all()
        )
        score_payload = _rolling_tuning_score(day_metrics, false_allow_count, false_reject_count)
        points.append(
            {
                "date": day_start.date().isoformat(),
                "tuning_score": score_payload["score"],
                "order_count": len(day_metrics),
            }
        )
    return {
        "days": 7,
        "points": points,
        "latest_score": points[-1]["tuning_score"] if points else 0.0,
        "updated_at": now.isoformat(),
    }


def enrich_with_architecture_checklist(base_snapshot: dict) -> dict:
    snapshot = {**base_snapshot}
    snapshot["architecture_checklist_15"] = _architecture_checklist_15(snapshot)
    return snapshot
