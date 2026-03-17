from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin, require_super_admin
from models import AuditLog, User
from schemas import AuditLogResponse, AuditTimelineItemResponse, AuditTimelineResponse
from services.audit_service import create_audit_log

router = APIRouter(prefix="/audit-logs", tags=["audit_logs"])


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

    parsed_from = None
    parsed_to = None
    if date_from:
        try:
            parsed_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_date_from") from exc
        query = query.filter(AuditLog.created_at >= parsed_from)
    if date_to:
        try:
            parsed_to = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_date_to") from exc
        query = query.filter(AuditLog.created_at <= parsed_to)

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