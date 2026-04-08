from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_strategy_service import (
    get_futures_strategy_execution_quality,
    get_futures_strategy_performance,
    get_futures_strategy_status,
)
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures/strategy", tags=["admin_futures_strategy"])


@router.get("/status")
def futures_strategy_status(
    refresh: bool = False,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    status = get_futures_strategy_status(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_STRATEGY_STATUS_VIEWED",
        entity_type="futures_strategy_status",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "signals": (status.get("metrics") or {}).get("futures_strategy_signal_total", 0),
            "allowed": (status.get("metrics") or {}).get("futures_strategy_allowed_total", 0),
            "rejected": (status.get("metrics") or {}).get("futures_strategy_rejected_total", 0),
        },
    )
    return status


@router.post("/run-paper-cycle")
def run_futures_strategy_cycle(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "PURE_LIVE_410", "message": "paper cycle kaldırıldı"})


@router.get("/performance")
def futures_strategy_performance(
    refresh: bool = False,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = get_futures_strategy_performance(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_STRATEGY_PERFORMANCE_VIEWED",
        entity_type="futures_strategy_performance",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "strategy_count": len(payload.get("strategy_registry") or []),
            "drift_alert_count": len(payload.get("strategy_drift_alerts") or []),
        },
    )
    return payload


@router.get("/execution-quality")
def futures_strategy_execution_quality(
    refresh: bool = False,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = get_futures_strategy_execution_quality(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_STRATEGY_EXECUTION_QUALITY_VIEWED",
        entity_type="futures_strategy_execution_quality",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if len(payload.get("strategy_drift_alerts") or []) > 0 else "info",
        details={
            "latest_tuning_score": ((payload.get("rolling_7d_tuning_score") or {}).get("latest_score") or 0.0),
            "drift_alert_count": len(payload.get("strategy_drift_alerts") or []),
        },
    )
    return payload
