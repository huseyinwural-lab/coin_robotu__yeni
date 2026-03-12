from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_capital_service import (
    get_futures_capital_budget,
    get_futures_capital_drift,
    get_futures_capital_usage,
)
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures", tags=["admin_futures_capital"])


@router.get("/capital-budget")
def futures_capital_budget(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_capital_budget(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_CAPITAL_BUDGET_VIEWED",
        entity_type="futures_capital_budget",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy_count": len(payload.get("strategy_capital_budget") or [])},
    )
    return payload


@router.get("/capital-usage")
def futures_capital_usage(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_capital_usage(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_CAPITAL_USAGE_VIEWED",
        entity_type="futures_capital_usage",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy_count": len(payload.get("strategy_capital_usage") or [])},
    )
    return payload


@router.get("/capital-drift")
def futures_capital_drift(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_capital_drift(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_CAPITAL_DRIFT_VIEWED",
        entity_type="futures_capital_drift",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if len(payload.get("capital_drift_events") or []) > 0 else "info",
        details={"drift_state": payload.get("drift_state", "NORMAL")},
    )
    return payload
