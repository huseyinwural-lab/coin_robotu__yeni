from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from core.config import settings
from models import ExecutionStateTransition, FailedEvent, IdempotencyCollision
from services.system_alert_service import create_system_alert

EXEC_ALERT_DEDUP_SECONDS = int(os.environ.get("EXEC_ALERT_DEDUP_SECONDS", "60"))
EXEC_TIMEOUT_SPIKE_THRESHOLD = int(os.environ.get("EXEC_TIMEOUT_SPIKE_THRESHOLD", "5"))
EXEC_TIMEOUT_SPIKE_WINDOW_SECONDS = int(os.environ.get("EXEC_TIMEOUT_SPIKE_WINDOW_SECONDS", "30"))
EXEC_FAILURE_AGG_THRESHOLD = int(os.environ.get("EXEC_FAILURE_AGG_THRESHOLD", "5"))
EXEC_FAILURE_AGG_WINDOW_SECONDS = int(os.environ.get("EXEC_FAILURE_AGG_WINDOW_SECONDS", "30"))


def _frontend_base_url() -> str:
    configured = (os.environ.get("ALERT_FRONTEND_BASE_URL") or "").strip()
    if configured:
        return configured.rstrip("/")
    emergent_preview = (os.environ.get("REACT_APP_BACKEND_URL") or "").strip()
    if emergent_preview:
        return emergent_preview.rstrip("/")
    if settings.cors_origins:
        return settings.cors_origins[0].rstrip("/")
    return "https://app.local"


def _build_ui_url(path: str, *, correlation_id: str | None = None, execution_event_id: str | None = None) -> str:
    base = _frontend_base_url()
    params = {
        "correlation_id": correlation_id,
        "execution_event_id": execution_event_id,
    }
    query = urlencode({key: value for key, value in params.items() if value})
    suffix = f"{path}?{query}" if query else path
    if not base:
        return suffix
    return f"{base}{suffix}"


def _build_webhook_payload(
    *,
    event_type: str,
    severity: str,
    correlation_id: str | None,
    execution_event_id: str | None,
    symbol: str | None,
    state: str | None,
    failure_reason: str | None,
    retry_count: int | None,
    max_retry: int | None,
) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "version": "1",
        "event_type": event_type,
        "severity": severity.lower(),
        "correlation_id": correlation_id,
        "execution_event_id": execution_event_id,
        "symbol": symbol,
        "state": state,
        "failure_reason": failure_reason,
        "retry_count": retry_count if retry_count is not None else 0,
        "max_retry": max_retry if max_retry is not None else 0,
        "timestamp": timestamp,
        "dashboard_url": _build_ui_url("/admin/execution/states", correlation_id=correlation_id, execution_event_id=execution_event_id),
        "trace_url": _build_ui_url("/admin/execution/trace", correlation_id=correlation_id, execution_event_id=execution_event_id),
    }


def _emit_execution_alert(
    db: Session,
    *,
    event_type: str,
    severity: str,
    message: str,
    correlation_id: str | None,
    execution_event_id: str | None,
    symbol: str | None,
    state: str | None,
    failure_reason: str | None,
    retry_count: int | None = None,
    max_retry: int | None = None,
    root_cause_code: str | None = None,
    entity_key: str | None = None,
    group_window_seconds: int | None = None,
) -> None:
    webhook_payload = _build_webhook_payload(
        event_type=event_type,
        severity=severity,
        correlation_id=correlation_id,
        execution_event_id=execution_event_id,
        symbol=symbol,
        state=state,
        failure_reason=failure_reason,
        retry_count=retry_count,
        max_retry=max_retry,
    )
    create_system_alert(
        db,
        alert_type=event_type,
        severity=severity,
        message=message,
        details={
            "summary": message,
            "event_type": event_type,
            "correlation_id": correlation_id,
            "execution_event_id": execution_event_id,
            "symbol": symbol,
            "state": state,
            "failure_reason": failure_reason,
            "retry_count": retry_count,
            "max_retry": max_retry,
            "webhook_payload": webhook_payload,
            "seen": False,
            "triggered_at": webhook_payload["timestamp"],
            "group_window_seconds": group_window_seconds or EXEC_ALERT_DEDUP_SECONDS,
            "escalation_tier": severity.lower(),
        },
        dedupe_window_seconds=group_window_seconds or EXEC_ALERT_DEDUP_SECONDS,
        entity_key=entity_key or correlation_id or execution_event_id or symbol,
        root_cause_code=root_cause_code,
        state_key=state,
    )


def trigger_execution_state_alert(
    db: Session,
    *,
    final_state: str,
    correlation_id: str | None,
    execution_event_id: str | None,
    symbol: str | None,
) -> None:
    normalized_state = str(final_state or "").lower()
    if normalized_state == "failed":
        _emit_execution_alert(
            db,
            event_type="execution_failed",
            severity="CRITICAL",
            message="Execution state failed",
            correlation_id=correlation_id,
            execution_event_id=execution_event_id,
            symbol=symbol,
            state=normalized_state,
            failure_reason="execution_state_failed",
            root_cause_code="execution_state_failed",
        )
    elif normalized_state == "timeout":
        _emit_execution_alert(
            db,
            event_type="execution_timeout",
            severity="WARNING",
            message="Execution timeout detected",
            correlation_id=correlation_id,
            execution_event_id=execution_event_id,
            symbol=symbol,
            state=normalized_state,
            failure_reason="timeout",
            root_cause_code="execution_timeout",
            group_window_seconds=EXEC_TIMEOUT_SPIKE_WINDOW_SECONDS,
        )


def trigger_timeout_spike_alert(
    db: Session,
    *,
    symbol: str | None,
    correlation_id: str | None,
    execution_event_id: str | None,
) -> None:
    since = datetime.now(timezone.utc) - timedelta(seconds=EXEC_TIMEOUT_SPIKE_WINDOW_SECONDS)
    timeout_count = (
        db.query(ExecutionStateTransition)
        .filter(
            ExecutionStateTransition.state == "timeout",
            ExecutionStateTransition.occurred_at >= since,
        )
        .count()
    )
    if timeout_count < EXEC_TIMEOUT_SPIKE_THRESHOLD:
        return
    _emit_execution_alert(
        db,
        event_type="execution_timeout_spike",
        severity="WARNING",
        message=f"Timeout spike detected: {timeout_count} in {EXEC_TIMEOUT_SPIKE_WINDOW_SECONDS}s",
        correlation_id=correlation_id,
        execution_event_id=execution_event_id,
        symbol=symbol,
        state="timeout",
        failure_reason="timeout_spike",
        root_cause_code="timeout_spike",
        entity_key=f"timeout_spike:{symbol or 'global'}",
    )


def _extract_symbol_from_failed_event(failed_event: FailedEvent) -> str | None:
    payload = failed_event.payload if isinstance(failed_event.payload, dict) else {}
    for key in ["symbol", "asset", "instrument"]:
        value = payload.get(key)
        if value:
            return str(value).upper()
    return None


def trigger_failed_event_alerts(db: Session, failed_event: FailedEvent) -> None:
    symbol = _extract_symbol_from_failed_event(failed_event)
    status = str(failed_event.status or "").lower()
    if status in {"dead", "quarantined"}:
        _emit_execution_alert(
            db,
            event_type="execution_dead_letter",
            severity="CRITICAL",
            message="Execution dead-letter event created",
            correlation_id=failed_event.correlation_id,
            execution_event_id=failed_event.entity_id,
            symbol=symbol,
            state=status,
            failure_reason=failed_event.dead_letter_reason or failed_event.error_message,
            retry_count=failed_event.retry_count,
            max_retry=failed_event.max_retry,
            root_cause_code="dead_letter",
        )

    if failed_event.max_retry > 0 and failed_event.retry_count >= failed_event.max_retry:
        _emit_execution_alert(
            db,
            event_type="execution_retry_max_reached",
            severity="CRITICAL",
            message="Execution retry budget exhausted",
            correlation_id=failed_event.correlation_id,
            execution_event_id=failed_event.entity_id,
            symbol=symbol,
            state=status,
            failure_reason=failed_event.error_message,
            retry_count=failed_event.retry_count,
            max_retry=failed_event.max_retry,
            root_cause_code="max_retry_reached",
        )

    since = datetime.now(timezone.utc) - timedelta(seconds=EXEC_FAILURE_AGG_WINDOW_SECONDS)
    failure_count = (
        db.query(FailedEvent)
        .filter(
            FailedEvent.created_at >= since,
            FailedEvent.status.in_(["pending", "retrying", "dead", "quarantined"]),
        )
        .count()
    )
    if failure_count >= EXEC_FAILURE_AGG_THRESHOLD:
        bucket_seconds = max(EXEC_FAILURE_AGG_WINDOW_SECONDS, 1)
        bucket_marker = int(datetime.now(timezone.utc).timestamp() // bucket_seconds)
        _emit_execution_alert(
            db,
            event_type="execution_failure_aggregation",
            severity="CRITICAL",
            message=f"{failure_count} failures detected in {EXEC_FAILURE_AGG_WINDOW_SECONDS}s",
            correlation_id=failed_event.correlation_id,
            execution_event_id=failed_event.entity_id,
            symbol=symbol,
            state=status,
            failure_reason="failure_aggregation",
            retry_count=failed_event.retry_count,
            max_retry=failed_event.max_retry,
            root_cause_code="failure_aggregation",
            entity_key=f"execution_failure_aggregation:{bucket_marker}",
            group_window_seconds=EXEC_FAILURE_AGG_WINDOW_SECONDS,
        )


def trigger_idempotency_collision_alert(db: Session, collision: IdempotencyCollision) -> None:
    _emit_execution_alert(
        db,
        event_type="execution_duplicate_collision",
        severity="WARNING",
        message="Duplicate idempotency collision detected",
        correlation_id=collision.correlation_id,
        execution_event_id=(collision.duplicate_request or {}).get("execution_event_id") if isinstance(collision.duplicate_request, dict) else None,
        symbol=None,
        state="collision",
        failure_reason="idempotency_collision",
        root_cause_code="idempotency_collision",
        entity_key=collision.idempotency_key,
    )
