from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_user
from models import AuditLog, User


router = APIRouter(prefix="/user/activity-log", tags=["user_activity_log"])


@router.get("")
def user_activity_log(
    limit: int = Query(default=100, ge=10, le=300),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.actor_user_id == current_user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "severity": row.severity,
            "details": row.details or {},
            "created_at": row.created_at,
        }
        for row in rows
    ]
