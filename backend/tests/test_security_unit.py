# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


# ---------------------------------------------------------------------------
# hash_password / verify_password tests
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_and_verify_correct_password(self):
        hashed = hash_password("MySecureP@ss1")
        assert verify_password("MySecureP@ss1", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("MySecureP@ss1")
        assert verify_password("WrongPassword!", hashed) is False

    def test_hash_produces_different_output_each_time(self):
        h1 = hash_password("SamePassword1!")
        h2 = hash_password("SamePassword1!")
        assert h1 != h2  # bcrypt uses random salts

    def test_hash_does_not_return_plaintext(self):
        hashed = hash_password("TestPass123!")
        assert hashed != "TestPass123!"
        assert hashed.startswith("$2")  # bcrypt prefix

    def test_empty_password_hash_and_verify(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False


# ---------------------------------------------------------------------------
# create_access_token / decode_access_token tests
# ---------------------------------------------------------------------------

class TestAccessToken:
    def test_create_and_decode_roundtrip(self):
        token = create_access_token(
            subject="user-123",
            role="admin",
            email="test@example.com",
            device_id="dev-001",
        )
        payload = decode_access_token(token)
        assert payload["sub"] == "user-123"
        assert payload["role"] == "admin"
        assert payload["email"] == "test@example.com"
        assert payload["device_id"] == "dev-001"
        assert payload["mfa_verified"] is False

    def test_mfa_verified_flag(self):
        token = create_access_token(
            subject="user-456",
            role="user",
            email="user@example.com",
            mfa_verified=True,
            device_id="dev-002",
        )
        payload = decode_access_token(token)
        assert payload["mfa_verified"] is True
        assert payload["mfa_verified_at"] is not None

    def test_step_up_scope_included(self):
        token = create_access_token(
            subject="user-789",
            role="admin",
            email="admin@example.com",
            device_id="dev-003",
            step_up_scope=["trading", "admin"],
        )
        payload = decode_access_token(token)
        assert "trading" in payload["step_up_scope"]
        assert "admin" in payload["step_up_scope"]

    def test_decode_invalid_token_raises(self):
        with pytest.raises(ValueError, match="Invalid or expired token"):
            decode_access_token("not.a.valid.token")

    def test_decode_tampered_token_raises(self):
        token = create_access_token(
            subject="user-000",
            role="user",
            email="user@example.com",
            device_id="dev-000",
        )
        # Tamper with the token payload
        parts = token.split(".")
        parts[1] = parts[1][:-2] + "XX"
        tampered = ".".join(parts)
        with pytest.raises(ValueError, match="Invalid or expired token"):
            decode_access_token(tampered)

    def test_ip_hash_and_device_fingerprint(self):
        token = create_access_token(
            subject="user-fp",
            role="user",
            email="fp@example.com",
            device_id="dev-fp",
            ip_hash="abc123hash",
            device_fingerprint="fp-xyz-987",
        )
        payload = decode_access_token(token)
        assert payload["ip_hash"] == "abc123hash"
        assert payload["device_fingerprint"] == "fp-xyz-987"

    def test_empty_device_id_trimmed(self):
        token = create_access_token(
            subject="user-empty-dev",
            role="user",
            email="e@example.com",
            device_id="  ",
        )
        payload = decode_access_token(token)
        assert payload["device_id"] == ""

    def test_step_up_scope_empty_strings_filtered(self):
        token = create_access_token(
            subject="user-scope",
            role="user",
            email="s@example.com",
            device_id="dev-s",
            step_up_scope=["trading", "", "  ", "admin"],
        )
        payload = decode_access_token(token)
        assert payload["step_up_scope"] == ["trading", "admin"]
