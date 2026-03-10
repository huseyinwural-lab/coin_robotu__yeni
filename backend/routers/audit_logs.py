from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import AuditLog, User
from schemas import AuditLogResponse

router = APIRouter(prefix="/audit-logs", tags=["audit_logs"])


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=10, le=300),
):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()