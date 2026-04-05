from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_user
from models import ExecutionMetric, PaperPosition, PendingSignal, SignalEvent, User, UserExecutionIntent
from schemas import (
    BlockedReasonTimelineEnvelopeResponse,
    DecisionCardEnvelopeResponse,
    DecisionCardResponse,
    DecisionTraceTimelineResponse,
    SymbolExplainabilityResponse,
    StrategyExplainResponse,
    TraceCoverageResponse,
)
from services.decision_card_service import (
    blocked_timeline_envelope,
    decision_card_envelope,
    get_user_decision_card,
    get_user_symbol_explainability,
    list_user_decision_cards,
)
from services.explainability_service import (
    TRACE_RETENTION_DAYS,
    build_reason_details,
    build_strategy_explanation,
    compute_trace_coverage,
    list_entity_trace_timeline,
)

router = APIRouter(prefix="/user", tags=["user_explainability"])


def _fallback_trace(
    *,
    trace_id: str,
    trace_scope: str,
    trace_type: str,
    entity_id: str,
    strategy_code: str | None,
    decision_status: str,
    reason_codes: list[str],
    feature_snapshot: dict,
    context_payload: dict,
    created_at,
) -> dict:
    created = created_at or datetime.now(timezone.utc)
    return {
        "trace_id": trace_id,
        "trace_scope": trace_scope,
        "trace_type": trace_type,
        "entity_id": entity_id,
        "strategy_code": strategy_code,
        "decision_status": decision_status,
        "position_action_reason": "none",
        "risk_adjustment_reason": "none",
        "strategy_override_reason": "none",
        "reason_codes": reason_codes,
        "reason_details": build_reason_details(reason_codes),
        "feature_snapshot": feature_snapshot,
        "context_payload": context_payload,
        "created_at": created,
        "expires_at": created + timedelta(days=TRACE_RETENTION_DAYS),
    }


@router.get("/signals/{signal_id}/decision-trace", response_model=DecisionTraceTimelineResponse)
def signal_decision_trace(
    signal_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    signal_row = (
        db.query(PendingSignal)
        .filter(PendingSignal.id == signal_id, PendingSignal.user_id == current_user.id)
        .first()
    )
    if signal_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal_not_found")

    timeline = list_entity_trace_timeline(
        db,
        user_id=current_user.id,
        trace_scope="signal",
        entity_id=signal_id,
        limit=25,
    )
    if timeline["trace_count"] > 0:
        return DecisionTraceTimelineResponse(**timeline)

    signal_event = (
        db.query(SignalEvent)
        .filter(SignalEvent.id == signal_row.signal_id, SignalEvent.user_id == current_user.id)
        .first()
    )
    reason_codes = (signal_event.reason_codes if signal_event else []) or ["signal_context_unavailable"]
    fallback = _fallback_trace(
        trace_id=f"fallback-{signal_row.id}",
        trace_scope="signal",
        trace_type="signal_snapshot",
        entity_id=signal_row.id,
        strategy_code=signal_row.strategy_code,
        decision_status=(signal_row.status or "pending").upper(),
        reason_codes=reason_codes,
        feature_snapshot={
            "confidence": float(signal_row.confidence or 0),
            "mode": signal_row.mode,
            "status": signal_row.status,
        },
        context_payload={
            "signal_id": signal_row.signal_id,
            "decision_note": signal_row.decision_note,
        },
        created_at=signal_row.created_at,
    )
    return DecisionTraceTimelineResponse(
        entity_scope="signal",
        entity_id=signal_row.id,
        trace_count=1,
        latest_trace=fallback,
        timeline=[fallback],
    )


@router.get("/trades/{trade_id}/decision-trace", response_model=DecisionTraceTimelineResponse)
def trade_decision_trace(
    trade_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    timeline = list_entity_trace_timeline(
        db,
        user_id=current_user.id,
        trace_scope="trade",
        entity_id=trade_id,
        limit=25,
    )
    if timeline["trace_count"] > 0:
        return DecisionTraceTimelineResponse(**timeline)

    position = (
        db.query(PaperPosition)
        .filter(PaperPosition.id == trade_id, PaperPosition.user_id == current_user.id)
        .first()
    )
    if position is not None:
        reason_codes = ["paper_trade_snapshot"]
        fallback = _fallback_trace(
            trace_id=f"fallback-{position.id}",
            trace_scope="trade",
            trace_type="paper_trade_snapshot",
            entity_id=position.id,
            strategy_code=None,
            decision_status=(position.status or "open").upper(),
            reason_codes=reason_codes,
            feature_snapshot={
                "quantity": float(position.quantity or 0),
                "entry_price": float(position.entry_price or 0),
                "realized_pnl": float(position.realized_pnl or 0),
                "unrealized_pnl": float(position.unrealized_pnl or 0),
            },
            context_payload={"symbol": position.symbol, "side": position.side},
            created_at=position.opened_at,
        )
        return DecisionTraceTimelineResponse(
            entity_scope="trade",
            entity_id=position.id,
            trace_count=1,
            latest_trace=fallback,
            timeline=[fallback],
        )

    execution_metric = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.order_id == trade_id, ExecutionMetric.user_id == current_user.id)
        .first()
    )
    if execution_metric is not None:
        reason_codes = ["execution_metric_snapshot"]
        fallback = _fallback_trace(
            trace_id=f"fallback-{execution_metric.id}",
            trace_scope="trade",
            trace_type="execution_metric_snapshot",
            entity_id=trade_id,
            strategy_code=execution_metric.strategy_type,
            decision_status=(execution_metric.final_status or "unknown").upper(),
            reason_codes=reason_codes,
            feature_snapshot={
                "executed_qty": float(execution_metric.executed_qty or 0),
                "mid_price": float(execution_metric.mid_price or 0),
                "price_avg": float(execution_metric.price_avg or 0),
                "execution_quality_score": float(execution_metric.execution_quality_score or 0),
            },
            context_payload={"symbol": execution_metric.symbol, "side": execution_metric.side},
            created_at=execution_metric.created_at,
        )
        return DecisionTraceTimelineResponse(
            entity_scope="trade",
            entity_id=trade_id,
            trace_count=1,
            latest_trace=fallback,
            timeline=[fallback],
        )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trade_not_found")


@router.get("/execution/intents/{intent_id}/decision-trace", response_model=DecisionTraceTimelineResponse)
def execution_intent_decision_trace(
    intent_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    intent = (
        db.query(UserExecutionIntent)
        .filter(UserExecutionIntent.id == intent_id, UserExecutionIntent.user_id == current_user.id)
        .first()
    )
    if intent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="intent_not_found")

    timeline = list_entity_trace_timeline(
        db,
        user_id=current_user.id,
        trace_scope="execution",
        entity_id=intent_id,
        limit=25,
    )
    if timeline["trace_count"] > 0:
        return DecisionTraceTimelineResponse(**timeline)

    reason_codes = intent.reject_reason_codes or ["execution_intent_snapshot"]
    fallback = _fallback_trace(
        trace_id=f"fallback-{intent.id}",
        trace_scope="execution",
        trace_type="execution_intent_snapshot",
        entity_id=intent.id,
        strategy_code=(intent.normalized_order_payload or {}).get("strategy_binding") or None,
        decision_status=(intent.status or "previewed").upper(),
        reason_codes=reason_codes,
        feature_snapshot={
            "symbol": intent.symbol,
            "market_type": intent.market_type,
            "side": intent.side,
            "notional": float(intent.notional or 0),
            "size": float(intent.size or 0),
            "intent_type": intent.intent_type,
        },
        context_payload={
            "position_id": intent.position_id,
            "queue_mode": intent.queue_mode,
            "risk_flags": intent.risk_flags or [],
            "normalized_order_payload": intent.normalized_order_payload or {},
        },
        created_at=intent.created_at,
    )
    return DecisionTraceTimelineResponse(
        entity_scope="execution",
        entity_id=intent.id,
        trace_count=1,
        latest_trace=fallback,
        timeline=[fallback],
    )


@router.get("/strategies/{strategy_code}/explain", response_model=StrategyExplainResponse)
def strategy_explain(
    strategy_code: str,
    lookback_days: int = Query(default=30, ge=1, le=90),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    payload = build_strategy_explanation(
        db,
        user_id=current_user.id,
        strategy_code=strategy_code,
        lookback_days=lookback_days,
    )
    return StrategyExplainResponse(**payload)


@router.get("/explainability/coverage", response_model=TraceCoverageResponse)
def explainability_coverage(
    days: int = Query(default=7, ge=1, le=30),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    payload = compute_trace_coverage(db, user_id=current_user.id, window_days=days)
    return TraceCoverageResponse(**payload)


@router.get("/decision-cards", response_model=DecisionCardEnvelopeResponse)
def user_decision_cards(
    limit: int = Query(default=40, ge=1, le=500),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    safe_limit = max(1, min(int(limit or 40), 200))
    items = list_user_decision_cards(db, current_user.id, limit=safe_limit)
    return DecisionCardEnvelopeResponse(**decision_card_envelope(items))


@router.get("/decision-cards/{symbol}", response_model=DecisionCardResponse)
def user_decision_card(
    symbol: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    item = get_user_decision_card(db, current_user.id, symbol)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="decision_card_not_found")
    return DecisionCardResponse(**item)


@router.get("/explainability/{symbol}", response_model=SymbolExplainabilityResponse)
def user_symbol_explainability(
    symbol: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    payload = get_user_symbol_explainability(db, current_user.id, symbol)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="symbol_explainability_not_found")
    return SymbolExplainabilityResponse(**payload)


@router.get("/blocked-reason-timeline/{symbol}", response_model=BlockedReasonTimelineEnvelopeResponse)
def user_blocked_reason_timeline(
    symbol: str,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    payload = get_user_symbol_explainability(db, current_user.id, symbol)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="symbol_not_found")
    timeline = (payload.get("blocked_reason_timeline") or [])[:limit]
    return BlockedReasonTimelineEnvelopeResponse(**blocked_timeline_envelope(symbol, timeline))


@router.get("/learning/safe-surface")
def user_learning_safe_surface(
    limit: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    cards = list_user_decision_cards(db, current_user.id, limit=limit)
    items = [
        {
            "symbol": item["symbol"],
            "decision": item["decision"],
            "confidence_adjustment": item.get("confidence_adjustment", 0),
            "learning_badges": item.get("learning_badges", []),
            "learning_quality_score": item.get("learning_quality_score"),
            "updated_at": item.get("updated_at"),
        }
        for item in cards
    ]
    return {
        "schema_version": "learning.v1",
        "engine_version": "learning-engine.v1",
        "generated_at": datetime.now(timezone.utc),
        "items": items,
    }
