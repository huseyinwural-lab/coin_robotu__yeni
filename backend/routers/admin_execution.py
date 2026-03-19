from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from dependencies.execution_guard_dependency import execution_guard_admin_approve_trade_dependency
from db import get_db
from deps import require_admin
from models import AuditLog, User, UserExchangeConnection, UserExecutionIntent
from schemas import (
    AdminExecutionIntentOwnerRevalidateResponse,
    AdminExecutionQueueDecisionRequest,
    AdminExecutionQueueDecisionResponse,
    ExecutionIntentQueueItemResponse,
    ExecutionReadinessResponse,
    GuardTelemetryResponse,
    ReleaseGateStatusResponse,
    ReleaseGateOverrideRequest,
    ReleaseGateOverrideResponse,
)
from services.audit_service import create_audit_log
from services.execution_intent_service import approve_execution_intent, list_execution_queue, reject_execution_intent
from services.execution_intent_service import queue_status_summary, rejection_reason_summary, retry_execution_intent
from services.execution_precheck_service import load_execution_policy_registry
from services.execution_readiness_service import evaluate_execution_readiness
from services.guard_metrics_service import build_guard_telemetry_payload
from services.execution_safety_service import ExecutionSafetyViolation
from services.live_mode_service import (
    create_release_gate_override,
    enforce_release_gate,
    revoke_release_gate_override,
    validate_exchange_credentials_for_user,
)

router = APIRouter(prefix="/admin", tags=["admin_execution"])


def _resolve_execution_mode_from_intent(row) -> str:
    provider_payload = getattr(row, "execution_provider_payload", None)
    if isinstance(provider_payload, dict) and bool(provider_payload.get("mocked")):
        return "mocked"
    normalized_payload = row.normalized_order_payload if isinstance(row.normalized_order_payload, dict) else {}
    hinted = str(normalized_payload.get("execution_mode") or "").strip().lower()
    if hinted in {"mocked", "live"}:
        return hinted
    return "live"


class ApproveTradeRequest(BaseModel):
    intent_id: str
    note: str = ""


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


@router.get("/execution-queue/rejection-summary")
def execution_queue_rejection_summary(
    limit: int = Query(default=500, ge=1, le=2000),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return {
        "queue": queue_status_summary(db),
        "rejection_reason_distribution": rejection_reason_summary(db, limit=limit),
    }


@router.post("/execution-queue/{intent_id}/approve", response_model=AdminExecutionQueueDecisionResponse)
def approve_intent(
    intent_id: str,
    payload: AdminExecutionQueueDecisionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = approve_execution_intent(db, intent_id, current_user.id, admin_note=payload.note)
    except ExecutionSafetyViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"reason_code": exc.reason_code, "message": exc.message, **(exc.details or {})},
        ) from exc
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
    execution_mode = _resolve_execution_mode_from_intent(row)
    return AdminExecutionQueueDecisionResponse(intent_id=row.id, status=row.status, admin_note=row.admin_note, execution_mode=execution_mode)


@router.post(
    "/approve-trade",
    response_model=AdminExecutionQueueDecisionResponse,
    dependencies=[Depends(execution_guard_admin_approve_trade_dependency)],
)
def approve_trade_alias(
    payload: ApproveTradeRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return approve_intent(
        intent_id=payload.intent_id,
        payload=AdminExecutionQueueDecisionRequest(note=payload.note),
        current_user=current_user,
        db=db,
    )


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
    execution_mode = _resolve_execution_mode_from_intent(row)
    return AdminExecutionQueueDecisionResponse(intent_id=row.id, status=row.status, admin_note=row.admin_note, execution_mode=execution_mode)


@router.post("/execution-queue/{intent_id}/retry", response_model=AdminExecutionQueueDecisionResponse)
def retry_intent(
    intent_id: str,
    payload: AdminExecutionQueueDecisionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = retry_execution_intent(db, intent_id, current_user.id, admin_note=payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="EXECUTION_INTENT_RETRIED",
        entity_type="execution_intent",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"note": payload.note},
    )
    execution_mode = _resolve_execution_mode_from_intent(row)
    return AdminExecutionQueueDecisionResponse(intent_id=row.id, status=row.status, admin_note=row.admin_note, execution_mode=execution_mode)


@router.post("/execution-queue/{intent_id}/owner-revalidate", response_model=AdminExecutionIntentOwnerRevalidateResponse)
def revalidate_intent_owner_connection(
    intent_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(UserExecutionIntent).filter(UserExecutionIntent.id == intent_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution_intent_not_found")

    connection = (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.user_id == row.user_id)
        .order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc())
        .first()
    )
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="owner_exchange_connection_not_found")

    payload, response_code = validate_exchange_credentials_for_user(
        db,
        row.user_id,
        exchange=connection.exchange,
        market_type=connection.market_type,
        environment=connection.environment,
        connection_id=connection.id,
    )
    reason_codes = payload.get("reason_codes") or []
    connection_snapshot = ((payload.get("connection") or {}).get("readiness_snapshot") or {}) if isinstance(payload, dict) else {}

    create_audit_log(
        db,
        action="EXECUTION_INTENT_OWNER_REVALIDATED",
        entity_type="execution_intent",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "owner_user_id": row.user_id,
            "connection_id": connection.id,
            "response_code": response_code,
            "reason_codes": reason_codes,
        },
    )

    return AdminExecutionIntentOwnerRevalidateResponse(
        intent_id=row.id,
        owner_user_id=row.user_id,
        connection_id=connection.id,
        can_trade=bool(payload.get("can_trade")),
        reason_codes=reason_codes,
        connection_health=str(connection_snapshot.get("connection_health") or "unknown"),
        readiness_status=str(connection_snapshot.get("readiness_status") or "unknown"),
        response_code=int(response_code),
    )


@router.get("/execution-readiness", response_model=ExecutionReadinessResponse)
def execution_readiness(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_user
    return ExecutionReadinessResponse(**evaluate_execution_readiness(db))


@router.get("/guard-telemetry", response_model=GuardTelemetryResponse)
def guard_telemetry(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_user
    payload = build_guard_telemetry_payload(db)
    return GuardTelemetryResponse(**payload)


@router.get("/release-gate", response_model=ReleaseGateStatusResponse)
def admin_release_gate_alias(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_user
    try:
        payload = enforce_release_gate(db, environment="prod")
    except Exception:
        db.rollback()
        payload = {
            "status": "BLOCKED",
            "reasons": ["release_gate_runtime_error"],
            "fail_reasons": ["release_gate_runtime_error"],
            "warning_reasons": [],
            "reason_codes": ["release_gate_runtime_error"],
            "blocking_metrics": {"runtime_error": True},
            "reason_code": "release_gate_runtime_error",
            "deploy_enable_flag": False,
            "override_active": False,
            "override_expires_at": None,
            "override_id": None,
            "live_activation": "disabled",
            "environment": "prod",
        }
    if str(payload.get("status") or "") == "BLOCKED" and not (payload.get("reason_codes") or []):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="INVALID_RELEASE_GATE_CONTRACT")
    payload["blocking_metrics"] = payload.get("blocking_metrics") or payload.get("metrics") or {}
    return ReleaseGateStatusResponse(**payload)


@router.post("/execution-readiness/override", response_model=ReleaseGateOverrideResponse)
def create_execution_guard_override(
    payload: ReleaseGateOverrideRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    reason_code = payload.reason_code or "execution_guard_manual_override"
    try:
        row = create_release_gate_override(
            db,
            admin_user_id=current_user.id,
            reason_code=reason_code,
            reason_note=payload.reason_note,
            ttl_minutes=payload.ttl_minutes,
            deploy_context={"source": "execution_guard", **(payload.deploy_context or {})},
            environment="prod",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    create_audit_log(
        db,
        action="execution_guard_override_created",
        entity_type="execution_guard_override",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning",
        details={"reason_code": row.reason_code, "reason_note": row.reason_note, "expires_at": row.expires_at.isoformat()},
    )
    return ReleaseGateOverrideResponse(
        override_id=row.id,
        admin_user_id=row.admin_user_id,
        reason_code=row.reason_code,
        reason_note=row.reason_note,
        release_gate_snapshot=row.release_gate_snapshot or {},
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        deploy_context=row.deploy_context or {},
        used_deploy_count=int(row.used_deploy_count or 0),
    )


@router.post("/execution-override", response_model=ReleaseGateOverrideResponse)
def create_execution_guard_override_alias(
    payload: ReleaseGateOverrideRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return create_execution_guard_override(payload=payload, current_user=current_user, db=db)


@router.post("/execution-readiness/override/{override_id}/revoke", response_model=ReleaseGateOverrideResponse)
def revoke_execution_guard_override(
    override_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = revoke_release_gate_override(db, override_id=override_id, admin_user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    create_audit_log(
        db,
        action="execution_guard_override_revoked",
        entity_type="execution_guard_override",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning",
        details={"revoked_at": row.revoked_at.isoformat() if row.revoked_at else None},
    )
    return ReleaseGateOverrideResponse(
        override_id=row.id,
        admin_user_id=row.admin_user_id,
        reason_code=row.reason_code,
        reason_note=row.reason_note,
        release_gate_snapshot=row.release_gate_snapshot or {},
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        deploy_context=row.deploy_context or {},
        used_deploy_count=int(row.used_deploy_count or 0),
    )


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