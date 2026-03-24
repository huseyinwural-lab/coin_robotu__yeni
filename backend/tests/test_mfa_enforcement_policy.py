import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.mfa_service import is_mfa_enforcement_required


def test_mfa_enforcement_auto_production(monkeypatch):
    monkeypatch.setenv("MFA_ENFORCEMENT_MODE", "auto")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("MFA_OPTIONAL_OVERRIDE_EMAILS", raising=False)
    assert is_mfa_enforcement_required(user_email="admin@example.com", endpoint_scope="admin") is True


def test_mfa_enforcement_auto_preview_optional(monkeypatch):
    monkeypatch.setenv("MFA_ENFORCEMENT_MODE", "auto")
    monkeypatch.setenv("APP_ENV", "preview")
    monkeypatch.delenv("MFA_OPTIONAL_OVERRIDE_EMAILS", raising=False)
    assert is_mfa_enforcement_required(user_email="admin@example.com", endpoint_scope="admin") is False


def test_mfa_enforcement_override_email(monkeypatch):
    monkeypatch.setenv("MFA_ENFORCEMENT_MODE", "auto")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MFA_OPTIONAL_OVERRIDE_EMAILS", "canary.admin@platform.local,other@example.com")
    assert is_mfa_enforcement_required(user_email="canary.admin@platform.local", endpoint_scope="admin") is False


def test_mfa_enforcement_forced(monkeypatch):
    monkeypatch.setenv("MFA_ENFORCEMENT_MODE", "enforce")
    monkeypatch.delenv("MFA_OPTIONAL_OVERRIDE_EMAILS", raising=False)
    assert is_mfa_enforcement_required(user_email="x@example.com", endpoint_scope="user") is True


def test_mfa_enforcement_optional_mode(monkeypatch):
    monkeypatch.setenv("MFA_ENFORCEMENT_MODE", "optional")
    monkeypatch.setenv("APP_ENV", "production")
    assert is_mfa_enforcement_required(user_email="x@example.com", endpoint_scope="admin") is False
