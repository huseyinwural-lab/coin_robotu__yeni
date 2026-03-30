from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from deps import require_user
from models import SystemAlert, User
from services.audit_service import build_critical_action_details, create_audit_log


router = APIRouter(prefix="/user/alerts", tags=["user_alerts"])


class UserAlertActionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=280)


def _category_for_alert(row: SystemAlert) -> str:
    text = f"{row.alert_type} {row.root_cause_code} {row.entity_key}".lower()
    if any(token in text for token in ["risk", "liquidation", "exposure", "loss"]):
        return "risk"
    if any(token in text for token in ["execution", "trade", "slippage", "queue"]):
        return "execution"
    return "system"


def _serialize(row: SystemAlert) -> dict:
    details = dict(row.details or {})
    return {
        "id": row.id,
        "severity": str(row.severity or "INFO").lower(),
        "category": _category_for_alert(row),
        "timestamp": row.last_triggered_at or row.created_at,
        "status": row.status,
        "message": row.message,
        "history": list(details.get("history") or []),
        "drilldown": {
            "execution_ref": details.get("execution_ref") or details.get("execution_id") or details.get("intent_id"),
            "activity_log_ref": details.get("audit_log_id") or details.get("correlation_id"),
            "strategy_ref": details.get("strategy_id"),
            "symbol": details.get("symbol") or row.entity_key,
            "decision_trace_ref": details.get("decision_trace_id") or details.get("trace_id"),
        },
        "details": details,
    }


@router.get("")
def list_user_alerts(
    severity: str | None = Query(default=None),
    category: str | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=100, ge=10, le=300),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    rows = db.query(SystemAlert).order_by(SystemAlert.last_triggered_at.desc()).limit(limit).all()
    items = [_serialize(row) for row in rows]
    if severity:
        items = [item for item in items if item["severity"] == severity.lower()]
    if category:
        items = [item for item in items if item["category"] == category.lower()]
    if query:
        q = query.lower()
        items = [item for item in items if q in item["message"].lower() or q in item["category"] or q in str(item["details"]).lower()]
    return {"items": items}


@router.post("/{alert_id}/ack")
def ack_user_alert(alert_id: str, payload: UserAlertActionRequest, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    row = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="alert_not_found")
    row.status = "ack"
    row.acknowledged_by = current_user.id
    row.acknowledged_at = datetime.now(timezone.utc)
    details = dict(row.details or {})
    history = list(details.get("history") or [])
    history.append({"action": "acknowledge", "actor": current_user.id, "timestamp": datetime.now(timezone.utc).isoformat(), "note": payload.note})
    details["history"] = history
    row.details = details
    db.commit()
    create_audit_log(db, action="user_alert_acknowledged", entity_type="system_alert", entity_id=row.id, actor_user_id=current_user.id, actor_role=current_user.role.value, details=build_critical_action_details(actor=current_user.id, reason=payload.note or "ack", scope="alert:ack", before_state={}, after_state={"status": "ack"}, action_ref=f"user-alert-ack:{row.id}"))
    return _serialize(row)


@router.post("/{alert_id}/dismiss")
def dismiss_user_alert(alert_id: str, payload: UserAlertActionRequest, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    row = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="alert_not_found")
    row.status = "dismissed"
    row.resolved_by = current_user.id
    row.resolved_at = datetime.now(timezone.utc)
    details = dict(row.details or {})
    history = list(details.get("history") or [])
    history.append({"action": "dismiss", "actor": current_user.id, "timestamp": datetime.now(timezone.utc).isoformat(), "note": payload.note})
    details["history"] = history
    row.details = details
    db.commit()
    create_audit_log(db, action="user_alert_dismissed", entity_type="system_alert", entity_id=row.id, actor_user_id=current_user.id, actor_role=current_user.role.value, details=build_critical_action_details(actor=current_user.id, reason=payload.note or "dismiss", scope="alert:dismiss", before_state={}, after_state={"status": "dismissed"}, action_ref=f"user-alert-dismiss:{row.id}"))
    return _serialize(row)
