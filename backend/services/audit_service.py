from enum import Enum

from sqlalchemy.orm import Session

from models import AuditLog
from services.ultra_log_service import classify_audit_category, safe_record_event


def create_audit_log(
    db: Session,
    *,
    action: str | Enum,
    entity_type: str,
    entity_id: str,
    severity: str = "info",
    actor_user_id: str | None = None,
    actor_role: str = "system",
    details: dict | None = None,
) -> AuditLog:
    resolved_action = action.value if isinstance(action, Enum) else str(action)
    audit_entry = AuditLog(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=resolved_action,
        entity_type=entity_type,
        entity_id=entity_id,
        severity=severity,
        details=details or {},
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)

    safe_record_event(
        category=classify_audit_category(resolved_action),
        event_name="audit_event",
        severity=str(severity or "info").lower(),
        payload={
            "audit_id": audit_entry.id,
            "action": resolved_action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "severity": severity,
            "actor_user_id": actor_user_id,
            "actor_role": actor_role,
            "details": details or {},
            "created_at": audit_entry.created_at.isoformat() if audit_entry.created_at else None,
        },
    )
    return audit_entry