import json
import time
import asyncio
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.alerts.runtime_alert_triggers import (
    check_failed_orders_trigger,
    check_queue_depth_trigger,
    check_worker_failure_trigger,
    trigger_runtime_threshold_alert,
)
from core.exchanges import get_execution_adapter
from core.runtime_alert_thresholds import get_runtime_alert_thresholds
from core.runtime_stream import runtime_stream_hub
from core.safety.canary_mode import evaluate_canary_constraints
from core.safety.kill_switch import evaluate_auto_kill_switch, get_kill_switch_state, is_kill_switch_active
from core.risk_engine import evaluate_risk
from db import redis_client
from models import ExecutionJob, ExecutionMetric, Order, Position
from services.audit_service import create_audit_log
from services.execution_readiness_service import validate_order_precheck


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


def _emit_timeline_event(event: dict) -> None:
    runtime_stream_hub.record_event(event)
    try:
        asyncio.run(runtime_stream_hub.publish_event(event))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(runtime_stream_hub.publish_event(event))
        finally:
            loop.close()


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
    enqueued_at = _utcnow().isoformat()
    payload = {
        "execution_job_id": job.id,
        "idempotency_key": job.idempotency_key,
        "user_id": job.user_id,
        "symbol": job.symbol,
        "side": job.side,
        "size": float(job.size),
        "strategy_name": job.strategy_name,
        "created_at": (job.created_at or _utcnow()).isoformat(),
        "enqueued_at": enqueued_at,
        "retry_count": int(job.retry_count),
    }
    redis_client.rpush(EXECUTION_QUEUE_KEY, json.dumps(payload, ensure_ascii=False, default=str))
    job.queue_payload = payload
    db.commit()
    check_queue_depth_trigger(db)
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
    adapter = get_execution_adapter()
    return adapter.submit_order(
        {
            "execution_job_id": job.id,
            "idempotency_key": job.idempotency_key,
            "user_id": job.user_id,
            "symbol": job.symbol,
            "side": job.side,
            "size": float(job.size or 0.0),
            "strategy_name": job.strategy_name,
            "mark_price": float((job.meta_payload or {}).get("mark_price") or 1.0),
        }
    )


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


def _record_execution_metric(db: Session, *, job: ExecutionJob, order: Order, exchange_result: dict) -> None:
    existing = db.query(ExecutionMetric).filter(ExecutionMetric.order_id == order.id).first()
    if existing is not None:
        return

    meta = dict(job.meta_payload or {})
    micro_guard = dict(meta.get("microstructure_guard") or {})
    mid_price = float(meta.get("mark_price") or 0.0)
    avg_fill_price = float(order.avg_fill_price or mid_price or 0.0) or None
    executed_qty = float(order.filled_size or job.size or 0.0) or None
    submitted_at = job.created_at or _utcnow()
    ack_at = order.sent_at or job.sent_at
    final_at = order.filled_at or order.failed_at or order.canceled_at or job.filled_at or job.failed_at or _utcnow()
    slippage_pct = None
    realized_slippage_bps = 0.0
    if avg_fill_price and mid_price > 0:
        slippage_pct = round((abs(avg_fill_price - mid_price) / mid_price) * 100, 6)
        realized_slippage_bps = round((abs(avg_fill_price - mid_price) / mid_price) * 10000, 6)
    predicted_slippage_bps = float(((micro_guard.get("slippage_prediction") or {}).get("expected_slippage_bps") or 0.0))
    slippage_error_bps = round(abs(realized_slippage_bps - predicted_slippage_bps), 6)
    quality_score = max(0.0, min(100.0, 100.0 - (realized_slippage_bps * 1.5) - ((job.total_ms or job.execution_ms or 0) / 120.0)))
    metric = ExecutionMetric(
        user_id=job.user_id,
        symbol=job.symbol,
        order_id=order.id,
        exchange_order_id=str(order.external_order_id or f"runtime-{job.id}"),
        client_order_id=job.idempotency_key,
        order_type="MARKET",
        exchange=str(micro_guard.get("selected_venue") or "binance"),
        market_type="futures",
        environment="paper",
        side=str(job.side or "BUY"),
        quote_qty=float((executed_qty or job.size or 0.0) * max(mid_price, 0.0)),
        mid_price=max(mid_price, 0.0),
        mid_price_timestamp=submitted_at.isoformat() if submitted_at else _utcnow().isoformat(),
        price_avg=avg_fill_price,
        executed_qty=executed_qty,
        slippage_pct=slippage_pct,
        execution_time_ms=float(job.total_ms or job.execution_ms or 0.0),
        status=str(order.state or job.state or "NEW"),
        final_status=str(order.state or job.state or "NEW"),
        failure_code=str(order.reject_reason or order.fail_reason or job.reject_reason or job.fail_reason or "") or None,
        strategy_type=str(job.strategy_name or "runtime_strategy"),
        volatility_regime="unknown",
        volatility_pct=0.0,
        execution_quality_score=round(quality_score, 4),
        submitted_at=submitted_at,
        ack_at=ack_at,
        final_at=final_at,
        validation_snapshot_id=None,
        raw_exchange_status={
            "exchange_result": exchange_result,
            "microstructure_guard": micro_guard,
            "predicted_slippage_bps": predicted_slippage_bps,
            "realized_slippage_bps": realized_slippage_bps,
            "slippage_error_bps": slippage_error_bps,
        },
        state_machine_path=[str(item) for item in (exchange_result.get("states") or [])],
    )
    db.add(metric)


def handle_execution_result(db: Session, *, job: ExecutionJob, order: Order, exchange_result: dict) -> dict:
    order.external_order_id = exchange_result.get("external_order_id")
    order.avg_fill_price = float(exchange_result.get("avg_fill_price") or 0.0)
    order.filled_size = float(exchange_result.get("filled_size") or 0.0)

    previous_state = str(order.state or "CREATED")
    for state in exchange_result.get("states", []):
        advance_order_state(db, order=order, new_state=state)
        job.state = state
        job.last_state_transition_at = _utcnow()
        if state == "SENT":
            job.sent_at = _utcnow()
        elif state == "FILLED":
            job.filled_at = _utcnow()
            _sync_position_after_fill(db, order=order)

        _emit_timeline_event(
            {
                "event_type": "execution_state_changed",
                "severity": "CRITICAL" if state in {"FAILED", "CANCELED"} else "INFO",
                "order_id": order.id,
                "user_id": job.user_id,
                "symbol": job.symbol,
                "side": job.side,
                "state": state,
                "previous_state": previous_state,
                "source": "execution_engine",
                "timestamp": _utcnow().isoformat(),
                "meta": {
                    "filled_qty": float(order.filled_size or 0.0),
                    "remaining_qty": max(0.0, float(order.size or 0.0) - float(order.filled_size or 0.0)),
                    "reject_reason": order.reject_reason,
                    "fail_reason": order.fail_reason,
                    "queue_wait_ms": job.queue_wait_ms,
                    "execution_ms": job.execution_ms,
                    "total_ms": job.total_ms,
                },
            }
        )
        previous_state = state

    _record_execution_metric(db, job=job, order=order, exchange_result=exchange_result)
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

    if is_kill_switch_active():
        state = get_kill_switch_state()
        return {
            "status": "rejected",
            "execution_job_id": None,
            "idempotency_key": None,
            "state": "FAILED",
            "risk": {"allowed": False, "reject_reason": "kill_switch_active", "details": state},
        }

    precheck = validate_order_precheck(
        db,
        user_id=user_id,
        symbol=symbol,
        market_type="futures",
        order_type=str(signal.get("order_type") or "market"),
        side=side,
        price=float(signal.get("mark_price") or 0.0),
        size=size,
        leverage=int(signal.get("leverage") or 1),
        margin_mode=str(signal.get("margin_mode") or "isolated"),
    )
    if not precheck.get("valid"):
        return {
            "status": "rejected",
            "execution_job_id": None,
            "idempotency_key": None,
            "state": "FAILED",
            "risk": {"allowed": False, "reject_reason": "precheck_failed", "details": precheck},
        }
    adjusted_size = float((precheck.get("adjustments") or {}).get("adjusted_size") or size)
    if adjusted_size > 0 and adjusted_size < size:
        size = adjusted_size
        signal = {**signal, "size": adjusted_size}
        create_audit_log(
            db,
            action="runtime_execution_microstructure_adjusted",
            entity_type="execution_job",
            entity_id=str(idempotency_key or f"{user_id}:{symbol}"),
            actor_user_id=user_id,
            actor_role="user",
            severity="warning",
            details={
                "requested_size": float(signal.get("size") or 0.0),
                "adjusted_size": adjusted_size,
                "guard_state": (precheck.get("microstructure_guard") or {}).get("state"),
            },
            commit=False,
        )

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
            "microstructure_guard": precheck.get("microstructure_guard") or {},
            "requested_size": float(signal.get("size") or size),
        },
    )
    db.add(job)
    db.flush()

    canary = evaluate_canary_constraints(
        db,
        user_id=user_id,
        strategy_name=strategy_name,
        size=size,
        mark_price=float(signal.get("mark_price") or 1.0),
    )
    if not canary.get("allowed"):
        job.state = "FAILED"
        job.reject_reason = canary.get("reject_reason")
        job.failed_at = _utcnow()
        job.last_state_transition_at = _utcnow()
        db.commit()
        return {
            "status": "rejected",
            "execution_job_id": job.id,
            "idempotency_key": idem_key,
            "state": job.state,
            "risk": {"allowed": False, "reject_reason": canary.get("reject_reason"), "details": canary},
        }

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
        _emit_timeline_event(
            {
                "event_type": "execution_state_changed",
                "severity": "CRITICAL",
                "order_id": None,
                "user_id": job.user_id,
                "symbol": job.symbol,
                "side": job.side,
                "state": "FAILED",
                "previous_state": "CREATED",
                "source": "execution_engine",
                "timestamp": _utcnow().isoformat(),
                "meta": {
                    "filled_qty": 0,
                    "remaining_qty": float(job.size or 0.0),
                    "reject_reason": job.reject_reason,
                },
            }
        )
        db.commit()
        return {
            "status": "rejected",
            "execution_job_id": job.id,
            "idempotency_key": idem_key,
            "risk": risk_decision,
            "state": job.state,
        }

    _emit_timeline_event(
        {
            "event_type": "execution_state_changed",
            "severity": "INFO",
            "order_id": None,
            "user_id": job.user_id,
            "symbol": job.symbol,
            "side": job.side,
            "state": "CREATED",
            "previous_state": None,
            "source": "execution_engine",
            "timestamp": _utcnow().isoformat(),
            "meta": {"filled_qty": 0, "remaining_qty": float(job.size or 0.0), "reject_reason": None},
        }
    )

    queue_payload = enqueue_execution(db, job)
    evaluate_auto_kill_switch(db)
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

    retry_at_ts = int(queue_payload.get("retry_at_ts") or 0)
    now_ms = int(time.time() * 1000)
    if retry_at_ts and now_ms < retry_at_ts:
        redis_client.rpush(EXECUTION_QUEUE_KEY, json.dumps(queue_payload, ensure_ascii=False, default=str))
        return {
            "status": "deferred",
            "execution_job_id": execution_job_id,
            "retry_at_ts": retry_at_ts,
        }

    order = _create_or_get_order(db, job=job)
    adapter = get_execution_adapter()

    execution_started = time.perf_counter()
    enqueued_at_raw = queue_payload.get("enqueued_at")
    queue_wait_ms = None
    if enqueued_at_raw:
        try:
            enqueued_dt = datetime.fromisoformat(str(enqueued_at_raw).replace("Z", "+00:00"))
            queue_wait_ms = max(0, int((_utcnow() - enqueued_dt).total_seconds() * 1000))
            job.queue_wait_ms = queue_wait_ms
        except Exception:  # noqa: BLE001
            queue_wait_ms = None

    try:
        leverage = int((job.meta_payload or {}).get("leverage") or 1)
        mark_price = float((job.meta_payload or {}).get("mark_price") or 1.0)
        required_margin = float(job.size or 0.0) * mark_price / max(leverage, 1)
        available_balance = float(adapter.get_available_balance(asset="USDT") or 0.0)
        if available_balance < required_margin:
            raise RuntimeError("insufficient_balance")

        exchange_result = adapter.submit_order(
            {
                "execution_job_id": job.id,
                "idempotency_key": job.idempotency_key,
                "symbol": job.symbol,
                "side": job.side,
                "size": float(job.size or 0.0),
                "strategy_name": job.strategy_name,
                "mark_price": mark_price,
                "order_type": str((job.meta_payload or {}).get("order_type") or "MARKET"),
                "limit_price": (job.meta_payload or {}).get("limit_price"),
            }
        )
        execution_ms = int((time.perf_counter() - execution_started) * 1000)
        total_ms = int((queue_wait_ms or 0) + execution_ms)
        job.execution_ms = execution_ms
        job.total_ms = total_ms
        job.failure_class = None

        thresholds = get_runtime_alert_thresholds()
        latency_limit = int(thresholds.get("execution_latency_ms_threshold") or 1200)
        if total_ms >= latency_limit:
            trigger_runtime_threshold_alert(
                db,
                alert_type="runtime_execution_latency_high",
                severity="WARNING",
                message=f"Execution latency high: {total_ms}ms",
                source="execution_engine",
                threshold=latency_limit,
                actual_value=total_ms,
                user_id=job.user_id,
                symbol=job.symbol,
                root_cause_code="execution_latency_threshold",
            )

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
        check_failed_orders_trigger(db)
        evaluate_auto_kill_switch(db)
        return {"status": "processed", **result}
    except Exception as exc:
        execution_ms = int((time.perf_counter() - execution_started) * 1000)
        job.execution_ms = execution_ms
        job.total_ms = int((queue_wait_ms or 0) + execution_ms)
        job.retry_count = int(job.retry_count or 0) + 1
        job.last_error = str(exc)[:250]
        job.fail_reason = str(exc)[:250]
        lowered = str(exc).lower()
        if "insufficient_balance" in lowered:
            job.failure_class = "insufficient_balance"
        elif "network" in lowered:
            job.failure_class = "network_error"
        elif "timeout" in lowered:
            job.failure_class = "timeout"
        elif "guard" in lowered:
            job.failure_class = "adapter_guard"
        elif "reject" in lowered:
            job.failure_class = "exchange_reject"
        else:
            job.failure_class = "unknown"
        if int(job.retry_count) >= int(job.max_retry):
            job.state = "FAILED"
            job.failed_at = _utcnow()
        job.last_state_transition_at = _utcnow()
        db.commit()

        if str(job.state).upper() == "FAILED":
            _emit_timeline_event(
                {
                    "event_type": "execution_state_changed",
                    "severity": "CRITICAL",
                    "order_id": order.id,
                    "user_id": job.user_id,
                    "symbol": job.symbol,
                    "side": job.side,
                    "state": "FAILED",
                    "previous_state": str(order.state or "SENT"),
                    "source": "execution_engine",
                    "timestamp": _utcnow().isoformat(),
                    "meta": {
                        "filled_qty": float(order.filled_size or 0.0),
                        "remaining_qty": max(0.0, float(order.size or 0.0) - float(order.filled_size or 0.0)),
                        "reject_reason": order.reject_reason,
                        "fail_reason": job.fail_reason,
                        "failure_class": job.failure_class,
                    },
                }
            )

        if str(job.state).upper() != "FAILED":
            queue_payload["retry_count"] = int(job.retry_count)
            backoff_ms = min(8000, 1000 * (2 ** max(0, int(job.retry_count) - 1)))
            queue_payload["retry_at_ts"] = int(time.time() * 1000) + backoff_ms
            redis_client.rpush(EXECUTION_QUEUE_KEY, json.dumps(queue_payload, ensure_ascii=False, default=str))

        check_worker_failure_trigger(db, threshold=3, window_minutes=15)
        check_failed_orders_trigger(db)
        if job.failure_class == "exchange_reject":
            auth_related = any(
                marker in lowered
                for marker in [
                    "invalid api-key",
                    "invalid api key",
                    "signature",
                    "-2015",
                    "x-proxy-token",
                    "proxy token",
                    "permission",
                    "unauthorized",
                ]
            )
            if auth_related:
                trigger_runtime_threshold_alert(
                    db,
                    alert_type="runtime_exchange_auth_invalid",
                    severity="CRITICAL",
                    message=f"Exchange auth/proxy reject detected: {job.symbol}",
                    source="execution_engine",
                    threshold=1,
                    actual_value=1,
                    user_id=job.user_id,
                    symbol=job.symbol,
                    root_cause_code="exchange_auth_invalid",
                )
        evaluate_auto_kill_switch(db)

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
