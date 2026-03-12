from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_strategy_service import (
    get_futures_strategy_execution_quality,
    get_futures_strategy_governance,
    get_futures_strategy_health,
    get_futures_strategy_performance,
)
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures", tags=["admin_futures_strategy_analytics"])


@router.get("/strategy-performance")
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


@router.get("/strategy-execution-quality")
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


@router.get("/strategy-health")
def futures_strategy_health(
    refresh: bool = False,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = get_futures_strategy_health(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_STRATEGY_HEALTH_VIEWED",
        entity_type="futures_strategy_health",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "strategy_count": len(payload.get("strategy_health_score") or []),
        },
    )
    return payload


@router.get("/strategy-governance")
def futures_strategy_governance(
    refresh: bool = False,
    compare_a: str | None = None,
    compare_b: str | None = None,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = get_futures_strategy_governance(
        db,
        pipeline_runtime.cache,
        current_admin.id,
        refresh=refresh,
        compare_a=compare_a,
        compare_b=compare_b,
    )
    create_audit_log(
        db,
        action="FUTURES_STRATEGY_GOVERNANCE_VIEWED",
        entity_type="futures_strategy_governance",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity=(
            "warning"
            if any(item.get("disable_state") == "DISABLED" for item in (payload.get("disable_state") or []))
            else "info"
        ),
        details={
            "strategy_count": len(payload.get("strategy_health_score") or []),
            "decay_event_count": len(payload.get("decay_events") or []),
        },
    )
    return payload
