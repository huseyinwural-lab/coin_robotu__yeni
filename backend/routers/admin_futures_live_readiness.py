from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_live_readiness_service import get_futures_live_readiness, get_futures_readiness_score
from services.pipeline.runtime import pipeline_runtime
from services.readiness_history_maintenance_service import get_readiness_retention_policy, run_readiness_history_maintenance
from services.readiness_maintenance_scheduler_service import read_readiness_maintenance_status
from services.readiness_history_service import build_readiness_audit_details, get_readiness_history
from services.readiness_policy_service import get_readiness_policy, update_readiness_policy

router = APIRouter(prefix="/admin/futures", tags=["admin_futures_live_readiness"])


@router.get("/live-readiness")
def futures_live_readiness(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_live_readiness(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_LIVE_READINESS_VIEWED",
        entity_type="futures_live_readiness",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if payload.get("readiness_state") != "READY" else "info",
        details=build_readiness_audit_details(payload),
    )
    return payload


@router.get("/live-readiness/history")
def futures_live_readiness_history(
    limit: int = Query(default=50, ge=1, le=200),
    days: int = Query(default=14, ge=1, le=90),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    exchange: str | None = Query(default=None),
    strategy: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_readiness_history(
        db,
        limit=limit,
        days=days,
        page=page,
        page_size=page_size,
        exchange=exchange,
        strategy=strategy,
        symbol=symbol,
    )


@router.get("/readiness/history")
def futures_readiness_history_alias(
    limit: int = Query(default=50, ge=1, le=200),
    days: int = Query(default=14, ge=1, le=90),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    exchange: str | None = Query(default=None),
    strategy: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_readiness_history(
        db,
        limit=limit,
        days=days,
        page=page,
        page_size=page_size,
        exchange=exchange,
        strategy=strategy,
        symbol=symbol,
    )


@router.get("/readiness/history/policy")
def futures_readiness_history_policy(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return get_readiness_retention_policy()


@router.post("/readiness/history/maintenance")
def futures_readiness_history_maintenance(
    dry_run: bool = Query(default=False),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = run_readiness_history_maintenance(db, dry_run=dry_run)
    create_audit_log(
        db,
        action="READINESS_HISTORY_MAINTENANCE_RUN",
        entity_type="readiness_history",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details=result,
    )
    return result


@router.get("/readiness/history/maintenance/status")
def futures_readiness_history_maintenance_status(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return read_readiness_maintenance_status()


@router.get("/readiness/policy")
def futures_readiness_policy(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return get_readiness_policy()


@router.put("/readiness/policy")
def futures_update_readiness_policy(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    updated = update_readiness_policy(payload)
    create_audit_log(
        db,
        action="READINESS_POLICY_UPDATED",
        entity_type="readiness_policy",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"policy": updated},
    )
    return updated


@router.get("/readiness-score")
def futures_readiness_score(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_readiness_score(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_READINESS_SCORE_VIEWED",
        entity_type="futures_readiness_score",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if payload.get("readiness_state") != "READY" else "info",
        details=build_readiness_audit_details(payload),
    )
    return payload
