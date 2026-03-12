from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_tail_risk_service import get_futures_global_risk, get_futures_tail_risk
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures", tags=["admin_futures_tail_risk"])


@router.get("/tail-risk")
def futures_tail_risk(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_tail_risk(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_TAIL_RISK_VIEWED",
        entity_type="futures_tail_risk",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if (payload.get("risk_state") or "NORMAL") != "NORMAL" else "info",
        details={"tail_risk_score": payload.get("tail_risk_score", 0.0)},
    )
    return payload


@router.get("/global-risk")
def futures_global_risk(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_global_risk(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_GLOBAL_RISK_VIEWED",
        entity_type="futures_global_risk",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="critical" if (payload.get("risk_state") or "NORMAL") == "PAUSE" else "warning",
        details={"global_risk_score": payload.get("global_risk_score", 0.0), "risk_state": payload.get("risk_state")},
    )
    return payload
