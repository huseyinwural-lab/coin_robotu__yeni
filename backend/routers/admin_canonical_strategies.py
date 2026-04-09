from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import CanonicalStrategyRegistry, User, UserTradeProjection
from schemas import (
    AdminStrategyTakipRowResponse,
    BlockedReasonTimelineEnvelopeResponse,
    CanonicalStrategyRegistryResponse,
    CanonicalStrategyRegistryUpdateRequest,
    StrategyFamilyGateBulkUpdateRequest,
    StrategyFamilyGateResponse,
)
from services.audit_service import create_audit_log
from services.canonical_strategy_registry_service import (
    CANONICAL_STRATEGIES,
    list_registry,
    refresh_registry_metrics,
    update_registry_entry,
)
from services.strategy_family_gate_service import list_strategy_family_gates, strategy_family_gate_payload, update_strategy_family_gates
from models import UserDecisionTrace


router = APIRouter(prefix="/admin/canonical-strategies", tags=["admin_canonical_strategies"])
TRACKED_STRATEGY_IDS = list(CANONICAL_STRATEGIES.keys())


def _resolve_trade_strategy_id(row: UserTradeProjection, strategy_set: set[str]) -> str | None:
    meta = row.meta_json if isinstance(row.meta_json, dict) else {}
    candidates = [
        str(row.strategy_name or "").strip(),
        str(meta.get("strategy_id") or "").strip(),
        str(meta.get("canonical_strategy_id") or "").strip(),
        str(row.strategy_template_id or "").strip(),
    ]
    for item in candidates:
        if item and item in strategy_set:
            return item
    return None


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
        priority=None,
        cooldown_policy=None,
        weight=None,
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
            "priority_locked": True,
            "weight_locked": True,
            "cooldown_locked": True,
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


@router.get("/strategy-family-gates", response_model=list[StrategyFamilyGateResponse])
def get_strategy_family_gates(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    rows = list_strategy_family_gates(db)
    return [StrategyFamilyGateResponse(**strategy_family_gate_payload(row)) for row in rows]


@router.put("/strategy-family-gates", response_model=list[StrategyFamilyGateResponse])
def put_strategy_family_gates(
    payload: StrategyFamilyGateBulkUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = update_strategy_family_gates(db, [item.model_dump(exclude_none=True) for item in payload.items])
    create_audit_log(
        db,
        action="strategy_family_gates_updated",
        entity_type="strategy_family_gate",
        entity_id="bulk",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"updated_families": [item.family for item in payload.items]},
    )
    return [StrategyFamilyGateResponse(**strategy_family_gate_payload(row)) for row in rows]


@router.get("/strategy-takip", response_model=list[AdminStrategyTakipRowResponse])
def get_strategy_takip(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    strategy_ids = TRACKED_STRATEGY_IDS
    strategy_set = set(strategy_ids)

    family_by_strategy = {
        strategy_id: str((CANONICAL_STRATEGIES.get(strategy_id) or {}).get("strategy_family") or "unknown")
        for strategy_id in strategy_ids
    }
    registry_rows = db.query(CanonicalStrategyRegistry).filter(CanonicalStrategyRegistry.strategy_id.in_(strategy_ids)).all()
    for row in registry_rows:
        family_by_strategy[row.strategy_id] = str(row.strategy_family or family_by_strategy.get(row.strategy_id) or "unknown")

    now = datetime.now(timezone.utc)
    window_starts = {
        1: now - timedelta(days=1),
        7: now - timedelta(days=7),
        30: now - timedelta(days=30),
        90: now - timedelta(days=90),
    }
    stats = {
        strategy_id: {
            1: {"wins": 0, "total": 0},
            7: {"wins": 0, "total": 0},
            30: {"wins": 0, "total": 0},
            90: {"wins": 0, "total": 0},
        }
        for strategy_id in strategy_ids
    }

    trade_rows = (
        db.query(UserTradeProjection)
        .filter(UserTradeProjection.closed_at.is_not(None), UserTradeProjection.closed_at >= window_starts[90])
        .all()
    )
    for row in trade_rows:
        strategy_id = _resolve_trade_strategy_id(row, strategy_set)
        if not strategy_id:
            continue
        closed_at = row.closed_at
        if closed_at is None:
            continue
        if closed_at.tzinfo is None:
            closed_at = closed_at.replace(tzinfo=timezone.utc)
        pnl = float(row.realized_pnl or 0)
        for days, start in window_starts.items():
            if closed_at < start:
                continue
            stats[strategy_id][days]["total"] += 1
            if pnl > 0:
                stats[strategy_id][days]["wins"] += 1

    def _pct(sid: str, days: int) -> float:
        total = int(stats[sid][days]["total"])
        wins = int(stats[sid][days]["wins"])
        return round((wins / total) * 100, 2) if total > 0 else 0.0

    return [
        AdminStrategyTakipRowResponse(
            strategy_id=sid,
            family=family_by_strategy.get(sid, "unknown"),
            success_1d_pct=_pct(sid, 1),
            success_7d_pct=_pct(sid, 7),
            success_30d_pct=_pct(sid, 30),
            success_90d_pct=_pct(sid, 90),
        )
        for sid in strategy_ids
    ]


@router.get("/blocked-reason-timeline/{symbol}", response_model=BlockedReasonTimelineEnvelopeResponse)
def get_blocked_reason_timeline(
    symbol: str,
    limit: int = Query(default=20, ge=1, le=100),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    normalized_symbol = symbol.strip().upper()
    rows = (
        db.query(UserDecisionTrace)
        .filter(UserDecisionTrace.trace_scope == "signal")
        .order_by(UserDecisionTrace.created_at.desc())
        .limit(500)
        .all()
    )
    items: list[dict] = []
    for row in rows:
        ctx = row.context_payload or {}
        ctx_symbol = str(ctx.get("symbol") or "").upper()
        if ctx_symbol != normalized_symbol:
            continue
        reason_codes = row.reason_codes or []
        items.append(
            {
                "event_time": row.created_at,
                "layer": (row.feature_snapshot or {}).get("layer") or "signal",
                "reason_code": reason_codes[0] if reason_codes else "UNKNOWN",
                "reason_detail": (row.reason_details or [{}])[0].get("description") if row.reason_details else "-",
                "previous_state": (row.feature_snapshot or {}).get("previous_state") or "unknown",
                "new_state": (row.feature_snapshot or {}).get("new_state") or row.decision_status,
                "entity_id": row.entity_id,
                "user_id": row.user_id,
            }
        )
        if len(items) >= limit:
            break

    return BlockedReasonTimelineEnvelopeResponse(
        schema_version="sprint3.v1",
        engine_version="canonical-engine.v3",
        generated_at=datetime.now(timezone.utc),
        symbol=normalized_symbol,
        items=items,
    )
