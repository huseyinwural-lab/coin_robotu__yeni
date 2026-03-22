import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import DecisionTraceCold, DecisionTraceHot, ExecutionIntent, ExecutionIntentEvent
from services.runtime_event_bus_service import (
    ack_runtime_event,
    consume_runtime_event,
    enqueue_quarantine_event,
    enqueue_retry_event,
    is_event_processed,
    mark_event_processed,
    publish_runtime_event,
    release_due_retry_events,
)
from services.paper_exchange_adapter_service import paper_exchange_adapter
from services.failed_event_service import upsert_failed_event
from core.users.user_exchange_connections import note_connection_runtime_event
from services.execution_safety_service import ExecutionSafetyViolation, enforce_execution_open_allowed_or_raise


def _canonical(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(payload: dict) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _classify_failure(envelope: dict, intent: ExecutionIntent | None, exc: Exception) -> str:
    if isinstance(exc, KeyError):
        return "schema_error"
    if intent is None:
        return "intent_state_violation"
    if isinstance(exc, ValueError) and str(exc) == "duplicate_terminal_event":
        return "duplicate_terminal_event"
    if isinstance(exc, RuntimeError) and str(exc) == "exchange_adapter_failure":
        return "exchange_adapter_failure"
    return "worker_internal_error"


def _handle_runtime_failure(
    db: Session,
    *,
    envelope: dict,
    error_message: str,
    reason_code: str,
    retry_count: int,
    max_retry: int,
    next_retry_at: datetime | None,
    status: str,
) -> None:
    payload = {
        "envelope": envelope,
        "reason_code": reason_code,
        "last_error": error_message,
        "queue": status,
    }
    upsert_failed_event(
        db,
        event_type=envelope.get("event_type", "unknown"),
        entity_type="runtime_event",
        entity_id=envelope.get("event_id", "unknown"),
        payload=payload,
        error_message=error_message,
        status=status,
        retry_count=retry_count,
        max_retry=max_retry,
        next_retry_at=next_retry_at,
        failure_class=reason_code,
        dead_letter_reason=reason_code if status == "quarantined" else None,
        last_action_by="execution_worker",
        correlation_id=str(envelope.get("correlation_id") or ""),
        retry_reason=reason_code,
        error_details={"metadata": envelope.get("metadata") or {}},
    )


def map_decision_to_intent(*, strategy_id: str, correlation_id: str, decision_result: dict, context_payload: dict) -> dict | None:
    action = decision_result.get("action")
    if action in {"REJECT", "HOLD"}:
        return None

    payload = {
        "strategy_id": strategy_id,
        "strategy_version_id": decision_result.get("strategy_version_id"),
        "account_id": context_payload.get("account_id") or context_payload.get("user_id"),
        "symbol": context_payload.get("symbol"),
        "side": action,
        "order_type": "MARKET",
        "quantity": float(decision_result.get("size") or 0),
        "price_reference": decision_result.get("price_reference") or {},
        "decision_hash": decision_result.get("decision_hash"),
        "context_hash": decision_result.get("context_hash"),
        "correlation_id": correlation_id,
    }
    payload["intent_hash"] = _hash(payload)
    payload["status"] = "pending"
    return payload


def dispatch_decision_result(
    db: Session,
    *,
    strategy_id: str,
    correlation_id: str,
    decision_result: dict,
    context_payload: dict,
) -> tuple[dict, dict | None, list[dict]]:
    emitted_events: list[dict] = []
    emitted_events.append(
        publish_runtime_event(
            event_type="decision.produced",
            payload={"strategy_id": strategy_id, "decision_result": decision_result, "context": context_payload},
            correlation_id=correlation_id,
            causation_id=decision_result.get("decision_hash"),
            partition_key=f"{context_payload.get('symbol')}::{strategy_id}",
        )
    )

    intent_payload = map_decision_to_intent(
        strategy_id=strategy_id,
        correlation_id=correlation_id,
        decision_result=decision_result,
        context_payload=context_payload,
    )

    db.add(
        DecisionTraceHot(
            trace_id=str(uuid.uuid4()),
            correlation_id=correlation_id,
            strategy_version_id=decision_result.get("strategy_version_id"),
            context_hash=decision_result.get("context_hash"),
            decision_hash=decision_result.get("decision_hash"),
            intent_hash=intent_payload.get("intent_hash") if intent_payload else None,
            context_payload=context_payload,
            decision_payload=decision_result,
            intent_payload=intent_payload or {},
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
        )
    )

    if decision_result.get("action") == "REJECT":
        emitted_events.append(
            publish_runtime_event(
                event_type="execution.intent.rejected",
                payload={"reason_codes": decision_result.get("reason_codes", []), "decision_hash": decision_result.get("decision_hash")},
                correlation_id=correlation_id,
                causation_id=decision_result.get("decision_hash"),
                partition_key=f"{context_payload.get('symbol')}::{strategy_id}",
            )
        )
        db.commit()
        return decision_result, None, emitted_events

    if decision_result.get("action") == "HOLD" or intent_payload is None:
        emitted_events.append(
            publish_runtime_event(
                event_type="execution.intent.rejected",
                payload={"reason_codes": ["hold_noop"], "decision_hash": decision_result.get("decision_hash")},
                correlation_id=correlation_id,
                causation_id=decision_result.get("decision_hash"),
                partition_key=f"{context_payload.get('symbol')}::{strategy_id}",
            )
        )
        db.commit()
        return decision_result, None, emitted_events

    existing_intent = db.query(ExecutionIntent).filter(ExecutionIntent.intent_hash == intent_payload["intent_hash"]).first()
    if existing_intent is not None:
        db.commit()
        return decision_result, {
            "intent_id": existing_intent.intent_id,
            "intent_hash": existing_intent.intent_hash,
            "status": existing_intent.status,
        }, emitted_events

    proposed_notional = float(decision_result.get("notional") or decision_result.get("size") or intent_payload.get("quantity") or 0.0)
    try:
        enforce_execution_open_allowed_or_raise(
            db,
            proposed_notional=proposed_notional,
            symbol=str(intent_payload.get("symbol") or ""),
            source="runtime_execution_dispatch",
            actor_user_id=str(intent_payload.get("account_id") or ""),
            actor_role="SYSTEM",
            entity_type="execution_intent",
            entity_id=str(intent_payload.get("intent_hash") or decision_result.get("decision_hash") or correlation_id),
        )
    except ExecutionSafetyViolation as exc:
        reason_code = exc.reason_code
        decision_result = {
            **decision_result,
            "action": "REJECT",
            "reason_codes": [reason_code],
            "execution_safety": {"reason_code": reason_code, **(exc.details or {})},
        }
        emitted_events.append(
            publish_runtime_event(
                event_type="execution.intent.rejected",
                payload={"reason_codes": [reason_code], "decision_hash": decision_result.get("decision_hash")},
                correlation_id=correlation_id,
                causation_id=decision_result.get("decision_hash"),
                partition_key=f"{context_payload.get('symbol')}::{strategy_id}",
            )
        )
        db.commit()
        return decision_result, None, emitted_events

    intent_row = ExecutionIntent(
        intent_id=str(uuid.uuid4()),
        strategy_id=strategy_id,
        strategy_version_id=intent_payload["strategy_version_id"],
        account_id=intent_payload.get("account_id"),
        symbol=intent_payload["symbol"],
        side=intent_payload["side"],
        order_type=intent_payload["order_type"],
        quantity=intent_payload["quantity"],
        price_reference=intent_payload["price_reference"],
        decision_hash=intent_payload["decision_hash"],
        context_hash=intent_payload["context_hash"],
        intent_hash=intent_payload["intent_hash"],
        correlation_id=correlation_id,
        status="pending",
    )
    db.add(intent_row)
    db.flush()

    emitted_events.append(
        publish_runtime_event(
            event_type="execution.intent.created",
            payload={"intent_id": intent_row.intent_id, "intent_hash": intent_row.intent_hash, "symbol": intent_row.symbol},
            correlation_id=correlation_id,
            causation_id=decision_result.get("decision_hash"),
            partition_key=f"{intent_row.symbol}::{strategy_id}",
        )
    )
    emitted_events.append(
        publish_runtime_event(
            event_type="execution.order.submission_requested",
            payload={"intent_id": intent_row.intent_id, "intent_hash": intent_row.intent_hash, "symbol": intent_row.symbol},
            correlation_id=correlation_id,
            causation_id=decision_result.get("decision_hash"),
            partition_key=f"{intent_row.symbol}::{strategy_id}",
        )
    )
    db.commit()

    return decision_result, {
        "intent_id": intent_row.intent_id,
        "intent_hash": intent_row.intent_hash,
        "status": intent_row.status,
    }, emitted_events


def process_submission_event_once(db: Session, worker_name: str = "execution-worker") -> dict | None:
    release_due_retry_events()
    consumed = consume_runtime_event("execution.order.submission_requested", worker_name=worker_name, timeout=1)
    if consumed is None:
        return None

    envelope, processing_queue, raw = consumed
    event_id = envelope.get("event_id")
    if not event_id:
        ack_runtime_event(processing_queue, raw)
        return {"status": "schema_error", "event_id": None}

    if is_event_processed(event_id):
        ack_runtime_event(processing_queue, raw)
        return {"status": "duplicate_skipped", "event_id": event_id}

    payload = envelope.get("payload") or {}
    intent_id = payload.get("intent_id")

    intent = None
    try:
        if not intent_id:
            raise KeyError("intent_id")

        intent = db.query(ExecutionIntent).filter(ExecutionIntent.intent_id == intent_id).first()
        if intent is None:
            raise ValueError("intent_missing")

        terminal_event = (
            db.query(ExecutionIntentEvent)
            .filter(
                ExecutionIntentEvent.intent_id == intent.intent_id,
                ExecutionIntentEvent.event_type == "execution.order.finalized",
            )
            .first()
        )
        if terminal_event is not None:
            raise ValueError("duplicate_terminal_event")

        try:
            enforce_execution_open_allowed_or_raise(
                db,
                proposed_notional=float(intent.quantity or 0.0),
                source="runtime_execution_worker",
                actor_user_id=str(intent.account_id or ""),
                actor_role="SYSTEM",
                entity_type="execution_intent",
                entity_id=str(intent.intent_id),
            )
        except ExecutionSafetyViolation as exc:
            reason_code = exc.reason_code
            db.add(
                ExecutionIntentEvent(
                    id=str(uuid.uuid4()),
                    intent_id=intent.intent_id,
                    event_type="execution.order.finalized",
                    event_status="rejected",
                    payload={"reason_code": reason_code, **(exc.details or {})},
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
            mark_event_processed(event_id)
            ack_runtime_event(processing_queue, raw)
            return {"status": "blocked", "event_id": event_id, "reason_code": reason_code}

        try:
            submission = paper_exchange_adapter.submit_order(
                {
                    "intent_hash": intent.intent_hash,
                    "quantity": intent.quantity,
                    "price_reference": intent.price_reference,
                }
            )
        except Exception as exc:
            raise RuntimeError("exchange_adapter_failure") from exc

        db.add(
            ExecutionIntentEvent(
                id=str(uuid.uuid4()),
                intent_id=intent.intent_id,
                event_type="execution.order.submitted",
                event_status="submitted",
                external_order_id=submission["external_order_id"],
                payload=submission,
            )
        )
        publish_runtime_event(
            event_type="execution.order.submitted",
            payload={"intent_id": intent.intent_id, "external_order_id": submission["external_order_id"]},
            correlation_id=intent.correlation_id,
            causation_id=envelope["event_id"],
            partition_key=f"{intent.symbol}::{intent.strategy_id}",
        )

        for state in submission["lifecycle"]:
            event_type = "execution.order.updated" if state not in {"FILLED", "CANCELED", "REJECTED"} else "execution.order.finalized"
            mapped_status = state.lower()
            db.add(
                ExecutionIntentEvent(
                    id=str(uuid.uuid4()),
                    intent_id=intent.intent_id,
                    event_type=event_type,
                    event_status=mapped_status,
                    external_order_id=submission["external_order_id"],
                    payload={"state": state},
                )
            )
            publish_runtime_event(
                event_type=event_type,
                payload={"intent_id": intent.intent_id, "state": state, "external_order_id": submission["external_order_id"]},
                correlation_id=intent.correlation_id,
                causation_id=envelope["event_id"],
                partition_key=f"{intent.symbol}::{intent.strategy_id}",
            )

        terminal = submission["lifecycle"][-1]
        db.add(
            DecisionTraceCold(
                archive_id=str(uuid.uuid4()),
                correlation_id=intent.correlation_id,
                strategy_version_id=intent.strategy_version_id,
                context_hash=intent.context_hash,
                decision_hash=intent.decision_hash,
                intent_hash=intent.intent_hash,
                artifact_id=None,
                lifecycle_summary={"lifecycle": submission["lifecycle"], "external_order_id": submission["external_order_id"]},
                terminal_state=terminal,
            )
        )

        if intent.account_id:
            note_connection_runtime_event(
                db,
                user_id=intent.account_id,
                outcome="success",
                reason_code="runtime_submission_ok",
                source="runtime_execution_success",
            )

        db.commit()
        mark_event_processed(event_id)
        ack_runtime_event(processing_queue, raw)
        return {"status": "processed", "event_id": event_id, "intent_id": intent.intent_id, "terminal_state": terminal}
    except Exception as exc:
        reason_code = _classify_failure(envelope, intent, exc)

        if intent is not None and intent.account_id:
            note_connection_runtime_event(
                db,
                user_id=intent.account_id,
                outcome="failure",
                reason_code=reason_code,
                source="runtime_execution_failure",
            )

        max_retry = 3
        retry_count = int(envelope.get("metadata", {}).get("retry_count", 0)) + 1
        backoff_seconds = 2 ** (retry_count - 1)
        next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
        envelope.setdefault("metadata", {})
        envelope["metadata"].update(
            {
                "retry_count": retry_count,
                "reason_code": reason_code,
                "last_error": str(exc),
            }
        )

        immediate_quarantine = {
            "schema_error",
            "intent_state_violation",
            "duplicate_terminal_event",
        }

        ack_runtime_event(processing_queue, raw)
        if reason_code in immediate_quarantine or retry_count >= max_retry:
            enqueue_quarantine_event(
                envelope=envelope,
                error_message=str(exc),
                reason_code=reason_code,
                retry_count=retry_count,
                max_retry=max_retry,
            )
            _handle_runtime_failure(
                db,
                envelope=envelope,
                error_message=str(exc),
                reason_code=reason_code,
                retry_count=retry_count,
                max_retry=max_retry,
                next_retry_at=None,
                status="quarantined",
            )
            return {"status": "quarantined", "event_id": event_id, "reason_code": reason_code}

        enqueue_retry_event(
            envelope=envelope,
            error_message=str(exc),
            reason_code=reason_code,
            retry_count=retry_count,
            max_retry=max_retry,
            next_retry_at=next_retry_at.isoformat(),
        )
        _handle_runtime_failure(
            db,
            envelope=envelope,
            error_message=str(exc),
            reason_code=reason_code,
            retry_count=retry_count,
            max_retry=max_retry,
            next_retry_at=next_retry_at,
            status="retrying",
        )
        return {"status": "retrying", "event_id": event_id, "reason_code": reason_code}
