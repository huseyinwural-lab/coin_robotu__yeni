import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin
from models import AdminControl, SystemAlert, User, UserExecutionIntent, UserRole
from services.audit_service import create_audit_log

router = APIRouter(prefix="/admin/action-center", tags=["admin_action_center"])


def _kill_switch_payload() -> dict:
    raw = redis_client.get("pipeline:kill_switch")
    if not raw:
        return {"active": False, "reasons": []}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        payload = json.loads(raw) if isinstance(raw, str) else {}
        return payload if isinstance(payload, dict) else {"active": False, "reasons": []}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"active": False, "reasons": []}


@router.get("/summary")
def action_center_summary(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=30)

    pending_approvals = db.query(User).filter(User.role == UserRole.USER, User.approval_status == "pending").count()
    stale_pending_approvals = (
        db.query(User)
        .filter(User.role == UserRole.USER, User.approval_status == "pending", User.approval_requested_at <= stale_cutoff)
        .count()
    )
    open_alerts = db.query(SystemAlert).filter(SystemAlert.status == "open").count()
    queued_intents = db.query(UserExecutionIntent).filter(UserExecutionIntent.status == "QUEUED").count()
    rejected_intents = db.query(UserExecutionIntent).filter(UserExecutionIntent.status == "REJECTED").count()
    rejected_rows = db.query(UserExecutionIntent).filter(UserExecutionIntent.status == "REJECTED").all()
    timeout_rejected_intents = sum(
        1 for row in rejected_rows if "pending_timeout" in [str(item) for item in (row.reject_reason_codes or [])]
    )

    kill_switch = _kill_switch_payload()
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()

    return {
        "pending_approvals": pending_approvals,
        "stale_pending_approvals": stale_pending_approvals,
        "open_alerts": open_alerts,
        "queued_intents": queued_intents,
        "rejected_intents": rejected_intents,
        "timeout_rejected_intents": timeout_rejected_intents,
        "kill_switch_active": bool(kill_switch.get("active")),
        "kill_switch_reasons": kill_switch.get("reasons") or [],
        "emergency_mode": bool(control.emergency_mode) if control else False,
        "disable_futures": bool(control.disable_futures) if control else False,
        "generated_at": now.isoformat(),
    }


@router.post("/close-next-actions")
def close_next_actions(payload: dict | None = None, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = payload or {}
    ack_open_alerts = bool(payload.get("ack_open_alerts", True))
    reject_stale_approvals = bool(payload.get("reject_stale_approvals", True))
    stale_days = int(payload.get("stale_days") or 30)
    retry_timeout_rejections = bool(payload.get("retry_timeout_rejections", True))
    clear_kill_switch = bool(payload.get("clear_kill_switch", False))

    acked_alerts = 0
    rejected_approvals = 0
    retried_intents = 0

    if ack_open_alerts:
        alerts = db.query(SystemAlert).filter(SystemAlert.status == "open").all()
        now = datetime.now(timezone.utc)
        for alert in alerts:
            alert.status = "ack"
            alert.updated_at = now
        acked_alerts = len(alerts)

    if reject_stale_approvals:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(stale_days, 1))
        stale_users = (
            db.query(User)
            .filter(
                User.role == UserRole.USER,
                User.approval_status == "pending",
                User.approval_requested_at <= cutoff,
            )
            .all()
        )
        now = datetime.now(timezone.utc)
        for user in stale_users:
            user.approval_status = "rejected"
            user.is_active = False
            user.approved_at = None
            user.disabled_at = now
        rejected_approvals = len(stale_users)

    if retry_timeout_rejections:
        timeout_rows = [
            row
            for row in db.query(UserExecutionIntent).filter(UserExecutionIntent.status == "REJECTED").all()
            if "pending_timeout" in [str(item) for item in (row.reject_reason_codes or [])]
        ]
        now = datetime.now(timezone.utc)
        for row in timeout_rows:
            row.status = "QUEUED"
            row.submitted_at = now
            row.approved_at = None
            row.released_at = None
            row.cancelled_at = None
            row.admin_user_id = current_admin.id
            row.admin_note = "requeued_by_action_center"
            row.reject_reason_codes = []
        retried_intents = len(timeout_rows)

    if clear_kill_switch:
        redis_client.set(
            "pipeline:kill_switch",
            json.dumps(
                {
                    "triggered": False,
                    "active": False,
                    "reasons": ["cleared_by_action_center"],
                    "cleared_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
        )
        control = db.query(AdminControl).filter(AdminControl.id == "global").first()
        if control:
            control.emergency_mode = False

    db.commit()
    create_audit_log(
        db,
        action="ACTION_CENTER_CLOSE_NEXT_ACTIONS",
        entity_type="admin_action_center",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={
            "acked_alerts": acked_alerts,
            "rejected_approvals": rejected_approvals,
            "retried_intents": retried_intents,
            "clear_kill_switch": clear_kill_switch,
            "stale_days": stale_days,
        },
    )
    return {
        "status": "completed",
        "acked_alerts": acked_alerts,
        "rejected_approvals": rejected_approvals,
        "retried_intents": retried_intents,
        "clear_kill_switch": clear_kill_switch,
    }
