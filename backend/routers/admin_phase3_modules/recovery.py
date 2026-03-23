from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from routers.admin_phase3_modules.common import (
    ensure_reason,
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


def _severity_rank(value: str) -> int:
    normalized = str(value or "INFO").upper()
    if normalized == "CRITICAL":
        return 3
    if normalized == "WARNING":
        return 2
    return 1


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

    preview_payload = {
        "type": "incident_playbook_preview",
        "actor_user_id": current_admin.id,
        "scope": payload.scope or {},
        "anomaly_notes": payload.anomaly_notes or [],
        "steps": steps,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    preview_token = save_preview_payload(preview_payload)

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
        },
    )
    db.commit()

    return shape_response(
        message="playbook_preview_ready",
        preview_token=preview_token,
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
        },
        severity="warning",
    )
    db.commit()

    return shape_response(
        message="playbook_apply_completed_in_non_destructive_mode",
        result={
            "confirmed": True,
            "non_destructive": True,
            "planned_actions": planned_actions,
        },
    )
