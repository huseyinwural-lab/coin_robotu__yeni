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
            symbol=row.symbol,
            market_type=row.market_type,
            side=row.side,
            notional=float(row.notional or 0),
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