from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import ExecutionIntent, ExecutionIntentEvent, FailedEvent
from services.audit_service import create_audit_log
from services.runtime_event_bus_service import publish_runtime_event, remove_quarantine_event, requeue_runtime_event


TERMINAL_STATES = {"filled", "canceled", "cancelled", "rejected", "expired"}


def list_quarantined_events(db: Session) -> list[FailedEvent]:
    return (
        db.query(FailedEvent)
        .filter(FailedEvent.entity_type == "runtime_event", FailedEvent.status.in_(["quarantined", "dead"]))
        .order_by(FailedEvent.updated_at.desc())
        .all()
    )


def replay_quarantined_event(db: Session, failed_event: FailedEvent) -> FailedEvent:
    envelope = (failed_event.payload or {}).get("envelope") or {}
    if envelope:
        requeue_runtime_event(envelope)
    failed_event.status = "retrying"
    failed_event.retry_count = 0
    failed_event.next_retry_at = None
    failed_event.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(failed_event)
    remove_quarantine_event(failed_event.entity_id)
    return failed_event


def dismiss_quarantined_event(db: Session, failed_event: FailedEvent) -> FailedEvent:
    failed_event.status = "resolved"
    failed_event.resolved_at = datetime.now(timezone.utc)
    failed_event.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(failed_event)
    remove_quarantine_event(failed_event.entity_id)
    return failed_event


def mark_quarantined_failed(db: Session, failed_event: FailedEvent) -> FailedEvent:
    failed_event.status = "dead"
    failed_event.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(failed_event)
    return failed_event


def _latest_intent_event(db: Session, intent_id: str) -> ExecutionIntentEvent | None:
    return (
        db.query(ExecutionIntentEvent)
        .filter(ExecutionIntentEvent.intent_id == intent_id)
        .order_by(ExecutionIntentEvent.created_at.desc())
        .first()
    )


def list_stuck_intents(
    db: Session,
    *,
    pending_threshold: int = 60,
    submitted_threshold: int = 120,
    partial_threshold: int = 300,
) -> list[dict]:
    now = datetime.now(timezone.utc)
    results: list[dict] = []
    intents = db.query(ExecutionIntent).order_by(ExecutionIntent.created_at.desc()).limit(200).all()

    for intent in intents:
        latest = _latest_intent_event(db, intent.intent_id)
        status = latest.event_status if latest else intent.status or "pending"
        last_event_at = latest.created_at if latest else intent.created_at
        if last_event_at and last_event_at.tzinfo is None:
            last_event_at = last_event_at.replace(tzinfo=timezone.utc)
        age_seconds = (now - last_event_at).total_seconds()
        reason = None

        if status == "pending" and age_seconds > pending_threshold:
            reason = "pending_timeout"
        elif status == "submitted" and age_seconds > submitted_threshold:
            reason = "submitted_timeout"
        elif status in {"partially_filled", "partial_fill"} and age_seconds > partial_threshold:
            reason = "partial_fill_timeout"

        if reason:
            results.append(
                {
                    "intent_id": intent.intent_id,
                    "strategy_id": intent.strategy_id,
                    "symbol": intent.symbol,
                    "status": status,
                    "age_seconds": age_seconds,
                    "last_event_at": last_event_at,
                    "reason": reason,
                }
            )

    return results


def _has_terminal_event(db: Session, intent_id: str) -> bool:
    return (
        db.query(ExecutionIntentEvent)
        .filter(
            ExecutionIntentEvent.intent_id == intent_id,
            ExecutionIntentEvent.event_type == "execution.order.finalized",
        )
        .first()
        is not None
    )


def perform_recovery_action(
    db: Session,
    *,
    intent_id: str,
    action: str,
    actor_user_id: str,
    actor_role: str,
) -> dict:
    intent = db.query(ExecutionIntent).filter(ExecutionIntent.intent_id == intent_id).first()
    if intent is None:
        raise ValueError("intent_not_found")
    if _has_terminal_event(db, intent_id):
        raise ValueError("intent_terminal")

    action = action.lower()

    if action == "sync_exchange_state":
        publish_runtime_event(
            event_type="execution.intent.resync",
            payload={"intent_id": intent_id, "symbol": intent.symbol},
            correlation_id=intent.correlation_id,
            causation_id=intent_id,
            partition_key=f"{intent.symbol}::{intent.strategy_id}",
        )
        create_audit_log(
            db,
            action="intent_resync_requested",
            entity_type="execution_intent",
            entity_id=intent_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            severity="warning",
            details={"intent_id": intent_id},
        )
        return {"status": "resync_queued", "intent_id": intent_id}

    if action == "replay_event_chain":
        publish_runtime_event(
            event_type="execution.order.submission_requested",
            payload={"intent_id": intent_id, "intent_hash": intent.intent_hash, "symbol": intent.symbol},
            correlation_id=intent.correlation_id,
            causation_id=intent_id,
            partition_key=f"{intent.symbol}::{intent.strategy_id}",
        )
        create_audit_log(
            db,
            action="intent_replay_requested",
            entity_type="execution_intent",
            entity_id=intent_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            severity="warning",
            details={"intent_id": intent_id},
        )
        return {"status": "replay_queued", "intent_id": intent_id}

    if action == "cancel_intent":
        db.add(
            ExecutionIntentEvent(
                id=str(uuid.uuid4()),
                intent_id=intent_id,
                event_type="execution.order.finalized",
                event_status="canceled",
                external_order_id="manual_cancel",
                payload={"reason": "manual_recovery_cancel"},
            )
        )
        db.commit()
        create_audit_log(
            db,
            action="intent_manual_cancel",
            entity_type="execution_intent",
            entity_id=intent_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            severity="warning",
            details={"intent_id": intent_id},
        )
        return {"status": "cancelled", "intent_id": intent_id}

    if action == "mark_failed":
        db.add(
            ExecutionIntentEvent(
                id=str(uuid.uuid4()),
                intent_id=intent_id,
                event_type="execution.order.finalized",
                event_status="failed",
                external_order_id="manual_failed",
                payload={"reason": "manual_recovery_failed"},
            )
        )
        db.commit()
        create_audit_log(
            db,
            action="intent_manual_failed",
            entity_type="execution_intent",
            entity_id=intent_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            severity="warning",
            details={"intent_id": intent_id},
        )
        return {"status": "failed", "intent_id": intent_id}

    raise ValueError("invalid_action")
