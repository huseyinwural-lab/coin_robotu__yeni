import os
import uuid

import core.execution_engine as execution_engine
from core.safety.kill_switch import deactivate_kill_switch
from db import SessionLocal
from models import ExecutionJob, User


class _FailingAdapter:
    def __init__(self, message: str):
        self.message = message

    def get_available_balance(self, *, asset: str = "USDT") -> float:
        return 1_000_000.0

    def submit_order(self, payload: dict) -> dict:
        raise RuntimeError(self.message)


def _run_failure_case(db, user_id: str, message: str):
    deactivate_kill_switch(source="test", reason="reset_before_each_case")
    submit = execution_engine.submit_signal(
        db,
        user_id=user_id,
        signal={
            "symbol": "ETHUSDT",
            "side": "BUY",
            "size": 0.1,
            "strategy_name": "ema_rsi",
            "mark_price": 120,
            "leverage": 1,
        },
        idempotency_key=f"failure-class-{uuid.uuid4()}",
    )
    assert submit.get("status") == "enqueued"
    execution_engine.get_execution_adapter = lambda: _FailingAdapter(message)  # noqa: E731
    execution_engine.execute_queued_job(db, queue_payload=submit["queue_payload"])
    row = db.query(ExecutionJob).filter(ExecutionJob.id == submit["execution_job_id"]).first()
    assert row is not None
    return row.failure_class


def test_execution_failure_classification(monkeypatch):
    os.environ["CANARY_MODE"] = "false"
    os.environ["RUNTIME_THRESHOLD_FAILED_ORDERS_THRESHOLD"] = "999"
    deactivate_kill_switch(source="test", reason="reset_before_failure_class_test")
    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.created_at.asc()).first()
        assert user is not None

        monkeypatch.setattr(execution_engine, "get_execution_adapter", lambda: _FailingAdapter("network_error"))
        assert _run_failure_case(db, user.id, "network_error") == "network_error"

        monkeypatch.setattr(execution_engine, "get_execution_adapter", lambda: _FailingAdapter("timeout"))
        assert _run_failure_case(db, user.id, "timeout") == "timeout"

        monkeypatch.setattr(execution_engine, "get_execution_adapter", lambda: _FailingAdapter("exchange_reject:400:oops"))
        assert _run_failure_case(db, user.id, "exchange_reject:400:oops") == "exchange_reject"

        monkeypatch.setattr(execution_engine, "get_execution_adapter", lambda: _FailingAdapter("something_else"))
        assert _run_failure_case(db, user.id, "something_else") == "unknown"
    finally:
        db.close()
