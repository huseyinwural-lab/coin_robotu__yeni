import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import DecisionTraceCold, DecisionTraceHot, ExecutionIntent, ExecutionIntentEvent
from services.runtime_event_bus_service import (
    ack_runtime_event,
    consume_runtime_event,
    is_event_processed,
    mark_event_processed,
    publish_runtime_event,
)
from services.paper_exchange_adapter_service import paper_exchange_adapter


def _canonical(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(payload: dict) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def map_decision_to_intent(*, strategy_id: str, correlation_id: str, decision_result: dict, context_payload: dict) -> dict | None:
    action = decision_result.get("action")
    if action in {"REJECT", "HOLD"}:
        return None

    payload = {
        "strategy_id": strategy_id,
        "strategy_version_id": decision_result.get("strategy_version_id"),
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

    intent_row = ExecutionIntent(
        intent_id=str(uuid.uuid4()),
        strategy_id=strategy_id,
        strategy_version_id=intent_payload["strategy_version_id"],
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
    consumed = consume_runtime_event("execution.order.submission_requested", worker_name=worker_name, timeout=1)
    if consumed is None:
        return None

    envelope, processing_queue, raw = consumed
    event_id = envelope["event_id"]
    if is_event_processed(event_id):
        ack_runtime_event(processing_queue, raw)
        return {"status": "duplicate_skipped", "event_id": event_id}

    payload = envelope["payload"]
    intent_id = payload["intent_id"]
    intent = db.query(ExecutionIntent).filter(ExecutionIntent.intent_id == intent_id).first()
    if intent is None:
        ack_runtime_event(processing_queue, raw)
        mark_event_processed(event_id)
        return {"status": "intent_missing", "event_id": event_id}

    submission = paper_exchange_adapter.submit_order(
        {
            "intent_hash": intent.intent_hash,
            "quantity": intent.quantity,
            "price_reference": intent.price_reference,
        }
    )

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

    db.commit()
    mark_event_processed(event_id)
    ack_runtime_event(processing_queue, raw)
    return {"status": "processed", "event_id": event_id, "intent_id": intent.intent_id, "terminal_state": terminal}
