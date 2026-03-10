from sqlalchemy.orm import Session

from models import AuditLog


def create_audit_log(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    severity: str = "info",
    actor_user_id: str | None = None,
    actor_role: str = "system",
    details: dict | None = None,
) -> AuditLog:
    audit_entry = AuditLog(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        severity=severity,
        details=details or {},
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry