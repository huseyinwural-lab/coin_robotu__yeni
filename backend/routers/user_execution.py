import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core.audit.audit_events import AuditEvent
from db import get_db
from deps import require_step_up_for, require_user
from models import User, UserExecutionIntent
from schemas import (
    ExecutionIntentCancelRequest,
    ExecutionIntentCancelResponse,
    ExecutionIntentPreviewRequest,
    ExecutionIntentPreviewResponse,
    ExecutionIntentQueueItemResponse,
    PositionActionPreviewRequest,
    PositionStateResponse,
    ExecutionIntentSubmitRequest,
    ExecutionIntentSubmitResponse,
    ExecutionPresetResponse,
)
from services.audit_service import create_audit_log, create_guard_audit_event
from services.execution_intent_service import (
    DUPLICATE_INTENT_REASON_CODE,
    DuplicateExecutionIntentError,
    cancel_execution_intent,
    get_execution_presets,
    list_user_execution_intents,
    preview_execution_intent,
    submit_execution_intent,
)
from services.execution_pipeline_orchestrator import ExecutionPipelineViolation
from services.commercial_controls_enforcement_service import CommercialControlViolation
from services.execution_readiness_service import enforce_execution_guard_or_raise
from services.execution_safety_service import ExecutionSafetyViolation
from services.explainability_rules_service import build_trade_explain
from services.quote_asset_constraints import (
    INVALID_QUOTE_ASSET_ERROR_CODE,
    build_invalid_quote_asset_detail,
    is_invalid_quote_asset_code,
)
from services.rate_limiter_service import consume_exchange_rate_limit
from services.position_management_service import list_user_positions
from services.strategy_intelligence_service import evaluate_hedge_suggestion

router = APIRouter(prefix="/user/execution", tags=["user_execution"])


def _quote_asset_http_exception(symbol: str | None):
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=build_invalid_quote_asset_detail(symbol),
    )


def _duplicate_intent_response(*, reason_code: str, message: str, intent_id: str, idempotency_key: str):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": "duplicate_intent",
            "reason_code": reason_code,
            "message": message,
            "intent_id": intent_id,
            "idempotency_key": idempotency_key,
        },
    )


def _guard_exchange_rate_limit():
    allowed, retry_after_seconds, _ = consume_exchange_rate_limit("binance", tokens=1.0)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "exchange_rate_limit_reached",
                "retry_after_seconds": retry_after_seconds,
            },
        )


def _execution_guard_enforced() -> bool:
    canary_mode = str(os.getenv("CANARY_MODE", "false") or "false").strip().lower() in {"1", "true", "yes"}
    default_flag = "0" if canary_mode else "1"
    return str(os.getenv("EXECUTION_GUARD_ENFORCEMENT_ENABLED", default_flag) or default_flag).strip().lower() in {
        "1",
        "true",
        "yes",
    }


@router.get("/presets", response_model=list[ExecutionPresetResponse])
def execution_presets(current_user: User = Depends(require_user)):
    _ = current_user
    return [ExecutionPresetResponse(**row) for row in get_execution_presets()]


@router.post("/intent/preview", response_model=ExecutionIntentPreviewResponse)
def preview_intent(
    payload: ExecutionIntentPreviewRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _guard_exchange_rate_limit()
    payload_data = payload.model_dump()
    try:
        intent, validation = preview_execution_intent(db, current_user.id, payload_data)
    except DuplicateExecutionIntentError as exc:
        create_audit_log(
            db,
            action="EXECUTION_INTENT_DUPLICATE_REJECTED",
            entity_type="execution_intent",
            entity_id=exc.intent_id,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            severity="warning",
            details={
                "reason_code": DUPLICATE_INTENT_REASON_CODE,
                "idempotency_key": exc.idempotency_key,
                "intent_id": exc.intent_id,
            },
        )
        return _duplicate_intent_response(
            reason_code=DUPLICATE_INTENT_REASON_CODE,
            message="Duplicate execution intent rejected",
            intent_id=exc.intent_id,
            idempotency_key=exc.idempotency_key,
        )
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
                metadata={"source": "user_execution_intent_preview", "raw_error_code": error_code},
            )
            raise _quote_asset_http_exception(payload_data.get("symbol")) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CommercialControlViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"reason_code": exc.reason_code, "message": exc.message, **(exc.details or {})},
        ) from exc

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
            "confidence": payload_data.get("signal_confidence"),
            "score": payload_data.get("score"),
            "timestamp": payload_data.get("timestamp"),
        },
    )
    create_audit_log(
        db,
        action="EXECUTION_INTENT_PREVIEWED",
        entity_type="execution_intent",
        entity_id=intent.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "intent_status": intent.status,
            "validation_status": validation.get("validation_status"),
            "reason_codes": validation.get("reject_reason_codes") or [],
        },
    )
    return ExecutionIntentPreviewResponse(
        intent_id=intent.intent_id,
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
        policy_decision=validation.get("policy_decision") or {},
        policy_trace=validation.get("policy_trace") or {},
        pipeline_stage_results=validation.get("pipeline_stage_results") or [],
        decision_trace=validation.get("decision_trace") or {},
        standardized_reject=validation.get("standardized_reject"),
        rollout_mode=str(validation.get("rollout_mode") or "shadow"),
    )


@router.post("/position-actions/preview", response_model=ExecutionIntentPreviewResponse)
def preview_position_action(
    payload: PositionActionPreviewRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _guard_exchange_rate_limit()
    mapped_payload = {
        "source_type": "position_action",
        "source_ref_id": payload.position_id,
        "intent_type": payload.intent_type,
        "position_id": payload.position_id,
        "market_type": "spot",
        "symbol": payload.symbol,
        "side": "sell",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": payload.size,
        "execution_mode": "position_action",
        "size": payload.size,
        "reduce_only": payload.reduce_only,
        "price": payload.price,
        "stop_price": payload.stop_price,
        "take_profit_price": payload.take_profit_price,
    }
    try:
        intent, validation = preview_execution_intent(db, current_user.id, mapped_payload)
    except DuplicateExecutionIntentError as exc:
        create_audit_log(
            db,
            action="EXECUTION_INTENT_DUPLICATE_REJECTED",
            entity_type="execution_intent",
            entity_id=exc.intent_id,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            severity="warning",
            details={
                "reason_code": DUPLICATE_INTENT_REASON_CODE,
                "idempotency_key": exc.idempotency_key,
                "intent_id": exc.intent_id,
            },
        )
        return _duplicate_intent_response(
            reason_code=DUPLICATE_INTENT_REASON_CODE,
            message="Duplicate execution intent rejected",
            intent_id=exc.intent_id,
            idempotency_key=exc.idempotency_key,
        )
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
                details={"error_code": error_code, "symbol": mapped_payload.get("symbol")},
            )
        if is_invalid_quote_asset_code(error_code):
            create_guard_audit_event(
                db,
                event="EXECUTION_BLOCKED",
                reason=INVALID_QUOTE_ASSET_ERROR_CODE,
                symbol=mapped_payload.get("symbol"),
                user_id=current_user.id,
                actor_user_id=current_user.id,
                actor_role=current_user.role.value,
                severity="warning",
                metadata={"source": "user_execution_position_action_preview", "raw_error_code": error_code},
            )
            raise _quote_asset_http_exception(mapped_payload.get("symbol")) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CommercialControlViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"reason_code": exc.reason_code, "message": exc.message, **(exc.details or {})},
        ) from exc
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
        action="POSITION_ACTION_PREVIEWED",
        entity_type="execution_intent",
        entity_id=intent.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "intent_type": intent.intent_type,
            "position_id": intent.position_id,
            "validation_status": validation.get("validation_status"),
        },
    )
    return ExecutionIntentPreviewResponse(
        intent_id=intent.intent_id,
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
        policy_decision=validation.get("policy_decision") or {},
        policy_trace=validation.get("policy_trace") or {},
        pipeline_stage_results=validation.get("pipeline_stage_results") or [],
        decision_trace=validation.get("decision_trace") or {},
        standardized_reject=validation.get("standardized_reject"),
        rollout_mode=str(validation.get("rollout_mode") or "shadow"),
    )


@router.post(
    "/position-actions/submit",
    response_model=ExecutionIntentSubmitResponse,
    dependencies=[Depends(require_step_up_for("trade_execution"))],
)
def submit_position_action(
    payload: ExecutionIntentSubmitRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    preview_intent = db.query(UserExecutionIntent).filter(UserExecutionIntent.intent_token == payload.intent_token).first()
    readiness = {"mode": "LIVE"}
    if (
        preview_intent is not None
        and str(preview_intent.intent_type or "").upper() == "OPEN_POSITION"
        and _execution_guard_enforced()
    ):
        readiness = enforce_execution_guard_or_raise(
            db,
            user_id=current_user.id,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            source="user_execution_position_action_submit",
        )
    _guard_exchange_rate_limit()
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
        message = str(exc)
        if message.startswith("order_validation_failed:"):
            first_failure_code = message.split(":", 1)[1].strip() or "ORDER_PRECHECK_FAILED"
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "ORDER_PRECHECK_FAILED",
                    "first_precheck_failure_code": first_failure_code,
                    "message": "Order precheck başarısız, submit engellendi.",
                },
            ) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc
    except CommercialControlViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"reason_code": exc.reason_code, "message": exc.message, **(exc.details or {})},
        ) from exc

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
        action="POSITION_ACTION_SUBMITTED",
        entity_type="execution_intent",
        entity_id=intent.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"intent_type": intent.intent_type, "position_id": intent.position_id, "intent_token": intent.intent_token},
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
            validation={"valid": True, "violations": [], "checks": {}},
            execution_mode=response_execution_mode,
            signal_score=None,
        ),
    )


@router.post(
    "/intent/submit",
    response_model=ExecutionIntentSubmitResponse,
    dependencies=[Depends(require_step_up_for("trade_execution"))],
)
def submit_intent(
    payload: ExecutionIntentSubmitRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    preview_intent = db.query(UserExecutionIntent).filter(UserExecutionIntent.intent_token == payload.intent_token).first()
    readiness = {"mode": "LIVE"}
    if (
        preview_intent is not None
        and str(preview_intent.intent_type or "").upper() == "OPEN_POSITION"
        and _execution_guard_enforced()
    ):
        readiness = enforce_execution_guard_or_raise(
            db,
            user_id=current_user.id,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            source="user_execution_intent_submit",
        )
    _guard_exchange_rate_limit()
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
        message = str(exc)
        if message.startswith("order_validation_failed:"):
            first_failure_code = message.split(":", 1)[1].strip() or "ORDER_PRECHECK_FAILED"
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "ORDER_PRECHECK_FAILED",
                    "first_precheck_failure_code": first_failure_code,
                    "message": "Order precheck başarısız, submit engellendi.",
                },
            ) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc
    except CommercialControlViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"reason_code": exc.reason_code, "message": exc.message, **(exc.details or {})},
        ) from exc

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
        action="EXECUTION_INTENT_SUBMITTED",
        entity_type="execution_intent",
        entity_id=intent.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"intent_token": intent.intent_token},
    )
    create_audit_log(
        db,
        action="EXECUTION_INTENT_QUEUED",
        entity_type="execution_intent",
        entity_id=intent.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"queue_mode": intent.queue_mode},
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
            validation={"valid": True, "violations": [], "checks": {}},
            execution_mode=response_execution_mode,
            signal_score=None,
        ),
    )


@router.post("/intent/cancel", response_model=ExecutionIntentCancelResponse)
def cancel_intent(
    payload: ExecutionIntentCancelRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        intent = cancel_execution_intent(db, current_user.id, payload.intent_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="EXECUTION_INTENT_CANCELLED",
        entity_type="execution_intent",
        entity_id=intent.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"intent_token": intent.intent_token},
    )
    return ExecutionIntentCancelResponse(intent_id=intent.id, intent_status=intent.status, cancelled=True)


@router.get("/intents", response_model=list[ExecutionIntentQueueItemResponse])
def list_intents(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    rows = list_user_execution_intents(db, current_user.id, limit=limit)
    return [
        ExecutionIntentQueueItemResponse(
            id=row.id,
            intent_token=row.intent_token,
            user_id=row.user_id,
            intent_type=row.intent_type,
            position_id=row.position_id,
            symbol=row.symbol,
            market_type=row.market_type,
            side=row.side,
            notional=float(row.notional or 0),
            size=float(row.size or 0),
            reduce_only=bool(row.reduce_only),
            price=float(row.price) if row.price is not None else None,
            stop_price=float(row.stop_price) if row.stop_price is not None else None,
            take_profit_price=float(row.take_profit_price) if row.take_profit_price is not None else None,
            status=row.status,
            risk_flags=row.risk_flags or [],
            reject_reason_codes=row.reject_reason_codes or [],
            normalized_order_payload=row.normalized_order_payload or {},
            risk_score=float(row.risk_score or 0),
            gate_decision=row.gate_decision,
            meta_engine_decision=row.meta_engine_decision,
            cluster_id=row.cluster_id,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/positions", response_model=list[PositionStateResponse])
def user_positions(
    include_closed: bool = Query(default=False),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    rows = list_user_positions(db, current_user.id, include_closed=include_closed)
    hedge_suggestion = evaluate_hedge_suggestion(db, user_id=current_user.id, volatility=4.0)
    live_enabled = str(os.getenv("LIVE_TRADING_ENABLED", "false") or "false").strip().lower() in {"1", "true", "yes"}
    execution_mode = "live" if live_enabled else "mock"
    return [
        PositionStateResponse(
            position_id=row.position_id,
            symbol=row.symbol,
            size=float(row.size or 0),
            entry_price=float(row.entry_price or 0),
            current_price=float(row.current_price or 0),
            unrealized_pnl=float(row.unrealized_pnl or 0),
            leverage=int(row.leverage or 1),
            strategy_id=row.strategy_id,
            cluster_id=row.cluster_id,
            status=row.status,
            execution_mode=execution_mode,
            recommended_action=(
                "reduce_or_hedge"
                if (float(row.unrealized_pnl or 0) < 0 and int(row.leverage or 1) >= 3)
                else (hedge_suggestion.get("recommended_action") or "monitor")
            ),
            risk_reduction_score=float(hedge_suggestion.get("risk_reduction_score") or 0),
            hedge_suggestion=hedge_suggestion,
            updated_at=row.updated_at,
        )
        for row in rows
    ]