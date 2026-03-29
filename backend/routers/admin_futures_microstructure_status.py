from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.execution_microstructure_service import (
    build_latest_execution_replay,
    build_microstructure_venue_summary,
    build_order_microstructure_assessment,
    get_microstructure_replay,
)
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


@router.get("/venues")
def futures_microstructure_venues(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = (current_admin, db)
    return build_microstructure_venue_summary(pipeline_runtime.cache if pipeline_runtime else None)


@router.get("/guard-preview")
def futures_microstructure_guard_preview(
    symbol: str = Query(..., min_length=3),
    side: str = Query("buy"),
    size: float = Query(..., gt=0),
    price: float = Query(..., gt=0),
    venue: str | None = Query(default=None),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return build_order_microstructure_assessment(
        db,
        pipeline_runtime.cache if pipeline_runtime else None,
        user_id=current_admin.id,
        symbol=symbol,
        side=side,
        price=price,
        size=size,
        order_type="market",
        preferred_venue=venue,
    )


@router.get("/budget-status")
def futures_microstructure_budget_status(
    symbol: str = Query(..., min_length=3),
    side: str = Query("buy"),
    size: float = Query(..., gt=0),
    price: float = Query(..., gt=0),
    strategy: str | None = Query(default=None),
    venue: str | None = Query(default=None),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = build_order_microstructure_assessment(
        db,
        pipeline_runtime.cache if pipeline_runtime else None,
        user_id=current_admin.id,
        symbol=symbol,
        side=side,
        price=price,
        size=size,
        order_type="market",
        strategy_binding=strategy,
        preferred_venue=venue,
    )
    return {
        "state": payload.get("state"),
        "execution_budget": payload.get("execution_budget") or {},
        "portfolio_capacity": payload.get("portfolio_capacity") or {},
        "impact_model": payload.get("impact_model") or {},
    }


@router.get("/slicing-preview")
def futures_microstructure_slicing_preview(
    symbol: str = Query(..., min_length=3),
    side: str = Query("buy"),
    size: float = Query(..., gt=0),
    price: float = Query(..., gt=0),
    strategy: str | None = Query(default=None),
    venue: str | None = Query(default=None),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = build_order_microstructure_assessment(
        db,
        pipeline_runtime.cache if pipeline_runtime else None,
        user_id=current_admin.id,
        symbol=symbol,
        side=side,
        price=price,
        size=size,
        order_type="market",
        strategy_binding=strategy,
        preferred_venue=venue,
    )
    return {
        "state": payload.get("state"),
        "execution_recommendation": payload.get("execution_recommendation") or {},
        "slicing_plan": payload.get("slicing_plan") or {},
        "impact_model": payload.get("impact_model") or {},
        "hidden_liquidity": payload.get("hidden_liquidity") or {},
        "depth_decay": payload.get("depth_decay") or {},
    }


@router.get("/replay")
def futures_microstructure_replay(
    symbol: str | None = Query(default=None),
    venue: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    return get_microstructure_replay(symbol=symbol, venue=venue, limit=limit)


@router.get("/execution-replay/latest")
def futures_microstructure_execution_replay_latest(
    symbol: str | None = Query(default=None),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return build_latest_execution_replay(db, symbol=symbol)
