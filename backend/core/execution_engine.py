import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.risk_engine import evaluate_risk
from db import redis_client
from models import ExecutionJob, Order, Position
from services.audit_service import create_audit_log


EXECUTION_QUEUE_KEY = "execution:jobs:queue"
TERMINAL_STATES = {"FILLED", "FAILED", "CANCELED"}
STATE_TRANSITIONS = {
    "CREATED": {"SENT", "FAILED", "CANCELED"},
    "SENT": {"PARTIALLY_FILLED", "FILLED", "FAILED", "CANCELED"},
    "PARTIALLY_FILLED": {"PARTIALLY_FILLED", "FILLED", "FAILED", "CANCELED"},
    "FILLED": set(),
    "FAILED": set(),
    "CANCELED": set(),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_idempotency_key(*, user_id: str, symbol: str, side: str, strategy_name: str, source_timestamp: str | None) -> str:
    ts = source_timestamp or _utcnow().isoformat()
    return f"{user_id}:{symbol.upper()}:{side.upper()}:{strategy_name}:{ts}"


def run_risk_checks(db: Session, *, signal: dict, user_id: str, risk_limits: dict | None = None) -> dict:
    return evaluate_risk(
        db,
        user_id=user_id,
        symbol=str(signal.get("symbol") or "UNKNOWN"),
        side=str(signal.get("side") or "BUY"),
        size=float(signal.get("size") or 0.0),
        leverage=int(signal.get("leverage") or 1),
        mark_price=float(signal.get("mark_price") or 1.0),
        limits=risk_limits,
    )


def enqueue_execution(db: Session, job: ExecutionJob) -> dict:
    payload = {
        "execution_job_id": job.id,
        "idempotency_key": job.idempotency_key,
        "user_id": job.user_id,
        "symbol": job.symbol,
        "side": job.side,
        "size": float(job.size),
        "strategy_name": job.strategy_name,
        "created_at": (job.created_at or _utcnow()).isoformat(),
        "retry_count": int(job.retry_count),
    }
    redis_client.rpush(EXECUTION_QUEUE_KEY, json.dumps(payload, ensure_ascii=False, default=str))
    job.queue_payload = payload
    db.commit()
    return payload


def _create_or_get_order(db: Session, *, job: ExecutionJob) -> Order:
    order = db.query(Order).filter(Order.execution_job_id == job.id).first()
    if order is not None:
        return order
    order = Order(
        execution_job_id=job.id,
        user_id=job.user_id,
        symbol=job.symbol,
        side=job.side,
        size=float(job.size),
        state="CREATED",
    )
    db.add(order)
    db.flush()
    return order


def advance_order_state(db: Session, *, order: Order, new_state: str, reason: str | None = None) -> None:
    current = str(order.state or "CREATED").upper()
    target = str(new_state).upper()
    if target not in STATE_TRANSITIONS.get(current, set()):
        raise ValueError("invalid_order_state_transition")

    now = _utcnow()
    order.state = target
    order.last_state_transition_at = now
    if target == "SENT":
        order.sent_at = now
    elif target == "PARTIALLY_FILLED":
        order.partial_filled_at = now
    elif target == "FILLED":
        order.filled_at = now
    elif target == "FAILED":
        order.failed_at = now
        order.fail_reason = reason
    elif target == "CANCELED":
        order.canceled_at = now
        order.reject_reason = reason


def route_to_exchange(job: ExecutionJob) -> dict:
    external_order_id = f"SIM-{job.id[:12]}"
    size = float(job.size or 0.0)
    states = ["SENT"]
    if size >= 2:
        states.append("PARTIALLY_FILLED")
    states.append("FILLED")
    return {
        "external_order_id": external_order_id,
        "states": states,
        "avg_fill_price": float((job.meta_payload or {}).get("mark_price") or 1.0),
        "filled_size": size,
    }


def _sync_position_after_fill(db: Session, *, order: Order) -> None:
    position_id = f"{order.user_id}:{order.symbol}"
    row = db.query(Position).filter(Position.position_id == position_id).first()
    if row is None:
        row = Position(
            position_id=position_id,
            user_id=order.user_id,
            symbol=order.symbol,
            size=float(order.filled_size or order.size),
            entry_price=float(order.avg_fill_price or 1.0),
            current_price=float(order.avg_fill_price or 1.0),
            unrealized_pnl=0.0,
            leverage=1,
            status="open",
            strategy_id=None,
            cluster_id=None,
            external_order_id=order.external_order_id,
            last_state_transition_at=_utcnow(),
            reject_reason=None,
            fail_reason=None,
        )
        db.add(row)
    else:
        row.size = float(row.size or 0.0) + float(order.filled_size or order.size)
        row.current_price = float(order.avg_fill_price or row.current_price or 1.0)
        row.external_order_id = order.external_order_id
        row.last_state_transition_at = _utcnow()
        row.status = "open"


def handle_execution_result(db: Session, *, job: ExecutionJob, order: Order, exchange_result: dict) -> dict:
    order.external_order_id = exchange_result.get("external_order_id")
    order.avg_fill_price = float(exchange_result.get("avg_fill_price") or 0.0)
    order.filled_size = float(exchange_result.get("filled_size") or 0.0)

    for state in exchange_result.get("states", []):
        advance_order_state(db, order=order, new_state=state)
        job.state = state
        job.last_state_transition_at = _utcnow()
        if state == "SENT":
            job.sent_at = _utcnow()
        elif state == "FILLED":
            job.filled_at = _utcnow()
            _sync_position_after_fill(db, order=order)

    db.commit()
    return {
        "execution_job_id": job.id,
        "order_id": order.id,
        "state": job.state,
        "external_order_id": order.external_order_id,
    }


def submit_signal(
    db: Session,
    *,
    user_id: str,
    signal: dict,
    idempotency_key: str | None = None,
    risk_limits: dict | None = None,
) -> dict:
    symbol = str(signal.get("symbol") or "").upper()
    side = str(signal.get("side") or "BUY").upper()
    size = float(signal.get("size") or 0.0)
    strategy_name = str(signal.get("strategy_name") or "runtime_strategy")

    if not symbol or side not in {"BUY", "SELL"} or size <= 0:
        raise ValueError("invalid_signal_payload")

    idem_key = idempotency_key or _build_idempotency_key(
        user_id=user_id,
        symbol=symbol,
        side=side,
        strategy_name=strategy_name,
        source_timestamp=signal.get("timestamp"),
    )

    existing = db.query(ExecutionJob).filter(ExecutionJob.idempotency_key == idem_key).first()
    if existing is not None:
        return {
            "status": "duplicate",
            "execution_job_id": existing.id,
            "state": existing.state,
            "idempotency_key": idem_key,
        }

    job = ExecutionJob(
        idempotency_key=idem_key,
        user_id=user_id,
        symbol=symbol,
        side=side,
        size=size,
        strategy_name=strategy_name,
        state="CREATED",
        meta_payload={
            "confidence": float(signal.get("confidence") or 0.0),
            "mark_price": float(signal.get("mark_price") or 1.0),
            "leverage": int(signal.get("leverage") or 1),
        },
    )
    db.add(job)
    db.flush()

    risk_decision = run_risk_checks(db, signal=signal, user_id=user_id, risk_limits=risk_limits)
    if not risk_decision.get("allowed"):
        job.state = "FAILED"
        job.reject_reason = risk_decision.get("reject_reason")
        job.failed_at = _utcnow()
        job.last_state_transition_at = _utcnow()
        create_audit_log(
            db,
            action="execution_signal_rejected",
            entity_type="execution_job",
            entity_id=job.id,
            actor_user_id=user_id,
            actor_role="user",
            severity="warning",
            details={"risk": risk_decision, "signal": signal},
        )
        db.commit()
        return {
            "status": "rejected",
            "execution_job_id": job.id,
            "idempotency_key": idem_key,
            "risk": risk_decision,
            "state": job.state,
        }

    queue_payload = enqueue_execution(db, job)
    create_audit_log(
        db,
        action="execution_signal_enqueued",
        entity_type="execution_job",
        entity_id=job.id,
        actor_user_id=user_id,
        actor_role="user",
        details={"signal": signal, "queue_payload": queue_payload},
    )
    return {
        "status": "enqueued",
        "execution_job_id": job.id,
        "idempotency_key": idem_key,
        "queue_payload": queue_payload,
        "state": job.state,
    }


def execute_queued_job(db: Session, *, queue_payload: dict) -> dict:
    execution_job_id = str(queue_payload.get("execution_job_id") or "")
    if not execution_job_id:
        return {"status": "ignored", "reason": "missing_execution_job_id"}

    job = db.query(ExecutionJob).filter(ExecutionJob.id == execution_job_id).first()
    if job is None:
        return {"status": "ignored", "reason": "execution_job_not_found", "execution_job_id": execution_job_id}
    if str(job.state).upper() in TERMINAL_STATES:
        return {"status": "ignored", "reason": "already_terminal", "execution_job_id": execution_job_id, "state": job.state}

    order = _create_or_get_order(db, job=job)

    try:
        exchange_result = route_to_exchange(job)
        result = handle_execution_result(db, job=job, order=order, exchange_result=exchange_result)
        create_audit_log(
            db,
            action="execution_job_processed",
            entity_type="execution_job",
            entity_id=job.id,
            actor_user_id=job.user_id,
            actor_role="system",
            details={"result": result},
        )
        return {"status": "processed", **result}
    except Exception as exc:
        job.retry_count = int(job.retry_count or 0) + 1
        job.last_error = str(exc)[:250]
        job.fail_reason = str(exc)[:250]
        if int(job.retry_count) >= int(job.max_retry):
            job.state = "FAILED"
            job.failed_at = _utcnow()
        job.last_state_transition_at = _utcnow()
        db.commit()

        if str(job.state).upper() != "FAILED":
            queue_payload["retry_count"] = int(job.retry_count)
            redis_client.rpush(EXECUTION_QUEUE_KEY, json.dumps(queue_payload, ensure_ascii=False, default=str))

        return {
            "status": "retry" if str(job.state).upper() != "FAILED" else "failed",
            "execution_job_id": job.id,
            "retry_count": int(job.retry_count),
            "state": job.state,
            "error": str(exc)[:250],
        }


def consume_execution_queue_once(db: Session) -> dict | None:
    raw = redis_client.lpop(EXECUTION_QUEUE_KEY)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    payload = json.loads(raw)
    return execute_queued_job(db, queue_payload=payload)
