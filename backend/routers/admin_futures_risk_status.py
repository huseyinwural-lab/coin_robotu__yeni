from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.futures_risk_monitor_service import build_futures_risk_status
from services.audit_service import create_audit_log
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures/risk", tags=["admin_futures_risk"])


@router.get("/status")
def futures_risk_status(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    status = build_futures_risk_status(db, pipeline_runtime.cache, current_admin.id)
    action = "FUTURES_RISK_CHECK_PASSED" if status.get("risk_check_result") == "allow" else "FUTURES_RISK_CHECK_REJECTED"
    create_audit_log(
        db,
        action=action,
        entity_type="futures_risk_status",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info" if action.endswith("PASSED") else "warning",
        details={
            "portfolio_leverage": status.get("portfolio_leverage"),
            "margin_usage": status.get("margin_usage"),
            "risk_reason": status.get("risk_reason", []),
        },
    )
    return status
