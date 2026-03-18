import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from db import SessionLocal
from models import User, UserRole
from services.audit_service import create_guard_audit_event
from services.guard_metrics_service import (
    build_guard_telemetry_payload,
    count_blocked_trades,
    count_overrides,
    top_block_reasons,
)


def _create_user(db, *, email_prefix: str, role: UserRole = UserRole.USER) -> User:
    row = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password("Pass1234!Aa"),
        role=role,
        is_active=True,
        approval_status="approved",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_guard_metrics_aggregate_counts_and_reasons():
    db = SessionLocal()
    try:
        user = _create_user(db, email_prefix="guard-telemetry-user")

        blocked_before = count_blocked_trades(db, last_24h=True)
        override_before = count_overrides(db, last_24h=True)

        create_guard_audit_event(
            db,
            event="EXECUTION_BLOCKED",
            reason="READINESS_FAIL",
            symbol="BTCUSDT",
            user_id=user.id,
            actor_user_id=user.id,
            actor_role=user.role.value,
            metadata={"mode": "mocked", "leverage": 20},
        )
        create_guard_audit_event(
            db,
            event="EXECUTION_BLOCKED",
            reason="LEVERAGE_TOO_HIGH",
            symbol="ETHUSDT",
            user_id=user.id,
            actor_user_id=user.id,
            actor_role=user.role.value,
            metadata={"mode": "mocked", "leverage": 125},
        )
        create_guard_audit_event(
            db,
            event="EXECUTION_OVERRIDE_ENABLED",
            reason="OVERRIDE_ACTIVE",
            symbol="BTCUSDT",
            user_id=user.id,
            actor_user_id=user.id,
            actor_role=user.role.value,
            metadata={"mode": "live"},
        )

        blocked_after = count_blocked_trades(db, last_24h=True)
        override_after = count_overrides(db, last_24h=True)

        assert blocked_after >= blocked_before + 2
        assert override_after >= override_before + 1

        reasons = top_block_reasons(db, last_24h=True)
        reason_codes = {item["reason"] for item in reasons}
        assert "READINESS_FAIL" in reason_codes
        assert "LEVERAGE_TOO_HIGH" in reason_codes

        payload = build_guard_telemetry_payload(db)
        assert isinstance(payload["blocked_24h"], int)
        assert isinstance(payload["override_24h"], int)
        assert isinstance(payload["top_reasons"], list)
    finally:
        db.close()


def test_guard_telemetry_payload_contract_is_crash_safe():
    db = SessionLocal()
    try:
        payload = build_guard_telemetry_payload(db)
        assert payload.get("blocked_24h") is not None
        assert payload.get("override_24h") is not None
        assert isinstance(payload.get("top_reasons"), list)
    finally:
        db.close()
