from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.system_alert_service import create_system_alert

router = APIRouter(prefix="/ops-alerts", tags=["ops_alerts"])


@router.post("/simulate")
def simulate_ops_alert(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    alert = create_system_alert(
        db,
        alert_type="ops_alert_simulation",
        severity="CRITICAL",
        message="Ops alert simulation",
        details={"triggered_by": current_admin.email},
        entity_key=current_admin.id,
        root_cause_code="ops_alert_simulation",
        state_key=f"simulated:{datetime.now(timezone.utc).isoformat()}",
        dedupe_window_seconds=0,
    )
    create_audit_log(
        db,
        action="ops_alert_simulated",
        entity_type="system_alert",
        entity_id=alert.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={"alert_id": alert.id},
    )

    delivery_status = alert.delivery_status or {}
    for channel in ["email", "slack"]:
        channel_payload = delivery_status.get(channel) or {}
        status_value = channel_payload.get("status")
        if status_value == "SENT":
            create_audit_log(
                db,
                action="ALERT_DELIVERY_SUCCESS",
                entity_type="system_alert",
                entity_id=alert.id,
                actor_user_id=current_admin.id,
                actor_role=current_admin.role.value,
                severity="info",
                details={"channel": channel, "provider_status": status_value},
            )
        elif status_value and status_value not in {"CHANNEL_DISABLED"}:
            create_audit_log(
                db,
                action="ALERT_DELIVERY_FAILED",
                entity_type="system_alert",
                entity_id=alert.id,
                actor_user_id=current_admin.id,
                actor_role=current_admin.role.value,
                severity="warning",
                details={
                    "channel": channel,
                    "provider_status": status_value,
                    "reason": channel_payload.get("reason"),
                },
            )
    return {"alert_id": alert.id, "delivery_status": alert.delivery_status}
