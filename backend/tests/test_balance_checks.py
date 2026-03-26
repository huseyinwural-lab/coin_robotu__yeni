import uuid

import core.execution_engine as execution_engine
from db import SessionLocal
from models import ExecutionJob, User


class _LowBalanceAdapter:
    def get_available_balance(self, *, asset: str = "USDT") -> float:
        return 0.0

    def submit_order(self, payload: dict) -> dict:
        raise AssertionError("submit_order should not be called when balance is insufficient")


def test_insufficient_balance_rejects_execution(monkeypatch):
    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.created_at.asc()).first()
        assert user is not None

        submit = execution_engine.submit_signal(
            db,
            user_id=user.id,
            signal={
                "symbol": "ETHUSDT",
                "side": "BUY",
                "size": 0.2,
                "strategy_name": "ema_rsi",
                "mark_price": 200,
                "leverage": 1,
            },
            idempotency_key=f"balance-test-{uuid.uuid4()}",
        )
        assert submit.get("status") == "enqueued"

        monkeypatch.setattr(execution_engine, "get_execution_adapter", lambda: _LowBalanceAdapter())
        result = execution_engine.execute_queued_job(db, queue_payload=submit["queue_payload"])
        assert result.get("status") in {"retry", "failed"}

        row = db.query(ExecutionJob).filter(ExecutionJob.id == submit["execution_job_id"]).first()
        assert row is not None
        assert row.failure_class == "insufficient_balance"
    finally:
        db.close()
