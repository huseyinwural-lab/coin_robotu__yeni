from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.audit.audit_events import AuditEvent
from db import get_db
from deps import require_step_up_for, require_user
from models import User, UserExecutionIntent
from schemas import (
    ExecutionIntentPreviewRequest,
    ExecutionIntentPreviewResponse,
    ExecutionIntentSubmitRequest,
    ExecutionIntentSubmitResponse,
    TradingPreviewRateLimitResponse,
    TradingPreviewResponse,
)
from services.audit_service import create_audit_log, create_guard_audit_event
from services.explainability_rules_service import build_trade_explain
from services.execution_intent_service import preview_execution_intent, submit_execution_intent
from services.execution_pipeline_orchestrator import ExecutionPipelineViolation
from services.execution_readiness_service import enforce_execution_guard_or_raise, validate_order_precheck
from services.execution_safety_service import ExecutionSafetyViolation
from services.quote_asset_constraints import (
    INVALID_QUOTE_ASSET_ERROR_CODE,
    build_invalid_quote_asset_detail,
    is_invalid_quote_asset_code,
)
from services.rate_limiter_service import consume_exchange_rate_limit
from services.trading_preview_service import build_execution_preview_metrics

router = APIRouter(prefix="/v1/user/trading", tags=["v1_user_trading"])


def _quote_asset_http_exception(symbol: str | None):
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=build_invalid_quote_asset_detail(symbol),
    )


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
        policy_decision=validation.get("policy_decision") or {},
        policy_trace=validation.get("policy_trace") or {},
        pipeline_stage_results=validation.get("pipeline_stage_results") or [],
        decision_trace=validation.get("decision_trace") or {},
        standardized_reject=validation.get("standardized_reject"),
        rollout_mode=str(validation.get("rollout_mode") or "shadow"),
        execution_mode="live",
    )


@router.post("/preview", response_model=TradingPreviewResponse)
def preview_trading(
    payload: ExecutionIntentPreviewRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={"code": "PURE_LIVE_410", "message": "manuel_preview_kapatildi_signal_auto_execution_kullan"},
    )

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
        if is_invalid_quote_asset_code(error_code):
            create_guard_audit_event(
                db,
                event="EXECUTION_BLOCKED",
                reason=INVALID_QUOTE_ASSET_ERROR_CODE,
                symbol=payload_data.get("symbol"),
                user_id=current_user.id,
                actor_user_id=current_user.id,
                actor_role=current_user.role.value,
                severity="warning",
                metadata={"source": "user_trading_preview", "raw_error_code": error_code},
            )
            raise _quote_asset_http_exception(payload_data.get("symbol")) from exc
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


@router.post(
    "/execute",
    response_model=ExecutionIntentSubmitResponse,
    dependencies=[Depends(require_step_up_for("trade_execution"))],
)
def execute_trading(
    payload: ExecutionIntentSubmitRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={"code": "PURE_LIVE_410", "message": "manuel_execute_kapatildi_signal_auto_execution_kullan"},
    )

    readiness = enforce_execution_guard_or_raise(
        db,
        user_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        source="user_trading_execute",
        symbol="UNKNOWN",
    )

    allowed, retry_after_seconds, _ = consume_exchange_rate_limit("binance", tokens=1.0)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "exchange_rate_limit_reached",
                "retry_after_seconds": retry_after_seconds,
            },
        )

    preview_intent = db.query(UserExecutionIntent).filter(UserExecutionIntent.intent_token == payload.intent_token).first()
    if preview_intent is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="intent_not_found")

    precheck_price = float(preview_intent.price or 0)
    precheck_size = float(preview_intent.size or 0)
    precheck_notional = float(preview_intent.notional or 0)
    if precheck_price <= 0 and precheck_notional > 0 and precheck_size > 0:
        precheck_price = precheck_notional / precheck_size

    precheck = validate_order_precheck(
        db,
        user_id=current_user.id,
        symbol=str(preview_intent.symbol or "").upper(),
        market_type=str(preview_intent.market_type or "spot"),
        order_type=str((preview_intent.normalized_order_payload or {}).get("order_type") or "market"),
        side=str(preview_intent.side or "buy"),
        price=precheck_price,
        size=precheck_size,
        leverage=int((preview_intent.normalized_order_payload or {}).get("leverage") or 1),
        margin_mode=str((preview_intent.normalized_order_payload or {}).get("margin_mode") or "isolated"),
    )
    if not precheck.get("valid"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "order_validation_failed", "violations": precheck.get("violations") or []},
        )

    try:
        intent = submit_execution_intent(db, current_user.id, payload.intent_token, preview_hash=payload.preview_hash)
    except ExecutionPipelineViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={
                **(exc.standardized_reject or {}),
                "pipeline": exc.pipeline_result,
            },
        ) from exc
    except ExecutionSafetyViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"reason_code": exc.reason_code, "message": exc.message, **(exc.details or {})},
        ) from exc
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
    submit_pipeline = (intent.normalized_order_payload or {}).get("submit_execution_pipeline") or {}
    submit_soft_reject = submit_pipeline.get("standardized_reject") or {}
    response_intent_status = "RELEASED" if str(intent.status or "").upper() == "RELEASED" else "QUEUED_FOR_APPROVAL"
    response_execution_mode = str(readiness.get("mode") or "LIVE").lower()
    return ExecutionIntentSubmitResponse(
        intent_id=intent.id,
        intent_status=response_intent_status,
        reason_codes=[str(submit_soft_reject.get("reason_code"))] if submit_soft_reject.get("reason_code") else [],
        queue_state=intent.status,
        execution_mode=response_execution_mode,
        policy_decision=submit_pipeline,
        pipeline_trace=submit_pipeline.get("stage_results") or [],
        explain=build_trade_explain(
            validation=precheck,
            execution_mode=response_execution_mode,
            signal_score=None,
        ),
    )
