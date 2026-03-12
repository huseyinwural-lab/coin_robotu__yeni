from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_risk_monitor_service import build_futures_adl_status
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures/adl", tags=["admin_futures_adl"])


@router.get("/status")
def futures_adl_status(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    status = build_futures_adl_status(db, pipeline_runtime.cache, current_admin.id)
    create_audit_log(
        db,
        action="FUTURES_ADL_STATUS_CHECK",
        entity_type="futures_adl_status",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "portfolio_adl_risk": status.get("portfolio_adl_risk", 0.0),
            "risk_level": status.get("risk_level", "LOW"),
            "dominant_side": status.get("dominant_side", "NONE"),
        },
    )
    return status
