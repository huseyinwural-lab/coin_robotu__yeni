from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import AuditLog, DebugIncident
from services.trading_lifecycle_debugger_service import get_lifecycle_chain


OPEN_STATUSES = {"open", "in_progress"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_severity(value: str | None) -> str:
    normalized = str(value or "CRITICAL").upper()
    if normalized not in {"INFO", "WARNING", "ERROR", "CRITICAL"}:
        return "CRITICAL"
    return normalized


def _extract_correlation_id(details: dict, entity_id: str) -> str | None:
    candidates = [
        details.get("correlation_id"),
        details.get("request_id"),
        details.get("trace_id"),
        details.get("chain_id"),
        entity_id,
    ]
    for item in candidates:
        value = str(item or "").strip()
        if value:
            return value
    return None


def _build_fingerprint(
    *,
    action: str,
    entity_type: str,
    correlation_id: str,
    reason_code: str,
    source_event_id: str,
) -> str:
    parts = [
        str(action or "").lower(),
        str(entity_type or "").lower(),
        str(correlation_id or "").lower(),
        str(reason_code or "unknown").lower(),
    ]
    if str(source_event_id or "").strip():
        parts.append(str(source_event_id or "").lower())
    seed = "|".join(parts)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def serialize_incident(row: DebugIncident) -> dict:
    return {
        "incident_id": row.incident_id,
        "title": row.title,
        "severity": row.severity,
        "tags": row.tags or [],
        "linked_correlation_id": row.linked_correlation_id,
        "source_event_id": row.source_event_id,
        "status": row.status,
        "auto_created": bool(row.auto_created),
        "fingerprint": row.fingerprint,
        "cluster_id": row.cluster_id,
        "root_cause": row.root_cause,
        "dedupe_window_seconds": int(row.dedupe_window_seconds or 0),
        "occurrence_count": int(row.occurrence_count or 0),
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
        "created_by": row.created_by,
        "details": row.details or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
    }


def maybe_auto_create_incident_from_audit(
    db: Session,
    *,
    audit_entry: AuditLog,
    dedupe_window_seconds: int = 300,
) -> DebugIncident | None:
    severity = _normalize_severity(audit_entry.severity)
    if severity != "CRITICAL":
        return None

    details = dict(audit_entry.details or {})
    duplicate_suppression_enabled = bool(details.get("incident_duplicate_suppression", True))
    if not duplicate_suppression_enabled:
        return None

    correlation_id = _extract_correlation_id(details, audit_entry.entity_id)
    if not correlation_id:
        return None

    reason_code = str((details.get("reason_codes") or [details.get("reason_code") or "unknown"])[0] or "unknown")
    source_event_id = str(audit_entry.id)
    fingerprint = str(details.get("incident_fingerprint") or "").strip()
    if not fingerprint:
        fingerprint = _build_fingerprint(
            action=audit_entry.action,
            entity_type=audit_entry.entity_type,
            correlation_id=correlation_id,
            reason_code=reason_code,
            source_event_id="",
        )

    if not fingerprint:
        return None

    cooldown = max(int(details.get("incident_cooldown_seconds") or dedupe_window_seconds or 300), 30)
    now = _utcnow()
    cooldown_floor = now - timedelta(seconds=cooldown)

    existing = (
        db.query(DebugIncident)
        .filter(DebugIncident.fingerprint == fingerprint, DebugIncident.status.in_(OPEN_STATUSES))
        .order_by(DebugIncident.last_seen_at.desc())
        .first()
    )
    if existing and existing.last_seen_at and existing.last_seen_at >= cooldown_floor:
        existing.occurrence_count = int(existing.occurrence_count or 1) + 1
        existing.last_seen_at = now
        existing.severity = severity
        merged_details = dict(existing.details or {})
        merged_details.update(
            {
                "last_source_event_id": source_event_id,
                "last_reason_code": reason_code,
                "last_action": audit_entry.action,
            }
        )
        existing.details = merged_details
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    incident = DebugIncident(
        incident_id=str(uuid.uuid4()),
        title=f"CRITICAL {audit_entry.action}",
        severity=severity,
        tags=["auto", "critical", str(audit_entry.entity_type or "event")],
        linked_correlation_id=correlation_id,
        source_event_id=source_event_id,
        fingerprint=fingerprint,
        cluster_id=details.get("cluster_id"),
        root_cause=reason_code,
        status="open",
        auto_created=True,
        dedupe_window_seconds=cooldown,
        occurrence_count=1,
        last_seen_at=now,
        created_by=audit_entry.actor_user_id,
        details={
            "reason_code": reason_code,
            "action": audit_entry.action,
            "entity_type": audit_entry.entity_type,
            "entity_id": audit_entry.entity_id,
            "source": "auto_from_critical_audit",
        },
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def create_manual_incident(
    db: Session,
    *,
    title: str,
    severity: str,
    tags: list[str] | None,
    linked_correlation_id: str,
    source_event_id: str | None,
    root_cause: str | None,
    cluster_id: str | None,
    created_by: str | None,
    details: dict | None,
) -> DebugIncident:
    now = _utcnow()
    normalized_tags = [str(item).strip().lower() for item in (tags or []) if str(item).strip()]
    normalized_severity = _normalize_severity(severity)
    fingerprint = _build_fingerprint(
        action="manual_incident",
        entity_type="trading_lifecycle",
        correlation_id=linked_correlation_id,
        reason_code=str(root_cause or "unknown"),
        source_event_id=str(source_event_id or "manual"),
    )

    incident = DebugIncident(
        incident_id=str(uuid.uuid4()),
        title=str(title or "Manual Incident"),
        severity=normalized_severity,
        tags=normalized_tags,
        linked_correlation_id=str(linked_correlation_id),
        source_event_id=str(source_event_id) if source_event_id else None,
        fingerprint=fingerprint,
        cluster_id=str(cluster_id) if cluster_id else None,
        root_cause=str(root_cause) if root_cause else None,
        status="open",
        auto_created=False,
        dedupe_window_seconds=300,
        occurrence_count=1,
        last_seen_at=now,
        created_by=created_by,
        details=details or {},
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def list_incidents(
    db: Session,
    *,
    limit: int = 50,
    status: str | None = None,
    severity: str | None = None,
    linked_correlation_id: str | None = None,
) -> list[DebugIncident]:
    query = db.query(DebugIncident)
    if status:
        query = query.filter(DebugIncident.status == status)
    if severity:
        query = query.filter(DebugIncident.severity == _normalize_severity(severity))
    if linked_correlation_id:
        query = query.filter(DebugIncident.linked_correlation_id == linked_correlation_id)
    return query.order_by(DebugIncident.last_seen_at.desc()).limit(max(limit, 1)).all()


def get_incident(db: Session, incident_id: str) -> DebugIncident | None:
    return db.query(DebugIncident).filter(DebugIncident.incident_id == incident_id).first()


def close_incident(db: Session, *, incident: DebugIncident, closed_by: str | None = None) -> DebugIncident:
    now = _utcnow()
    incident.status = "closed"
    incident.closed_at = now
    incident.updated_at = now
    if closed_by:
        details = dict(incident.details or {})
        details["closed_by"] = closed_by
        incident.details = details
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def build_incident_debug_bundle(db: Session, *, incident: DebugIncident) -> dict:
    correlation_id = str(incident.linked_correlation_id or "").strip()
    lifecycle = get_lifecycle_chain(db, correlation_id, limit=1500) if correlation_id else {}
    return {
        "incident": serialize_incident(incident),
        "lifecycle": lifecycle,
        "exported_at": _utcnow().isoformat(),
    }
