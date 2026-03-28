from __future__ import annotations

import logging
import os
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from statistics import mean
from threading import Lock

from sqlalchemy.orm import Session

from models import UserExecutionIntent
from services.system_alert_service import create_system_alert

logger = logging.getLogger("observability")

OBSERVABILITY_WINDOW_MINUTES = 5
ERROR_RATE_THRESHOLD = float(os.environ.get("OBS_ERROR_RATE_THRESHOLD", "0.03"))
LATENCY_P95_THRESHOLD_MS = float(os.environ.get("OBS_LATENCY_P95_THRESHOLD_MS", "1000"))
QUEUE_SIZE_THRESHOLD = int(os.environ.get("OBS_QUEUE_SIZE_THRESHOLD", "30"))
READY_QUEUE_CRITICAL_FACTOR = int(os.environ.get("OBS_READY_QUEUE_CRITICAL_FACTOR", "2"))

_OBSERVATIONS: deque[dict] = deque(maxlen=6000)
_OBS_LOCK = Lock()
_READY_OVERRIDE: dict[str, object] = {"active": False, "reason": None, "until": None}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _categorize_endpoint(path: str, method: str) -> str:
    endpoint = f"{method.upper()} {path}"
    if endpoint in {"POST /api/auth/login/admin", "POST /api/auth/login/user"}:
        return "auth_login"
    if endpoint == "POST /api/user/execution/intent/submit":
        return "execution_intent_submit"
    if endpoint == "POST /api/admin/kill-switch":
        return "admin_kill_switch"
    return "other"


def record_http_observation(*, path: str, method: str, status_code: int, duration_ms: float) -> None:
    entry = {
        "timestamp": _utcnow(),
        "source": "http",
        "category": _categorize_endpoint(path, method),
        "path": path,
        "method": method.upper(),
        "status_code": int(status_code),
        "duration_ms": float(duration_ms),
    }
    with _OBS_LOCK:
        _OBSERVATIONS.append(entry)


def record_worker_step_observation(*, step_name: str, duration_ms: float, success: bool) -> None:
    entry = {
        "timestamp": _utcnow(),
        "source": "worker",
        "category": "queue_processing",
        "path": step_name,
        "method": "WORKER",
        "status_code": 200 if success else 500,
        "duration_ms": float(duration_ms),
    }
    with _OBS_LOCK:
        _OBSERVATIONS.append(entry)


def _window_observations(minutes: int = OBSERVABILITY_WINDOW_MINUTES) -> list[dict]:
    cutoff = _utcnow() - timedelta(minutes=minutes)
    with _OBS_LOCK:
        return [row for row in list(_OBSERVATIONS) if row["timestamp"] >= cutoff]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, int(round((percentile / 100) * (len(ordered) - 1)))))
    return float(ordered[rank])


def _pending_queue_size(db: Session) -> int:
    return int(
        db.query(UserExecutionIntent)
        .filter(UserExecutionIntent.status.in_(["PREVIEWED", "QUEUED_FOR_APPROVAL", "SUBMITTED"]))
        .count()
    )


def collect_observability_snapshot(db: Session, *, minutes: int = OBSERVABILITY_WINDOW_MINUTES) -> dict:
    rows = _window_observations(minutes)
    total = len(rows)
    errors_4xx = len([row for row in rows if 400 <= int(row["status_code"]) < 500])
    errors_5xx = len([row for row in rows if int(row["status_code"]) >= 500])
    errors_total = errors_4xx + errors_5xx

    durations = [float(row["duration_ms"]) for row in rows]
    latency_p95 = _percentile(durations, 95)
    latency_avg = float(mean(durations)) if durations else 0.0

    categories = {"auth_login", "execution_intent_submit", "admin_kill_switch", "queue_processing", "other"}
    latency_by_category: dict[str, float] = {}
    for category in categories:
        category_durations = [float(row["duration_ms"]) for row in rows if row["category"] == category]
        latency_by_category[category] = _percentile(category_durations, 95)

    queue_size = _pending_queue_size(db)
    throughput = round(len(rows) / max(minutes, 1), 4)
    error_rate = (errors_total / total) if total else 0.0
    error_rate_5xx = (errors_5xx / total) if total else 0.0
    error_rate_4xx = (errors_4xx / total) if total else 0.0

    return {
        "timestamp": _utcnow().isoformat(),
        "window_minutes": minutes,
        "total_requests": total,
        "errors_4xx": errors_4xx,
        "errors_5xx": errors_5xx,
        "error_rate": round(error_rate, 6),
        "error_rate_4xx": round(error_rate_4xx, 6),
        "error_rate_5xx": round(error_rate_5xx, 6),
        "latency_ms_p95": round(latency_p95, 2),
        "latency_ms_avg": round(latency_avg, 2),
        "latency_ms_p95_by_category": {k: round(v, 2) for k, v in latency_by_category.items()},
        "event_processing_latency": round(latency_by_category.get("queue_processing", 0.0), 2),
        "trade_execution_latency": round(latency_by_category.get("execution_intent_submit", 0.0), 2),
        "replay_duration": round(max(latency_by_category.get("other", 0.0), latency_avg), 2),
        "failure_rate": round(error_rate, 6),
        "success_rate": round(max(0.0, 1 - error_rate), 6),
        "throughput": throughput,
        "queue_size": queue_size,
        "thresholds": {
            "error_rate": ERROR_RATE_THRESHOLD,
            "latency_p95_ms": LATENCY_P95_THRESHOLD_MS,
            "queue_size": QUEUE_SIZE_THRESHOLD,
        },
    }


def build_metrics_exposition(snapshot: dict) -> str:
    lines = [
        "# TYPE event_processing_latency gauge",
        f"event_processing_latency{{window=\"{snapshot['window_minutes']}m\"}} {snapshot.get('event_processing_latency', 0)}",
        "# TYPE trade_execution_latency gauge",
        f"trade_execution_latency{{window=\"{snapshot['window_minutes']}m\"}} {snapshot.get('trade_execution_latency', 0)}",
        "# TYPE failure_rate gauge",
        f"failure_rate{{window=\"{snapshot['window_minutes']}m\"}} {snapshot.get('failure_rate', snapshot['error_rate'])}",
        "# TYPE success_rate gauge",
        f"success_rate{{window=\"{snapshot['window_minutes']}m\"}} {snapshot.get('success_rate', 0)}",
        "# TYPE replay_duration gauge",
        f"replay_duration{{window=\"{snapshot['window_minutes']}m\"}} {snapshot.get('replay_duration', 0)}",
        "# TYPE throughput gauge",
        f"throughput{{window=\"{snapshot['window_minutes']}m\"}} {snapshot.get('throughput', 0)}",
        "# TYPE observability_error_rate_ratio gauge",
        f"observability_error_rate_ratio{{window=\"{snapshot['window_minutes']}m\"}} {snapshot['error_rate']}",
        "# TYPE observability_error_rate_4xx_ratio gauge",
        f"observability_error_rate_4xx_ratio{{window=\"{snapshot['window_minutes']}m\"}} {snapshot['error_rate_4xx']}",
        "# TYPE observability_error_rate_5xx_ratio gauge",
        f"observability_error_rate_5xx_ratio{{window=\"{snapshot['window_minutes']}m\"}} {snapshot['error_rate_5xx']}",
        "# TYPE observability_latency_ms_p95 gauge",
        f"observability_latency_ms_p95 {snapshot['latency_ms_p95']}",
        "# TYPE observability_latency_ms_avg gauge",
        f"observability_latency_ms_avg {snapshot['latency_ms_avg']}",
        "# TYPE observability_queue_size gauge",
        f"observability_queue_size {snapshot['queue_size']}",
    ]
    for category, value in sorted((snapshot.get("latency_ms_p95_by_category") or {}).items()):
        lines.append(f"observability_endpoint_latency_ms_p95{{endpoint=\"{category}\"}} {value}")
    return "\n".join(lines) + "\n"


def _build_alert_details(*, alert_type: str, severity: str, summary: str, correlation_id: str | None, payload: dict) -> dict:
    return {
        "alert_type": alert_type,
        "severity": severity,
        "service": os.environ.get("OBSERVABILITY_SERVICE_NAME", "backend-api"),
        "environment": os.environ.get("APP_ENVIRONMENT", "dev"),
        "triggered_at": _utcnow().isoformat(),
        "summary": summary,
        "correlation_id": correlation_id,
        "payload": payload,
    }


def emit_threshold_alerts(db: Session, *, snapshot: dict | None = None) -> list[str]:
    snapshot = snapshot or collect_observability_snapshot(db)
    created_alert_ids: list[str] = []

    if float(snapshot["error_rate"]) >= ERROR_RATE_THRESHOLD:
        alert = create_system_alert(
            db,
            alert_type="observability_error_rate_threshold",
            severity="CRITICAL",
            message="Error rate threshold exceeded",
            details=_build_alert_details(
                alert_type="observability_error_rate_threshold",
                severity="CRITICAL",
                summary=f"error_rate={snapshot['error_rate']} >= {ERROR_RATE_THRESHOLD}",
                correlation_id=None,
                payload=snapshot,
            ),
            root_cause_code="OBS_ERROR_RATE_THRESHOLD",
            dedupe_window_seconds=300,
        )
        created_alert_ids.append(alert.id)

    if float(snapshot["latency_ms_p95"]) >= LATENCY_P95_THRESHOLD_MS:
        alert = create_system_alert(
            db,
            alert_type="observability_latency_threshold",
            severity="WARNING",
            message="Latency p95 threshold exceeded",
            details=_build_alert_details(
                alert_type="observability_latency_threshold",
                severity="WARNING",
                summary=f"latency_p95_ms={snapshot['latency_ms_p95']} >= {LATENCY_P95_THRESHOLD_MS}",
                correlation_id=None,
                payload=snapshot,
            ),
            root_cause_code="OBS_LATENCY_THRESHOLD",
            dedupe_window_seconds=300,
        )
        created_alert_ids.append(alert.id)

    if int(snapshot["queue_size"]) >= QUEUE_SIZE_THRESHOLD:
        alert = create_system_alert(
            db,
            alert_type="observability_queue_pressure",
            severity="CRITICAL",
            message="Queue size threshold exceeded",
            details=_build_alert_details(
                alert_type="observability_queue_pressure",
                severity="CRITICAL",
                summary=f"queue_size={snapshot['queue_size']} >= {QUEUE_SIZE_THRESHOLD}",
                correlation_id=None,
                payload=snapshot,
            ),
            root_cause_code="OBS_QUEUE_THRESHOLD",
            dedupe_window_seconds=300,
        )
        created_alert_ids.append(alert.id)

    return created_alert_ids


def activate_ready_override(*, reason: str, seconds: int = 120) -> None:
    until = _utcnow() + timedelta(seconds=max(seconds, 1))
    _READY_OVERRIDE["active"] = True
    _READY_OVERRIDE["reason"] = reason
    _READY_OVERRIDE["until"] = until


def current_ready_override() -> dict:
    active = bool(_READY_OVERRIDE.get("active"))
    until = _READY_OVERRIDE.get("until")
    if not active:
        return {"active": False, "reason": None}

    if isinstance(until, datetime) and until < _utcnow():
        _READY_OVERRIDE["active"] = False
        _READY_OVERRIDE["reason"] = None
        _READY_OVERRIDE["until"] = None
        return {"active": False, "reason": None}

    return {
        "active": True,
        "reason": _READY_OVERRIDE.get("reason"),
        "until": until.isoformat() if isinstance(until, datetime) else None,
    }


def trigger_fake_error_scenario(db: Session, *, correlation_id: str | None = None) -> dict:
    correlation_id = correlation_id or str(uuid.uuid4())
    record_worker_step_observation(step_name="fake_error_injection", duration_ms=5.0, success=False)
    try:
        raise RuntimeError("phase5_fake_error_injection")
    except RuntimeError:
        logger.exception(
            "observability_fake_error",
            extra={
                "event_name": "observability_fake_error",
                "reason_code": "FAKE_ERROR",
                "correlation_id": correlation_id,
            },
        )

    alert = create_system_alert(
        db,
        alert_type="observability_fake_error",
        severity="CRITICAL",
        message="Fake error scenario triggered",
        details=_build_alert_details(
            alert_type="observability_fake_error",
            severity="CRITICAL",
            summary="Fake error injected for observability verification",
            correlation_id=correlation_id,
            payload={"scenario": "fake_error"},
        ),
        root_cause_code="FAKE_ERROR",
        dedupe_window_seconds=0,
    )
    return {"alert_id": alert.id, "delivery_status": alert.delivery_status, "correlation_id": correlation_id}


def trigger_queue_pressure_scenario(db: Session, *, queue_size: int) -> dict:
    record_worker_step_observation(step_name="queue_pressure_simulation", duration_ms=25.0, success=True)
    synthetic_snapshot = collect_observability_snapshot(db)
    synthetic_snapshot["queue_size"] = int(queue_size)
    alert_ids = emit_threshold_alerts(db, snapshot=synthetic_snapshot)
    return {
        "queue_size": int(queue_size),
        "threshold": QUEUE_SIZE_THRESHOLD,
        "alert_ids": alert_ids,
    }


def trigger_ready_fail_scenario(db: Session, *, reason: str = "dependency_simulated_down", duration_seconds: int = 120) -> dict:
    activate_ready_override(reason=reason, seconds=duration_seconds)
    alert = create_system_alert(
        db,
        alert_type="observability_ready_fail",
        severity="CRITICAL",
        message="Readiness check failed by simulation",
        details=_build_alert_details(
            alert_type="observability_ready_fail",
            severity="CRITICAL",
            summary=f"/ready forced to fail: {reason}",
            correlation_id=None,
            payload={"reason": reason, "duration_seconds": duration_seconds},
        ),
        root_cause_code="READY_FAIL_SIMULATION",
        dedupe_window_seconds=0,
    )
    return {
        "reason": reason,
        "until": current_ready_override().get("until"),
        "alert_id": alert.id,
        "delivery_status": alert.delivery_status,
    }