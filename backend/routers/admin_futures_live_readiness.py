from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import AuditLog, User
from services.audit_service import create_audit_log
from services.futures_live_readiness_service import get_futures_live_readiness, get_futures_readiness_score
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures", tags=["admin_futures_live_readiness"])


@router.get("/live-readiness")
def futures_live_readiness(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_live_readiness(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_LIVE_READINESS_VIEWED",
        entity_type="futures_live_readiness",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if payload.get("readiness_state") != "READY" else "info",
        details={"readiness_score": payload.get("readiness_score", 0.0), "readiness_state": payload.get("readiness_state")},
    )
    return payload


@router.get("/live-readiness/history")
def futures_live_readiness_history(
    limit: int = Query(default=50, ge=1, le=200),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action == "GO_LIVE_VALIDATOR_RUN")
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    items = [
        {
            "id": row.id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "actor_user_id": row.actor_user_id,
            "action": row.action,
            "severity": row.severity,
            "details": row.details,
        }
        for row in rows
    ]
    return {"count": len(items), "items": items}


@router.get("/readiness-score")
def futures_readiness_score(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_readiness_score(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_READINESS_SCORE_VIEWED",
        entity_type="futures_readiness_score",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if payload.get("readiness_state") != "READY" else "info",
        details={"readiness_score": payload.get("readiness_score", 0.0), "readiness_state": payload.get("readiness_state")},
    )
    return payload
