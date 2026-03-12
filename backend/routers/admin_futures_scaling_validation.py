from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_scaling_validation_service import get_futures_scaling_report, get_futures_scaling_validation
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures", tags=["admin_futures_scaling_validation"])


@router.get("/scaling-validation")
def futures_scaling_validation(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_scaling_validation(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_SCALING_VALIDATION_VIEWED",
        entity_type="futures_scaling_validation",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if payload.get("robustness_state") != "scalable" else "info",
        details={"robustness_score": payload.get("scaling_robustness_score", 0.0)},
    )
    return payload


@router.get("/scaling-report")
def futures_scaling_report(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_scaling_report(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_SCALING_REPORT_VIEWED",
        entity_type="futures_scaling_report",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={"rows": len(payload.get("scaling_performance_report") or [])},
    )
    return payload
