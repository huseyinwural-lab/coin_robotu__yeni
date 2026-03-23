import json
import os
import uuid
import hashlib
import csv
import io
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import Text, cast, func, or_
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
    SystemAlert,
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
    ExecutionAnalyticsSnapshotSummaryResponse,
    IncidentSnapshotExportRequest,
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
    SystemAlertResponse,
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
from services.execution_alert_service import (
    trigger_execution_state_alert,
    trigger_idempotency_collision_alert,
    trigger_timeout_spike_alert,
)
from routers.admin_phase3_modules import alerts_router, analytics_router, export_router, recovery_router

router = APIRouter(prefix="/admin-phase3", tags=["admin_phase3"])

PROD_CONFIRMATION_PHRASE = "CONFIRM_PROD_MANUAL_ACTION"
STATE_ENUM = {
    "created",
    "submitted",
    "acknowledged",
    "partially_filled",
    "timeout",
    "fallback_submitted",
    "filled",
    "rejected",
    "failed",
    "cancelled",
}
STATUS_ENUM = {"filled", "timeout", "rejected", "failed", "cancelled", "submitted", "pending"}
SOURCE_TYPE_ENUM = {"production", "paper", "simulation", "replay"}


def _normalize_enum(value: str | None, allowed: set[str], field_name: str) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if normalized not in allowed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} geçersiz: {normalized}")
    return normalized


def _parse_iso_datetime(value: str | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} ISO format olmalı") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _extract_order_id_from_details(details: dict) -> str:
    if not isinstance(details, dict):
        return ""
    for key in ["order_id", "external_order_id", "execution_order_id"]:
        value = details.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _build_transition_query(
    db: Session,
    *,
    state: str | None = None,
    source_type: str | None = None,
    symbol: str | None = None,
    strategy: str | None = None,
    status_filter: str | None = None,
    correlation_id: str | None = None,
    order_id: str | None = None,
    search: str | None = None,
    time_from: datetime | None = None,
    time_to: datetime | None = None,
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
    if correlation_id:
        query = query.filter(ExecutionStateTransition.correlation_id == correlation_id)
    if time_from:
        query = query.filter(ExecutionStateTransition.occurred_at >= time_from)
    if time_to:
        query = query.filter(ExecutionStateTransition.occurred_at <= time_to)
    if order_id:
        query = query.filter(cast(ExecutionStateTransition.details, Text).ilike(f"%{order_id.strip()}%"))
    if search:
        token = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ExecutionStateTransition.execution_event_id.ilike(token),
                ExecutionStateTransition.correlation_id.ilike(token),
                ExecutionEvent.symbol.ilike(token),
                ExecutionEvent.strategy_id.ilike(token),
                cast(ExecutionStateTransition.details, Text).ilike(token),
                cast(ExecutionEvent.response_payload, Text).ilike(token),
            )
        )
    return query


def _serialize_failed_event_row(row: FailedEvent) -> dict:
    return {
        "id": row.id,
        "event_type": row.event_type,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "status": row.status,
        "failure_class": row.failure_class,
        "error_message": row.error_message,
        "correlation_id": row.correlation_id,
        "retry_count": row.retry_count,
        "max_retry": row.max_retry,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "dead_letter_reason": row.dead_letter_reason,
        "last_action_by": row.last_action_by,
        "retry_reason": row.retry_reason,
        "payload": row.payload or {},
        "error_details": row.error_details or {},
    }


def _rows_to_csv_text(rows: list[dict], columns: list[str]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in columns})
    return output.getvalue()


def _require_incident_export_scope(payload: IncidentSnapshotExportRequest) -> tuple[str, dict]:
    has_corr = bool(str(payload.correlation_id or "").strip())
    has_event = bool(str(payload.execution_event_id or "").strip())
    has_time = bool(str(payload.time_from or "").strip() or str(payload.time_to or "").strip())
    active_scopes = int(has_corr) + int(has_event) + int(has_time)
    if active_scopes == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="correlation_id veya execution_event_id veya time range zorunlu")
    if active_scopes > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tek scope kullanın: correlation_id veya execution_event_id veya time range",
        )

    if has_corr:
        return "correlation_id", {"correlation_id": str(payload.correlation_id).strip()}
    if has_event:
        return "execution_event_id", {"execution_event_id": str(payload.execution_event_id).strip()}

    time_from = _parse_iso_datetime(payload.time_from, "time_from")
    time_to = _parse_iso_datetime(payload.time_to, "time_to")
    if not time_from or not time_to:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="time range scope için time_from + time_to zorunlu")
    if time_from > time_to:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="time_from <= time_to olmalı")
    return "time_range", {"time_from": time_from.isoformat(), "time_to": time_to.isoformat()}


def _scope_signature(scope_type: str, scope_payload: dict) -> str:
    if scope_type == "correlation_id":
        return f"correlation_id:{str(scope_payload.get('correlation_id') or '').strip().lower()}"
    if scope_type == "execution_event_id":
        return f"execution_event_id:{str(scope_payload.get('execution_event_id') or '').strip().lower()}"
    return f"time_range:{str(scope_payload.get('time_from') or '').strip()}::{str(scope_payload.get('time_to') or '').strip()}"


def _is_same_scope(primary_scope_type: str, primary_scope_payload: dict, compare_scope_type: str, compare_scope_payload: dict) -> bool:
    return _scope_signature(primary_scope_type, primary_scope_payload) == _scope_signature(compare_scope_type, compare_scope_payload)


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
    status_value: str | None = Query(default=None, alias="status"),
    status_filter: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    order_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    limit: int = Query(default=300, ge=50, le=1000),
):
    normalized_state = _normalize_enum(state, STATE_ENUM, "state")
    normalized_source = _normalize_enum(source_type, SOURCE_TYPE_ENUM, "source_type")
    normalized_status = _normalize_enum(status_value or status_filter, STATUS_ENUM, "status")
    parsed_time_from = _parse_iso_datetime(time_from, "time_from")
    parsed_time_to = _parse_iso_datetime(time_to, "time_to")
    if parsed_time_from and parsed_time_to and parsed_time_from > parsed_time_to:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="time_from <= time_to olmalı")

    query = _build_transition_query(
        db,
        state=normalized_state,
        source_type=normalized_source,
        symbol=symbol,
        strategy=strategy,
        status_filter=normalized_status,
        correlation_id=str(correlation_id or "").strip() or None,
        order_id=str(order_id or "").strip() or None,
        search=search,
        time_from=parsed_time_from,
        time_to=parsed_time_to,
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


def _resolve_execution_analytics_filters(
    *,
    state: str | None,
    source_type: str | None,
    symbol: str | None,
    strategy: str | None,
    status_value: str | None,
    status_filter: str | None,
    correlation_id: str | None,
    order_id: str | None,
    search: str | None,
    time_from: str | None,
    time_to: str | None,
    snapshot_at: str | None,
) -> dict:
    normalized_state = _normalize_enum(state, STATE_ENUM, "state")
    normalized_source = _normalize_enum(source_type, SOURCE_TYPE_ENUM, "source_type")
    normalized_status = _normalize_enum(status_value or status_filter, STATUS_ENUM, "status")
    parsed_time_from = _parse_iso_datetime(time_from, "time_from")
    parsed_time_to = _parse_iso_datetime(time_to, "time_to")
    parsed_snapshot_at = _parse_iso_datetime(snapshot_at, "snapshot_at")

    if parsed_time_from and parsed_time_to and parsed_time_from > parsed_time_to:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="time_from <= time_to olmalı")

    effective_snapshot = parsed_snapshot_at or parsed_time_to or datetime.now(timezone.utc).replace(microsecond=0)
    return {
        "state": normalized_state,
        "source_type": normalized_source,
        "symbol": symbol,
        "strategy": strategy,
        "status": normalized_status,
        "correlation_id": correlation_id,
        "order_id": order_id,
        "search": search,
        "time_from": parsed_time_from,
        "time_to": effective_snapshot,
        "snapshot_at": effective_snapshot,
    }


def _requires_event_scope_filters(filters_ctx: dict) -> bool:
    return any(
        [
            filters_ctx["state"],
            filters_ctx["source_type"],
            filters_ctx["symbol"],
            filters_ctx["strategy"],
            filters_ctx["status"],
            filters_ctx["order_id"],
        ]
    )


def _serialize_execution_filter_context(filters_ctx: dict) -> dict:
    return {
        "state": filters_ctx["state"],
        "source_type": filters_ctx["source_type"],
        "symbol": filters_ctx["symbol"],
        "strategy": filters_ctx["strategy"],
        "status": filters_ctx["status"],
        "correlation_id": filters_ctx["correlation_id"],
        "order_id": filters_ctx["order_id"],
        "search": filters_ctx["search"],
        "time_from": filters_ctx["time_from"].isoformat() if filters_ctx["time_from"] else None,
        "time_to": filters_ctx["time_to"].isoformat(),
        "snapshot_at": filters_ctx["snapshot_at"].isoformat(),
    }


def _transition_rows_with_filters(
    db: Session,
    filters_ctx: dict,
    *,
    scope_type: str | None = None,
    scope_payload: dict | None = None,
) -> list[ExecutionStateTransition]:
    query = _build_transition_query(
        db,
        state=filters_ctx["state"],
        source_type=filters_ctx["source_type"],
        symbol=filters_ctx["symbol"],
        strategy=filters_ctx["strategy"],
        status_filter=filters_ctx["status"],
        correlation_id=str(filters_ctx["correlation_id"] or "").strip() or None,
        order_id=str(filters_ctx["order_id"] or "").strip() or None,
        search=filters_ctx["search"],
        time_from=filters_ctx["time_from"],
        time_to=filters_ctx["time_to"],
    )

    if scope_type == "correlation_id":
        query = query.filter(ExecutionStateTransition.correlation_id == scope_payload["correlation_id"])
    elif scope_type == "execution_event_id":
        query = query.filter(ExecutionStateTransition.execution_event_id == scope_payload["execution_event_id"])

    return query.order_by(ExecutionStateTransition.occurred_at.asc()).all()


def _failure_rows_with_filters(
    db: Session,
    filters_ctx: dict,
    transition_rows: list[ExecutionStateTransition],
    *,
    scope_type: str | None = None,
    scope_payload: dict | None = None,
    extra_correlations: set[str] | None = None,
) -> list[FailedEvent]:
    transition_correlations = {
        str(row.correlation_id) for row in transition_rows if str(row.correlation_id or "").strip()
    }
    scoped_correlations = set(transition_correlations)
    if extra_correlations:
        scoped_correlations.update({str(item) for item in extra_correlations if str(item or "").strip()})

    failure_query = db.query(FailedEvent).filter(FailedEvent.created_at <= filters_ctx["time_to"])
    if filters_ctx["time_from"]:
        failure_query = failure_query.filter(FailedEvent.created_at >= filters_ctx["time_from"])

    if scope_type == "correlation_id":
        failure_query = failure_query.filter(FailedEvent.correlation_id == scope_payload["correlation_id"])
    elif scope_type == "execution_event_id":
        if scoped_correlations:
            failure_query = failure_query.filter(FailedEvent.correlation_id.in_(sorted(scoped_correlations)))
        else:
            failure_query = failure_query.filter(FailedEvent.id == "")
    elif filters_ctx["correlation_id"]:
        failure_query = failure_query.filter(FailedEvent.correlation_id == filters_ctx["correlation_id"])

    if _requires_event_scope_filters(filters_ctx) and not filters_ctx["correlation_id"] and scope_type not in {"correlation_id", "execution_event_id"}:
        if scoped_correlations:
            failure_query = failure_query.filter(FailedEvent.correlation_id.in_(sorted(scoped_correlations)))
        else:
            failure_query = failure_query.filter(FailedEvent.id == "")

    if filters_ctx["search"]:
        token = f"%{str(filters_ctx['search']).strip()}%"
        failure_query = failure_query.filter(
            or_(
                FailedEvent.correlation_id.ilike(token),
                FailedEvent.entity_id.ilike(token),
                FailedEvent.error_message.ilike(token),
                cast(FailedEvent.payload, Text).ilike(token),
                cast(FailedEvent.error_details, Text).ilike(token),
            )
        )

    return failure_query.order_by(FailedEvent.created_at.asc()).all()


def _build_execution_analytics_summary(
    db: Session,
    *,
    state: str | None,
    source_type: str | None,
    symbol: str | None,
    strategy: str | None,
    status_value: str | None,
    status_filter: str | None,
    correlation_id: str | None,
    order_id: str | None,
    search: str | None,
    time_from: str | None,
    time_to: str | None,
    snapshot_at: str | None,
) -> ExecutionAnalyticsSnapshotSummaryResponse:
    filters_ctx = _resolve_execution_analytics_filters(
        state=state,
        source_type=source_type,
        symbol=symbol,
        strategy=strategy,
        status_value=status_value,
        status_filter=status_filter,
        correlation_id=correlation_id,
        order_id=order_id,
        search=search,
        time_from=time_from,
        time_to=time_to,
        snapshot_at=snapshot_at,
    )

    rows = _transition_rows_with_filters(db, filters_ctx)
    total = len(rows)
    state_counter = _state_counter(rows)
    latency_per_state: dict[str, float] = {}
    latency_state_counts: dict[str, int] = {}
    timeout_count = 0
    retry_count = 0
    fallback_count = 0
    failed_count = 0

    for row in rows:
        state_name = str(row.state or "")
        if row.latency_ms is not None:
            latency_per_state[state_name] = latency_per_state.get(state_name, 0.0) + float(row.latency_ms)
            latency_state_counts[state_name] = latency_state_counts.get(state_name, 0) + 1
        if state_name == "timeout":
            timeout_count += 1
        if state_name.startswith("retry_"):
            retry_count += 1
        if state_name == "fallback_submitted":
            fallback_count += 1
        if state_name in {"failed", "rejected"}:
            failed_count += 1

    for state_name, total_latency in list(latency_per_state.items()):
        count = max(latency_state_counts.get(state_name, 1), 1)
        latency_per_state[state_name] = round(total_latency / count, 4)

    failure_rows = _failure_rows_with_filters(db, filters_ctx, rows)

    dead_letter_trend: dict[str, int] = {}
    for row in failure_rows:
        if row.status not in {"dead", "quarantined"}:
            continue
        key = row.created_at.date().isoformat()
        dead_letter_trend[key] = dead_letter_trend.get(key, 0) + 1

    success_transitions = state_counter.get("filled", 0)
    retry_success_ratio = round(success_transitions / max(retry_count, 1), 4) if retry_count else 0.0

    applied_filters = _serialize_execution_filter_context(filters_ctx)

    return ExecutionAnalyticsSnapshotSummaryResponse(
        snapshot_at=filters_ctx["snapshot_at"],
        filters=applied_filters,
        totals={
            "transitions": total,
            "events": len({row.execution_event_id for row in rows}),
            "failures": len(failure_rows),
        },
        latency_per_state=latency_per_state,
        timeout_metrics={
            "timeout_count": timeout_count,
            "timeout_rate": round(timeout_count / max(total, 1), 4),
        },
        retry_metrics={
            "retry_count": retry_count,
            "retry_success_ratio": retry_success_ratio,
            "fallback_usage_rate": round(fallback_count / max(total, 1), 4),
        },
        failure_metrics={
            "failed_or_rejected_count": failed_count,
            "failure_rate": round(failed_count / max(total, 1), 4),
            "dead_letter_count": len([row for row in failure_rows if row.status in {"dead", "quarantined"}]),
        },
        dead_letter_trend=[
            {"date": key, "count": value}
            for key, value in sorted(dead_letter_trend.items())
        ],
    )


@router.get("/execution-analytics", response_model=ExecutionAnalyticsSnapshotSummaryResponse)
def execution_analytics_summary_legacy(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    state: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    strategy: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    status_filter: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    order_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    snapshot_at: str | None = Query(default=None),
):
    return _build_execution_analytics_summary(
        db,
        state=state,
        source_type=source_type,
        symbol=symbol,
        strategy=strategy,
        status_value=status_value,
        status_filter=status_filter,
        correlation_id=correlation_id,
        order_id=order_id,
        search=search,
        time_from=time_from,
        time_to=time_to,
        snapshot_at=snapshot_at,
    )


@router.get("/execution-analytics/summary", response_model=ExecutionAnalyticsSnapshotSummaryResponse)
def execution_analytics_summary(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    state: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    strategy: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    status_filter: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    order_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    snapshot_at: str | None = Query(default=None),
):
    return _build_execution_analytics_summary(
        db,
        state=state,
        source_type=source_type,
        symbol=symbol,
        strategy=strategy,
        status_value=status_value,
        status_filter=status_filter,
        correlation_id=correlation_id,
        order_id=order_id,
        search=search,
        time_from=time_from,
        time_to=time_to,
        snapshot_at=snapshot_at,
    )


@router.get("/execution-analytics/state-latency")
def execution_analytics_state_latency(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    state: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    strategy: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    status_filter: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    order_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    snapshot_at: str | None = Query(default=None),
):
    filters_ctx = _resolve_execution_analytics_filters(
        state=state,
        source_type=source_type,
        symbol=symbol,
        strategy=strategy,
        status_value=status_value,
        status_filter=status_filter,
        correlation_id=correlation_id,
        order_id=order_id,
        search=search,
        time_from=time_from,
        time_to=time_to,
        snapshot_at=snapshot_at,
    )

    rows = _transition_rows_with_filters(db, filters_ctx)

    stats: dict[str, dict] = {}
    for row in rows:
        if row.latency_ms is None:
            continue
        key = str(row.state or "unknown")
        bucket = stats.setdefault(
            key,
            {"state": key, "count": 0, "total_latency_ms": 0.0, "min_latency_ms": None, "max_latency_ms": None},
        )
        latency_value = float(row.latency_ms)
        bucket["count"] += 1
        bucket["total_latency_ms"] += latency_value
        bucket["min_latency_ms"] = latency_value if bucket["min_latency_ms"] is None else min(bucket["min_latency_ms"], latency_value)
        bucket["max_latency_ms"] = latency_value if bucket["max_latency_ms"] is None else max(bucket["max_latency_ms"], latency_value)

    result_rows: list[dict] = []
    for item in sorted(stats.values(), key=lambda x: x["state"]):
        count = max(item["count"], 1)
        result_rows.append(
            {
                "state": item["state"],
                "count": item["count"],
                "avg_latency_ms": round(item["total_latency_ms"] / count, 4),
                "min_latency_ms": item["min_latency_ms"],
                "max_latency_ms": item["max_latency_ms"],
            }
        )

    return {
        "snapshot_at": filters_ctx["snapshot_at"],
        "filters": _serialize_execution_filter_context(filters_ctx),
        "totals": {
            "transitions": len(rows),
            "states": len(result_rows),
        },
        "rows": result_rows,
    }


@router.get("/execution-analytics/failure-trends")
def execution_analytics_failure_trends(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    state: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    strategy: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    status_filter: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    order_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    snapshot_at: str | None = Query(default=None),
):
    filters_ctx = _resolve_execution_analytics_filters(
        state=state,
        source_type=source_type,
        symbol=symbol,
        strategy=strategy,
        status_value=status_value,
        status_filter=status_filter,
        correlation_id=correlation_id,
        order_id=order_id,
        search=search,
        time_from=time_from,
        time_to=time_to,
        snapshot_at=snapshot_at,
    )

    transition_rows = _transition_rows_with_filters(db, filters_ctx)
    failure_rows = _failure_rows_with_filters(db, filters_ctx, transition_rows)

    daily_counts: dict[str, dict] = {}
    failure_class_counter: dict[str, int] = {}
    for row in failure_rows:
        day_key = row.created_at.date().isoformat()
        daily = daily_counts.setdefault(
            day_key,
            {"date": day_key, "total_failures": 0, "dead_letter_count": 0, "resolved_count": 0, "open_count": 0},
        )
        daily["total_failures"] += 1
        if row.status in {"dead", "quarantined"}:
            daily["dead_letter_count"] += 1
        if row.status in {"resolved", "closed"}:
            daily["resolved_count"] += 1
        else:
            daily["open_count"] += 1
        cls = str(row.failure_class or "unknown")
        failure_class_counter[cls] = failure_class_counter.get(cls, 0) + 1

    top_failure_classes = [
        {"failure_class": key, "count": value}
        for key, value in sorted(failure_class_counter.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]

    return {
        "snapshot_at": filters_ctx["snapshot_at"],
        "filters": _serialize_execution_filter_context(filters_ctx),
        "totals": {
            "failures": len(failure_rows),
            "dead_letter_total": sum(item["dead_letter_count"] for item in daily_counts.values()),
            "resolved_total": sum(item["resolved_count"] for item in daily_counts.values()),
        },
        "daily_trend": [daily_counts[key] for key in sorted(daily_counts.keys())],
        "top_failure_classes": top_failure_classes,
    }


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


@router.get("/execution-alerts", response_model=list[SystemAlertResponse])
def list_execution_alerts(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    status_filter: str = Query(default="all", pattern="^(all|open|ack|resolved)$"),
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=50),
):
    query = db.query(SystemAlert).filter(SystemAlert.alert_type.ilike("execution_%"))
    if status_filter != "all":
        query = query.filter(SystemAlert.status == status_filter)
    if severity:
        query = query.filter(SystemAlert.severity == severity.upper())
    return query.order_by(SystemAlert.last_triggered_at.desc()).limit(limit).all()


@router.post("/execution-alerts/{alert_id}/ack", response_model=SystemAlertResponse)
def ack_execution_alert(alert_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.query(SystemAlert).filter(SystemAlert.id == alert_id, SystemAlert.alert_type.ilike("execution_%")).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert_not_found")
    row.status = "ack"
    row.updated_at = datetime.now(timezone.utc)
    details = dict(row.details or {})
    details["seen"] = True
    row.details = details
    db.commit()
    db.refresh(row)
    return row


@router.post("/execution-alerts/{alert_id}/seen", response_model=SystemAlertResponse)
def seen_execution_alert(alert_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.query(SystemAlert).filter(SystemAlert.id == alert_id, SystemAlert.alert_type.ilike("execution_%")).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert_not_found")
    details = dict(row.details or {})
    details["seen"] = True
    row.details = details
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def _build_incident_snapshot_scope_bundle(
    db: Session,
    payload: IncidentSnapshotExportRequest,
    *,
    scope_type: str,
    scope_payload: dict,
) -> dict:
    filters_ctx = _resolve_execution_analytics_filters(
        state=payload.state,
        source_type=payload.source_type,
        symbol=payload.symbol,
        strategy=payload.strategy,
        status_value=payload.status,
        status_filter=None,
        correlation_id=payload.correlation_id,
        order_id=payload.order_id,
        search=payload.search,
        time_from=payload.time_from,
        time_to=payload.time_to,
        snapshot_at=None,
    )

    transition_rows = _transition_rows_with_filters(
        db,
        filters_ctx,
        scope_type=scope_type,
        scope_payload=scope_payload,
    )
    transition_event_ids = {str(row.execution_event_id) for row in transition_rows if str(row.execution_event_id or "").strip()}
    transition_correlations = {str(row.correlation_id) for row in transition_rows if str(row.correlation_id or "").strip()}

    event_query = db.query(ExecutionEvent)
    if scope_type == "correlation_id":
        event_query = event_query.filter(ExecutionEvent.correlation_id == scope_payload["correlation_id"])
    elif scope_type == "execution_event_id":
        event_query = event_query.filter(ExecutionEvent.id == scope_payload["execution_event_id"])
    elif filters_ctx["time_from"]:
        event_query = event_query.filter(ExecutionEvent.created_at >= filters_ctx["time_from"])
    event_query = event_query.filter(ExecutionEvent.created_at <= filters_ctx["time_to"])

    if filters_ctx["source_type"]:
        event_query = event_query.filter(ExecutionEvent.source_type == filters_ctx["source_type"])
    if filters_ctx["symbol"]:
        event_query = event_query.filter(ExecutionEvent.symbol == str(filters_ctx["symbol"]).upper())
    if filters_ctx["strategy"]:
        event_query = event_query.filter(ExecutionEvent.strategy_id == filters_ctx["strategy"])
    if filters_ctx["status"]:
        event_query = event_query.filter(ExecutionEvent.execution_status == filters_ctx["status"])
    if filters_ctx["order_id"]:
        token = f"%{str(filters_ctx['order_id']).strip()}%"
        event_query = event_query.filter(cast(ExecutionEvent.response_payload, Text).ilike(token))
    if filters_ctx["search"]:
        token = f"%{str(filters_ctx['search']).strip()}%"
        event_query = event_query.filter(
            or_(
                ExecutionEvent.id.ilike(token),
                ExecutionEvent.correlation_id.ilike(token),
                ExecutionEvent.symbol.ilike(token),
                ExecutionEvent.strategy_id.ilike(token),
                cast(ExecutionEvent.response_payload, Text).ilike(token),
            )
        )
    if filters_ctx["state"]:
        if transition_event_ids:
            event_query = event_query.filter(ExecutionEvent.id.in_(sorted(transition_event_ids)))
        else:
            event_query = event_query.filter(ExecutionEvent.id == "")

    event_rows = event_query.order_by(ExecutionEvent.created_at.asc()).all()
    scoped_event_ids = set(transition_event_ids)
    scoped_event_ids.update({str(row.id) for row in event_rows if str(row.id or "").strip()})
    scoped_correlations = set(transition_correlations)
    scoped_correlations.update({str(row.correlation_id) for row in event_rows if str(row.correlation_id or "").strip()})

    failure_rows = _failure_rows_with_filters(
        db,
        filters_ctx,
        transition_rows,
        scope_type=scope_type,
        scope_payload=scope_payload,
        extra_correlations=scoped_correlations,
    )

    manual_query = db.query(ExecutionManualAction).filter(ExecutionManualAction.created_at <= filters_ctx["time_to"])
    if scope_type == "correlation_id":
        manual_query = manual_query.filter(ExecutionManualAction.correlation_id == scope_payload["correlation_id"])
    elif scope_type == "execution_event_id":
        manual_query = manual_query.filter(ExecutionManualAction.execution_event_id == scope_payload["execution_event_id"])
    elif filters_ctx["time_from"]:
        manual_query = manual_query.filter(ExecutionManualAction.created_at >= filters_ctx["time_from"])

    if _requires_event_scope_filters(filters_ctx):
        if scoped_event_ids:
            manual_query = manual_query.filter(ExecutionManualAction.execution_event_id.in_(sorted(scoped_event_ids)))
        elif scoped_correlations:
            manual_query = manual_query.filter(ExecutionManualAction.correlation_id.in_(sorted(scoped_correlations)))
        else:
            manual_query = manual_query.filter(ExecutionManualAction.action_id == "")

    if filters_ctx["search"]:
        token = f"%{str(filters_ctx['search']).strip()}%"
        manual_query = manual_query.filter(
            or_(
                ExecutionManualAction.execution_event_id.ilike(token),
                ExecutionManualAction.correlation_id.ilike(token),
                ExecutionManualAction.reason_note.ilike(token),
                cast(ExecutionManualAction.details, Text).ilike(token),
            )
        )
    if filters_ctx["order_id"]:
        token = f"%{str(filters_ctx['order_id']).strip()}%"
        manual_query = manual_query.filter(cast(ExecutionManualAction.details, Text).ilike(token))
    manual_rows = manual_query.order_by(ExecutionManualAction.created_at.asc()).all()

    collision_query = db.query(IdempotencyCollision).filter(IdempotencyCollision.created_at <= filters_ctx["time_to"])
    if scope_type == "correlation_id":
        collision_query = collision_query.filter(IdempotencyCollision.correlation_id == scope_payload["correlation_id"])
    elif scope_type == "execution_event_id":
        if scoped_correlations:
            collision_query = collision_query.filter(IdempotencyCollision.correlation_id.in_(sorted(scoped_correlations)))
        else:
            collision_query = collision_query.filter(IdempotencyCollision.collision_id == "")
    elif filters_ctx["time_from"]:
        collision_query = collision_query.filter(IdempotencyCollision.created_at >= filters_ctx["time_from"])

    if _requires_event_scope_filters(filters_ctx) and scope_type not in {"correlation_id", "execution_event_id"}:
        if scoped_correlations:
            collision_query = collision_query.filter(IdempotencyCollision.correlation_id.in_(sorted(scoped_correlations)))
        else:
            collision_query = collision_query.filter(IdempotencyCollision.collision_id == "")

    if filters_ctx["search"]:
        token = f"%{str(filters_ctx['search']).strip()}%"
        collision_query = collision_query.filter(
            or_(
                IdempotencyCollision.correlation_id.ilike(token),
                IdempotencyCollision.intent_id.ilike(token),
                IdempotencyCollision.idempotency_key.ilike(token),
                cast(IdempotencyCollision.original_request, Text).ilike(token),
                cast(IdempotencyCollision.duplicate_request, Text).ilike(token),
            )
        )
    if filters_ctx["order_id"]:
        token = f"%{str(filters_ctx['order_id']).strip()}%"
        collision_query = collision_query.filter(
            or_(
                cast(IdempotencyCollision.original_request, Text).ilike(token),
                cast(IdempotencyCollision.duplicate_request, Text).ilike(token),
            )
        )
    collision_rows = collision_query.order_by(IdempotencyCollision.created_at.asc()).all()

    trace_query = db.query(ExecutionTraceIndex).filter(ExecutionTraceIndex.created_at <= filters_ctx["time_to"])
    if scope_type == "correlation_id":
        trace_query = trace_query.filter(ExecutionTraceIndex.correlation_id == scope_payload["correlation_id"])
    elif scope_type == "execution_event_id":
        trace_query = trace_query.filter(ExecutionTraceIndex.execution_event_id == scope_payload["execution_event_id"])
    elif filters_ctx["time_from"]:
        trace_query = trace_query.filter(ExecutionTraceIndex.created_at >= filters_ctx["time_from"])

    if _requires_event_scope_filters(filters_ctx):
        if scoped_event_ids and scoped_correlations:
            trace_query = trace_query.filter(
                or_(
                    ExecutionTraceIndex.execution_event_id.in_(sorted(scoped_event_ids)),
                    ExecutionTraceIndex.correlation_id.in_(sorted(scoped_correlations)),
                )
            )
        elif scoped_event_ids:
            trace_query = trace_query.filter(ExecutionTraceIndex.execution_event_id.in_(sorted(scoped_event_ids)))
        elif scoped_correlations:
            trace_query = trace_query.filter(ExecutionTraceIndex.correlation_id.in_(sorted(scoped_correlations)))
        else:
            trace_query = trace_query.filter(ExecutionTraceIndex.trace_id == "")

    if filters_ctx["search"]:
        token = f"%{str(filters_ctx['search']).strip()}%"
        trace_query = trace_query.filter(
            or_(
                ExecutionTraceIndex.correlation_id.ilike(token),
                ExecutionTraceIndex.execution_event_id.ilike(token),
                ExecutionTraceIndex.intent_id.ilike(token),
                ExecutionTraceIndex.stage.ilike(token),
                cast(ExecutionTraceIndex.payload, Text).ilike(token),
            )
        )
    if filters_ctx["order_id"]:
        token = f"%{str(filters_ctx['order_id']).strip()}%"
        trace_query = trace_query.filter(cast(ExecutionTraceIndex.payload, Text).ilike(token))
    trace_rows = trace_query.order_by(ExecutionTraceIndex.created_at.asc()).all()

    serialized_events = [_serialize_execution_event(row) for row in event_rows]
    serialized_transitions = [_serialize_transition(row) for row in transition_rows]
    serialized_failures = [_serialize_failed_event_row(row) for row in failure_rows]
    serialized_manual = [
        {
            "action_id": row.action_id,
            "execution_event_id": row.execution_event_id,
            "correlation_id": row.correlation_id,
            "action_type": row.action_type,
            "requested_by": row.requested_by,
            "requested_role": row.requested_role,
            "reason_note": row.reason_note,
            "is_prod_guard_applied": row.is_prod_guard_applied,
            "idempotency_checked": row.idempotency_checked,
            "replay_safe_checked": row.replay_safe_checked,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "details": row.details or {},
        }
        for row in manual_rows
    ]
    serialized_collisions = [
        {
            "collision_id": row.collision_id,
            "intent_id": row.intent_id,
            "idempotency_key": row.idempotency_key,
            "actor": row.actor,
            "correlation_id": row.correlation_id,
            "status": row.status,
            "resolution_action": row.resolution_action,
            "resolution_note": row.resolution_note,
            "resolved_by": row.resolved_by,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in collision_rows
    ]
    serialized_trace = [
        {
            "trace_id": row.trace_id,
            "correlation_id": row.correlation_id,
            "execution_event_id": row.execution_event_id,
            "intent_id": row.intent_id,
            "stage": row.stage,
            "actor": row.actor,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "payload": row.payload or {},
        }
        for row in trace_rows
    ]

    row_counts = {
        "events": len(serialized_events),
        "transitions": len(serialized_transitions),
        "failed_events": len(serialized_failures),
        "manual_actions": len(serialized_manual),
        "idempotency_collisions": len(serialized_collisions),
        "trace": len(serialized_trace),
    }

    return {
        "filters_ctx": filters_ctx,
        "scope_type": scope_type,
        "scope_payload": scope_payload,
        "events": serialized_events,
        "transitions": serialized_transitions,
        "failures": serialized_failures,
        "manual_actions": serialized_manual,
        "idempotency_collisions": serialized_collisions,
        "trace": serialized_trace,
        "row_counts": row_counts,
    }


def _build_snapshot_diff_payload(
    *,
    scope_a_type: str,
    scope_a_payload: dict,
    scope_a_bundle: dict,
    scope_b_type: str,
    scope_b_payload: dict,
    scope_b_bundle: dict,
) -> tuple[dict, str]:
    a_counts = scope_a_bundle["row_counts"]
    b_counts = scope_b_bundle["row_counts"]

    dead_letter_a = sum(1 for row in scope_a_bundle["failures"] if str(row.get("status", "")).lower() in {"dead", "quarantined"})
    dead_letter_b = sum(1 for row in scope_b_bundle["failures"] if str(row.get("status", "")).lower() in {"dead", "quarantined"})

    def _pct_change(current_value: int, compare_value: int) -> int:
        if compare_value == 0:
            return 100 if current_value > 0 else 0
        return int(round(((current_value - compare_value) / compare_value) * 100))

    counts = {
        "events_delta": a_counts["events"] - b_counts["events"],
        "transitions_delta": a_counts["transitions"] - b_counts["transitions"],
        "failed_events_delta": a_counts["failed_events"] - b_counts["failed_events"],
        "dead_letter_delta": dead_letter_a - dead_letter_b,
        "manual_actions_delta": a_counts["manual_actions"] - b_counts["manual_actions"],
        "idempotency_collisions_delta": a_counts["idempotency_collisions"] - b_counts["idempotency_collisions"],
    }

    percentage_change = {
        "events": _pct_change(a_counts["events"], b_counts["events"]),
        "failed_events": _pct_change(a_counts["failed_events"], b_counts["failed_events"]),
        "dead_letter": _pct_change(dead_letter_a, dead_letter_b),
        "manual_actions": _pct_change(a_counts["manual_actions"], b_counts["manual_actions"]),
    }

    before_after = {
        "events": {
            "before": b_counts["events"],
            "after": a_counts["events"],
            "delta": counts["events_delta"],
            "percentage": percentage_change["events"],
        },
        "failed_events": {
            "before": b_counts["failed_events"],
            "after": a_counts["failed_events"],
            "delta": counts["failed_events_delta"],
            "percentage": percentage_change["failed_events"],
        },
        "dead_letter": {
            "before": dead_letter_b,
            "after": dead_letter_a,
            "delta": counts["dead_letter_delta"],
            "percentage": percentage_change["dead_letter"],
        },
        "manual_actions": {
            "before": b_counts["manual_actions"],
            "after": a_counts["manual_actions"],
            "delta": counts["manual_actions_delta"],
            "percentage": percentage_change["manual_actions"],
        },
    }

    anomaly_notes: list[str] = []
    recommended_actions: list[dict] = []

    def _add_action(action: str, severity: str, reason: str) -> None:
        recommended_actions.append(
            {
                "action": action,
                "severity": severity,
                "reason": reason,
            }
        )

    def _format_reason(label: str, before_value: int, after_value: int, pct_value: int) -> str:
        if after_value > before_value:
            direction = "increased"
        elif after_value < before_value:
            direction = "decreased"
        else:
            direction = "unchanged"
        if direction == "unchanged":
            return f"{label} unchanged ({before_value} → {after_value})"
        return f"{label} {direction} {abs(pct_value)}% ({before_value} → {after_value})"

    if counts["failed_events_delta"] > 0 and percentage_change["failed_events"] > 50:
        anomaly_notes.append(f"FAILED_EVENTS increased by {percentage_change['failed_events']}% (CRITICAL_RISK)")
        _add_action(
            "retry_policy_tune",
            "critical",
            _format_reason("Failures", b_counts["failed_events"], a_counts["failed_events"], percentage_change["failed_events"]),
        )
    elif counts["failed_events_delta"] < 0:
        anomaly_notes.append("FAILED_EVENTS decreased (IMPROVED)")

    if counts["dead_letter_delta"] > 0 and percentage_change["dead_letter"] > 30:
        anomaly_notes.append(f"DEAD_LETTER increased by {percentage_change['dead_letter']}% (HIGH_RISK)")
        _add_action(
            "guardrail_hardening",
            "warning",
            _format_reason("Dead letter", dead_letter_b, dead_letter_a, percentage_change["dead_letter"]),
        )
    elif counts["dead_letter_delta"] < 0:
        anomaly_notes.append("DEAD_LETTER decreased (IMPROVED)")

    if counts["manual_actions_delta"] > 0:
        anomaly_notes.append("OPERATOR_INTERVENTION increased")
        _add_action(
            "runbook_review",
            "warning",
            _format_reason("Manual actions", b_counts["manual_actions"], a_counts["manual_actions"], percentage_change["manual_actions"]),
        )
    elif counts["manual_actions_delta"] < 0:
        anomaly_notes.append("MANUAL_ACTIONS decreased (REDUCED)")

    if counts["idempotency_collisions_delta"] > 0:
        _add_action(
            "guardrail_hardening",
            "warning",
            f"Idempotency collisions increased {counts['idempotency_collisions_delta']} ({b_counts['idempotency_collisions']} → {a_counts['idempotency_collisions']})",
        )

    if counts["failed_events_delta"] < 0 or counts["dead_letter_delta"] < 0 or counts["manual_actions_delta"] < 0:
        _add_action(
            "keep_current_policy",
            "info",
            _format_reason("Failures", b_counts["failed_events"], a_counts["failed_events"], percentage_change["failed_events"]),
        )

    if not recommended_actions:
        _add_action("keep_current_policy", "info", _format_reason("Failures", b_counts["failed_events"], a_counts["failed_events"], percentage_change["failed_events"]))

    diff_payload = {
        "scope_a": {
            "filter_scope": scope_a_type,
            "scope_identifiers": scope_a_payload,
            "row_counts": a_counts,
        },
        "scope_b": {
            "filter_scope": scope_b_type,
            "scope_identifiers": scope_b_payload,
            "row_counts": b_counts,
        },
        "counts": counts,
        "percentage_change": percentage_change,
        "before_after": before_after,
        "anomaly_notes": anomaly_notes,
        "recommended_actions": recommended_actions,
    }

    summary_lines = [
        "Snapshot Diff Summary",
        f"- FAILED EVENTS: {percentage_change['failed_events']}% ({'↑' if counts['failed_events_delta'] > 0 else '↓' if counts['failed_events_delta'] < 0 else '='})",
        f"- DEAD LETTER: {percentage_change['dead_letter']}% ({'↑' if counts['dead_letter_delta'] > 0 else '↓' if counts['dead_letter_delta'] < 0 else '='})",
        f"- MANUAL ACTIONS: {counts['manual_actions_delta']} ({'↑' if counts['manual_actions_delta'] > 0 else '↓' if counts['manual_actions_delta'] < 0 else '='})",
        "Anomaly Notes",
    ]
    if anomaly_notes:
        summary_lines.extend([f"- {note}" for note in anomaly_notes])
    else:
        summary_lines.append("- none")

    summary_lines.append("Recommended Actions")
    for item in recommended_actions:
        summary_lines.append(f"- [{item['severity']}] {item['action']} ({item['reason']})")
    return diff_payload, "\n".join(summary_lines) + "\n"


@router.post("/incident-snapshots/export")
def export_incident_snapshot_bundle(
    payload: IncidentSnapshotExportRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope_type, scope_payload = _require_incident_export_scope(payload)
    primary_bundle = _build_incident_snapshot_scope_bundle(
        db,
        payload,
        scope_type=scope_type,
        scope_payload=scope_payload,
    )
    filters_ctx = primary_bundle["filters_ctx"]
    serialized_events = primary_bundle["events"]
    serialized_transitions = primary_bundle["transitions"]
    serialized_failures = primary_bundle["failures"]
    serialized_manual = primary_bundle["manual_actions"]
    serialized_collisions = primary_bundle["idempotency_collisions"]
    serialized_trace = primary_bundle["trace"]

    compare_bundle = None
    compare_scope_payload = None
    compare_scope_type = None
    compare_fields_present = any(
        [
            payload.compare_correlation_id,
            payload.compare_execution_event_id,
            payload.compare_time_from,
            payload.compare_time_to,
        ]
    )
    compare_enabled = bool(payload.compare_enabled or compare_fields_present)
    if payload.compare_enabled and not compare_fields_present:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="compare scope is required when compare is enabled")

    if compare_enabled:
        compare_request = IncidentSnapshotExportRequest(
            correlation_id=payload.compare_correlation_id,
            execution_event_id=payload.compare_execution_event_id,
            time_from=payload.compare_time_from,
            time_to=payload.compare_time_to,
            compare_enabled=False,
            search=payload.search,
            state=payload.state,
            status=payload.status,
            source_type=payload.source_type,
            symbol=payload.symbol,
            strategy=payload.strategy,
            order_id=payload.order_id,
        )
        compare_scope_type, compare_scope_payload = _require_incident_export_scope(compare_request)
        if _is_same_scope(scope_type, scope_payload, compare_scope_type, compare_scope_payload):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Primary and compare snapshots cannot be identical",
            )
        compare_bundle = _build_incident_snapshot_scope_bundle(
            db,
            compare_request,
            scope_type=compare_scope_type,
            scope_payload=compare_scope_payload,
        )

    generated_files = [
        "summary.json",
        "trace.json",
        "events.csv",
        "transitions.csv",
        "failed_events.csv",
        "manual_actions.csv",
        "idempotency_collisions.csv",
        "README.txt",
    ]
    diff_json = None
    diff_summary_text = None
    if compare_bundle is not None:
        generated_files.extend(["diff.json", "diff_summary.txt"])
        diff_json, diff_summary_text = _build_snapshot_diff_payload(
            scope_a_type=scope_type,
            scope_a_payload=scope_payload,
            scope_a_bundle=primary_bundle,
            scope_b_type=compare_scope_type,
            scope_b_payload=compare_scope_payload,
            scope_b_bundle=compare_bundle,
        )

    metadata = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "actor": str(current_admin.id),
        "filter_scope": scope_type,
        "selected_scope_priority": scope_type,
        "scope_priority_order": ["correlation_id", "execution_event_id", "time_range"],
        "scope_identifiers": scope_payload,
        "row_counts": {
            "events": primary_bundle["row_counts"]["events"],
            "transitions": primary_bundle["row_counts"]["transitions"],
            "failed_events": primary_bundle["row_counts"]["failed_events"],
            "manual_actions": primary_bundle["row_counts"]["manual_actions"],
            "idempotency_collisions": primary_bundle["row_counts"]["idempotency_collisions"],
            "trace": primary_bundle["row_counts"]["trace"],
        },
        "generated_files": generated_files,
    }
    if compare_bundle is not None:
        metadata["compare_scope"] = {
            "filter_scope": compare_scope_type,
            "scope_identifiers": compare_scope_payload,
            "row_counts": compare_bundle["row_counts"],
        }
    summary_json = {
        **metadata,
        "filters": _serialize_execution_filter_context(filters_ctx),
    }

    events_csv = _rows_to_csv_text(
        serialized_events,
        ["id", "symbol", "side", "execution_status", "source_type", "environment", "correlation_id", "strategy_id", "created_at"],
    )
    transitions_csv = _rows_to_csv_text(
        serialized_transitions,
        ["id", "execution_event_id", "state", "from_state", "to_state", "sequence", "latency_ms", "correlation_id", "source_type", "environment", "is_manual", "occurred_at"],
    )
    failed_csv = _rows_to_csv_text(
        serialized_failures,
        ["id", "event_type", "entity_type", "entity_id", "status", "failure_class", "correlation_id", "retry_count", "max_retry", "dead_letter_reason", "created_at", "updated_at"],
    )
    manual_csv = _rows_to_csv_text(
        serialized_manual,
        ["action_id", "execution_event_id", "correlation_id", "action_type", "requested_by", "requested_role", "reason_note", "is_prod_guard_applied", "idempotency_checked", "replay_safe_checked", "created_at"],
    )
    collisions_csv = _rows_to_csv_text(
        serialized_collisions,
        ["collision_id", "intent_id", "idempotency_key", "actor", "correlation_id", "status", "resolution_action", "resolved_by", "resolved_at", "created_at"],
    )

    readme_text = (
        "Incident Snapshot Bundle\n"
        "- summary.json: export metadata + filter scope\n"
        "- trace.json: correlation trace timeline\n"
        "- events.csv: execution events\n"
        "- transitions.csv: state transitions\n"
        "- failed_events.csv: failure and dead-letter rows\n"
        "- manual_actions.csv: manual intervention records\n"
        "- idempotency_collisions.csv: collision records\n"
    )
    if compare_bundle is not None:
        readme_text += "- diff.json: two snapshot count delta + scope comparison\n"
        readme_text += "- diff_summary.txt: operational human-readable summary\n"

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("summary.json", json.dumps(summary_json, ensure_ascii=False, indent=2))
        bundle.writestr("trace.json", json.dumps(serialized_trace, ensure_ascii=False, indent=2))
        bundle.writestr("events.csv", events_csv)
        bundle.writestr("transitions.csv", transitions_csv)
        bundle.writestr("failed_events.csv", failed_csv)
        bundle.writestr("manual_actions.csv", manual_csv)
        bundle.writestr("idempotency_collisions.csv", collisions_csv)
        bundle.writestr("README.txt", readme_text)
        if diff_json is not None and diff_summary_text is not None:
            bundle.writestr("diff.json", json.dumps(diff_json, ensure_ascii=False, indent=2))
            bundle.writestr("diff_summary.txt", diff_summary_text)

    filename = f"incident_snapshot_{scope_type}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"
    create_audit_log(
        db,
        action="incident_snapshot_export",
        entity_type="execution_incident_snapshot",
        entity_id=scope_payload.get("correlation_id") or scope_payload.get("execution_event_id") or "time_range",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details=summary_json,
    )
    db.commit()

    return Response(
        content=archive.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Incident-Snapshot-Scope": scope_type,
            "X-Incident-Snapshot-Scope-Selected": scope_type,
        },
    )


@router.post("/incident-snapshots/diff")
def incident_snapshot_diff_preview(
    payload: IncidentSnapshotExportRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope_type, scope_payload = _require_incident_export_scope(payload)
    primary_bundle = _build_incident_snapshot_scope_bundle(
        db,
        payload,
        scope_type=scope_type,
        scope_payload=scope_payload,
    )

    compare_fields_present = any(
        [
            payload.compare_correlation_id,
            payload.compare_execution_event_id,
            payload.compare_time_from,
            payload.compare_time_to,
        ]
    )
    compare_enabled = bool(payload.compare_enabled or compare_fields_present)
    if payload.compare_enabled and not compare_fields_present:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="compare scope is required when compare is enabled")

    diff_payload = None
    diff_summary = ""
    compare_scope_payload = None
    compare_scope_type = None

    if compare_enabled:
        compare_request = IncidentSnapshotExportRequest(
            correlation_id=payload.compare_correlation_id,
            execution_event_id=payload.compare_execution_event_id,
            time_from=payload.compare_time_from,
            time_to=payload.compare_time_to,
            compare_enabled=False,
            search=payload.search,
            state=payload.state,
            status=payload.status,
            source_type=payload.source_type,
            symbol=payload.symbol,
            strategy=payload.strategy,
            order_id=payload.order_id,
        )
        compare_scope_type, compare_scope_payload = _require_incident_export_scope(compare_request)
        if _is_same_scope(scope_type, scope_payload, compare_scope_type, compare_scope_payload):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Primary and compare snapshots cannot be identical",
            )

        compare_bundle = _build_incident_snapshot_scope_bundle(
            db,
            compare_request,
            scope_type=compare_scope_type,
            scope_payload=compare_scope_payload,
        )
        diff_payload, diff_summary = _build_snapshot_diff_payload(
            scope_a_type=scope_type,
            scope_a_payload=scope_payload,
            scope_a_bundle=primary_bundle,
            scope_b_type=compare_scope_type,
            scope_b_payload=compare_scope_payload,
            scope_b_bundle=compare_bundle,
        )

    trace_id = str(uuid.uuid4())
    state_snapshot = {
        "compare_enabled": compare_enabled,
        "scope_a": {"filter_scope": scope_type, "scope_identifiers": scope_payload},
        "scope_b": {"filter_scope": compare_scope_type, "scope_identifiers": compare_scope_payload} if compare_enabled else None,
        "preview": {
            "events": primary_bundle["row_counts"]["events"],
            "failures": primary_bundle["row_counts"]["failed_events"],
            "transitions": primary_bundle["row_counts"]["transitions"],
        },
        "diff": diff_payload,
        "diff_summary": diff_summary,
    }

    create_audit_log(
        db,
        action="incident_snapshot_diff_preview",
        entity_type="execution_incident_snapshot",
        entity_id=scope_payload.get("correlation_id") or scope_payload.get("execution_event_id") or trace_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "trace_id": trace_id,
            "scope": scope_payload,
            "compare_scope": compare_scope_payload,
            "preview": state_snapshot["preview"],
        },
    )
    db.commit()

    return {
        "status": "success",
        "trace_id": trace_id,
        "message": "incident snapshot diff generated",
        "state_snapshot": state_snapshot,
    }


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

    created_collision: IdempotencyCollision | None = None

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
        created_collision = collision
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

    try:
        trigger_execution_state_alert(
            db,
            final_state=execution_result["final_state"],
            correlation_id=corr_id,
            execution_event_id=event_row.id,
            symbol=symbol.upper(),
        )
        if "timeout" in [str(item).lower() for item in execution_result.get("state_path", [])]:
            trigger_timeout_spike_alert(
                db,
                symbol=symbol.upper(),
                correlation_id=corr_id,
                execution_event_id=event_row.id,
            )
        if created_collision is not None:
            trigger_idempotency_collision_alert(db, created_collision)
    except Exception:
        pass

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


router.include_router(analytics_router)
router.include_router(export_router)
router.include_router(recovery_router)
router.include_router(alerts_router)
