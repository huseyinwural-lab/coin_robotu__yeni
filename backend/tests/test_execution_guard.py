# ruff: noqa: E402
import sys
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from db import SessionLocal
from models import AuditLog, User, UserRole
from services.execution_readiness_service import enforce_execution_guard_or_raise


def test_execution_guard_blocks_with_423_and_writes_audit_event():
    db = SessionLocal()
    try:
        user = User(
            email=f"guard-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("GuardPass123!"),
            role=UserRole.USER,
            is_active=True,
            approval_status="approved",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        with pytest.raises(HTTPException) as exc:
            enforce_execution_guard_or_raise(
                db,
                user_id=user.id,
                actor_user_id=user.id,
                actor_role=user.role.value,
                source="unit_test_execution_guard",
            )
        assert exc.value.status_code == 423
        assert exc.value.detail == "EXECUTION_BLOCKED_BY_READINESS"

        audit_row = (
            db.query(AuditLog)
            .filter(AuditLog.actor_user_id == user.id, AuditLog.action == "EXECUTION_BLOCKED")
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        assert audit_row is not None
    finally:
        db.close()
