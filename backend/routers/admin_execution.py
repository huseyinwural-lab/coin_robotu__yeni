from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import AuditLog, User
from schemas import (
    AdminExecutionQueueDecisionRequest,
    AdminExecutionQueueDecisionResponse,
    ExecutionIntentQueueItemResponse,
)
from services.audit_service import create_audit_log
from services.execution_intent_service import approve_execution_intent, list_execution_queue, reject_execution_intent
from services.execution_precheck_service import load_execution_policy_registry

router = APIRouter(prefix="/admin", tags=["admin_execution"])


@router.get("/execution-queue", response_model=list[ExecutionIntentQueueItemResponse])
def execution_queue(
    status_filter: str = Query(default="QUEUED"),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    rows = list_execution_queue(db, status_filter=status_filter, limit=limit)
    user_map = {row.id: row.email for row in db.query(User).filter(User.id.in_([item.user_id for item in rows])).all()} if rows else {}
    return [
        ExecutionIntentQueueItemResponse(
            id=row.id,
            intent_token=row.intent_token,
            user_id=row.user_id,
            user_email=user_map.get(row.user_id),
            symbol=row.symbol,
            market_type=row.market_type,
            side=row.side,
            notional=float(row.notional or 0),
            status=row.status,
            risk_flags=row.risk_flags or [],
            reject_reason_codes=row.reject_reason_codes or [],
            normalized_order_payload=row.normalized_order_payload or {},
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/execution-queue/{intent_id}/approve", response_model=AdminExecutionQueueDecisionResponse)
def approve_intent(
    intent_id: str,
    payload: AdminExecutionQueueDecisionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = approve_execution_intent(db, intent_id, current_user.id, admin_note=payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="EXECUTION_INTENT_APPROVED",
        entity_type="execution_intent",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"note": payload.note},
    )
    create_audit_log(
        db,
        action="EXECUTION_ORDER_RELEASED",
        entity_type="execution_intent",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"released_at": row.released_at.isoformat() if row.released_at else None},
    )
    return AdminExecutionQueueDecisionResponse(intent_id=row.id, status=row.status, admin_note=row.admin_note)


@router.post("/execution-queue/{intent_id}/reject", response_model=AdminExecutionQueueDecisionResponse)
def reject_intent(
    intent_id: str,
    payload: AdminExecutionQueueDecisionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = reject_execution_intent(db, intent_id, current_user.id, admin_note=payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="EXECUTION_INTENT_REJECTED",
        entity_type="execution_intent",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"note": payload.note, "reason_codes": row.reject_reason_codes or []},
    )
    return AdminExecutionQueueDecisionResponse(intent_id=row.id, status=row.status, admin_note=row.admin_note)


@router.get("/execution-policies")
def execution_policies(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_user
    registry = load_execution_policy_registry()
    recent_violations = (
        db.query(AuditLog)
        .filter(AuditLog.action.in_(["EXECUTION_INTENT_REJECTED"]))
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "registry": registry,
        "recent_policy_violations": [
            {
                "entity_id": row.entity_id,
                "actor_user_id": row.actor_user_id,
                "details": row.details,
                "created_at": row.created_at,
            }
            for row in recent_violations
        ],
    }