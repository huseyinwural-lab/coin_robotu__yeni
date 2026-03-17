import io
import json
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin, require_super_admin
from models import AuditLog, User
from schemas import AuditLogResponse, AuditTimelineItemResponse, AuditTimelineResponse
from services.audit_service import create_audit_log

router = APIRouter(prefix="/audit-logs", tags=["audit_logs"])


def _parse_iso_datetime(value: str | None, *, detail_code: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail_code) from exc


def _build_timeline_query(
    db: Session,
    *,
    action: str | None,
    severity: str | None,
    entity_type: str | None,
    actor_user_id: str | None,
    request_id: str | None,
    session_id: str | None,
    q: str | None,
    date_from: str | None,
    date_to: str | None,
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action.strip()}%"))
    if severity:
        query = query.filter(AuditLog.severity == severity.strip())
    if entity_type:
        query = query.filter(AuditLog.entity_type.ilike(f"%{entity_type.strip()}%"))
    if actor_user_id:
        query = query.filter(AuditLog.actor_user_id == actor_user_id.strip())

    details_text = cast(AuditLog.details, String)
    if request_id:
        query = query.filter(details_text.ilike(f"%{request_id.strip()}%"))
    if session_id:
        query = query.filter(details_text.ilike(f"%{session_id.strip()}%"))
    if q:
        needle = f"%{q.strip()}%"
        query = query.filter(
            AuditLog.action.ilike(needle)
            | AuditLog.entity_type.ilike(needle)
            | AuditLog.entity_id.ilike(needle)
            | details_text.ilike(needle)
        )

    parsed_from = _parse_iso_datetime(date_from, detail_code="invalid_date_from")
    parsed_to = _parse_iso_datetime(date_to, detail_code="invalid_date_to")
    if parsed_from:
        query = query.filter(AuditLog.created_at >= parsed_from)
    if parsed_to:
        query = query.filter(AuditLog.created_at <= parsed_to)
    return query


def _serialize_timeline_item(row: AuditLog) -> dict:
    details = row.details or {}
    return {
        "id": row.id,
        "actor_user_id": row.actor_user_id,
        "actor_role": row.actor_role,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "severity": row.severity,
        "details": details,
        "request_id": details.get("request_id"),
        "session_id": details.get("session_id"),
        "route": details.get("route"),
        "method": details.get("method"),
        "created_at": row.created_at.isoformat(),
    }


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=10, le=300),
):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()


@router.get("/timeline", response_model=AuditTimelineResponse)
def audit_logs_timeline(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=20, le=500),
    action: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    actor_user_id: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    query = _build_timeline_query(
        db,
        action=action,
        severity=severity,
        entity_type=entity_type,
        actor_user_id=actor_user_id,
        request_id=request_id,
        session_id=session_id,
        q=q,
        date_from=date_from,
        date_to=date_to,
    )

    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    items = [
        AuditTimelineItemResponse(
            id=row.id,
            actor_user_id=row.actor_user_id,
            actor_role=row.actor_role,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            severity=row.severity,
            details=row.details or {},
            request_id=(row.details or {}).get("request_id"),
            session_id=(row.details or {}).get("session_id"),
            route=(row.details or {}).get("route"),
            method=(row.details or {}).get("method"),
            created_at=row.created_at,
        )
        for row in rows
    ]
    return AuditTimelineResponse(total=len(items), items=items)


@router.post("/admin/retention/prune")
def prune_old_audit_logs(
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
    days: int = Query(default=90, ge=30, le=365),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    to_delete_ids = [row.id for row in db.query(AuditLog.id).filter(AuditLog.created_at < cutoff).all()]
    deleted_count = 0
    if to_delete_ids:
        deleted_count = (
            db.query(AuditLog)
            .filter(AuditLog.id.in_(to_delete_ids))
            .delete(synchronize_session=False)
        )
        db.commit()

    create_audit_log(
        db,
        action="AUDIT_RETENTION_PRUNE",
        entity_type="audit_logs",
        entity_id="retention",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"days": days, "deleted_count": int(deleted_count)},
    )
    return {"days": days, "deleted_count": int(deleted_count)}


@router.get("/admin/incident-export")
def export_incident_package(
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=500, ge=50, le=1500),
    action: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    actor_user_id: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    query = _build_timeline_query(
        db,
        action=action,
        severity=severity,
        entity_type=entity_type,
        actor_user_id=actor_user_id,
        request_id=request_id,
        session_id=session_id,
        q=q,
        date_from=date_from,
        date_to=date_to,
    )
    timeline_rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    timeline_items = [_serialize_timeline_item(row) for row in timeline_rows]

    request_ids = {item.get("request_id") for item in timeline_items if item.get("request_id")}
    session_ids = {item.get("session_id") for item in timeline_items if item.get("session_id")}
    actor_ids = {item.get("actor_user_id") for item in timeline_items if item.get("actor_user_id")}

    domain_query = db.query(AuditLog).filter(AuditLog.action.ilike("DOMAIN_%"))
    if timeline_rows:
        from_ts = min(row.created_at for row in timeline_rows) - timedelta(minutes=30)
        to_ts = max(row.created_at for row in timeline_rows) + timedelta(minutes=30)
        domain_query = domain_query.filter(AuditLog.created_at >= from_ts, AuditLog.created_at <= to_ts)

    details_text = cast(AuditLog.details, String)
    if request_ids or session_ids:
        or_filters = []
        for rid in request_ids:
            or_filters.append(details_text.ilike(f"%{rid}%"))
        for sid in session_ids:
            or_filters.append(details_text.ilike(f"%{sid}%"))
        from sqlalchemy import or_  # local import to keep file lightweight

        domain_query = domain_query.filter(or_(*or_filters))
    elif actor_ids:
        domain_query = domain_query.filter(AuditLog.actor_user_id.in_(list(actor_ids)))

    domain_rows = domain_query.order_by(AuditLog.created_at.desc()).limit(600).all()
    domain_items = [_serialize_timeline_item(row) for row in domain_rows]

    severity_counter = Counter(item.get("severity") or "unknown" for item in timeline_items)
    action_counter = Counter(item.get("action") or "unknown" for item in timeline_items)

    incident_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "limit": limit,
            "action": action,
            "severity": severity,
            "entity_type": entity_type,
            "actor_user_id": actor_user_id,
            "request_id": request_id,
            "session_id": session_id,
            "q": q,
            "date_from": date_from,
            "date_to": date_to,
        },
        "timeline": timeline_items,
        "related_domain_events": domain_items,
    }
    summary_payload = {
        "generated_at": incident_payload["generated_at"],
        "metrics": {
            "timeline_event_count": len(timeline_items),
            "related_domain_event_count": len(domain_items),
            "unique_request_ids": len(request_ids),
            "unique_session_ids": len(session_ids),
            "severity_breakdown": dict(severity_counter),
            "top_actions": action_counter.most_common(10),
            "window_start": timeline_items[-1]["created_at"] if timeline_items else None,
            "window_end": timeline_items[0]["created_at"] if timeline_items else None,
        },
        "notes": [
            "Bu özet hızlı yönetici okuması için hazırlanır.",
            "Teknik detaylar incident.json içinde tutulur.",
        ],
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("incident.json", json.dumps(incident_payload, ensure_ascii=False, indent=2))
        archive.writestr("summary.json", json.dumps(summary_payload, ensure_ascii=False, indent=2))
    buffer.seek(0)

    create_audit_log(
        db,
        action="INCIDENT_PACKAGE_EXPORTED",
        entity_type="incident_export",
        entity_id="audit_logs",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "timeline_event_count": len(timeline_items),
            "related_domain_event_count": len(domain_items),
            "limit": limit,
            "severity": severity,
            "action": action,
        },
    )

    filename = f"incident_package_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([buffer.getvalue()]), media_type="application/zip", headers=headers)