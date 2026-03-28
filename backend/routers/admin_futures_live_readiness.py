from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_live_readiness_service import get_futures_live_readiness, get_futures_readiness_score
from services.pipeline.runtime import pipeline_runtime
from services.readiness_history_service import build_readiness_audit_details, get_readiness_history

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
        details=build_readiness_audit_details(payload),
    )
    return payload


@router.get("/live-readiness/history")
def futures_live_readiness_history(
    limit: int = Query(default=50, ge=1, le=200),
    days: int = Query(default=14, ge=1, le=90),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_readiness_history(db, limit=limit, days=days)


@router.get("/readiness/history")
def futures_readiness_history_alias(
    limit: int = Query(default=50, ge=1, le=200),
    days: int = Query(default=14, ge=1, le=90),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_readiness_history(db, limit=limit, days=days)


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
        details=build_readiness_audit_details(payload),
    )
    return payload
