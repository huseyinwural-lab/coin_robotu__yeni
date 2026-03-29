import hashlib
import json
import os
from enum import Enum
from datetime import datetime, timezone

from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from core.observability.request_context import get_request_context
from models import AuditLog
from services.debug_incident_service import maybe_auto_create_incident_from_audit


GUARD_EVENT_TYPES = {
    "EXECUTION_BLOCKED",
    "EXECUTION_ALLOWED",
    "EXECUTION_OVERRIDE_ENABLED",
}

ALLOWED_ENVIRONMENTS = {"prod", "staging", "test", "canary"}


def _extract_correlation_id(entity_id: str, details: dict) -> str:
    for candidate in [
        details.get("correlation_id"),
        details.get("trace_id"),
        details.get("request_id"),
        entity_id,
    ]:
        value = str(candidate or "").strip()
        if value:
            return value
    return str(entity_id or "unknown")


def _normalize_environment(details: dict) -> tuple[str, bool]:
    raw = str(details.get("environment") or os.environ.get("APP_ENVIRONMENT") or "prod").strip().lower()
    aliases = {
        "production": "prod",
        "live": "prod",
        "dev": "staging",
        "development": "staging",
        "qa": "test",
    }
    normalized = aliases.get(raw, raw)
    if normalized not in ALLOWED_ENVIRONMENTS:
        normalized = "test"
    is_test_event = bool(details.get("is_test_event", normalized in {"test", "canary"}))
    return normalized, is_test_event


def _compute_event_hash(previous_hash: str, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(f"{previous_hash}|{canonical}".encode("utf-8")).hexdigest()


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
    commit: bool = True,
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
    environment, is_test_event = _normalize_environment(merged_details)
    correlation_id = _extract_correlation_id(entity_id, merged_details)
    merged_details["environment"] = environment
    merged_details["correlation_id"] = correlation_id
    merged_details["is_test_event"] = bool(is_test_event)

    previous_entry = (
        db.query(AuditLog)
        .filter(
            or_(
                AuditLog.entity_id == correlation_id,
                cast(AuditLog.details, String).ilike(f"%{correlation_id}%"),
            )
        )
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    previous_hash = str(previous_entry.event_hash or "GENESIS") if previous_entry else "GENESIS"
    created_at = datetime.now(timezone.utc)
    signature_payload = {
        "action": resolved_action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "severity": str(severity).upper(),
        "environment": environment,
        "is_test_event": bool(is_test_event),
        "correlation_id": correlation_id,
        "details": merged_details,
        "created_at": created_at.isoformat(),
    }
    event_hash = _compute_event_hash(previous_hash, signature_payload)

    audit_entry = AuditLog(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=resolved_action,
        entity_type=entity_type,
        entity_id=entity_id,
        severity=severity,
        environment=environment,
        is_test_event=bool(is_test_event),
        previous_event_hash=previous_hash,
        event_hash=event_hash,
        signature_version="v1",
        details=merged_details,
        created_at=created_at,
    )
    db.add(audit_entry)
    if commit:
        db.commit()
        db.refresh(audit_entry)
        try:
            maybe_auto_create_incident_from_audit(db, audit_entry=audit_entry)
        except Exception:
            db.rollback()
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


def create_guard_audit_event(
    db: Session,
    *,
    event: str,
    reason: str,
    user_id: str,
    symbol: str | None = None,
    actor_user_id: str | None = None,
    actor_role: str = "system",
    severity: str = "info",
    metadata: dict | None = None,
) -> AuditLog:
    event_name = str(event or "").strip().upper()
    if event_name not in GUARD_EVENT_TYPES:
        raise ValueError("invalid_guard_event")

    normalized_reason = str(reason or "").strip().upper()
    if not normalized_reason:
        raise ValueError("guard_reason_required")

    payload = {
        "event": event_name,
        "reason": normalized_reason,
        "symbol": str(symbol or "UNKNOWN").upper(),
        "user_id": str(user_id or ""),
        "metadata": dict(metadata or {}),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return create_audit_log(
        db,
        action=event_name,
        entity_type="execution_guard",
        entity_id=str(user_id or "unknown"),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity=severity,
        details=payload,
    )


def build_critical_action_details(
    *,
    actor: str,
    reason: str,
    scope: str,
    before_state: dict | str | None = None,
    after_state: dict | str | None = None,
    rollback_ref: str | None = None,
    incident_ref: str | None = None,
    recommendation_ref: str | None = None,
    execution_ref: str | None = None,
    action_ref: str | None = None,
    extra: dict | None = None,
) -> dict:
    return {
        "actor": actor,
        "reason": str(reason or "").strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scope": str(scope or "global").strip(),
        "before_state": before_state or {},
        "after_state": after_state or {},
        "rollback_ref": rollback_ref,
        "incident_ref": incident_ref,
        "recommendation_ref": recommendation_ref,
        "execution_ref": execution_ref,
        "action_ref": action_ref,
        **(extra or {}),
    }