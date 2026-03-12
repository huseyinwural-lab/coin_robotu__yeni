from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_user
from models import ExecutionMetric, PaperPosition, PendingSignal, SignalEvent, User, UserExecutionIntent
from schemas import (
    DecisionTraceTimelineResponse,
    StrategyExplainResponse,
    TraceCoverageResponse,
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
        },
        context_payload={
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
