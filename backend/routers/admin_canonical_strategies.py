from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from schemas import (
    CanonicalStrategyRegistryResponse,
    CanonicalStrategyRegistryUpdateRequest,
)
from services.audit_service import create_audit_log
from services.canonical_strategy_registry_service import (
    list_registry,
    refresh_registry_metrics,
    update_registry_entry,
)


router = APIRouter(prefix="/admin/canonical-strategies", tags=["admin_canonical_strategies"])


@router.get("/registry", response_model=list[CanonicalStrategyRegistryResponse])
def get_canonical_registry(
    include_legacy: bool = Query(default=True),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = list_registry(db, include_legacy=include_legacy)
    return [CanonicalStrategyRegistryResponse.model_validate(row) for row in rows]


@router.put("/registry/{strategy_id}", response_model=CanonicalStrategyRegistryResponse)
def put_canonical_registry(
    strategy_id: str,
    payload: CanonicalStrategyRegistryUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = update_registry_entry(
        db,
        strategy_id,
        direction=payload.direction,
        market_regime=payload.market_regime,
        is_enabled=payload.is_enabled,
        priority=payload.priority,
        cooldown_policy=payload.cooldown_policy,
        weight=payload.weight,
        risk_profile=payload.risk_profile,
        forced_disable_reason=payload.forced_disable_reason,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_registry_item_not_found")

    create_audit_log(
        db,
        action="canonical_strategy_registry_updated",
        entity_type="canonical_strategy_registry",
        entity_id=row.strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "strategy_id": row.strategy_id,
            "is_enabled": row.is_enabled,
            "direction": row.direction,
            "market_regime": row.market_regime,
            "priority": row.priority,
            "weight": row.weight,
        },
    )
    return CanonicalStrategyRegistryResponse.model_validate(row)


@router.post("/registry/refresh-metrics", response_model=list[CanonicalStrategyRegistryResponse])
def post_refresh_registry_metrics(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = refresh_registry_metrics(db)
    create_audit_log(
        db,
        action="canonical_strategy_metrics_refreshed",
        entity_type="canonical_strategy_registry",
        entity_id="registry",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"refreshed_at": datetime.now(timezone.utc).isoformat(), "count": len(rows)},
    )
    return [CanonicalStrategyRegistryResponse.model_validate(row) for row in rows]
