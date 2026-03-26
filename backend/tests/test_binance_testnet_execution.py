import os

from core.go_live_checklist import run_testnet_lifecycle_validation
from db import SessionLocal
from models import User


def test_binance_testnet_order_lifecycle_market_limit_cancel():
    os.environ["EXECUTION_MODE"] = "testnet"
    os.environ["TESTNET_TRADING_ENABLED"] = "true"
    os.environ["LIVE_TRADING_ENABLED"] = "false"
    os.environ["LIVE_ROUTE_APPROVED"] = "false"

    db = SessionLocal()
    try:
        canary_user = db.query(User).filter(User.email == "canary.admin@platform.local").first()
        if canary_user is None:
            candidates = db.query(User).order_by(User.created_at.asc()).limit(50).all()
            canary_user = next(
                (item for item in candidates if getattr(getattr(item, "role", None), "value", "") in {"super_admin", "admin", "ops"}),
                None,
            )
        if canary_user is None:
            canary_user = db.query(User).order_by(User.created_at.asc()).first()
        assert canary_user is not None

        result = None
        for _ in range(2):
            result = run_testnet_lifecycle_validation(db, user_id=canary_user.id, symbol="BTCUSDT", size=0.0001)
            if result.get("status") == "PASS":
                break

        assert result.get("status") == "PASS"
        assert result.get("market_order_id")
        assert result.get("cancel_order_id")
        assert result.get("timeline_event_count", 0) > 0
        assert result.get("db_state", {}).get("external_order_id")

        market_submit_raw = result.get("response_log", {}).get("steps", {}).get("market_submit", {}).get("raw", {})
        assert market_submit_raw.get("orderId")
    finally:
        db.close()
