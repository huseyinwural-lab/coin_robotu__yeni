from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from schemas import (
    AdminAnomalyAlertPolicyResponse,
    AdminAnomalyAlertPolicyUpdateRequest,
    AdminAnomalyMutePatternRequest,
    AdminAnomalyMutePatternResponse,
)
from services.audit_service import create_audit_log
from services.scanner_anomaly_alert_service import (
    get_anomaly_alert_policy,
    list_active_pattern_mutes,
    mute_pattern,
    save_anomaly_alert_policy,
)


router = APIRouter(prefix="/admin/anomaly-alerts", tags=["admin_anomaly_alerts"])


@router.get("/policy", response_model=AdminAnomalyAlertPolicyResponse)
def get_alert_policy(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return AdminAnomalyAlertPolicyResponse(**get_anomaly_alert_policy())


@router.put("/policy", response_model=AdminAnomalyAlertPolicyResponse)
def update_alert_policy(
    payload: AdminAnomalyAlertPolicyUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    updated = save_anomaly_alert_policy(payload.model_dump())
    create_audit_log(
        db,
        action="ANOMALY_ALERT_POLICY_UPDATED",
        entity_type="anomaly_alert_policy",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=str(getattr(current_admin, "role", "admin") or "admin").lower(),
        severity="info",
        details=updated,
    )
    return AdminAnomalyAlertPolicyResponse(**updated)


@router.post("/mutes", response_model=AdminAnomalyMutePatternResponse)
def create_pattern_mute(
    payload: AdminAnomalyMutePatternRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    muted = mute_pattern(
        payload_hash=payload.payload_hash,
        duration_seconds=payload.duration_seconds,
        reason=payload.reason,
        actor_user_id=current_admin.id,
    )
    create_audit_log(
        db,
        action="ANOMALY_PATTERN_MUTED",
        entity_type="anomaly_pattern",
        entity_id=payload.payload_hash,
        actor_user_id=current_admin.id,
        actor_role=str(getattr(current_admin, "role", "admin") or "admin").lower(),
        severity="warning",
        details={
            "payload_hash": payload.payload_hash,
            "duration_seconds": payload.duration_seconds,
            "reason": payload.reason,
            "mute_until": muted["mute_until"].isoformat(),
        },
    )
    return AdminAnomalyMutePatternResponse(
        status="muted",
        payload_hash=payload.payload_hash,
        mute_until=muted["mute_until"],
        duration_seconds=payload.duration_seconds,
    )


@router.get("/mutes", response_model=list[AdminAnomalyMutePatternResponse])
def get_active_mutes(
    current_admin: User = Depends(require_admin),
    limit: int = Query(default=30, ge=1, le=200),
):
    _ = current_admin
    rows = list_active_pattern_mutes(limit=limit)
    return [
        AdminAnomalyMutePatternResponse(
            status="muted",
            payload_hash=row["payload_hash"],
            mute_until=row["mute_until"],
            duration_seconds=row["duration_seconds"],
        )
        for row in rows
    ]
