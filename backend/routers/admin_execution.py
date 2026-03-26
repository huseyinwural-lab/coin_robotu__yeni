import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from dependencies.execution_guard_dependency import execution_guard_admin_approve_trade_dependency
from db import get_db, redis_client
from deps import require_admin, require_super_admin
from models import AuditLog, BrandSetting, SystemAlert, User, UserExchangeConnection, UserExecutionIntent
from schemas import (
    AdminExecutionQueueBulkDecisionRequest,
    AdminExecutionQueueBulkDecisionResponse,
    AdminExecutionQueueControlRequest,
    AdminExecutionQueueControlResponse,
    AdminExecutionIntentOwnerRevalidateResponse,
    AdminExecutionQueueDecisionRequest,
    AdminExecutionQueueDecisionResponse,
    AdminExecutionQueueEditRequest,
    AdminExecutionQueueEditResponse,
    ExecutionDecisionGateConfigResponse,
    ExecutionDecisionGateConfigUpdateRequest,
    ExecutionIntentDetailResponse,
    ExecutionIntentHistoryItemResponse,
    ExecutionIntentQueueItemResponse,
    ExecutionReadinessResponse,
    GuardTelemetryResponse,
    ReleaseGateStatusResponse,
    ReleaseGateOverrideRequest,
    ReleaseGateOverrideResponse,
)
from services.audit_service import create_audit_log
from services.execution_intent_service import (
    approve_execution_intent,
    build_execution_intent_detail,
    build_intent_risk_payload,
    build_queue_observability_metrics,
    cancel_execution_intent_by_admin,
    edit_execution_intent_by_admin,
    execute_approved_intent,
    list_execution_queue,
    queue_status_summary,
    reject_execution_intent,
    rejection_reason_summary,
    rejection_reason_trend,
    resolve_intent_detail_version,
    resolve_intent_operational_status,
    retry_execution_intent,
)
from services.execution_precheck_service import load_execution_policy_registry
from services.execution_readiness_service import evaluate_execution_readiness
from services.guard_metrics_service import build_guard_telemetry_payload
from services.execution_safety_service import ExecutionSafetyViolation
from services.commercial_controls_enforcement_service import CommercialControlViolation
from services.system_alert_service import create_system_alert
from services.live_mode_service import (
    create_release_gate_override,
    enforce_release_gate,
    revoke_release_gate_override,
    validate_exchange_credentials_for_user,
)

router = APIRouter(prefix="/admin", tags=["admin_execution"])
QUEUE_CONTROL_STATE_KEY = "execution_queue:control_state:v1"
BULK_ACTION_LIMIT = 20
DECISION_GATE_CONFIG_KEY = "execution_decision_gate"
DEFAULT_DECISION_GATE_CONFIG = {
    "execution_decision_gate_enforced": True,
    "thresholds": {
        "queue_backlog": 100,
        "high_risk_spike": 5,
        "reject_spike": 10,
    },
}


def _queue_control_state() -> dict:
    raw = redis_client.get(QUEUE_CONTROL_STATE_KEY)
    if raw and isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        payload = json.loads(raw) if isinstance(raw, str) and raw else {}
    except Exception:
        payload = {}
    return {
        "paused": bool(payload.get("paused", False)),
        "paused_by": payload.get("paused_by"),
        "paused_reason": payload.get("paused_reason"),
        "paused_at": payload.get("paused_at"),
        "updated_at": payload.get("updated_at"),
    }


def _set_queue_control_state(*, paused: bool, actor_id: str, reason: str) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "paused": bool(paused),
        "paused_by": actor_id,
        "paused_reason": reason,
        "paused_at": now_iso if paused else None,
        "updated_at": now_iso,
    }
    redis_client.set(QUEUE_CONTROL_STATE_KEY, json.dumps(payload, ensure_ascii=False))
    return payload


def _resolve_decision_reason(payload: AdminExecutionQueueDecisionRequest) -> str:
    return str(payload.reason or payload.note or "").strip()


def _execution_alert_user_state(details: dict, user_id: str) -> dict:
    states = dict((details or {}).get("user_states") or {})
    return dict(states.get(user_id) or {})


def _set_execution_alert_user_state(details: dict, *, user_id: str, patch: dict) -> dict:
    details_payload = dict(details or {})
    states = dict(details_payload.get("user_states") or {})
    current = dict(states.get(user_id) or {})
    current.update(patch)
    states[user_id] = current
    details_payload["user_states"] = states
    return details_payload


def _log_decision_block(
    db: Session,
    *,
    action: str,
    intent_id: str | None,
    actor: User,
    reason_code: str,
) -> None:
    create_audit_log(
        db,
        action=f"EXECUTION_DECISION_BLOCKED_{action.upper()}",
        entity_type="execution_intent",
        entity_id=intent_id,
        actor_user_id=actor.id,
        actor_role=actor.role.value,
        severity="warning",
        details={"reason_code": reason_code},
    )


def _decision_gate_config(db: Session) -> dict:
    brand = db.query(BrandSetting).filter(BrandSetting.id == "default").first()
    if brand is None:
        brand = BrandSetting(id="default", metadata_json={})
        db.add(brand)
        db.commit()
        db.refresh(brand)

    metadata = dict(brand.metadata_json or {})
    config = dict(metadata.get(DECISION_GATE_CONFIG_KEY) or {})
    merged = {
        "execution_decision_gate_enforced": bool(
            config.get("execution_decision_gate_enforced", DEFAULT_DECISION_GATE_CONFIG["execution_decision_gate_enforced"])
        ),
        "thresholds": {
            **DEFAULT_DECISION_GATE_CONFIG["thresholds"],
            **dict(config.get("thresholds") or {}),
        },
    }
    return merged


def _update_decision_gate_config(db: Session, *, patch: dict, actor_user_id: str) -> dict:
    brand = db.query(BrandSetting).filter(BrandSetting.id == "default").first()
    if brand is None:
        brand = BrandSetting(id="default", metadata_json={})
        db.add(brand)
        db.commit()
        db.refresh(brand)

    metadata = dict(brand.metadata_json or {})
    current = _decision_gate_config(db)
    updated = {
        "execution_decision_gate_enforced": bool(
            patch.get("execution_decision_gate_enforced", current["execution_decision_gate_enforced"])
        ),
        "thresholds": {
            **current["thresholds"],
            **dict(patch.get("thresholds") or {}),
        },
    }
    metadata[DECISION_GATE_CONFIG_KEY] = updated
    brand.metadata_json = metadata
    brand.updated_by_user_id = actor_user_id
    db.commit()
    return updated


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
    search: str | None = Query(default=None),
    risk_filter: str = Query(default="all"),
    type_filter: str = Query(default="all"),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    thresholds = (_decision_gate_config(db).get("thresholds") or {})
    rows = list_execution_queue(
        db,
        status_filter=status_filter,
        limit=limit,
        search=search,
        risk_filter=risk_filter,
        intent_type=type_filter,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    user_map = {row.id: row.email for row in db.query(User).filter(User.id.in_([item.user_id for item in rows])).all()} if rows else {}
    snapshot_at = datetime.now(timezone.utc)

    high_risk_count = 0
    for item in rows:
        if build_intent_risk_payload(item).get("is_high_risk"):
            high_risk_count += 1
    if len(rows) >= int(thresholds.get("queue_backlog", 100)):
        create_system_alert(
            db,
            alert_type="execution_queue_backlog",
            severity="WARNING",
            message="Execution queue backlog yükseldi",
            details={"queued_count": len(rows), "status_filter": status_filter},
            entity_key="execution_queue",
            root_cause_code="execution_queue_backlog",
            state_key="execution_queue_backlog",
        )
    if high_risk_count >= int(thresholds.get("high_risk_spike", 5)):
        create_system_alert(
            db,
            alert_type="execution_queue_high_risk_spike",
            severity="CRITICAL",
            message="Execution queue high-risk intent spike",
            details={"high_risk_count": high_risk_count},
            entity_key="execution_queue",
            root_cause_code="high_risk_spike",
            state_key="execution_queue_high_risk_spike",
        )

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
            risk_payload=build_intent_risk_payload(row),
            operational_status=resolve_intent_operational_status(row),
            expected_impact=build_execution_intent_detail(db, row).get("expected_impact") or {},
            detail_version=resolve_intent_detail_version(row),
            snapshot_generated_at=snapshot_at,
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
    thresholds = (_decision_gate_config(db).get("thresholds") or {})
    distribution = rejection_reason_summary(db, limit=limit)
    trend = rejection_reason_trend(db, limit=limit)
    guidance = [
        {
            "reason_code": item.get("reason_code"),
            "action": "review_execution_payload",
            "guidance": "Risk ve payload alanlarını gözden geçirip retry öncesi re-validation yapın.",
        }
        for item in distribution[:10]
    ]

    reject_spike = sum(item.get("count", 0) for item in distribution[:3])
    if reject_spike >= int(thresholds.get("reject_spike", 10)):
        create_system_alert(
            db,
            alert_type="execution_reject_spike",
            severity="WARNING",
            message="Execution reject spike detected",
            details={"top_reason_count": reject_spike},
            entity_key="execution_queue",
            root_cause_code="reject_spike",
            state_key="execution_reject_spike",
        )

    return {
        "queue": queue_status_summary(db),
        "rejection_reason_distribution": distribution,
        "trend": trend,
        "guidance": guidance,
    }


@router.post("/execution-queue/{intent_id}/approve", response_model=AdminExecutionQueueDecisionResponse)
def approve_intent(
    intent_id: str,
    payload: AdminExecutionQueueDecisionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    gate_config = _decision_gate_config(db)
    gate_enforced = bool(gate_config.get("execution_decision_gate_enforced", True))

    queue_state = _queue_control_state()
    if queue_state.get("paused") and not bool(payload.override_execute):
        _log_decision_block(db, action="approve", intent_id=intent_id, actor=current_user, reason_code="execution_queue_paused")
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="execution_queue_paused")

    decision_reason = _resolve_decision_reason(payload)
    if len(decision_reason) < 3:
        _log_decision_block(db, action="approve", intent_id=intent_id, actor=current_user, reason_code="decision_reason_required")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="decision_reason_required")

    if bool(payload.override_execute) and str(current_user.role.value or "") != "super_admin":
        _log_decision_block(db, action="approve", intent_id=intent_id, actor=current_user, reason_code="override_requires_super_admin")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="override_requires_super_admin")

    try:
        row = approve_execution_intent(
            db,
            intent_id,
            current_user.id,
            admin_note=decision_reason,
            detail_version=payload.detail_version,
            read_acknowledged=bool(payload.read_acknowledged),
            double_confirmation=bool(payload.double_confirmation),
            allow_override=bool(payload.override_execute),
        )
    except ExecutionSafetyViolation as exc:
        db.rollback()
        _log_decision_block(db, action="approve", intent_id=intent_id, actor=current_user, reason_code=str(exc.reason_code))
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"reason_code": exc.reason_code, "message": exc.message, **(exc.details or {})},
        ) from exc
    except ValueError as exc:
        db.rollback()
        _log_decision_block(db, action="approve", intent_id=intent_id, actor=current_user, reason_code=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if bool(payload.read_acknowledged):
        create_audit_log(
            db,
            action="EXECUTION_DETAIL_ACKNOWLEDGED",
            entity_type="execution_intent",
            entity_id=row.id,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            details={"detail_version": payload.detail_version},
        )

    if not gate_enforced:
        try:
            row = execute_approved_intent(
                db,
                row.id,
                current_user.id,
                execution_reason=f"legacy_flow:{decision_reason}",
                execute_confirmation=True,
                detail_version=resolve_intent_detail_version(row),
            )
            create_audit_log(
                db,
                action="EXECUTION_DECISION_GATE_LEGACY_APPROVE_EXECUTE",
                entity_type="execution_intent",
                entity_id=row.id,
                actor_user_id=current_user.id,
                actor_role=current_user.role.value,
                severity="warning",
                details={"reason": decision_reason},
            )
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except CommercialControlViolation as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail={"reason_code": exc.reason_code, "message": exc.message, **(exc.details or {})},
            ) from exc

    create_audit_log(
        db,
        action="EXECUTION_INTENT_APPROVED",
        entity_type="execution_intent",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "reason": decision_reason,
            "detail_version": payload.detail_version,
            "read_acknowledged": bool(payload.read_acknowledged),
            "double_confirmation": bool(payload.double_confirmation),
            "override_execute": bool(payload.override_execute),
        },
    )
    if bool(payload.override_execute):
        create_audit_log(
            db,
            action="EXECUTION_INTENT_OVERRIDE_APPROVED",
            entity_type="execution_intent",
            entity_id=row.id,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            severity="warning",
            details={"reason": decision_reason},
        )
    execution_mode = _resolve_execution_mode_from_intent(row)
    return AdminExecutionQueueDecisionResponse(
        intent_id=row.id,
        status=row.status,
        admin_note=row.admin_note,
        execution_mode=execution_mode,
        detail_version=resolve_intent_detail_version(row),
    )


@router.post("/execution-queue/{intent_id}/execute", response_model=AdminExecutionQueueDecisionResponse)
def execute_intent(
    intent_id: str,
    payload: AdminExecutionQueueDecisionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    queue_state = _queue_control_state()
    if queue_state.get("paused") and not bool(payload.override_execute):
        _log_decision_block(db, action="execute", intent_id=intent_id, actor=current_user, reason_code="execution_queue_paused")
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="execution_queue_paused")

    decision_reason = _resolve_decision_reason(payload)
    if len(decision_reason) < 3:
        _log_decision_block(db, action="execute", intent_id=intent_id, actor=current_user, reason_code="decision_reason_required")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="decision_reason_required")

    try:
        row = execute_approved_intent(
            db,
            intent_id,
            current_user.id,
            execution_reason=decision_reason,
            execute_confirmation=bool(payload.execute_confirmation),
            detail_version=payload.detail_version,
        )
    except ValueError as exc:
        db.rollback()
        _log_decision_block(db, action="execute", intent_id=intent_id, actor=current_user, reason_code=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CommercialControlViolation as exc:
        db.rollback()
        _log_decision_block(db, action="execute", intent_id=intent_id, actor=current_user, reason_code=exc.reason_code)
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"reason_code": exc.reason_code, "message": exc.message, **(exc.details or {})},
        ) from exc

    create_audit_log(
        db,
        action="EXECUTION_INTENT_EXECUTED",
        entity_type="execution_intent",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "reason": decision_reason,
            "execute_confirmation": bool(payload.execute_confirmation),
            "detail_version": payload.detail_version,
        },
    )
    return AdminExecutionQueueDecisionResponse(
        intent_id=row.id,
        status=row.status,
        admin_note=row.admin_note,
        execution_mode=_resolve_execution_mode_from_intent(row),
        detail_version=resolve_intent_detail_version(row),
    )


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
        payload=AdminExecutionQueueDecisionRequest(note=payload.note, reason=payload.note, read_acknowledged=True),
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
    decision_reason = _resolve_decision_reason(payload)
    if len(decision_reason) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="decision_reason_required")

    try:
        row = reject_execution_intent(
            db,
            intent_id,
            current_user.id,
            admin_note=decision_reason,
            detail_version=payload.detail_version,
            read_acknowledged=bool(payload.read_acknowledged),
        )
    except ValueError as exc:
        db.rollback()
        _log_decision_block(db, action="reject", intent_id=intent_id, actor=current_user, reason_code=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="EXECUTION_INTENT_REJECTED",
        entity_type="execution_intent",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"reason": decision_reason, "reason_codes": row.reject_reason_codes or [], "detail_version": payload.detail_version},
    )
    execution_mode = _resolve_execution_mode_from_intent(row)
    return AdminExecutionQueueDecisionResponse(
        intent_id=row.id,
        status=row.status,
        admin_note=row.admin_note,
        execution_mode=execution_mode,
        detail_version=resolve_intent_detail_version(row),
    )


@router.post("/execution-queue/{intent_id}/retry", response_model=AdminExecutionQueueDecisionResponse)
def retry_intent(
    intent_id: str,
    payload: AdminExecutionQueueDecisionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    queue_state = _queue_control_state()
    if queue_state.get("paused"):
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="execution_queue_paused")

    decision_reason = _resolve_decision_reason(payload)
    if len(decision_reason) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="decision_reason_required")

    try:
        row = retry_execution_intent(db, intent_id, current_user.id, admin_note=decision_reason)
    except ValueError as exc:
        db.rollback()
        _log_decision_block(db, action="retry", intent_id=intent_id, actor=current_user, reason_code=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="EXECUTION_INTENT_RETRIED",
        entity_type="execution_intent",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"reason": decision_reason},
    )
    execution_mode = _resolve_execution_mode_from_intent(row)
    return AdminExecutionQueueDecisionResponse(
        intent_id=row.id,
        status=row.status,
        admin_note=row.admin_note,
        execution_mode=execution_mode,
        detail_version=resolve_intent_detail_version(row),
    )


@router.post("/execution-queue/{intent_id}/cancel", response_model=AdminExecutionQueueDecisionResponse)
def cancel_intent_by_admin(
    intent_id: str,
    payload: AdminExecutionQueueDecisionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    decision_reason = _resolve_decision_reason(payload)
    if len(decision_reason) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="decision_reason_required")

    try:
        row = cancel_execution_intent_by_admin(db, intent_id, current_user.id, admin_note=decision_reason)
    except ValueError as exc:
        db.rollback()
        _log_decision_block(db, action="cancel", intent_id=intent_id, actor=current_user, reason_code=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="EXECUTION_INTENT_CANCELLED",
        entity_type="execution_intent",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"reason": decision_reason},
    )
    execution_mode = _resolve_execution_mode_from_intent(row)
    return AdminExecutionQueueDecisionResponse(
        intent_id=row.id,
        status=row.status,
        admin_note=row.admin_note,
        execution_mode=execution_mode,
        detail_version=resolve_intent_detail_version(row),
    )


@router.get("/execution-queue/{intent_id}/detail", response_model=ExecutionIntentDetailResponse)
def execution_intent_detail(
    intent_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    row = db.query(UserExecutionIntent).filter(UserExecutionIntent.id == intent_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution_intent_not_found")
    payload = build_execution_intent_detail(db, row)
    return ExecutionIntentDetailResponse(**payload)


@router.get("/execution-queue/{intent_id}/history", response_model=list[ExecutionIntentHistoryItemResponse])
def execution_intent_history(
    intent_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    row = db.query(UserExecutionIntent).filter(UserExecutionIntent.id == intent_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution_intent_not_found")

    audits = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "execution_intent", AuditLog.entity_id == intent_id)
        .order_by(AuditLog.created_at.asc())
        .limit(limit)
        .all()
    )
    synthetic_events = [
        {
            "id": f"synthetic-created-{row.id}",
            "action": "INTENT_CREATED",
            "actor_user_id": row.user_id,
            "actor_role": "user",
            "reason": "intent_created",
            "details": {},
            "created_at": row.created_at,
        }
    ]
    if row.submitted_at:
        synthetic_events.append(
            {
                "id": f"synthetic-queued-{row.id}",
                "action": "INTENT_QUEUED",
                "actor_user_id": row.user_id,
                "actor_role": "user",
                "reason": "intent_queued",
                "details": {},
                "created_at": row.submitted_at,
            }
        )

    items = [
        ExecutionIntentHistoryItemResponse(
            id=entry.id,
            action=entry.action,
            actor_user_id=entry.actor_user_id,
            actor_role=entry.actor_role,
            reason=(entry.details or {}).get("reason") or (entry.details or {}).get("note"),
            details=entry.details or {},
            created_at=entry.created_at,
        )
        for entry in audits
    ]
    items.extend(ExecutionIntentHistoryItemResponse(**entry) for entry in synthetic_events)
    items.sort(key=lambda item: item.created_at)
    return items


@router.post("/execution-queue/bulk-decision", response_model=AdminExecutionQueueBulkDecisionResponse)
def execution_queue_bulk_decision(
    payload: AdminExecutionQueueBulkDecisionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    action = str(payload.action or "").lower()
    if action not in {"approve", "reject", "cancel"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_bulk_action")
    if not payload.intent_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bulk_intent_ids_required")
    if len(payload.intent_ids) > BULK_ACTION_LIMIT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bulk_action_limit_exceeded_20")

    reason = str(payload.reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="decision_reason_required")

    rows = (
        db.query(UserExecutionIntent)
        .filter(UserExecutionIntent.id.in_(payload.intent_ids))
        .all()
    )
    high_risk_exists = any(build_intent_risk_payload(row).get("is_high_risk") for row in rows)
    if high_risk_exists and not bool(payload.double_confirmation):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bulk_high_risk_double_confirmation_required")

    processed_ids = []
    failures = []

    for intent_id in payload.intent_ids:
        try:
            if action == "approve":
                approve_execution_intent(
                    db,
                    intent_id,
                    current_user.id,
                    admin_note=reason,
                    detail_version=None,
                    read_acknowledged=bool(payload.read_acknowledged),
                    double_confirmation=bool(payload.double_confirmation),
                    allow_override=False,
                )
            elif action == "reject":
                reject_execution_intent(
                    db,
                    intent_id,
                    current_user.id,
                    admin_note=reason,
                    read_acknowledged=bool(payload.read_acknowledged),
                )
            else:
                cancel_execution_intent_by_admin(db, intent_id, current_user.id, admin_note=reason)

            processed_ids.append(intent_id)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            failures.append({"intent_id": intent_id, "error": str(exc)})

    create_audit_log(
        db,
        action="EXECUTION_QUEUE_BULK_ACTION",
        entity_type="execution_queue",
        entity_id="bulk",
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "action": action,
            "reason": reason,
            "processed_count": len(processed_ids),
            "failed_count": len(failures),
            "contains_high_risk": high_risk_exists,
        },
    )

    return AdminExecutionQueueBulkDecisionResponse(
        action=action,
        processed_count=len(processed_ids),
        failed_count=len(failures),
        processed_intent_ids=processed_ids,
        failures=failures,
    )


@router.post("/execution-queue/control/pause", response_model=AdminExecutionQueueControlResponse)
def pause_execution_queue(
    payload: AdminExecutionQueueControlRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    reason = str(payload.reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="decision_reason_required")
    state = _set_queue_control_state(paused=True, actor_id=current_super_admin.id, reason=reason)
    create_audit_log(
        db,
        action="EXECUTION_QUEUE_PAUSED",
        entity_type="execution_queue",
        entity_id="global",
        actor_user_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        severity="warning",
        details={"reason": reason, "state": state},
    )
    return AdminExecutionQueueControlResponse(**state)


@router.post("/execution-queue/control/resume", response_model=AdminExecutionQueueControlResponse)
def resume_execution_queue(
    payload: AdminExecutionQueueControlRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    reason = str(payload.reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="decision_reason_required")
    state = _set_queue_control_state(paused=False, actor_id=current_super_admin.id, reason=reason)
    create_audit_log(
        db,
        action="EXECUTION_QUEUE_RESUMED",
        entity_type="execution_queue",
        entity_id="global",
        actor_user_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        details={"reason": reason, "state": state},
    )
    return AdminExecutionQueueControlResponse(**state)


@router.post("/execution-queue/control/clear", response_model=AdminExecutionQueueBulkDecisionResponse)
def clear_execution_queue(
    payload: AdminExecutionQueueControlRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    reason = str(payload.reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="decision_reason_required")

    queue_rows = list_execution_queue(db, status_filter="QUEUED", limit=500)
    processed = []
    failures = []
    for row in queue_rows:
        try:
            cancel_execution_intent_by_admin(db, row.id, current_super_admin.id, admin_note=reason)
            processed.append(row.id)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            failures.append({"intent_id": row.id, "error": str(exc)})

    create_audit_log(
        db,
        action="EXECUTION_QUEUE_CLEARED",
        entity_type="execution_queue",
        entity_id="global",
        actor_user_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        severity="warning",
        details={"reason": reason, "cleared_count": len(processed), "failed_count": len(failures)},
    )
    return AdminExecutionQueueBulkDecisionResponse(
        action="clear",
        processed_count=len(processed),
        failed_count=len(failures),
        processed_intent_ids=processed,
        failures=failures,
    )


@router.get("/execution-queue/control/state", response_model=AdminExecutionQueueControlResponse)
def execution_queue_control_state(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = (current_user, db)
    return AdminExecutionQueueControlResponse(**_queue_control_state())


@router.patch("/execution-queue/{intent_id}/edit", response_model=AdminExecutionQueueEditResponse)
def edit_execution_queue_intent(
    intent_id: str,
    payload: AdminExecutionQueueEditRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    patch = {
        "notional": payload.notional,
        "size": payload.size,
        "price": payload.price,
        "stop_price": payload.stop_price,
        "take_profit_price": payload.take_profit_price,
    }
    try:
        row, diff = edit_execution_intent_by_admin(
            db,
            intent_id,
            current_user.id,
            reason=payload.reason,
            patch=patch,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="EXECUTION_INTENT_EDITED",
        entity_type="execution_intent",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"reason": payload.reason, "diff": diff},
    )
    return AdminExecutionQueueEditResponse(
        intent_id=row.id,
        status=row.status,
        diff=diff,
        detail_version=resolve_intent_detail_version(row),
    )


@router.get("/execution-queue/observability")
def execution_queue_observability(
    days: int = Query(default=7, ge=1, le=30),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return {
        "queue": queue_status_summary(db),
        "metrics": build_queue_observability_metrics(db, days=days),
        "queue_control_state": _queue_control_state(),
    }


@router.get("/execution-queue/config", response_model=ExecutionDecisionGateConfigResponse)
def execution_decision_gate_config(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_user
    return ExecutionDecisionGateConfigResponse(**_decision_gate_config(db))


@router.patch("/execution-queue/config", response_model=ExecutionDecisionGateConfigResponse)
def update_execution_decision_gate_config(
    payload: ExecutionDecisionGateConfigUpdateRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    patch_payload = {
        "execution_decision_gate_enforced": payload.execution_decision_gate_enforced,
        "thresholds": payload.thresholds or {},
    }
    updated = _update_decision_gate_config(db, patch=patch_payload, actor_user_id=current_super_admin.id)
    create_audit_log(
        db,
        action="EXECUTION_DECISION_GATE_CONFIG_UPDATED",
        entity_type="execution_queue",
        entity_id="config",
        actor_user_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        details={"patch": patch_payload, "updated": updated},
    )
    return ExecutionDecisionGateConfigResponse(**updated)


@router.get("/execution-queue/alerts")
def list_execution_queue_alerts(
    status_filter: str = Query(default="all"),
    limit: int = Query(default=100, ge=1, le=300),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    alert_types = ["execution_queue_backlog", "execution_queue_high_risk_spike", "execution_reject_spike"]
    query = db.query(SystemAlert).filter(SystemAlert.alert_type.in_(alert_types)).order_by(SystemAlert.created_at.desc())
    rows = query.limit(limit).all()

    items = []
    for row in rows:
        details = dict(row.details or {})
        state = _execution_alert_user_state(details, current_user.id)
        item_status = "acked" if state.get("acked_at") else "read" if state.get("read_at") else "unread"
        if status_filter != "all" and item_status != status_filter:
            continue
        items.append(
            {
                "id": row.id,
                "alert_type": row.alert_type,
                "severity": row.severity,
                "message": row.message,
                "details": details,
                "status": item_status,
                "read_at": state.get("read_at"),
                "acked_at": state.get("acked_at"),
                "acked_by": state.get("acked_by"),
                "entity_key": row.entity_key,
                "deep_link": f"/admin/execution-queue?intent_id={row.entity_key}" if row.entity_key else "/admin/execution-queue",
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return items


@router.post("/execution-queue/alerts/{alert_id}/read")
def mark_execution_alert_read(
    alert_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert_not_found")
    row.details = _set_execution_alert_user_state(
        dict(row.details or {}),
        user_id=current_user.id,
        patch={"read_at": datetime.now(timezone.utc).isoformat()},
    )
    db.commit()
    create_audit_log(
        db,
        action="EXECUTION_ALERT_MARKED_READ",
        entity_type="system_alert",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"alert_type": row.alert_type},
    )
    return {"status": "ok", "alert_id": row.id}


@router.post("/execution-queue/alerts/{alert_id}/ack")
def ack_execution_alert(
    alert_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert_not_found")
    now_iso = datetime.now(timezone.utc).isoformat()
    row.details = _set_execution_alert_user_state(
        dict(row.details or {}),
        user_id=current_user.id,
        patch={
            "read_at": now_iso,
            "acked_at": now_iso,
            "acked_by": current_user.id,
        },
    )
    db.commit()
    create_audit_log(
        db,
        action="EXECUTION_ALERT_ACKED",
        entity_type="system_alert",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"alert_type": row.alert_type},
    )
    return {"status": "ok", "alert_id": row.id}


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
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    reason_code = payload.reason_code or "EXECUTION_GUARD_MANUAL_OVERRIDE"
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
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return create_execution_guard_override(payload=payload, current_user=current_user, db=db)


@router.post("/execution-readiness/override/{override_id}/revoke", response_model=ReleaseGateOverrideResponse)
def revoke_execution_guard_override(
    override_id: str,
    current_user: User = Depends(require_super_admin),
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