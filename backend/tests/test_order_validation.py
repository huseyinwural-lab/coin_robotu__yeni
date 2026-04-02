# ruff: noqa: E402
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from db import SessionLocal
from models import User, UserExchangeConnection, UserRole
from services.execution_readiness_service import validate_order_precheck


def test_order_validation_rejects_invalid_leverage_and_min_order_size():
    db = SessionLocal()
    try:
        user = User(
            email=f"order-validation-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("OrderPass123!"),
            role=UserRole.USER,
            is_active=True,
            approval_status="approved",
        )
        db.add(user)
        db.flush()

        conn = UserExchangeConnection(
            user_id=user.id,
            account_label="default",
            exchange="bybit",
            market_type="futures",
            environment="live",
            is_default=True,
            readiness_snapshot={"connection_health": "online", "can_trade": True, "validation_latency_ms": 10},
            permission_snapshot=["trade"],
            api_key_encrypted="x",
            api_secret_encrypted="y",
        )
        db.add(conn)
        db.commit()

        result = validate_order_precheck(
            db,
            user_id=user.id,
            symbol="BTCUSDT",
            market_type="futures",
            order_type="market",
            side="buy",
            price=100,
            size=0.0001,
            leverage=100,
            margin_mode="isolated",
        )
        assert result["valid"] is False
        codes = {item.get("code") for item in (result.get("violations") or [])}
        assert "leverage_limit_exceeded" in codes
        assert "min_order_size_violation" in codes
    finally:
        db.close()
