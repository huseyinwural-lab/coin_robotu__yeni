# ruff: noqa: E402
import uuid
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password, verify_password
from db import SessionLocal
from models import User, UserOnboardingProfile, UserRole
from services.password_reset_service import (
    consume_password_reset_token,
    issue_password_reset_token,
    validate_password_strength,
)


def _create_test_user(db):
    unique = uuid.uuid4().hex[:10]
    email = f"reset-{unique}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("OldPass123!"),
        role=UserRole.USER,
        is_active=True,
        approval_status="approved",
    )
    db.add(user)
    db.flush()

    onboarding = UserOnboardingProfile(user_id=user.id, email_verified=True)
    db.add(onboarding)
    db.commit()
    db.refresh(user)
    return user


def test_validate_password_strength_requires_symbol():
    with pytest.raises(HTTPException) as exc:
        validate_password_strength("StrongPass12")
    assert exc.value.status_code == 400
    assert exc.value.detail == "password_requires_symbol"


def test_issue_password_reset_token_returns_none_for_unknown_email():
    db = SessionLocal()
    try:
        payload = issue_password_reset_token(db, "missing-user@example.com")
        assert payload["user"] is None
        assert payload["token"] is None
    finally:
        db.close()


def test_issue_and_consume_password_reset_token_updates_password_and_clears_token():
    db = SessionLocal()
    try:
        user = _create_test_user(db)

        issued = issue_password_reset_token(db, user.email)
        assert issued["user"] is not None
        assert issued["token"]

        updated = consume_password_reset_token(db, issued["token"], "NewPass1234!")
        assert updated.id == user.id
        assert verify_password("NewPass1234!", updated.password_hash)

        profile = db.query(UserOnboardingProfile).filter(UserOnboardingProfile.user_id == user.id).first()
        assert profile is not None
        assert profile.password_reset_token_hash is None
        assert profile.password_reset_expires_at is None
    finally:
        db.close()
