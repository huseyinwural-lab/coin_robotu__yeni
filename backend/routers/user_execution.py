from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_user
from models import User
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
from services.audit_service import create_audit_log
from services.execution_intent_service import (
    cancel_execution_intent,
    get_execution_presets,
    list_user_execution_intents,
    preview_execution_intent,
    submit_execution_intent,
)
from services.position_management_service import list_user_positions
from services.strategy_intelligence_service import evaluate_hedge_suggestion

router = APIRouter(prefix="/user/execution", tags=["user_execution"])


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
    intent, validation = preview_execution_intent(db, current_user.id, payload.model_dump())
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
    )


@router.post("/position-actions/preview", response_model=ExecutionIntentPreviewResponse)
def preview_position_action(
    payload: PositionActionPreviewRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
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
    intent, validation = preview_execution_intent(db, current_user.id, mapped_payload)
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
    )


@router.post("/position-actions/submit", response_model=ExecutionIntentSubmitResponse)
def submit_position_action(
    payload: ExecutionIntentSubmitRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        intent = submit_execution_intent(db, current_user.id, payload.intent_token, preview_hash=payload.preview_hash)
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc

    create_audit_log(
        db,
        action="POSITION_ACTION_SUBMITTED",
        entity_type="execution_intent",
        entity_id=intent.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"intent_type": intent.intent_type, "position_id": intent.position_id, "intent_token": intent.intent_token},
    )
    return ExecutionIntentSubmitResponse(
        intent_id=intent.id,
        intent_status="QUEUED_FOR_APPROVAL",
        reason_codes=[],
        queue_state=intent.status,
    )


@router.post("/intent/submit", response_model=ExecutionIntentSubmitResponse)
def submit_intent(
    payload: ExecutionIntentSubmitRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        intent = submit_execution_intent(db, current_user.id, payload.intent_token, preview_hash=payload.preview_hash)
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc

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
    return ExecutionIntentSubmitResponse(
        intent_id=intent.id,
        intent_status="QUEUED_FOR_APPROVAL",
        reason_codes=[],
        queue_state=intent.status,
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