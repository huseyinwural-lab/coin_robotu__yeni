from datetime import datetime, timezone
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
from sqlalchemy import func
import json

from db import get_db
from deps import require_admin
from models import AlertPolicy, FailedEvent, PlaybookExecutionRun, PlaybookRollbackMarker, StateRebuildLog, User
from services.execution_readiness_service import evaluate_execution_readiness
from services.observability_service import collect_observability_snapshot
from services.pipeline.runtime import pipeline_runtime
from routers.admin_phase3_modules.common import (
    ensure_reason,
    ensure_super_admin,
    read_preview_payload,
    save_preview_payload,
    shape_response,
    write_audit_event,
)

router = APIRouter(tags=["admin_phase3_recovery"])


class PlaybookActionInput(BaseModel):
    action: str
    severity: str = "INFO"
    reason: str = ""


class PlaybookPreviewRequest(BaseModel):
    recommended_actions: list[PlaybookActionInput] = Field(default_factory=list)
    anomaly_notes: list[str] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)


class PlaybookApplyRequest(BaseModel):
    preview_token: str
    confirm: bool = False
    reason: str = Field(..., min_length=3)


class PlaybookApproveRequest(BaseModel):
    playbook_run_id: str
    confirm: bool = False
    reason: str = Field(..., min_length=3)


class PlaybookExecuteRequest(BaseModel):
    playbook_run_id: str
    confirm: bool = False
    reason: str = Field(..., min_length=3)


class PlaybookRollbackRequest(BaseModel):
    playbook_run_id: str
    confirm: bool = False
    reason: str = Field(..., min_length=3)


class PlaybookRetryRequest(BaseModel):
    original_playbook_run_id: str
    confirm: bool = False
    reason: str = Field(..., min_length=3)


def _severity_rank(value: str) -> int:
    normalized = str(value or "INFO").upper()
    if normalized == "CRITICAL":
        return 3
    if normalized == "WARNING":
        return 2
    return 1


def _upsert_rollback_marker(
    db: Session,
    *,
    playbook_run_id: str,
    chain_id: str,
    execution_state: str,
    rollback_state: str,
    rollback_payload: dict,
    created_by: str,
) -> PlaybookRollbackMarker:
    marker = db.query(PlaybookRollbackMarker).filter(PlaybookRollbackMarker.playbook_run_id == playbook_run_id).first()
    if marker is None:
        marker = PlaybookRollbackMarker(
            playbook_run_id=playbook_run_id,
            chain_id=chain_id,
            execution_state=execution_state,
            rollback_state=rollback_state,
            rollback_payload=rollback_payload,
            created_by=created_by,
        )
        db.add(marker)
    else:
        marker.execution_state = execution_state
        marker.rollback_state = rollback_state
        marker.rollback_payload = rollback_payload
        marker.updated_at = datetime.now(timezone.utc)
    return marker


def _normalize_status(value: bool) -> str:
    return "ready" if value else "blocked"


def _cache_get_json(cache_client, key: str, fallback: dict) -> dict:
    if cache_client is None:
        return fallback
    try:
        raw = cache_client.get(key)
        if raw is None:
            return fallback
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else fallback
        if isinstance(raw, dict):
            return raw
    except Exception:
        return fallback
    return fallback


def _execute_playbook_step(
    db: Session,
    *,
    step: dict,
    reason: str,
    actor_id: str,
) -> dict:
    action_name = str(step.get("action") or "").strip().lower()
    timestamp = datetime.now(timezone.utc).isoformat()

    if "fail" in action_name:
        return {
            "status": "failed",
            "message": "forced_failure_by_step_name",
            "rollback_step": None,
            "operation": {"action": action_name, "mode": "forced_failure", "executed_at": timestamp},
        }

    if action_name == "guardrail_hardening":
        policy = db.query(AlertPolicy).filter(AlertPolicy.id == "global").first()
        if policy is None:
            policy = AlertPolicy(id="global")
            db.add(policy)
            db.flush()
        previous_value = int(policy.gate_override_warning_per_day or 0)
        policy.gate_override_warning_per_day = previous_value + 1
        policy.updated_at = datetime.now(timezone.utc)
        return {
            "status": "executed",
            "message": "guardrail_policy_hardened",
            "rollback_step": {
                "action": "guardrail_hardening_rollback",
                "policy_id": policy.id,
                "previous_warning_limit": previous_value,
            },
            "operation": {
                "action": action_name,
                "changed_field": "gate_override_warning_per_day",
                "before": previous_value,
                "after": int(policy.gate_override_warning_per_day or 0),
                "reason": reason,
                "actor_id": actor_id,
                "executed_at": timestamp,
            },
        }

    if action_name == "retry_policy_tune":
        rows = (
            db.query(FailedEvent)
            .filter(FailedEvent.status.in_(["pending", "failed"]))
            .order_by(FailedEvent.created_at.asc())
            .limit(25)
            .all()
        )
        updated = []
        now = datetime.now(timezone.utc)
        for row in rows:
            previous_max_retry = int(row.max_retry or 0)
            row.max_retry = previous_max_retry + 1
            row.next_retry_at = now
            row.retry_reason = reason
            row.updated_at = now
            updated.append({"id": row.id, "previous_max_retry": previous_max_retry, "new_max_retry": int(row.max_retry or 0)})

        return {
            "status": "executed",
            "message": "failed_event_retry_policy_tuned",
            "rollback_step": {
                "action": "retry_policy_tune_rollback",
                "rows": [{"id": item["id"], "previous_max_retry": item["previous_max_retry"]} for item in updated],
            },
            "operation": {
                "action": action_name,
                "affected_count": len(updated),
                "affected_ids": [item["id"] for item in updated],
                "reason": reason,
                "actor_id": actor_id,
                "executed_at": timestamp,
            },
        }

    if action_name == "runbook_review":
        log_row = StateRebuildLog(
            rebuild_type="playbook_runbook_review",
            status="completed",
            trigger_source="playbook_execute",
            details={"reason": reason, "actor_id": actor_id},
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        db.add(log_row)
        db.flush()
        return {
            "status": "executed",
            "message": "runbook_review_logged",
            "rollback_step": {
                "action": "runbook_review_rollback",
                "state_rebuild_log_id": log_row.id,
            },
            "operation": {
                "action": action_name,
                "state_rebuild_log_id": log_row.id,
                "reason": reason,
                "actor_id": actor_id,
                "executed_at": timestamp,
            },
        }

    return {
        "status": "executed",
        "message": "no_op_execution",
        "rollback_step": {
            "action": "noop_rollback",
            "note": f"no side effect for action={action_name or 'unknown'}",
        },
        "operation": {
            "action": action_name or "unknown",
            "mode": "no_op",
            "reason": reason,
            "actor_id": actor_id,
            "executed_at": timestamp,
        },
    }


def _rollback_playbook_step(db: Session, *, rollback_step: dict, actor_id: str) -> dict:
    action_name = str(rollback_step.get("action") or "").strip().lower()
    timestamp = datetime.now(timezone.utc).isoformat()

    if action_name == "guardrail_hardening_rollback":
        policy_id = str(rollback_step.get("policy_id") or "global")
        previous_value = int(rollback_step.get("previous_warning_limit") or 0)
        policy = db.query(AlertPolicy).filter(AlertPolicy.id == policy_id).first()
        if policy:
            policy.gate_override_warning_per_day = previous_value
            policy.updated_at = datetime.now(timezone.utc)
        return {"status": "executed", "message": "guardrail_policy_restored", "action": action_name, "executed_at": timestamp}

    if action_name == "retry_policy_tune_rollback":
        rows = rollback_step.get("rows") or []
        restored = 0
        for item in rows:
            row_id = str(item.get("id") or "")
            previous_max_retry = int(item.get("previous_max_retry") or 0)
            row = db.query(FailedEvent).filter(FailedEvent.id == row_id).first()
            if row is None:
                continue
            row.max_retry = previous_max_retry
            row.updated_at = datetime.now(timezone.utc)
            restored += 1
        return {
            "status": "executed",
            "message": "retry_policy_restored",
            "action": action_name,
            "restored_count": restored,
            "executed_at": timestamp,
        }

    if action_name == "runbook_review_rollback":
        log_id = str(rollback_step.get("state_rebuild_log_id") or "")
        if log_id:
            row = db.query(StateRebuildLog).filter(StateRebuildLog.id == log_id).first()
            if row:
                row.status = "rolled_back"
                row.finished_at = datetime.now(timezone.utc)
                details = dict(row.details or {})
                details["rolled_back_by"] = actor_id
                row.details = details
        return {"status": "executed", "message": "runbook_review_rollback_marked", "action": action_name, "executed_at": timestamp}

    return {
        "status": "executed",
        "message": "no_op_rollback",
        "action": action_name or "unknown",
        "executed_at": timestamp,
    }


@router.get("/incident-snapshots/playbook/preflight")
def incident_snapshot_playbook_preflight(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    required_tables = [
        "playbook_execution_runs",
        "playbook_rollback_markers",
        "signal_governance_decisions",
    ]
    required_migration = "20260323_0063"

    db_ready = False
    db_error = None
    migration_version = None
    migration_compatible = False

    try:
        db.execute(text("SELECT 1"))
        db_ready = True
    except Exception as exc:
        db_error = str(exc)

    try:
        migration_version = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
    except Exception as exc:
        db_error = db_error or str(exc)

    if migration_version:
        migration_compatible = str(migration_version) >= required_migration

    table_results: dict[str, bool] = {}
    inspector = inspect(db.bind)
    available_tables = set(inspector.get_table_names())
    for table_name in required_tables:
        table_results[table_name] = table_name in available_tables

    execution_readiness = {}
    try:
        execution_readiness = evaluate_execution_readiness(db, user_id=current_admin.id)
    except Exception as exc:
        execution_readiness = {
            "status": "DEGRADED",
            "mode": "MOCKED",
            "note": str(exc),
        }

    slack_mock_enabled = os.environ.get("ALERT_ALLOW_MOCK_SLACK", "true").strip().lower() in {"1", "true", "yes", "mock"}
    execution_mode = str(execution_readiness.get("mode") or "MOCKED").upper()
    binance_mocked = execution_mode != "LIVE"

    runtime_queue_state = _cache_get_json(pipeline_runtime.cache, "scanner:queue:state", {})
    runtime_worker_state = _cache_get_json(pipeline_runtime.cache, "scanner:worker:last", {})
    observability_snapshot = collect_observability_snapshot(db)
    failed_backlog = (
        db.query(func.count(FailedEvent.id))
        .filter(FailedEvent.status.in_(["pending", "failed"]))
        .scalar()
    ) or 0

    queue_depth = int(runtime_queue_state.get("depth") or observability_snapshot.get("queue_size") or 0)
    worker_latency_ms = float(runtime_queue_state.get("cycle_latency_ms") or 0.0)
    worker_seen = bool(runtime_worker_state)
    worker_utilization = float(runtime_queue_state.get("worker_utilization") or 0.0)

    queue_health_status = "ready"
    queue_health_ui = "OK"
    if queue_depth >= 80 or failed_backlog >= 20 or worker_latency_ms >= 12000:
        queue_health_status = "blocked"
        queue_health_ui = "ERROR"
    elif queue_depth >= 30 or failed_backlog >= 5 or worker_latency_ms >= 6000:
        queue_health_status = "warning"
        queue_health_ui = "WARNING"

    execution_engine_status = "ready"
    execution_engine_ui = "OK"
    if not worker_seen:
        execution_engine_status = "warning"
        execution_engine_ui = "WARNING"
    if queue_health_status == "blocked":
        execution_engine_status = "blocked"
        execution_engine_ui = "ERROR"

    def _check_payload(*, key: str, label: str, status_value: str, ui_status: str, detail: str) -> dict:
        return {
            "key": key,
            "label": label,
            "status": status_value,
            "ui_status": ui_status,
            "detail": detail,
        }

    checks = [
        _check_payload(
            key="db_readiness",
            label="DB readiness",
            status_value=_normalize_status(db_ready),
            ui_status="OK" if db_ready else "ERROR",
            detail="Database bağlantısı aktif" if db_ready else (db_error or "Database erişilemedi"),
        ),
        _check_payload(
            key="migration_compatibility",
            label="Migration compatibility",
            status_value=_normalize_status(migration_compatible),
            ui_status="OK" if migration_compatible else "ERROR",
            detail=f"current={migration_version or 'unknown'} required>={required_migration}",
        ),
        _check_payload(
            key="table_access",
            label="Playbook/Governance tables",
            status_value=_normalize_status(all(table_results.values())),
            ui_status="OK" if all(table_results.values()) else "ERROR",
            detail=", ".join([f"{name}:{'ok' if exists else 'missing'}" for name, exists in table_results.items()]),
        ),
        _check_payload(
            key="integration_readiness",
            label="Integration readiness",
            status_value="ready",
            ui_status="OK" if (slack_mock_enabled and binance_mocked) else "WARNING",
            detail=f"slack={'MOCKED' if slack_mock_enabled else 'LIVE'} | binance={'MOCKED' if binance_mocked else 'LIVE'}",
        ),
        _check_payload(
            key="execution_engine_readiness",
            label="Execution engine readiness",
            status_value=execution_engine_status,
            ui_status=execution_engine_ui,
            detail=f"worker_seen={worker_seen} worker_utilization={round(worker_utilization, 4)}",
        ),
        _check_payload(
            key="queue_job_health",
            label="Queue / job health",
            status_value=queue_health_status,
            ui_status=queue_health_ui,
            detail=(
                f"queue_depth={queue_depth} failed_backlog={failed_backlog} "
                f"worker_latency_ms={round(worker_latency_ms, 2)}"
            ),
        ),
        _check_payload(
            key="playbook_flow_gate",
            label="Preview/Approve/Execute gate",
            status_value=_normalize_status(
                db_ready and migration_compatible and all(table_results.values()) and execution_engine_status != "blocked"
            ),
            ui_status="OK" if (db_ready and migration_compatible and all(table_results.values()) and execution_engine_status != "blocked") else "ERROR",
            detail="Flow çalıştırılabilir" if (db_ready and migration_compatible and all(table_results.values()) and execution_engine_status != "blocked") else "Ön koşullar eksik",
        ),
    ]

    has_error = any(item["status"] == "blocked" for item in checks)
    has_warning = any(item["status"] == "warning" for item in checks)
    overall_state = "error" if has_error else "warning" if has_warning else "ready"
    overall_ui_status = "ERROR" if has_error else "WARNING" if has_warning else "OK"
    preflight_score = max(
        0,
        100
        - (30 if has_error else 0)
        - (10 * sum(1 for item in checks if item["status"] == "warning"))
        - (5 if queue_depth >= 30 else 0)
        - (5 if failed_backlog >= 5 else 0),
    )

    return shape_response(
        message="playbook_preflight_ready" if overall_state == "ready" else "playbook_preflight_warning" if overall_state == "warning" else "playbook_preflight_blocked",
        overall_state=overall_state,
        overall_ui_status=overall_ui_status,
        preflight_score=preflight_score,
        execution_disable=overall_state == "error",
        checked_at=datetime.now(timezone.utc).isoformat(),
        checks=checks,
        migration={
            "current": migration_version,
            "required": required_migration,
            "compatible": migration_compatible,
        },
        tables=table_results,
        integration_modes={
            "slack": "MOCKED" if slack_mock_enabled else "LIVE",
            "binance": "MOCKED" if binance_mocked else "LIVE",
            "execution_mode": execution_mode,
            "execution_status": str(execution_readiness.get("status") or "unknown"),
        },
        queue_job_metrics={
            "queue_depth": queue_depth,
            "failed_backlog": int(failed_backlog),
            "worker_latency_ms": round(worker_latency_ms, 2),
            "worker_seen": worker_seen,
            "worker_utilization": round(worker_utilization, 4),
            "observability_queue_size": int(observability_snapshot.get("queue_size") or 0),
        },
        score_components={
            "runtime_worker_health": 50,
            "db_migration_tables": 30,
            "backlog_pressure": 20,
        },
        role_gate={
            "current_role": str(getattr(current_admin.role, "value", current_admin.role) or "admin"),
            "approve_allowed": str(getattr(current_admin.role, "value", current_admin.role) or "") == "super_admin",
            "apply_allowed": str(getattr(current_admin.role, "value", current_admin.role) or "") == "super_admin" and overall_state != "error",
            "execute_allowed": str(getattr(current_admin.role, "value", current_admin.role) or "") == "super_admin" and overall_state != "error",
        },
    )


@router.post("/incident-snapshots/playbook/preview")
def incident_snapshot_playbook_preview(
    payload: PlaybookPreviewRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    actions = payload.recommended_actions or []
    if not actions:
        actions = [
            PlaybookActionInput(action="keep current policy", severity="INFO", reason="stable").model_dump(),
        ]
    else:
        actions = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in actions]

    highest_severity = "INFO"
    if any(_severity_rank(item.get("severity")) == 3 for item in actions):
        highest_severity = "CRITICAL"
    elif any(_severity_rank(item.get("severity")) == 2 for item in actions):
        highest_severity = "WARNING"

    steps = [
        {
            "step": index + 1,
            "action": item.get("action"),
            "severity": str(item.get("severity") or "INFO").upper(),
            "reason": item.get("reason") or "",
            "mode": "preview_only",
        }
        for index, item in enumerate(actions)
    ]

    chain_id = str(payload.scope.get("chain_id") or f"playbook_chain_{uuid.uuid4().hex[:12]}")
    preview_payload = {
        "type": "incident_playbook_preview",
        "actor_user_id": current_admin.id,
        "scope": payload.scope or {},
        "anomaly_notes": payload.anomaly_notes or [],
        "steps": steps,
        "chain_id": chain_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    preview_token = save_preview_payload(preview_payload)

    playbook_run = PlaybookExecutionRun(
        preview_token=preview_token,
        chain_id=chain_id,
        execution_state="preview",
        step_index=0,
        total_steps=len(steps),
        failure_reason=None,
        parent_run_id=None,
        retry_attempt=0,
        steps=steps,
        scope_payload=payload.scope or {},
        created_by=current_admin.id,
    )
    db.add(playbook_run)
    db.flush()

    write_audit_event(
        db,
        user=current_admin,
        action="incident_playbook_preview",
        entity_type="execution_incident_snapshot",
        entity_id=preview_token,
        details={
            "preview_token": preview_token,
            "steps": steps,
            "scope": payload.scope or {},
            "anomaly_notes": payload.anomaly_notes or [],
            "non_destructive": True,
            "playbook_run_id": playbook_run.id,
            "chain_id": chain_id,
        },
    )
    db.commit()

    return shape_response(
        message="playbook_preview_ready",
        preview_token=preview_token,
        playbook_run_id=playbook_run.id,
        chain_id=chain_id,
        execution_state="preview",
        preview={
            "non_destructive": True,
            "highest_severity": highest_severity,
            "steps": steps,
            "anomaly_notes": payload.anomaly_notes or [],
        },
    )


@router.post("/incident-snapshots/playbook/apply")
def incident_snapshot_playbook_apply(
    payload: PlaybookApplyRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ensure_super_admin(current_admin)
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirm_required")

    reason = ensure_reason(payload.reason, field_name="reason", min_length=3)
    preview_payload = read_preview_payload(payload.preview_token)
    if not preview_payload or preview_payload.get("type") != "incident_playbook_preview":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="preview_token_invalid_or_expired")

    run_row = db.query(PlaybookExecutionRun).filter(PlaybookExecutionRun.preview_token == payload.preview_token).first()
    if run_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook_run_not_found")
    if run_row.execution_state not in {"preview", "planned"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="playbook_state_invalid_for_plan")

    steps = preview_payload.get("steps") or []
    planned_actions = [
        {
            "step": item.get("step"),
            "action": item.get("action"),
            "severity": item.get("severity"),
            "execution_mode": "planned_non_destructive",
            "result": "queued_for_operator_review",
        }
        for item in steps
    ]

    run_row.execution_state = "planned"
    run_row.updated_at = datetime.now(timezone.utc)
    _upsert_rollback_marker(
        db,
        playbook_run_id=run_row.id,
        chain_id=run_row.chain_id,
        execution_state="planned",
        rollback_state="ready",
        rollback_payload={"planned_actions": planned_actions, "reason": reason},
        created_by=current_admin.id,
    )

    write_audit_event(
        db,
        user=current_admin,
        action="incident_playbook_apply",
        entity_type="execution_incident_snapshot",
        entity_id=payload.preview_token,
        details={
            "preview_token": payload.preview_token,
            "reason": reason,
            "planned_actions": planned_actions,
            "scope": preview_payload.get("scope") or {},
            "non_destructive": True,
            "playbook_run_id": run_row.id,
            "chain_id": run_row.chain_id,
        },
        severity="warning",
    )
    db.commit()

    return shape_response(
        message="playbook_apply_completed_in_non_destructive_mode",
        result={
            "confirmed": True,
            "non_destructive": True,
            "playbook_run_id": run_row.id,
            "execution_state": run_row.execution_state,
            "planned_actions": planned_actions,
        },
    )


@router.post("/incident-snapshots/playbook/approve")
@router.post("/playbook/approve")
def incident_snapshot_playbook_approve(
    payload: PlaybookApproveRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ensure_super_admin(current_admin)
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirm_required")
    reason = ensure_reason(payload.reason, min_length=3)

    run_row = db.query(PlaybookExecutionRun).filter(PlaybookExecutionRun.id == payload.playbook_run_id).first()
    if run_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook_run_not_found")
    if run_row.execution_state not in {"preview", "planned"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="playbook_must_be_preview_or_planned_before_approve")

    run_row.execution_state = "approved"
    run_row.step_index = 0
    run_row.total_steps = len(run_row.steps or [])
    run_row.failure_reason = None
    run_row.approved_by = current_admin.id
    run_row.updated_at = datetime.now(timezone.utc)
    _upsert_rollback_marker(
        db,
        playbook_run_id=run_row.id,
        chain_id=run_row.chain_id,
        execution_state="approved",
        rollback_state="not_available",
        rollback_payload={"approved_at": datetime.now(timezone.utc).isoformat(), "reason": reason},
        created_by=current_admin.id,
    )

    write_audit_event(
        db,
        user=current_admin,
        action="incident_playbook_approve",
        entity_type="playbook_execution_run",
        entity_id=run_row.id,
        details={
            "reason": reason,
            "execution_state": "approved",
            "chain_id": run_row.chain_id,
        },
        severity="warning",
    )
    db.commit()
    return shape_response(
        message="playbook_approved",
        playbook_run_id=run_row.id,
        execution_state=run_row.execution_state,
        chain_id=run_row.chain_id,
    )


@router.post("/incident-snapshots/playbook/execute")
@router.post("/playbook/execute")
def incident_snapshot_playbook_execute(
    payload: PlaybookExecuteRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ensure_super_admin(current_admin)
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirm_required")
    reason = ensure_reason(payload.reason, min_length=3)

    run_row = db.query(PlaybookExecutionRun).filter(PlaybookExecutionRun.id == payload.playbook_run_id).first()
    if run_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook_run_not_found")
    if run_row.execution_state != "approved":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="playbook_must_be_approved_before_execute")

    run_row.execution_state = "executing"
    run_row.step_index = 0
    run_row.total_steps = len(run_row.steps or [])
    run_row.failure_reason = None
    run_row.updated_at = datetime.now(timezone.utc)
    db.flush()

    write_audit_event(
        db,
        user=current_admin,
        action="incident_playbook_execute_started",
        entity_type="playbook_execution_run",
        entity_id=run_row.id,
        details={
            "reason": reason,
            "execution_state": "executing",
            "chain_id": run_row.chain_id,
            "total_steps": run_row.total_steps,
        },
        severity="warning",
    )
    db.commit()

    executed_steps = []
    rollback_steps = []
    failed_step_payload = None
    for index, item in enumerate(run_row.steps or [], start=1):
        result = _execute_playbook_step(db, step=item, reason=reason, actor_id=current_admin.id)
        step_payload = {
            "step": index,
            "action": item.get("action"),
            "severity": item.get("severity"),
            "status": result.get("status"),
            "message": result.get("message"),
            "operation": result.get("operation") or {},
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }
        executed_steps.append(step_payload)
        run_row.step_index = index
        run_row.updated_at = datetime.now(timezone.utc)

        write_audit_event(
            db,
            user=current_admin,
            action="incident_playbook_execute_step",
            entity_type="playbook_execution_run",
            entity_id=run_row.id,
            details={
                "reason": reason,
                "chain_id": run_row.chain_id,
                "step": index,
                "step_payload": step_payload,
                "execution_state": "executing" if result.get("status") != "failed" else "failed",
            },
            severity="warning" if result.get("status") == "failed" else "info",
        )

        if result.get("status") == "failed":
            failed_step_payload = step_payload
            run_row.execution_state = "failed"
            run_row.failure_reason = str(result.get("message") or "step_failed")
            run_row.executed_by = current_admin.id
            _upsert_rollback_marker(
                db,
                playbook_run_id=run_row.id,
                chain_id=run_row.chain_id,
                execution_state="failed",
                rollback_state="not_available",
                rollback_payload={
                    "reason": reason,
                    "executed_steps": executed_steps,
                    "failed_step": failed_step_payload,
                    "rollback_steps": rollback_steps,
                },
                created_by=current_admin.id,
            )
            write_audit_event(
                db,
                user=current_admin,
                action="incident_playbook_execute_failed",
                entity_type="playbook_execution_run",
                entity_id=run_row.id,
                details={
                    "reason": reason,
                    "chain_id": run_row.chain_id,
                    "failed_step": failed_step_payload,
                    "step_index": run_row.step_index,
                    "total_steps": run_row.total_steps,
                    "failure_reason": run_row.failure_reason,
                },
                severity="warning",
            )
            db.commit()
            return shape_response(
                message="playbook_execute_failed",
                playbook_run_id=run_row.id,
                chain_id=run_row.chain_id,
                execution_state=run_row.execution_state,
                step_index=run_row.step_index,
                total_steps=run_row.total_steps,
                failure_reason=run_row.failure_reason,
                executed_steps=executed_steps,
                failed_step=failed_step_payload,
                rollback_state="not_available",
            )

        rollback_step = result.get("rollback_step")
        if isinstance(rollback_step, dict):
            rollback_steps.append({"step": index, **rollback_step})

        db.commit()

    run_row.execution_state = "executed"
    run_row.executed_by = current_admin.id
    run_row.failure_reason = None
    run_row.updated_at = datetime.now(timezone.utc)
    _upsert_rollback_marker(
        db,
        playbook_run_id=run_row.id,
        chain_id=run_row.chain_id,
        execution_state="rollback_available",
        rollback_state="rollback_available",
        rollback_payload={
            "reason": reason,
            "executed_steps": executed_steps,
            "rollback_steps": rollback_steps,
            "rollback_available_at": datetime.now(timezone.utc).isoformat(),
        },
        created_by=current_admin.id,
    )
    write_audit_event(
        db,
        user=current_admin,
        action="incident_playbook_execute_completed",
        entity_type="playbook_execution_run",
        entity_id=run_row.id,
        details={
            "reason": reason,
            "chain_id": run_row.chain_id,
            "step_index": run_row.step_index,
            "total_steps": run_row.total_steps,
            "executed_steps": executed_steps,
            "rollback_available": True,
        },
        severity="info",
    )
    db.commit()

    return shape_response(
        message="playbook_execute_completed",
        playbook_run_id=run_row.id,
        execution_state=run_row.execution_state,
        chain_id=run_row.chain_id,
        step_index=run_row.step_index,
        total_steps=run_row.total_steps,
        failure_reason=run_row.failure_reason,
        rollback_state="rollback_available",
        executed_steps=executed_steps,
        failed_step=None,
    )


@router.post("/incident-snapshots/playbook/rollback")
@router.post("/playbook/rollback")
def incident_snapshot_playbook_rollback(
    payload: PlaybookRollbackRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ensure_super_admin(current_admin)
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirm_required")
    reason = ensure_reason(payload.reason, min_length=3)

    run_row = db.query(PlaybookExecutionRun).filter(PlaybookExecutionRun.id == payload.playbook_run_id).first()
    if run_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook_run_not_found")
    if run_row.execution_state != "executed":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="rollback_requires_executed_state")

    marker = db.query(PlaybookRollbackMarker).filter(PlaybookRollbackMarker.playbook_run_id == run_row.id).first()
    if marker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rollback_marker_not_found")
    if marker.rollback_state != "rollback_available":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="rollback_not_available")

    rollback_steps = list((marker.rollback_payload or {}).get("rollback_steps") or [])
    rollback_results = []
    for item in reversed(rollback_steps):
        result = _rollback_playbook_step(db, rollback_step=item, actor_id=current_admin.id)
        rollback_results.append({
            "step": item.get("step"),
            "action": item.get("action"),
            "status": result.get("status"),
            "message": result.get("message"),
            "executed_at": result.get("executed_at"),
        })
        write_audit_event(
            db,
            user=current_admin,
            action="incident_playbook_rollback_step",
            entity_type="playbook_execution_run",
            entity_id=run_row.id,
            details={
                "reason": reason,
                "chain_id": run_row.chain_id,
                "rollback_step": item,
                "rollback_result": result,
            },
            severity="warning",
        )

    run_row.execution_state = "rollback_executed"
    run_row.updated_at = datetime.now(timezone.utc)
    marker.execution_state = "rollback_executed"
    marker.rollback_state = "rollback_executed"
    marker.rollback_payload = {
        **(marker.rollback_payload or {}),
        "rollback_reason": reason,
        "rollback_results": rollback_results,
        "rollback_executed_at": datetime.now(timezone.utc).isoformat(),
        "rolled_back_by": current_admin.id,
    }
    marker.updated_at = datetime.now(timezone.utc)

    write_audit_event(
        db,
        user=current_admin,
        action="incident_playbook_rollback",
        entity_type="playbook_execution_run",
        entity_id=run_row.id,
        details={
            "reason": reason,
            "chain_id": run_row.chain_id,
            "rollback_count": len(rollback_results),
            "execution_state": run_row.execution_state,
        },
        severity="warning",
    )
    db.commit()

    return shape_response(
        message="playbook_rollback_executed",
        playbook_run_id=run_row.id,
        chain_id=run_row.chain_id,
        execution_state=run_row.execution_state,
        rollback_state=marker.rollback_state,
        rollback_results=rollback_results,
    )


@router.post("/incident-snapshots/playbook/retry")
@router.post("/playbook/retry")
def incident_snapshot_playbook_retry(
    payload: PlaybookRetryRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ensure_super_admin(current_admin)
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirm_required")
    reason = ensure_reason(payload.reason, min_length=3)

    original_run = db.query(PlaybookExecutionRun).filter(PlaybookExecutionRun.id == payload.original_playbook_run_id).first()
    if original_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook_run_not_found")
    if original_run.execution_state != "failed":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="retry_requires_failed_state")

    retry_preview_token = f"retry_{uuid.uuid4().hex[:20]}"
    retry_run = PlaybookExecutionRun(
        preview_token=retry_preview_token,
        chain_id=original_run.chain_id,
        execution_state="approved",
        step_index=0,
        total_steps=len(original_run.steps or []),
        failure_reason=None,
        parent_run_id=original_run.id,
        retry_attempt=int(original_run.retry_attempt or 0) + 1,
        steps=original_run.steps or [],
        scope_payload={
            **(original_run.scope_payload or {}),
            "retry_of_run_id": original_run.id,
            "retry_reason": reason,
        },
        approved_by=current_admin.id,
        created_by=current_admin.id,
    )
    db.add(retry_run)
    db.flush()

    _upsert_rollback_marker(
        db,
        playbook_run_id=retry_run.id,
        chain_id=retry_run.chain_id,
        execution_state="approved",
        rollback_state="not_available",
        rollback_payload={
            "retry_of_run_id": original_run.id,
            "retry_reason": reason,
            "retry_attempt": retry_run.retry_attempt,
        },
        created_by=current_admin.id,
    )

    write_audit_event(
        db,
        user=current_admin,
        action="incident_playbook_retry_created",
        entity_type="playbook_execution_run",
        entity_id=retry_run.id,
        details={
            "reason": reason,
            "original_playbook_run_id": original_run.id,
            "retry_playbook_run_id": retry_run.id,
            "retry_attempt": retry_run.retry_attempt,
            "chain_id": retry_run.chain_id,
        },
        severity="warning",
    )
    db.commit()

    return shape_response(
        message="playbook_retry_created",
        original_playbook_run_id=original_run.id,
        retry_playbook_run_id=retry_run.id,
        parent_run_id=retry_run.parent_run_id,
        execution_state=retry_run.execution_state,
        step_index=retry_run.step_index,
        total_steps=retry_run.total_steps,
        retry_attempt=retry_run.retry_attempt,
        chain_id=retry_run.chain_id,
    )


@router.get("/incident-snapshots/playbook/runs/{playbook_run_id}")
def incident_snapshot_playbook_run_detail(
    playbook_run_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    run_row = db.query(PlaybookExecutionRun).filter(PlaybookExecutionRun.id == playbook_run_id).first()
    if run_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook_run_not_found")
    rollback_marker = db.query(PlaybookRollbackMarker).filter(PlaybookRollbackMarker.playbook_run_id == playbook_run_id).first()
    return shape_response(
        playbook_run={
            "id": run_row.id,
            "preview_token": run_row.preview_token,
            "chain_id": run_row.chain_id,
            "execution_state": run_row.execution_state,
            "step_index": int(run_row.step_index or 0),
            "total_steps": int(run_row.total_steps or len(run_row.steps or [])),
            "failure_reason": run_row.failure_reason,
            "parent_run_id": run_row.parent_run_id,
            "retry_attempt": int(run_row.retry_attempt or 0),
            "steps": run_row.steps,
            "scope_payload": run_row.scope_payload,
            "created_by": run_row.created_by,
            "approved_by": run_row.approved_by,
            "executed_by": run_row.executed_by,
            "created_at": run_row.created_at.isoformat() if run_row.created_at else None,
            "updated_at": run_row.updated_at.isoformat() if run_row.updated_at else None,
        },
        rollback_marker=(
            {
                "id": rollback_marker.id,
                "playbook_run_id": rollback_marker.playbook_run_id,
                "chain_id": rollback_marker.chain_id,
                "execution_state": rollback_marker.execution_state,
                "rollback_state": rollback_marker.rollback_state,
                "rollback_payload": rollback_marker.rollback_payload,
                "created_by": rollback_marker.created_by,
                "created_at": rollback_marker.created_at.isoformat() if rollback_marker.created_at else None,
                "updated_at": rollback_marker.updated_at.isoformat() if rollback_marker.updated_at else None,
            }
            if rollback_marker
            else None
        ),
    )
