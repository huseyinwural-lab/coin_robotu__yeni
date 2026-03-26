import os
import uuid

from core.execution_engine import submit_signal
from db import SessionLocal
from models import User


def test_canary_rejects_large_notional():
    os.environ["CANARY_MODE"] = "true"
    os.environ["CANARY_MAX_NOTIONAL"] = "100"
    os.environ["CANARY_ALLOWED_STRATEGIES"] = "ema_rsi"
    os.environ["CANARY_ALLOWED_USER_IDS"] = ""

    db = SessionLocal()
    try:
        admin_user = (
            db.query(User)
            .filter(User.role.in_(["super_admin", "admin", "ops"]))
            .order_by(User.created_at.asc())
            .first()
        )
        if admin_user is None:
            admin_user = db.query(User).order_by(User.created_at.asc()).first()
        assert admin_user is not None

        result = submit_signal(
            db,
            user_id=admin_user.id,
            signal={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 2.0,
                "strategy_name": "ema_rsi",
                "mark_price": 100,
                "leverage": 1,
            },
            idempotency_key=f"canary-limit-{uuid.uuid4()}",
        )
        assert result.get("status") == "rejected"
        assert result.get("risk", {}).get("reject_reason") == "canary_max_notional_exceeded"
    finally:
        db.close()
