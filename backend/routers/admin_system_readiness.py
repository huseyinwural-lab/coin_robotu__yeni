from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_live_readiness_service import get_futures_live_readiness, get_futures_readiness_score
from services.pipeline.runtime import pipeline_runtime
from services.readiness_history_service import build_readiness_audit_details

router = APIRouter(prefix="/admin/system", tags=["admin_system_readiness"])


@router.get("/live-readiness")
def system_live_readiness(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_live_readiness(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="SYSTEM_LIVE_READINESS_VIEWED",
        entity_type="system_live_readiness",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if payload.get("readiness_state") != "READY" else "info",
        details=build_readiness_audit_details(payload),
    )
    return payload


@router.get("/readiness-score")
def system_readiness_score(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_readiness_score(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="SYSTEM_READINESS_SCORE_VIEWED",
        entity_type="system_readiness_score",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if payload.get("readiness_state") != "READY" else "info",
        details=build_readiness_audit_details(payload),
    )
    return payload


