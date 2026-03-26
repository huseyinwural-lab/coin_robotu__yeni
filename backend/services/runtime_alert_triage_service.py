from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.alerts.suggested_actions import get_suggested_action
from models import AlertTriageAction, SystemAlert, User
from services.audit_service import create_audit_log


def _is_admin(user: User) -> bool:
    return user.role.value in {"super_admin", "admin", "ops"}


def list_runtime_alerts(
    db: Session,
    *,
    current_user: User,
    limit: int,
    severity: str | None = None,
    state: str | None = None,
    symbol: str | None = None,
    user_id: str | None = None,
    window_minutes: int | None = None,
) -> dict:
    query = db.query(SystemAlert).filter(SystemAlert.alert_type.like("runtime_%"))
    if window_minutes:
        since = datetime.now(timezone.utc) - timedelta(minutes=max(1, window_minutes))
        query = query.filter(SystemAlert.created_at >= since)
    if severity:
        query = query.filter(SystemAlert.severity == severity.upper())
    if state:
        query = query.filter(SystemAlert.status == state)

    rows = query.order_by(SystemAlert.created_at.desc()).limit(max(1, min(limit, 200))).all()
    is_admin = _is_admin(current_user)

    items = []
    for row in rows:
        details = row.details or {}
        alert_user_id = details.get("user_id")
        alert_symbol = details.get("symbol")

        if not is_admin and alert_user_id not in {None, current_user.id}:
            continue
        if symbol and str(alert_symbol or "").upper() != str(symbol).upper():
            continue
        if user_id and str(alert_user_id or "") != str(user_id):
            continue

        history_rows = (
            db.query(AlertTriageAction)
            .filter(AlertTriageAction.alert_id == row.id)
            .order_by(AlertTriageAction.created_at.desc())
            .limit(10)
            .all()
        )
        history = [
            {
                "action_type": h.action_type,
                "actor_user_id": h.actor_user_id,
                "note": h.note,
                "mute_until": h.mute_until.isoformat() if h.mute_until else None,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in history_rows
        ]

        items.append(
            {
                "id": row.id,
                "alert_type": row.alert_type,
                "severity": row.severity,
                "message": row.message,
                "status": row.status,
                "details": details,
                "acknowledged_by": row.acknowledged_by,
                "acknowledged_at": row.acknowledged_at.isoformat() if row.acknowledged_at else None,
                "resolved_by": row.resolved_by,
                "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                "mute_until": row.mute_until.isoformat() if row.mute_until else None,
                "operator_note": row.operator_note,
                "suggestion": get_suggested_action(row.alert_type),
                "history": history,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )

    return {"status": "ok", "items": items}


def apply_alert_action(
    db: Session,
    *,
    current_user: User,
    alert_id: str,
    action_type: str,
    note: str | None = None,
    mute_minutes: int | None = None,
) -> dict:
    alert = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
    if alert is None:
        raise ValueError("alert_not_found")

    now = datetime.now(timezone.utc)
    action = str(action_type).strip().lower()

    if action == "acknowledge":
        alert.status = "acknowledged"
        alert.acknowledged_by = current_user.id
        alert.acknowledged_at = now
    elif action == "mute_temporarily":
        minutes = int(mute_minutes or 15)
        alert.status = "muted"
        alert.mute_until = now + timedelta(minutes=minutes)
    elif action == "resolve":
        alert.status = "resolved"
        alert.resolved_by = current_user.id
        alert.resolved_at = now
    elif action == "escalate":
        alert.status = "escalated"
    elif action == "attach_note":
        alert.operator_note = (note or "").strip()
    else:
        raise ValueError("invalid_alert_action")

    if note:
        alert.operator_note = note.strip()

    triage = AlertTriageAction(
        alert_id=alert.id,
        action_type=action,
        actor_user_id=current_user.id,
        note=note,
        mute_until=alert.mute_until if action == "mute_temporarily" else None,
        details={"status": alert.status},
    )
    db.add(triage)

    create_audit_log(
        db,
        action="runtime_alert_action",
        entity_type="system_alert",
        entity_id=alert.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "action": action,
            "note": note,
            "mute_minutes": mute_minutes,
            "new_status": alert.status,
        },
    )

    db.commit()
    db.refresh(alert)
    return {
        "status": "ok",
        "alert_id": alert.id,
        "alert_status": alert.status,
        "mute_until": alert.mute_until.isoformat() if alert.mute_until else None,
        "operator_note": alert.operator_note,
    }
