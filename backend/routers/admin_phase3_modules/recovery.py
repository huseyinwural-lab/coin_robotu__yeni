from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import PlaybookExecutionRun, PlaybookRollbackMarker, User
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
