from datetime import datetime, timezone
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text

from db import get_db
from deps import require_admin
from models import PlaybookExecutionRun, PlaybookRollbackMarker, User
from services.execution_readiness_service import evaluate_execution_readiness
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
    required_migration = "20260323_0062"

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

    checks = [
        {
            "key": "db_readiness",
            "label": "DB readiness",
            "status": _normalize_status(db_ready),
            "detail": "Database bağlantısı aktif" if db_ready else (db_error or "Database erişilemedi"),
        },
        {
            "key": "migration_compatibility",
            "label": "Migration compatibility",
            "status": _normalize_status(migration_compatible),
            "detail": f"current={migration_version or 'unknown'} required>={required_migration}",
        },
        {
            "key": "table_access",
            "label": "Playbook/Governance tables",
            "status": _normalize_status(all(table_results.values())),
            "detail": ", ".join([f"{name}:{'ok' if exists else 'missing'}" for name, exists in table_results.items()]),
        },
        {
            "key": "integration_readiness",
            "label": "Integration readiness",
            "status": "ready",
            "detail": f"slack={'MOCKED' if slack_mock_enabled else 'LIVE'} | binance={'MOCKED' if binance_mocked else 'LIVE'}",
        },
        {
            "key": "playbook_flow_gate",
            "label": "Preview/Approve/Execute gate",
            "status": _normalize_status(db_ready and migration_compatible and all(table_results.values())),
            "detail": "Flow çalıştırılabilir" if (db_ready and migration_compatible and all(table_results.values())) else "Ön koşullar eksik",
        },
    ]

    overall_ready = all(item["status"] == "ready" for item in checks if item["key"] != "integration_readiness")

    return shape_response(
        message="playbook_preflight_ready" if overall_ready else "playbook_preflight_blocked",
        overall_state="ready" if overall_ready else "blocked",
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
        role_gate={
            "current_role": str(getattr(current_admin.role, "value", current_admin.role) or "admin"),
            "approve_allowed": str(getattr(current_admin.role, "value", current_admin.role) or "") == "super_admin",
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
    if run_row.execution_state != "planned":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="playbook_must_be_planned_before_approve")

    run_row.execution_state = "approved"
    run_row.approved_by = current_admin.id
    run_row.updated_at = datetime.now(timezone.utc)
    _upsert_rollback_marker(
        db,
        playbook_run_id=run_row.id,
        chain_id=run_row.chain_id,
        execution_state="approved",
        rollback_state="ready",
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
def incident_snapshot_playbook_execute(
    payload: PlaybookExecuteRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirm_required")
    reason = ensure_reason(payload.reason, min_length=3)

    run_row = db.query(PlaybookExecutionRun).filter(PlaybookExecutionRun.id == payload.playbook_run_id).first()
    if run_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook_run_not_found")
    if run_row.execution_state != "approved":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="playbook_must_be_approved_before_execute")

    executed_steps = []
    failed_step = None
    for item in run_row.steps or []:
        action_name = str(item.get("action") or "")
        if "fail" in action_name:
            failed_step = action_name
            executed_steps.append({
                "action": action_name,
                "status": "failed",
                "message": "partial_failure_detected",
            })
            break
        executed_steps.append({
            "action": action_name,
            "status": "executed",
            "message": "executed_step",
        })

    if failed_step:
        run_row.execution_state = "failed"
        rollback_state = "required"
    else:
        run_row.execution_state = "executed"
        rollback_state = "ready"

    run_row.executed_by = current_admin.id
    run_row.updated_at = datetime.now(timezone.utc)

    _upsert_rollback_marker(
        db,
        playbook_run_id=run_row.id,
        chain_id=run_row.chain_id,
        execution_state=run_row.execution_state,
        rollback_state=rollback_state,
        rollback_payload={
            "reason": reason,
            "executed_steps": executed_steps,
            "failed_step": failed_step,
        },
        created_by=current_admin.id,
    )

    write_audit_event(
        db,
        user=current_admin,
        action="incident_playbook_execute",
        entity_type="playbook_execution_run",
        entity_id=run_row.id,
        details={
            "reason": reason,
            "execution_state": run_row.execution_state,
            "chain_id": run_row.chain_id,
            "executed_steps": executed_steps,
            "failed_step": failed_step,
        },
        severity="warning" if failed_step else "info",
    )
    db.commit()

    return shape_response(
        message="playbook_execute_completed" if not failed_step else "playbook_execute_partial_failure",
        playbook_run_id=run_row.id,
        execution_state=run_row.execution_state,
        chain_id=run_row.chain_id,
        rollback_state=rollback_state,
        executed_steps=executed_steps,
        failed_step=failed_step,
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
