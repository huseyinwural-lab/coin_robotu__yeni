import time
import os

from core import execution_engine
from core.execution_engine import submit_signal
from core.safety.kill_switch import deactivate_kill_switch
from db import SessionLocal
from models import SystemAlert, User


class _RejectingAdapter:
    def get_available_balance(self, *, asset: str = "USDT") -> float:
        return 10000.0

    def submit_order(self, payload: dict) -> dict:
        raise RuntimeError("exchange_reject:401:Invalid API-key, IP, or permissions for action")


def test_exchange_auth_reject_creates_runtime_alert(monkeypatch):
    db = SessionLocal()
    try:
        deactivate_kill_switch(source="test", reason="pre_test_reset")
        os.environ["CANARY_MODE"] = "false"
        user = db.query(User).order_by(User.created_at.asc()).first()
        assert user is not None

        submit_result = submit_signal(
            db,
            user_id=user.id,
            signal={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 0.001,
                "strategy_name": "ema_rsi",
                "mark_price": 10000,
                "leverage": 1,
            },
            idempotency_key=f"test-auth-alert-iter4-{int(time.time() * 1000)}",
        )
        assert submit_result.get("status") == "enqueued"
        queue_payload = submit_result.get("queue_payload")
        assert queue_payload

        monkeypatch.setattr(execution_engine, "get_execution_adapter", lambda: _RejectingAdapter())
        process_result = execution_engine.execute_queued_job(db, queue_payload=queue_payload)
        assert process_result.get("status") in {"retry", "failed"}

        alert = (
            db.query(SystemAlert)
            .filter(SystemAlert.alert_type == "runtime_exchange_auth_invalid")
            .order_by(SystemAlert.created_at.desc())
            .first()
        )
        assert alert is not None
        assert str(alert.severity).upper() == "CRITICAL"
    finally:
        db.close()