# ruff: noqa: E402
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from db import SessionLocal
from models import User, UserExchangeConnection, UserRole, UserScannerResult
from routers.screener import list_filtered_screener_results
from services.explainability_rules_service import build_screener_explain
from services.execution_readiness_service import validate_order_precheck


def _create_user(db, *, email_prefix: str) -> User:
    row = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password("Pass1234!Aa"),
        role=UserRole.USER,
        is_active=True,
        approval_status="approved",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_build_screener_explain_is_deterministic_and_non_empty():
    payload = {
        "rsi": 28,
        "volume_spike": 2.1,
        "price": 101,
        "ma50": 96,
    }
    first = build_screener_explain(payload=payload, signal="long", signal_score=87)
    second = build_screener_explain(payload=payload, signal="long", signal_score=87)

    assert isinstance(first, list)
    assert len(first) >= 1
    assert first == second


def test_validate_order_precheck_includes_explain():
    db = SessionLocal()
    try:
        user = _create_user(db, email_prefix="explain-precheck")
        db.add(
            UserExchangeConnection(
                user_id=user.id,
                account_label="default",
                exchange="binance",
                market_type="futures",
                environment="live",
                is_default=True,
                readiness_snapshot={"connection_health": "online", "can_trade": True, "validation_success": True},
                permission_snapshot=["trade"],
                api_key_encrypted="x",
                api_secret_encrypted="y",
            )
        )
        db.commit()

        result = validate_order_precheck(
            db,
            user_id=user.id,
            symbol="BTCUSDT",
            market_type="futures",
            order_type="market",
            side="buy",
            price=100000,
            size=0.001,
            leverage=1,
            margin_mode="isolated",
        )

        assert "explain" in result
        assert isinstance(result["explain"], list)
        assert len(result["explain"]) >= 1
    finally:
        db.close()


def test_screener_endpoint_rows_include_explain():
    db = SessionLocal()
    try:
        user = _create_user(db, email_prefix="explain-screener")
        db.add(
            UserScannerResult(
                run_id=f"run-{uuid.uuid4().hex[:8]}",
                user_id=user.id,
                symbol="BTCUSDT",
                strategy_code="spot_pullback_v1",
                signal="long",
                confidence=0.81,
                signal_score=87,
                reason_codes=["signal_detected"],
                payload={"rsi": 28, "volume_spike": 2.1, "price": 101, "ma50": 96, "timeframe": "1h"},
            )
        )
        db.commit()

        rows = list_filtered_screener_results(
            filters=None,
            rsi_min=None,
            rsi_max=None,
            volume_min=None,
            market_cap_min=None,
            timeframe=None,
            limit=20,
            current_user=user,
            db=db,
        )
        assert len(rows) >= 1
        assert isinstance(rows[0].explain, list)
        assert len(rows[0].explain) >= 1
    finally:
        db.close()
