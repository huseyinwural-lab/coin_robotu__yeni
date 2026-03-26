from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.alerts.suggested_actions import get_suggested_action
from core.runtime_alert_thresholds import get_runtime_alert_thresholds
from db import redis_client
from models import ExecutionJob
from services.system_alert_service import create_system_alert


def _alert_details(
    *,
    severity: str,
    source: str,
    threshold: float | int,
    actual_value: float | int,
    user_id: str | None = None,
    symbol: str | None = None,
) -> dict:
    return {
        "severity": severity,
        "source": source,
        "user_id": user_id,
        "symbol": symbol,
        "threshold": threshold,
        "actual_value": actual_value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def trigger_runtime_threshold_alert(
    db: Session,
    *,
    alert_type: str,
    severity: str,
    message: str,
    source: str,
    threshold: float | int,
    actual_value: float | int,
    user_id: str | None = None,
    symbol: str | None = None,
    root_cause_code: str | None = None,
) -> None:
    suggestion = get_suggested_action(alert_type)
    create_system_alert(
        db,
        alert_type=alert_type,
        severity=severity,
        message=message,
        details=_alert_details(
            severity=severity,
            source=source,
            threshold=threshold,
            actual_value=actual_value,
            user_id=user_id,
            symbol=symbol,
        )
        | suggestion,
        entity_key=user_id or symbol or source,
        root_cause_code=root_cause_code,
        state_key=alert_type,
    )


def check_queue_depth_trigger(db: Session, *, threshold: int | None = None) -> None:
    cfg = get_runtime_alert_thresholds()
    limit = int(threshold if threshold is not None else cfg["queue_depth_threshold"])
    queue_depth = len(redis_client.lrange("execution:jobs:queue", 0, -1) or [])
    if queue_depth >= limit:
        trigger_runtime_threshold_alert(
            db,
            alert_type="runtime_queue_depth_high",
            severity="WARNING",
            message=f"Execution queue depth high: {queue_depth}",
            source="runtime_queue",
            threshold=limit,
            actual_value=queue_depth,
            root_cause_code="queue_depth_threshold",
        )


def check_failed_orders_trigger(db: Session, *, threshold: int | None = None, window_size: int | None = None) -> None:
    cfg = get_runtime_alert_thresholds()
    threshold_value = int(threshold if threshold is not None else cfg["failed_orders_threshold"])
    window_value = int(window_size if window_size is not None else cfg["failed_orders_window"])
    rows = (
        db.query(ExecutionJob)
        .order_by(ExecutionJob.created_at.desc())
        .limit(window_value)
        .all()
    )
    failed_count = sum(1 for row in rows if str(row.state).upper() == "FAILED")
    if failed_count >= threshold_value:
        trigger_runtime_threshold_alert(
            db,
            alert_type="runtime_failed_orders_high",
            severity="CRITICAL",
            message=f"Failed orders increased: {failed_count}/{window_value}",
            source="runtime_execution",
            threshold=threshold_value,
            actual_value=failed_count,
            root_cause_code="failed_orders_threshold",
        )


def check_worker_failure_trigger(db: Session, *, threshold: int = 3, window_minutes: int = 15) -> None:
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    failed_recent = (
        db.query(ExecutionJob)
        .filter(ExecutionJob.state == "FAILED", ExecutionJob.updated_at >= since)
        .count()
    )
    if failed_recent >= threshold:
        trigger_runtime_threshold_alert(
            db,
            alert_type="runtime_worker_failures_high",
            severity="CRITICAL",
            message=f"Worker failures high in {window_minutes}m: {failed_recent}",
            source="execution_worker",
            threshold=threshold,
            actual_value=failed_recent,
            root_cause_code="worker_failure_threshold",
        )


def check_pnl_drop_trigger(
    db: Session,
    *,
    user_id: str,
    symbol: str,
    previous_net_pnl: float,
    current_net_pnl: float,
    threshold_pct: float | None = None,
) -> None:
    cfg = get_runtime_alert_thresholds()
    threshold_value = float(threshold_pct if threshold_pct is not None else cfg["net_pnl_drop_pct"])
    baseline = abs(float(previous_net_pnl or 0.0))
    if baseline <= 0:
        return
    drop_pct = ((previous_net_pnl - current_net_pnl) / baseline) * 100.0
    if drop_pct >= threshold_value:
        trigger_runtime_threshold_alert(
            db,
            alert_type="runtime_pnl_drop",
            severity="WARNING",
            message=f"PnL drop detected: {drop_pct:.2f}%",
            source="pnl_engine",
            threshold=threshold_value,
            actual_value=round(drop_pct, 6),
            user_id=user_id,
            symbol=symbol,
            root_cause_code="pnl_drop_threshold",
        )


def check_daily_loss_trigger(db: Session, *, user_id: str, daily_loss_usd: float, configured_limit: float) -> None:
    if abs(float(daily_loss_usd)) >= abs(float(configured_limit)):
        trigger_runtime_threshold_alert(
            db,
            alert_type="runtime_daily_loss_limit",
            severity="CRITICAL",
            message=f"Daily loss limit exceeded: {daily_loss_usd:.4f}",
            source="risk_engine",
            threshold=abs(float(configured_limit)),
            actual_value=abs(float(daily_loss_usd)),
            user_id=user_id,
            root_cause_code="daily_loss_threshold",
        )


def check_snapshot_compare_delta_trigger(
    db: Session,
    *,
    delta_pct: float,
    threshold_pct: float | None = None,
    metric: str = "total_revenue_usd",
) -> None:
    cfg = get_runtime_alert_thresholds()
    threshold_value = float(threshold_pct if threshold_pct is not None else cfg["net_pnl_drop_pct"])
    if abs(float(delta_pct or 0.0)) >= abs(float(threshold_value)):
        trigger_runtime_threshold_alert(
            db,
            alert_type="runtime_snapshot_delta_high",
            severity="WARNING",
            message=f"Snapshot delta threshold exceeded for {metric}: {delta_pct:.2f}%",
            source="snapshot_compare",
            threshold=threshold_value,
            actual_value=round(float(delta_pct), 6),
            root_cause_code="snapshot_delta_threshold",
        )
