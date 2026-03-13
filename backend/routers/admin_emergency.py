import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin
from models import AdminControl, User, UserExecutionIntent
from schemas import AdminEmergencyStopRequest, AdminEmergencyStopResponse
from services.audit_service import create_audit_log
from services.pipeline.kill_switch_service import (
    liquidate_open_positions_for_kill_switch,
    pause_all_bots_for_kill_switch,
)

router = APIRouter(prefix="/v1/admin", tags=["v1_admin_emergency"])


@router.post("/emergency_stop", response_model=AdminEmergencyStopResponse)
def emergency_stop(
    payload: AdminEmergencyStopRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stopped_bots_count = pause_all_bots_for_kill_switch(db)
    closed_positions = liquidate_open_positions_for_kill_switch(db)

    emergency_intents = (
        db.query(UserExecutionIntent)
        .filter(UserExecutionIntent.status.in_(["PREVIEWED", "SUBMITTED", "QUEUED", "APPROVED"]))
        .all()
    )
    for intent in emergency_intents:
        intent.status = "REJECTED"
        intent.admin_user_id = current_admin.id
        intent.admin_note = f"emergency_stop:{payload.reason}"

    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    if control:
        control.emergency_mode = True
        control.disable_futures = True

    triggered_at = datetime.now(timezone.utc)
    db.commit()

    kill_switch_payload = {
        "triggered": True,
        "active": True,
        "reasons": ["admin_emergency_stop", payload.reason],
        "triggered_at": triggered_at.isoformat(),
        "stopped_bots_count": stopped_bots_count,
        "closed_positions_count": len(closed_positions),
        "rejected_intents_count": len(emergency_intents),
    }
    redis_client.set("pipeline:kill_switch", json.dumps(kill_switch_payload))

    create_audit_log(
        db,
        action="ADMIN_EMERGENCY_STOP_TRIGGERED",
        entity_type="kill_switch",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="critical",
        details={
            "reason": payload.reason,
            "stopped_bots_count": stopped_bots_count,
            "closed_positions_count": len(closed_positions),
            "rejected_intents_count": len(emergency_intents),
            "disable_futures": True,
        },
    )

    return AdminEmergencyStopResponse(
        status="triggered",
        reason=payload.reason,
        stop_all_bots_applied=True,
        closed_positions_count=len(closed_positions),
        rejected_intents_count=len(emergency_intents),
        disable_futures_applied=True,
        emergency_mode_active=True,
        kill_switch_reasons=kill_switch_payload["reasons"],
        triggered_at=triggered_at,
    )
