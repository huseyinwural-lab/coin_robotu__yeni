from enum import Enum

from sqlalchemy.orm import Session

from core.observability.request_context import get_request_context
from models import AuditLog


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
    request_context = get_request_context()
    merged_details = {
        **(details or {}),
        "request_id": request_context.get("request_id"),
        "session_id": request_context.get("session_id"),
        "route": request_context.get("route"),
        "method": request_context.get("method"),
    }
    audit_entry = AuditLog(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=resolved_action,
        entity_type=entity_type,
        entity_id=entity_id,
        severity=severity,
        details=merged_details,
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry


def create_domain_event(
    db: Session,
    *,
    event_name: str,
    entity_type: str,
    entity_id: str,
    actor_user_id: str | None = None,
    actor_role: str = "system",
    severity: str = "info",
    payload: dict | None = None,
) -> AuditLog:
    normalized = str(event_name or "unknown").strip().lower().replace(" ", "_")
    return create_audit_log(
        db,
        action=f"DOMAIN_{normalized}",
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity=severity,
        details={"event_name": normalized, "payload": payload or {}},
    )