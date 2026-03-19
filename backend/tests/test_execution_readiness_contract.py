# ruff: noqa: E402
import sys
import uuid
from pathlib import Path

from fastapi import HTTPException

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from db import SessionLocal
from models import User, UserExchangeConnection, UserRole
from services.execution_readiness_service import (
    enforce_execution_guard_or_raise,
    evaluate_execution_readiness,
    validate_order_precheck,
)


def _create_user(db, *, email_prefix: str) -> User:
    user = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password("Pass1234!Aa"),
        role=UserRole.USER,
        is_active=True,
        approval_status="approved",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_execution_readiness_blocked_when_no_connection():
    db = SessionLocal()
    try:
        user = _create_user(db, email_prefix="readiness-none")
        readiness = evaluate_execution_readiness(db, user_id=user.id)
        assert readiness["final_status"] == "BLOCKED"
        assert "no_exchange_connection" in (readiness.get("reason_codes") or [])
    finally:
        db.close()


def test_execution_readiness_mocked_ready_when_connection_exists():
    db = SessionLocal()
    try:
        user = _create_user(db, email_prefix="readiness-mocked")
        row = UserExchangeConnection(
            user_id=user.id,
            account_label="default",
            exchange="bybit",
            market_type="futures",
            environment="testnet",
            is_default=True,
            readiness_snapshot={
                "connection_health": "offline",
                "can_trade": False,
                "validation_latency_ms": 12,
            },
            permission_snapshot=[],
            api_key_encrypted="",
            api_secret_encrypted="",
        )
        db.add(row)
        db.commit()

        readiness = evaluate_execution_readiness(db, user_id=user.id)
        assert readiness["mode"] == "MOCKED"
        assert readiness["mocked_flag"] is True
        assert readiness["final_status"] == "READY"
    finally:
        db.close()


def test_execution_guard_raises_423_when_blocked():
    db = SessionLocal()
    try:
        user = _create_user(db, email_prefix="guard-block")
        try:
            enforce_execution_guard_or_raise(
                db,
                user_id=user.id,
                actor_user_id=user.id,
                actor_role=user.role.value,
                source="unit_test",
            )
            assert False, "guard should block"
        except HTTPException as exc:
            assert exc.status_code == 423
    finally:
        db.close()


def test_validate_order_precheck_returns_violations_for_limit_breach():
    db = SessionLocal()
    try:
        user = _create_user(db, email_prefix="precheck")
        row = UserExchangeConnection(
            user_id=user.id,
            account_label="default",
            exchange="bybit",
            market_type="futures",
            environment="testnet",
            is_default=True,
            readiness_snapshot={"connection_health": "online", "can_trade": True},
            permission_snapshot=["trade"],
            api_key_encrypted="x",
            api_secret_encrypted="y",
        )
        db.add(row)
        db.commit()

        result = validate_order_precheck(
            db,
            user_id=user.id,
            symbol="BTCUSDT",
            market_type="futures",
            order_type="market",
            side="buy",
            price=1000,
            size=10,
            leverage=99,
            margin_mode="isolated",
        )
        assert result["valid"] is False
        assert len(result["violations"]) >= 1
    finally:
        db.close()
