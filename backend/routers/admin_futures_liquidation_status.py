from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.futures_risk_monitor_service import build_futures_liquidation_status
from services.audit_service import create_audit_log
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures/liquidation-protection", tags=["admin_futures_liquidation"])


@router.get("/status")
def futures_liquidation_status(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    previous_policy = None
    if pipeline_runtime.cache:
        previous_policy = pipeline_runtime.cache.get("futures:risk:last_policy")
        if isinstance(previous_policy, bytes):
            previous_policy = previous_policy.decode()

    status = build_futures_liquidation_status(db, pipeline_runtime.cache, current_admin.id)
    if (status.get("gate_rejections") or []):
        create_audit_log(
            db,
            action="FUTURES_GATE_REJECTED",
            entity_type="futures_liquidation_status",
            entity_id=current_admin.id,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            severity="warning",
            details={"gate_rejections": status.get("gate_rejections", [])[:5]},
        )

    current_policy = status.get("policy_state")
    if previous_policy != current_policy:
        create_audit_log(
            db,
            action="FUTURES_POLICY_STATE_CHANGED",
            entity_type="futures_liquidation_status",
            entity_id=current_admin.id,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            severity="info",
            details={"from": previous_policy, "to": current_policy},
        )
        if pipeline_runtime.cache:
            pipeline_runtime.cache.set("futures:risk:last_policy", current_policy or "SAFE")

    return status
