import json
import os
import uuid
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Text, cast, or_
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import (
    BacktestResultCard,
    BotProfile,
    DecisionTraceCold,
    DecisionTraceHot,
    ExecutionEvent,
    ExecutionIntent,
    ExecutionIntentEvent,
    ExecutionManualAction,
    ExecutionPolicy,
    ExecutionStateTransition,
    ExecutionTraceIndex,
    FailedEvent,
    IdempotencyCollision,
    RiskExposureGroup,
    StateRebuildLog,
    User,
)
from schemas import (
    BacktestResultCardCreate,
    BacktestResultCardResponse,
    BacktestResultCardUpdate,
    CorrelationMatrixResponse,
    ExecutionCorrelationTraceResponse,
    ExecutionEventResponse,
    ExecutionManualActionRequest,
    ExecutionPolicyCreate,
    ExecutionPolicyResponse,
    ExecutionSimulationBatchRequest,
    ExecutionSimulationBatchResponse,
    ExecutionStateControlQueryResponse,
    ExecutionStateDetailResponse,
    ExecutionStateTransitionResponse,
    ExecutionPolicyUpdate,
    FailedEventResponse,
    HardeningChecklistRunResponse,
    HardeningChecklistTrendResponse,
    HardeningSummaryResponse,
    RiskExposureGroupCreate,
    RiskExposureGroupResponse,
    RiskExposureGroupUpdate,
    StateRebuildLogResponse,
    IdempotencyCollisionResolveRequest,
    IdempotencyCollisionResponse,
)
from services.audit_service import create_audit_log
from services.execution_policy_service import get_policy_for_strategy
from services.failed_event_service import create_failed_event, mark_failed_event_resolved, mark_failed_event_retry
from services.hardening_checklist_service import (
    get_hardening_trend,
    get_latest_hardening_checklist_run,
    run_hardening_checklist,
)
from services.pipeline.cache_store import incr_counter
from services.pipeline.correlation_service import build_correlation_matrix
from services.pipeline.execution_engine import open_paper_position
from services.pipeline.runtime import pipeline_runtime
from services.state_rebuild_service import run_state_rebuild

router = APIRouter(prefix="/admin-phase3", tags=["admin_phase3"])

PROD_CONFIRMATION_PHRASE = "CONFIRM_PROD_MANUAL_ACTION"


def _is_prod_environment() -> bool:
    return str(os.environ.get("APP_ENV") or "production").lower() == "production"


def _serialize_execution_event(row: ExecutionEvent) -> dict:
    return {
        "id": row.id,
        "bot_profile_id": row.bot_profile_id,
        "exchange": row.exchange,
        "symbol": row.symbol,
        "side": row.side,
        "quantity": float(row.quantity or 0),
        "mock_price": float(row.mock_price or 0),
        "execution_status": row.execution_status,
        "source_type": row.source_type,
        "environment": row.environment,
        "correlation_id": row.correlation_id,
        "triggered_by": row.triggered_by,
        "parent_event_id": row.parent_event_id,
        "strategy_id": row.strategy_id,
        "response_payload": row.response_payload or {},
        "note": row.note,
        "created_at": row.created_at,
    }


def _serialize_transition(row: ExecutionStateTransition) -> dict:
    return {
        "id": row.id,
        "execution_event_id": row.execution_event_id,
        "state": row.state,
        "from_state": row.from_state,
        "to_state": row.to_state,
        "sequence": row.sequence,
        "latency_ms": row.latency_ms,
        "correlation_id": row.correlation_id,
        "source_type": row.source_type,
        "environment": row.environment,
        "is_manual": bool(row.is_manual),
        "details": row.details or {},
        "occurred_at": row.occurred_at,
    }


def _state_counter(rows: list[ExecutionStateTransition]) -> dict[str, int]:
    counters: dict[str, int] = {
        "created": 0,
        "submitted": 0,
        "acknowledged": 0,
        "partially_filled": 0,
        "timeout": 0,
        "fallback_submitted": 0,
        "filled": 0,
        "rejected": 0,
        "failed": 0,
        "cancelled": 0,
    }
    for row in rows:
        state = str(row.state or "")
        if state.startswith("retry_"):
            counters["retry_n"] = counters.get("retry_n", 0) + 1
            continue
        if state in counters:
            counters[state] += 1
    counters.setdefault("retry_n", 0)
    return counters


def _insert_trace_index(
    db: Session,
    *,
    correlation_id: str,
    stage: str,
    actor: str,
    payload: dict,
    execution_event_id: str | None = None,
    intent_id: str | None = None,
) -> None:
    row = ExecutionTraceIndex(
        trace_id=str(uuid.uuid4()),
        correlation_id=correlation_id,
        execution_event_id=execution_event_id,
        intent_id=intent_id,
        stage=stage,
        actor=actor,
        payload=payload,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)


def _require_manual_action_guard(current_user: User, payload: ExecutionManualActionRequest) -> None:
    if not str(payload.correlation_id or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="correlation_id zorunlu")

    if _is_prod_environment():
        if str(current_user.role.value) != "super_admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="prod ortamda manuel aksiyon için super_admin gerekli")
        if str(payload.confirmation_phrase or "").strip() != PROD_CONFIRMATION_PHRASE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="prod confirmation phrase geçersiz")



@router.get("/execution-policies", response_model=list[ExecutionPolicyResponse])
def list_execution_policies(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(ExecutionPolicy).order_by(ExecutionPolicy.strategy_type.asc()).all()


@router.post("/execution-policies", response_model=ExecutionPolicyResponse)
def create_execution_policy(
    payload: ExecutionPolicyCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(ExecutionPolicy).filter(ExecutionPolicy.strategy_type == payload.strategy_type).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Policy already exists for strategy")
    policy = ExecutionPolicy(**payload.model_dump())
    db.add(policy)
    db.commit()
    db.refresh(policy)
    create_audit_log(
        db,
        action="execution_policy_created",
        entity_type="execution_policy",
        entity_id=policy.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy_type": policy.strategy_type, "style": policy.execution_style},
    )
    return policy


@router.put("/execution-policies/{policy_id}", response_model=ExecutionPolicyResponse)
def update_execution_policy(
    policy_id: str,
    payload: ExecutionPolicyUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    policy = db.query(ExecutionPolicy).filter(ExecutionPolicy.id == policy_id).first()
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution policy not found")
    for key, value in payload.model_dump().items():
        setattr(policy, key, value)
    db.commit()
    db.refresh(policy)
    create_audit_log(
        db,
        action="execution_policy_updated",
        entity_type="execution_policy",
        entity_id=policy.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy_type": policy.strategy_type, "style": policy.execution_style},
    )
    return policy


@router.get("/exposure-groups", response_model=list[RiskExposureGroupResponse])
def list_exposure_groups(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(RiskExposureGroup).order_by(RiskExposureGroup.name.asc()).all()


@router.post("/exposure-groups", response_model=RiskExposureGroupResponse)
def create_exposure_group(
    payload: RiskExposureGroupCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(RiskExposureGroup).filter(RiskExposureGroup.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exposure group already exists")
    group = RiskExposureGroup(**payload.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    create_audit_log(
        db,
        action="exposure_group_created",
        entity_type="risk_exposure_group",
        entity_id=group.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"name": group.name},
    )
    return group


@router.put("/exposure-groups/{group_id}", response_model=RiskExposureGroupResponse)
def update_exposure_group(
    group_id: str,
    payload: RiskExposureGroupUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    group = db.query(RiskExposureGroup).filter(RiskExposureGroup.id == group_id).first()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exposure group not found")
    for key, value in payload.model_dump().items():
        setattr(group, key, value)
    db.commit()
    db.refresh(group)
    create_audit_log(
        db,
        action="exposure_group_updated",
        entity_type="risk_exposure_group",
        entity_id=group.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"name": group.name},
    )
    return group


@router.get("/failed-events", response_model=list[FailedEventResponse])
def list_failed_events(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=20, le=500),
    status_filter: str | None = Query(default=None),
    search: str | None = Query(default=None),
    failure_class: str | None = Query(default=None),
):
    query = db.query(FailedEvent)
    if status_filter:
        query = query.filter(FailedEvent.status == status_filter)
    if failure_class:
        query = query.filter(FailedEvent.failure_class == failure_class)
    if search:
        token = f"%{search.strip()}%"
        query = query.filter(
            (FailedEvent.entity_id.ilike(token))
            | (FailedEvent.event_type.ilike(token))
            | (FailedEvent.error_message.ilike(token))
            | (FailedEvent.correlation_id.ilike(token))
        )
    return query.order_by(FailedEvent.created_at.desc()).limit(limit).all()


@router.get("/failed-events/dead-letter", response_model=list[FailedEventResponse])
def list_dead_letter_events(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=20, le=500),
):
    return (
        db.query(FailedEvent)
        .filter(FailedEvent.status.in_(["dead", "quarantined"]))
        .order_by(FailedEvent.created_at.desc())
        .limit(limit)
        .all()
    )


@router.post("/failed-events/{event_id}/retry", response_model=FailedEventResponse)
def retry_failed_event(event_id: str, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    failed_event = db.query(FailedEvent).filter(FailedEvent.id == event_id).first()
    if failed_event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Failed event not found")
    row = mark_failed_event_retry(db, failed_event, actor=str(current_user.id), retry_reason="manual_retry")
    if row.correlation_id:
        _insert_trace_index(
            db,
            correlation_id=row.correlation_id,
            stage="failed_event_retry",
            actor=str(current_user.id),
            payload={"failed_event_id": row.id, "status": row.status},
        )
        db.commit()
    return row


@router.post("/failed-events/{event_id}/resolve", response_model=FailedEventResponse)
def resolve_failed_event(event_id: str, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    failed_event = db.query(FailedEvent).filter(FailedEvent.id == event_id).first()
    if failed_event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Failed event not found")
    row = mark_failed_event_resolved(db, failed_event, actor=str(current_user.id))
    if row.correlation_id:
        _insert_trace_index(
            db,
            correlation_id=row.correlation_id,
            stage="failed_event_resolved",
            actor=str(current_user.id),
            payload={"failed_event_id": row.id, "status": row.status},
        )
        db.commit()
    return row


@router.post("/failed-events/{event_id}/reprocess", response_model=FailedEventResponse)
def reprocess_failed_event(event_id: str, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    failed_event = db.query(FailedEvent).filter(FailedEvent.id == event_id).first()
    if failed_event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Failed event not found")
    failed_event.status = "retrying"
    failed_event.retry_count = 0
    failed_event.next_retry_at = datetime.now(timezone.utc)
    failed_event.retry_reason = "manual_reprocess"
    failed_event.last_action_by = str(current_user.id)
    if failed_event.correlation_id:
        _insert_trace_index(
            db,
            correlation_id=failed_event.correlation_id,
            stage="failed_event_reprocess",
            actor=str(current_user.id),
            payload={"failed_event_id": failed_event.id, "status": failed_event.status},
        )
    db.commit()
    db.refresh(failed_event)
    return failed_event


@router.post("/failed-events/bulk-retry", response_model=list[FailedEventResponse])
def bulk_retry_failed_events(
    event_ids: list[str],
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.query(FailedEvent).filter(FailedEvent.id.in_(event_ids)).all()
    return [mark_failed_event_retry(db, row, actor=str(current_user.id), retry_reason="bulk_manual_retry") for row in rows]


@router.post("/failed-events/bulk-resolve", response_model=list[FailedEventResponse])
def bulk_resolve_failed_events(
    event_ids: list[str],
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.query(FailedEvent).filter(FailedEvent.id.in_(event_ids)).all()
    return [mark_failed_event_resolved(db, row, actor=str(current_user.id)) for row in rows]


@router.post("/failed-events/seed", response_model=FailedEventResponse)
def seed_failed_event(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    existing = db.query(FailedEvent).filter(FailedEvent.status.in_(["pending", "retrying"]))
    latest = existing.order_by(FailedEvent.created_at.desc()).first()
    if latest:
        return latest

    seeded = create_failed_event(
        db,
        event_type="seeded_failed_event",
        entity_type="phase3_admin",
        entity_id="seed",
        payload={"source": "manual_seed_button", "hint": "for retry/resolve UI validation"},
        error_message="Seeded failed event for deterministic admin UI testing",
    )
    create_audit_log(
        db,
        action="failed_event_seeded",
        entity_type="failed_event",
        entity_id=seeded.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"event_type": seeded.event_type},
    )
    return seeded


@router.get("/state-rebuild-logs", response_model=list[StateRebuildLogResponse])
def list_state_rebuild_logs(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(StateRebuildLog).order_by(StateRebuildLog.started_at.desc()).limit(200).all()


@router.post("/state-rebuild/run", response_model=StateRebuildLogResponse)
def trigger_state_rebuild(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    scope_type: str = Query(default="full"),
    scope_value: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    rebuild_log = run_state_rebuild(
        db,
        trigger_source="manual_admin",
        scope_type=scope_type,
        scope_value=scope_value,
        date_from=date_from,
        date_to=date_to,
    )
    create_audit_log(
        db,
        action="state_rebuild_triggered",
        entity_type="state_rebuild",
        entity_id=rebuild_log.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"status": rebuild_log.status},
    )
    return rebuild_log


@router.get("/backtest-cards", response_model=list[BacktestResultCardResponse])
def list_backtest_cards(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(BacktestResultCard).order_by(BacktestResultCard.updated_at.desc()).all()


@router.post("/backtest-cards", response_model=BacktestResultCardResponse)
def create_backtest_card(
    payload: BacktestResultCardCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    card = BacktestResultCard(**payload.model_dump())
    db.add(card)
    db.commit()
    db.refresh(card)
    create_audit_log(
        db,
        action="backtest_card_created",
        entity_type="backtest_card",
        entity_id=card.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy": card.strategy_type, "risk_label": card.risk_label},
    )
    return card


@router.put("/backtest-cards/{card_id}", response_model=BacktestResultCardResponse)
def update_backtest_card(
    card_id: str,
    payload: BacktestResultCardUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    card = db.query(BacktestResultCard).filter(BacktestResultCard.id == card_id).first()
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest card not found")
    for key, value in payload.model_dump().items():
        setattr(card, key, value)
    db.commit()
    db.refresh(card)
    create_audit_log(
        db,
        action="backtest_card_updated",
        entity_type="backtest_card",
        entity_id=card.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy": card.strategy_type, "risk_label": card.risk_label},
    )
    return card


@router.get("/hardening-summary", response_model=HardeningSummaryResponse)
def get_hardening_summary(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return pipeline_runtime.hardening_summary(db)


@router.get("/execution-state-transitions", response_model=list[ExecutionStateTransitionResponse])
def list_execution_state_transitions(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=20, le=500),
):
    return pipeline_runtime.list_execution_state_transitions(db, limit)


@router.get("/execution-state-transitions/control", response_model=ExecutionStateControlQueryResponse)
def list_execution_state_transitions_control(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    state: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    strategy: str | None = Query(default=None),
    status_filter: str | None = Query(default=None),
    search: str | None = Query(default=None),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    limit: int = Query(default=300, ge=50, le=1000),
):
    query = db.query(ExecutionStateTransition).join(ExecutionEvent, ExecutionEvent.id == ExecutionStateTransition.execution_event_id)
    if state:
        query = query.filter(ExecutionStateTransition.state == state)
    if source_type:
        query = query.filter(ExecutionStateTransition.source_type == source_type)
    if symbol:
        query = query.filter(ExecutionEvent.symbol == symbol.upper())
    if strategy:
        query = query.filter(ExecutionEvent.strategy_id == strategy)
    if status_filter:
        query = query.filter(ExecutionEvent.execution_status == status_filter)
    if time_from:
        query = query.filter(ExecutionStateTransition.occurred_at >= datetime.fromisoformat(time_from))
    if time_to:
        query = query.filter(ExecutionStateTransition.occurred_at <= datetime.fromisoformat(time_to))
    if search:
        token = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ExecutionStateTransition.execution_event_id.ilike(token),
                ExecutionStateTransition.correlation_id.ilike(token),
                ExecutionEvent.symbol.ilike(token),
                cast(ExecutionStateTransition.details, Text).ilike(token),
            )
        )

    rows = query.order_by(ExecutionStateTransition.occurred_at.desc()).limit(limit).all()
    summary_counts: dict[str, int] = {}
    for row in rows:
        summary_counts[row.state] = summary_counts.get(row.state, 0) + 1
    return ExecutionStateControlQueryResponse(
        rows=[ExecutionStateTransitionResponse(**_serialize_transition(row)) for row in rows],
        summary_counts=summary_counts,
        state_counters=_state_counter(rows),
    )


@router.get("/execution-state-transitions/{execution_event_id}/detail", response_model=ExecutionStateDetailResponse)
def execution_state_detail(
    execution_event_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    event = db.query(ExecutionEvent).filter(ExecutionEvent.id == execution_event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution event not found")
    transitions = (
        db.query(ExecutionStateTransition)
        .filter(ExecutionStateTransition.execution_event_id == execution_event_id)
        .order_by(ExecutionStateTransition.sequence.asc(), ExecutionStateTransition.occurred_at.asc())
        .all()
    )
    path = [row.state for row in transitions]
    current_state = path[-1] if path else event.execution_status
    previous_state = path[-2] if len(path) > 1 else None
    dwell_time = 0.0
    if len(transitions) > 1:
        dwell_time = max((transitions[-1].occurred_at - transitions[-2].occurred_at).total_seconds(), 0)

    return ExecutionStateDetailResponse(
        execution_event=ExecutionEventResponse(**_serialize_execution_event(event)),
        current_state=current_state,
        previous_state=previous_state,
        full_state_path=path,
        transition_count=len(transitions),
        dwell_time_seconds=dwell_time,
        transitions=[ExecutionStateTransitionResponse(**_serialize_transition(row)) for row in transitions],
    )


@router.post("/execution-state-transitions/{execution_event_id}/manual-action")
def manual_execution_action(
    execution_event_id: str,
    payload: ExecutionManualActionRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _require_manual_action_guard(current_admin, payload)
    event = db.query(ExecutionEvent).filter(ExecutionEvent.id == execution_event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution event not found")

    open_collision = (
        db.query(IdempotencyCollision)
        .filter(
            IdempotencyCollision.correlation_id == payload.correlation_id,
            IdempotencyCollision.status == "open",
        )
        .first()
    )
    if open_collision and payload.action_type in {"force_state_change", "reprocess"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Open idempotency collision varken bu aksiyon replay-safe değil")

    replay_guard = (
        db.query(ExecutionManualAction)
        .filter(
            ExecutionManualAction.execution_event_id == execution_event_id,
            ExecutionManualAction.correlation_id == payload.correlation_id,
            ExecutionManualAction.action_type == payload.action_type,
        )
        .order_by(ExecutionManualAction.created_at.desc())
        .first()
    )
    if replay_guard:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Aynı manual action zaten uygulanmış")

    target_state = event.execution_status
    if payload.action_type == "force_state_change":
        target_state = str(payload.payload.get("to_state") or "").strip()
        if not target_state:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="force_state_change için to_state zorunlu")
    elif payload.action_type == "cancel_execution":
        target_state = "cancelled"
    elif payload.action_type == "reprocess":
        target_state = "submitted"
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz action_type")

    prev_state = event.execution_status
    event.execution_status = target_state
    event.triggered_by = str(current_admin.id)
    event.correlation_id = payload.correlation_id
    event.source_type = "replay" if payload.action_type == "reprocess" else event.source_type
    db.add(event)

    transition = ExecutionStateTransition(
        execution_event_id=event.id,
        state=target_state,
        from_state=prev_state,
        to_state=target_state,
        sequence=int(datetime.now(timezone.utc).timestamp()),
        latency_ms=0,
        correlation_id=payload.correlation_id,
        source_type=event.source_type,
        environment=event.environment,
        is_manual=True,
        details={"reason_note": payload.reason_note, "action_type": payload.action_type, **(payload.payload or {})},
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(transition)

    manual_row = ExecutionManualAction(
        action_id=str(uuid.uuid4()),
        execution_event_id=event.id,
        correlation_id=payload.correlation_id,
        action_type=payload.action_type,
        requested_by=str(current_admin.id),
        requested_role=current_admin.role.value,
        confirmation_phrase=payload.confirmation_phrase,
        reason_note=payload.reason_note,
        is_prod_guard_applied=_is_prod_environment(),
        idempotency_checked=True,
        replay_safe_checked=True,
        details=payload.payload or {},
        created_at=datetime.now(timezone.utc),
    )
    db.add(manual_row)

    _insert_trace_index(
        db,
        correlation_id=payload.correlation_id,
        stage=f"manual_{payload.action_type}",
        actor=str(current_admin.id),
        payload={"execution_event_id": event.id, "prev_state": prev_state, "to_state": target_state},
        execution_event_id=event.id,
    )
    db.commit()

    create_audit_log(
        db,
        action="execution_manual_action",
        entity_type="execution_event",
        entity_id=event.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "action_type": payload.action_type,
            "correlation_id": payload.correlation_id,
            "to_state": target_state,
        },
    )

    return {
        "status": "success",
        "execution_event_id": event.id,
        "previous_state": prev_state,
        "current_state": target_state,
        "manual_action_id": manual_row.action_id,
    }


@router.get("/correlation-matrix", response_model=CorrelationMatrixResponse)
def get_correlation_matrix(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    window: int = Query(default=200, ge=30, le=500),
):
    symbols: list[str] = []
    for group in db.query(RiskExposureGroup).all():
        symbols.extend(group.symbols)

    if not symbols:
        for bot in db.query(BotProfile).all():
            symbols.extend(bot.symbols)

    if not symbols:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    return build_correlation_matrix(pipeline_runtime.cache, symbols, window=window)


@router.get("/idempotency-collisions", response_model=list[IdempotencyCollisionResponse])
def list_idempotency_collisions(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=300, ge=20, le=1000),
):
    query = db.query(IdempotencyCollision)
    if status_filter:
        query = query.filter(IdempotencyCollision.status == status_filter)
    if search:
        token = f"%{search.strip()}%"
        query = query.filter(
            or_(
                IdempotencyCollision.idempotency_key.ilike(token),
                IdempotencyCollision.intent_id.ilike(token),
                IdempotencyCollision.correlation_id.ilike(token),
            )
        )
    rows = query.order_by(IdempotencyCollision.created_at.desc()).limit(limit).all()
    return [IdempotencyCollisionResponse.model_validate(item) for item in rows]


@router.post("/idempotency-collisions/{collision_id}/resolve", response_model=IdempotencyCollisionResponse)
def resolve_idempotency_collision(
    collision_id: str,
    payload: IdempotencyCollisionResolveRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(IdempotencyCollision).filter(IdempotencyCollision.collision_id == collision_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="collision not found")

    action = str(payload.action or "").strip()
    allowed_actions = {"mark_safe_duplicate", "release_blocked_retry", "suppress_replay", "force_reprocess_new_key"}
    if action not in allowed_actions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"action invalid: {sorted(allowed_actions)}")

    row.status = "resolved"
    row.resolution_action = action
    row.resolution_note = payload.reason_note
    row.resolved_by = str(current_admin.id)
    row.resolved_at = datetime.now(timezone.utc)
    db.add(row)

    _insert_trace_index(
        db,
        correlation_id=payload.correlation_id,
        stage="idempotency_collision_resolved",
        actor=str(current_admin.id),
        payload={"collision_id": collision_id, "action": action, "note": payload.reason_note},
    )
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="idempotency_collision_resolved",
        entity_type="idempotency_collision",
        entity_id=row.collision_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"action": action, "correlation_id": payload.correlation_id},
    )
    return IdempotencyCollisionResponse.model_validate(row)


@router.get("/execution-trace/{correlation_id}", response_model=ExecutionCorrelationTraceResponse)
def execution_trace_chain(
    correlation_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    chain_rows = (
        db.query(ExecutionTraceIndex)
        .filter(ExecutionTraceIndex.correlation_id == correlation_id)
        .order_by(ExecutionTraceIndex.created_at.asc())
        .all()
    )
    intent_rows = (
        db.query(ExecutionIntent)
        .filter(ExecutionIntent.correlation_id == correlation_id)
        .order_by(ExecutionIntent.created_at.asc())
        .all()
    )
    event_rows = (
        db.query(ExecutionEvent)
        .filter(ExecutionEvent.correlation_id == correlation_id)
        .order_by(ExecutionEvent.created_at.asc())
        .all()
    )
    failure_rows = (
        db.query(FailedEvent)
        .filter(FailedEvent.correlation_id == correlation_id)
        .order_by(FailedEvent.created_at.asc())
        .all()
    )
    if not chain_rows:
        hot_rows = db.query(DecisionTraceHot).filter(DecisionTraceHot.correlation_id == correlation_id).all()
        for hot in hot_rows:
            chain_rows.append(
                ExecutionTraceIndex(
                    trace_id=str(uuid.uuid4()),
                    correlation_id=correlation_id,
                    execution_event_id=None,
                    intent_id=None,
                    stage="decision_hot_trace",
                    actor="system",
                    payload={
                        "decision_hash": hot.decision_hash,
                        "context_hash": hot.context_hash,
                        "intent_hash": hot.intent_hash,
                    },
                    created_at=hot.created_at,
                )
            )
        cold_rows = db.query(DecisionTraceCold).filter(DecisionTraceCold.correlation_id == correlation_id).all()
        for cold in cold_rows:
            chain_rows.append(
                ExecutionTraceIndex(
                    trace_id=str(uuid.uuid4()),
                    correlation_id=correlation_id,
                    execution_event_id=None,
                    intent_id=None,
                    stage="decision_cold_trace",
                    actor="system",
                    payload={
                        "decision_hash": cold.decision_hash,
                        "terminal_state": cold.terminal_state,
                        "lifecycle": cold.lifecycle_summary,
                    },
                    created_at=cold.created_at,
                )
            )

    return ExecutionCorrelationTraceResponse(
        correlation_id=correlation_id,
        chain=[
            {
                "stage": item.stage,
                "actor": item.actor,
                "payload": item.payload or {},
                "created_at": item.created_at,
            }
            for item in sorted(chain_rows, key=lambda it: it.created_at)
        ],
        intents=[
            {
                "intent_id": row.intent_id,
                "intent_hash": row.intent_hash,
                "status": row.status,
                "symbol": row.symbol,
                "side": row.side,
                "created_at": row.created_at,
            }
            for row in intent_rows
        ],
        events=[_serialize_execution_event(item) for item in event_rows],
        failures=[FailedEventResponse.model_validate(item) for item in failure_rows],
    )


@router.post("/hardening-checklist/run", response_model=HardeningChecklistRunResponse)
def run_hardening_checklist_endpoint(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    checklist = run_hardening_checklist(db)
    create_audit_log(
        db,
        action="hardening_checklist_run",
        entity_type="hardening_checklist",
        entity_id=checklist.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"score": checklist.score, "critical_blocked": checklist.critical_blocked},
    )
    return checklist


@router.get("/hardening-checklist/latest", response_model=HardeningChecklistRunResponse)
def get_latest_hardening_checklist_endpoint(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    latest = get_latest_hardening_checklist_run(db)
    if latest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hardening checklist run yet")
    return latest


@router.get("/hardening-checklist/trend", response_model=HardeningChecklistTrendResponse)
def get_hardening_checklist_trend_endpoint(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_hardening_trend(db)


@router.post("/execution-state-transitions/simulate")
def simulate_execution_state_flow(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    strategy_type: str = Query(default="breakout"),
    symbol: str = Query(default="BTCUSDT"),
    side: str = Query(default="long"),
    outcome: str = Query(default="filled"),
    retry_budget: int = Query(default=2, ge=0, le=5),
    source_type: str = Query(default="simulation"),
    environment: str = Query(default="simulation"),
    correlation_id: str | None = Query(default=None),
):
    normalized_source = str(source_type or "simulation").lower()
    if normalized_source not in {"simulation", "paper", "replay"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source_type simulation/paper/replay olmalı")

    corr_id = str(correlation_id or f"sim_{uuid.uuid4().hex[:16]}")
    scenario_key_payload = {
        "strategy_type": strategy_type,
        "symbol": symbol.upper(),
        "side": side.lower(),
        "outcome": outcome,
        "retry_budget": retry_budget,
        "source_type": normalized_source,
        "environment": environment,
    }
    idempotency_key = hashlib.sha256(
        json.dumps(scenario_key_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    allowed_outcomes = {"filled", "timeout", "rejected", "failed", "partial"}
    allowed_sides = {"long", "short"}
    if outcome not in allowed_outcomes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid outcome. Allowed: {sorted(allowed_outcomes)}",
        )
    if side.lower() not in allowed_sides:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid side. Allowed: {sorted(allowed_sides)}",
        )

    bot = (
        db.query(BotProfile)
        .filter(BotProfile.strategy_type == strategy_type)
        .order_by(BotProfile.created_at.desc())
        .first()
    )
    if bot is None:
        bot = db.query(BotProfile).order_by(BotProfile.created_at.desc()).first()
    if bot is None:
        bot = BotProfile(
            user_id=current_admin.id,
            name=f"auto_sim_{strategy_type}",
            strategy_type=strategy_type,
            exchange="paper",
            market_type="futures",
            symbols=[symbol.upper()],
            timeframe="15m",
            trend_timeframe="1h",
            leverage=1,
            is_enabled=True,
            is_running=False,
            is_deleted=False,
        )
        db.add(bot)
        db.commit()
        db.refresh(bot)

    user = db.query(User).filter(User.id == bot.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bot owner not found")

    try:
        policy = get_policy_for_strategy(db, strategy_type)
    except Exception:
        policy = ExecutionPolicy(
            strategy_type=strategy_type,
            execution_style="maker_first",
            order_preference="limit",
            timeout_seconds=90,
            fallback_behavior="market_if_timeout",
            partial_fill_tolerance_pct=35,
            execution_urgency="normal",
            maker_only=False,
            disable_taker=False,
            max_slippage_bps=15,
            active=True,
            metadata={"source": "auto_seed_for_execution_simulation"},
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)
    execution_result = open_paper_position(
        db,
        user=user,
        bot=bot,
        symbol=symbol.upper(),
        direction=side.lower(),
        market_price=100.0,
        quantity=0.01,
        leverage=1,
        stop_loss=98.0 if side.lower() == "long" else 102.0,
        take_profit=104.0 if side.lower() == "long" else 96.0,
        execution_policy={
            "style": policy.execution_style,
            "order_preference": policy.order_preference,
            "timeout_seconds": policy.timeout_seconds,
            "fallback_behavior": policy.fallback_behavior,
            "partial_fill_tolerance_pct": policy.partial_fill_tolerance_pct,
            "execution_urgency": policy.execution_urgency,
            "retry_limit": retry_budget,
        },
        response_payload={"mode": "simulation", "trigger": "admin_manual"},
        execution_context={
            "forced_outcome": None if outcome == "filled" else outcome,
            "spread_bps": 12,
            "latency_ms": 220,
            "partial_fill_ratio": 0.42,
        },
        source_type=normalized_source,
        environment=environment,
        correlation_id=corr_id,
        triggered_by=str(current_admin.id),
    )

    event_row = execution_result["execution_event"]
    base_payload = event_row.response_payload if isinstance(event_row.response_payload, dict) else {}
    event_payload = {
        **base_payload,
        "idempotency_key": idempotency_key,
        "idempotency_context": scenario_key_payload,
        "simulation_result_panel": {
        "final_state": execution_result["final_state"],
        "state_path": execution_result["state_path"],
        "retry_budget_used": execution_result.get("retry_budget_used", 0),
        "partial_fill_ratio": execution_result.get("partial_fill_ratio", 0),
        "created_records": {
            "execution_event_id": event_row.id,
            "position_created": bool(execution_result.get("position")),
        },
        },
    }
    event_row.response_payload = event_payload
    db.add(event_row)

    duplicate_sim = (
        db.query(ExecutionEvent)
        .filter(
            ExecutionEvent.id != event_row.id,
            ExecutionEvent.source_type == normalized_source,
            ExecutionEvent.environment == environment,
        )
        .order_by(ExecutionEvent.created_at.desc())
        .all()
    )
    for candidate in duplicate_sim:
        payload = candidate.response_payload if isinstance(candidate.response_payload, dict) else {}
        if str(payload.get("idempotency_key") or "") != idempotency_key:
            continue
        collision = IdempotencyCollision(
            collision_id=str(uuid.uuid4()),
            intent_id=None,
            idempotency_key=idempotency_key,
            original_request={"execution_event_id": candidate.id, "payload": payload},
            duplicate_request={"execution_event_id": event_row.id, "payload": event_payload},
            actor=str(current_admin.id),
            correlation_id=corr_id,
            status="open",
            created_at=datetime.now(timezone.utc),
        )
        db.add(collision)
        break

    _insert_trace_index(
        db,
        correlation_id=corr_id,
        stage="simulation_created",
        actor=str(current_admin.id),
        payload={
            "execution_event_id": event_row.id,
            "state_path": execution_result["state_path"],
            "source_type": normalized_source,
        },
        execution_event_id=event_row.id,
    )
    db.commit()

    create_audit_log(
        db,
        action="execution_state_simulated",
        entity_type="execution_event",
        entity_id=execution_result["execution_event"].id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy_type": strategy_type, "final_state": execution_result["final_state"]},
    )
    incr_counter(pipeline_runtime.cache, "metrics:state_transitions:5m", execution_result["transition_count"])

    return {
        "execution_event_id": execution_result["execution_event"].id,
        "final_state": execution_result["final_state"],
        "state_path": execution_result["state_path"],
        "retry_budget_used": execution_result.get("retry_budget_used", 0),
        "partial_fill_ratio": execution_result.get("partial_fill_ratio", 0),
        "source_type": normalized_source,
        "environment": environment,
        "correlation_id": corr_id,
    }


@router.post("/execution-state-transitions/simulate-batch", response_model=ExecutionSimulationBatchResponse)
def simulate_execution_state_flow_batch(
    payload: ExecutionSimulationBatchRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    records: list[dict] = []
    for scenario in payload.scenarios[:50]:
        result = simulate_execution_state_flow(
            current_admin=current_admin,
            db=db,
            strategy_type=str(scenario.get("strategy_type") or "breakout"),
            symbol=str(scenario.get("symbol") or "BTCUSDT"),
            side=str(scenario.get("side") or "long"),
            outcome=str(scenario.get("outcome") or "filled"),
            retry_budget=int(scenario.get("retry_budget") or 2),
            source_type=str(scenario.get("source_type") or "simulation"),
            environment=str(scenario.get("environment") or "simulation"),
            correlation_id=str(scenario.get("correlation_id") or f"sim_batch_{uuid.uuid4().hex[:12]}"),
        )
        records.append(result)

    return ExecutionSimulationBatchResponse(
        status="success",
        total=len(payload.scenarios[:50]),
        created=len(records),
        records=records,
    )
