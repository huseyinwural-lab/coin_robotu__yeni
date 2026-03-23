from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import SystemAlert, User
from routers.admin_phase3_modules.common import (
    ensure_reason,
    ensure_super_admin,
    read_preview_payload,
    read_json_config,
    save_preview_payload,
    save_json_config,
    shape_response,
    write_audit_event,
)

router = APIRouter(tags=["admin_phase3_alerts"])

AUTO_ACK_POLICY_KEY = "admin_phase3:execution_alerts:auto_ack_policy:v1"


class InfoAutoAckPolicyUpdateRequest(BaseModel):
    enabled: bool = True
    threshold_hours: int = Field(default=24, ge=1, le=168)
    only_execution_alerts: bool = True
    reason: str = Field(..., min_length=3)


def _default_policy() -> dict:
    return {
        "enabled": True,
        "threshold_hours": 24,
        "only_execution_alerts": True,
        "updated_at": None,
    }


def _load_policy() -> dict:
    return read_json_config(AUTO_ACK_POLICY_KEY, _default_policy())


def _find_policy_matches(db: Session, *, policy: dict) -> list[SystemAlert]:
    threshold_hours = int(policy.get("threshold_hours") or 24)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=threshold_hours)
    query = db.query(SystemAlert).filter(
        SystemAlert.severity == "INFO",
        SystemAlert.status == "open",
        SystemAlert.created_at <= cutoff,
    )
    if policy.get("only_execution_alerts", True):
        query = query.filter(SystemAlert.alert_type.ilike("execution_%"))
    return query.order_by(SystemAlert.created_at.asc()).limit(500).all()


@router.get("/execution-alerts/auto-ack/policy")
def execution_alerts_auto_ack_policy_get(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = db
    return shape_response(policy=_load_policy())


@router.put("/execution-alerts/auto-ack/policy")
def execution_alerts_auto_ack_policy_update(
    payload: InfoAutoAckPolicyUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ensure_super_admin(current_admin)
    reason = ensure_reason(payload.reason, min_length=3)
    next_policy = {
        "enabled": bool(payload.enabled),
        "threshold_hours": int(payload.threshold_hours),
        "only_execution_alerts": bool(payload.only_execution_alerts),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_json_config(AUTO_ACK_POLICY_KEY, next_policy)

    write_audit_event(
        db,
        user=current_admin,
        action="execution_alert_auto_ack_policy_update",
        entity_type="system_alert_policy",
        entity_id="execution_info_auto_ack",
        details={
            "reason": reason,
            "policy": next_policy,
        },
        severity="warning",
    )
    db.commit()

    return shape_response(message="auto_ack_policy_updated", policy=next_policy)


@router.post("/execution-alerts/auto-ack/run")
def execution_alerts_auto_ack_run(
    preview_token: str = Query(...),
    reason: str = Query(default="scheduled_auto_ack"),
    dry_run: bool = Query(default=False),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    policy = _load_policy()
    if not policy.get("enabled"):
        return shape_response(message="auto_ack_policy_disabled", policy=policy, acked_count=0, ids=[])

    preview_payload = read_preview_payload(preview_token)
    if not preview_payload or preview_payload.get("type") != "auto_ack_preview":
        raise HTTPException(status_code=422, detail="preview_token_invalid_or_expired")

    reason_value = ensure_reason(reason, min_length=3)
    rows = _find_policy_matches(db, policy=policy)
    matched_ids = [row.id for row in rows]

    if not dry_run:
        now = datetime.now(timezone.utc)
        for row in rows:
            details = dict(row.details or {})
            details["auto_acked"] = True
            details["auto_acked_at"] = now.isoformat()
            details["auto_acked_by"] = "policy"
            row.details = details
            row.status = "ack"
            row.updated_at = now

    write_audit_event(
        db,
        user=current_admin,
        action="execution_alert_info_auto_ack_run",
        entity_type="system_alert",
        entity_id="bulk",
        details={
            "reason": reason_value,
            "policy": policy,
            "preview_token": preview_token,
            "dry_run": dry_run,
            "matched_count": len(matched_ids),
            "matched_ids": matched_ids,
        },
        severity="warning",
    )
    db.commit()

    return shape_response(
        message="auto_ack_dry_run_completed" if dry_run else "auto_ack_run_completed",
        policy=policy,
        preview_token=preview_token,
        dry_run=dry_run,
        acked_count=len(matched_ids),
        ids=matched_ids,
    )


@router.post("/execution-alerts/auto-ack/preview")
def execution_alerts_auto_ack_preview(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    policy = _load_policy()
    rows = _find_policy_matches(db, policy=policy)
    matched_ids = [row.id for row in rows]
    preview_payload = {
        "type": "auto_ack_preview",
        "policy": policy,
        "matched_ids": matched_ids,
        "created_by": current_admin.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    preview_token = save_preview_payload(preview_payload)

    write_audit_event(
        db,
        user=current_admin,
        action="execution_alert_info_auto_ack_preview",
        entity_type="system_alert",
        entity_id="bulk",
        details={
            "policy": policy,
            "preview_token": preview_token,
            "matched_count": len(matched_ids),
            "matched_ids": matched_ids,
        },
    )
    db.commit()

    return shape_response(
        message="auto_ack_preview_ready",
        policy=policy,
        preview_token=preview_token,
        matched_count=len(matched_ids),
        ids=matched_ids,
    )
