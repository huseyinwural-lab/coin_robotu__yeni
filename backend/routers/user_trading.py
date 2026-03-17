from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.audit.audit_events import AuditEvent
from db import get_db
from deps import require_user
from models import User
from schemas import (
    ExecutionIntentPreviewRequest,
    ExecutionIntentPreviewResponse,
    ExecutionIntentSubmitRequest,
    ExecutionIntentSubmitResponse,
    TradingPreviewRateLimitResponse,
    TradingPreviewResponse,
)
from services.audit_service import create_audit_log
from services.execution_intent_service import preview_execution_intent, submit_execution_intent
from services.rate_limiter_service import consume_exchange_rate_limit
from services.trading_preview_service import build_execution_preview_metrics

router = APIRouter(prefix="/v1/user/trading", tags=["v1_user_trading"])


def _build_preview_response(intent, validation: dict) -> ExecutionIntentPreviewResponse:
    return ExecutionIntentPreviewResponse(
        intent_id=intent.id,
        intent_token=intent.intent_token,
        preview_hash=intent.preview_hash,
        intent_type=intent.intent_type,
        position_id=intent.position_id,
        validation_status=validation.get("validation_status"),
        reject_reason_codes=validation.get("reject_reason_codes") or [],
        normalized_order_payload=validation.get("normalized_order_payload") or {},
        risk_flags=validation.get("risk_flags") or [],
        queue_mode=intent.queue_mode,
        approval_required=bool(intent.approval_required),
        intent_status=intent.status,
        meta_strategy_summary=validation.get("meta_strategy_summary") or {},
        portfolio_risk_impact=validation.get("portfolio_risk_impact") or {},
        gate_decision=str(validation.get("gate_decision") or intent.gate_decision or "ALLOW"),
        meta_engine_decision=str(validation.get("meta_engine_decision") or intent.meta_engine_decision or "ALLOW"),
        size=float(intent.size or 0),
        reduce_only=bool(intent.reduce_only),
        price=float(intent.price) if intent.price is not None else None,
        stop_price=float(intent.stop_price) if intent.stop_price is not None else None,
        take_profit_price=float(intent.take_profit_price) if intent.take_profit_price is not None else None,
        strategy_conflict_warning=validation.get("strategy_conflict_warning"),
        allocation_adjustment_notice=validation.get("allocation_adjustment_notice"),
        hedge_suggestion=validation.get("hedge_suggestion") or {},
        risk_reduction_score=validation.get("risk_reduction_score"),
        venue_context=validation.get("venue_context") or {},
        requested_leverage=validation.get("requested_leverage"),
        recommended_leverage=validation.get("recommended_leverage"),
        applied_leverage=validation.get("applied_leverage"),
        leverage_policy_mode=validation.get("leverage_policy_mode"),
        leverage_clamp_reasons=validation.get("leverage_clamp_reasons") or [],
    )


@router.post("/preview", response_model=TradingPreviewResponse)
def preview_trading(
    payload: ExecutionIntentPreviewRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    allowed, retry_after_seconds, remaining_tokens = consume_exchange_rate_limit("binance", tokens=1.0)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "exchange_rate_limit_reached",
                "retry_after_seconds": retry_after_seconds,
            },
        )

    payload_data = payload.model_dump()
    try:
        intent, validation = preview_execution_intent(db, current_user.id, payload_data)
    except ValueError as exc:
        error_code = str(exc)
        if error_code in {
            "scanner_execution_symbol_mismatch",
            "invalid_quote_asset",
            "unsupported_quote_asset",
            "symbol_required_for_execution_intent",
            "symbol_required_for_execution_order",
            "quote_asset_mismatch",
        }:
            create_audit_log(
                db,
                action=AuditEvent.SYMBOL_INTEGRITY_REJECT,
                entity_type="execution_intent_preview",
                entity_id=current_user.id,
                actor_user_id=current_user.id,
                actor_role=current_user.role.value,
                severity="warning",
                details={"error_code": error_code, "symbol": payload_data.get("symbol")},
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action=validation.get("preflight_event_code") or AuditEvent.ORDER_PREFLIGHT,
        entity_type="execution_intent",
        entity_id=intent.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning" if validation.get("validation_status") != "valid" else "info",
        details={
            "stage": "ORDER PREFLIGHT",
            "validation_status": validation.get("validation_status"),
            "symbol_integrity_ok": bool(validation.get("symbol_integrity_ok", False)),
            "reject_reason_codes": validation.get("reject_reason_codes") or [],
        },
    )

    create_audit_log(
        db,
        action=AuditEvent.RISK_RESULT,
        entity_type="execution_intent",
        entity_id=intent.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "stage": "RISK RESULT",
            "risk_flags": validation.get("risk_flags") or [],
            "gate_decision": validation.get("gate_decision"),
            "meta_engine_decision": validation.get("meta_engine_decision"),
            "portfolio_risk_impact": validation.get("portfolio_risk_impact") or {},
        },
    )
    create_audit_log(
        db,
        action=AuditEvent.EXECUTION_INTENT,
        entity_type="execution_intent",
        entity_id=intent.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "stage": "EXECUTION INTENT",
            "symbol": (validation.get("normalized_order_payload") or {}).get("symbol"),
            "side": (validation.get("normalized_order_payload") or {}).get("side"),
            "strategy": (validation.get("normalized_order_payload") or {}).get("strategy_binding"),
            "confidence": payload_data.get("confidence") or payload_data.get("signal_confidence"),
            "score": payload_data.get("score"),
            "timestamp": payload_data.get("timestamp"),
        },
    )
    preview_response = _build_preview_response(intent, validation)
    try:
        metrics = build_execution_preview_metrics(db, current_user.id, payload_data, validation)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="TRADING_PREVIEW_V1",
        entity_type="execution_intent",
        entity_id=intent.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "intent_status": intent.status,
            "validation_status": validation.get("validation_status"),
            "risk_reward_ratio": metrics.get("risk_reward_ratio"),
            "estimated_notional": metrics.get("estimated_notional"),
        },
    )

    return TradingPreviewResponse(
        preview=preview_response,
        metrics=metrics,
        rate_limit=TradingPreviewRateLimitResponse(
            allowed=allowed,
            retry_after_seconds=retry_after_seconds,
            remaining_tokens=remaining_tokens,
        ),
    )


@router.post("/execute", response_model=ExecutionIntentSubmitResponse)
def execute_trading(
    payload: ExecutionIntentSubmitRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    allowed, retry_after_seconds, _ = consume_exchange_rate_limit("binance", tokens=1.0)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "exchange_rate_limit_reached",
                "retry_after_seconds": retry_after_seconds,
            },
        )

    try:
        intent = submit_execution_intent(db, current_user.id, payload.intent_token, preview_hash=payload.preview_hash)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action=AuditEvent.EXCHANGE_ORDER,
        entity_type="execution_intent",
        entity_id=intent.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "stage": "EXCHANGE ORDER",
            "symbol": intent.symbol,
            "side": intent.side,
            "intent_type": intent.intent_type,
            "status": intent.status,
        },
    )
    create_audit_log(
        db,
        action="TRADING_EXECUTE_V1",
        entity_type="execution_intent",
        entity_id=intent.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"intent_token": intent.intent_token, "queue_mode": intent.queue_mode},
    )
    return ExecutionIntentSubmitResponse(
        intent_id=intent.id,
        intent_status="QUEUED_FOR_APPROVAL",
        reason_codes=[],
        queue_state=intent.status,
    )
