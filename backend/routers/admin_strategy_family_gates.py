from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User, UserDecisionTrace
from schemas import (
    BlockedReasonTimelineEnvelopeResponse,
    StrategyFamilyGateBulkUpdateRequest,
    StrategyFamilyGateResponse,
)
from services.audit_service import create_audit_log
from services.strategy_family_gate_service import list_strategy_family_gates, strategy_family_gate_payload, update_strategy_family_gates


router = APIRouter(prefix="/admin", tags=["admin_strategy_family_gates"])


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


@router.get("/blocked-reason-timeline/{symbol}", response_model=BlockedReasonTimelineEnvelopeResponse)
def get_admin_blocked_reason_timeline(
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
        if str(ctx.get("symbol") or "").upper() != normalized_symbol:
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
