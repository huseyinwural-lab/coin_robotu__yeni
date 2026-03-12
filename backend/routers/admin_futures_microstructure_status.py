from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_microstructure_service import build_microstructure_status
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures/microstructure", tags=["admin_futures_microstructure"])


@router.get("/status")
def futures_microstructure_status(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    status = build_microstructure_status(db, pipeline_runtime.cache, current_admin.id)
    create_audit_log(
        db,
        action="FUTURES_MICROSTRUCTURE_STATUS_CHECK",
        entity_type="futures_microstructure_status",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if status.get("portfolio_microstructure_state") in {"CRITICAL", "BLOCKED"} else "info",
        details={
            "portfolio_microstructure_state": status.get("portfolio_microstructure_state"),
            "portfolio_microstructure_risk_score": status.get("portfolio_microstructure_risk_score"),
            "gate_rejections": len(status.get("gate_rejections") or []),
        },
    )
    return status
