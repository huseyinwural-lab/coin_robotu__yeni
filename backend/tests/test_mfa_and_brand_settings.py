# ruff: noqa: E402
import io
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from db import SessionLocal
from models import User, UserRole
from server import fastapi_app


client = TestClient(fastapi_app)


def _create_approved_user(email_prefix: str, role: UserRole = UserRole.USER) -> tuple[str, str]:
    db = SessionLocal()
    try:
        email = f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.com"
        password = "Pass1234!Aa"
        row = User(
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
            approval_status="approved",
        )
        db.add(row)
        db.commit()
        return email, password
    finally:
        db.close()


def _admin_login_headers() -> dict:
    response = client.post("/api/auth/login/admin", json={"email": "admin@platform.local", "password": "Admin12345!"})
    assert response.status_code == 200
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


def test_brand_settings_update_and_logo_upload_roundtrip():
    headers = _admin_login_headers()

    update = client.put("/api/admin/brand-settings", headers=headers, json={"app_name": "XILO BRAND QA"})
    assert update.status_code == 200
    assert update.json().get("app_name") == "XILO BRAND QA"

    payload = io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\nIDATx\x9cc``\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82")
    files = {"file": ("brand.png", payload, "image/png")}
    upload = client.post("/api/admin/brand-settings/logo-upload", headers=headers, files=files)
    assert upload.status_code == 200
    assert upload.json().get("has_logo") is True

    public_settings = client.get("/api/branding/settings")
    assert public_settings.status_code == 200
    assert public_settings.json().get("logo_url") == "/api/branding/logo"

    logo = client.get("/api/branding/logo")
    assert logo.status_code == 200
    assert logo.headers.get("content-type", "").startswith("image/")


def test_optional_mfa_login_flow_email_method():
    email, password = _create_approved_user("mfa-user")

    login_plain = client.post("/api/auth/login/user", json={"email": email, "password": password})
    assert login_plain.status_code == 200
    plain_token = login_plain.json().get("access_token")
    assert plain_token
    headers = {"Authorization": f"Bearer {plain_token}"}

    put_settings = client.put(
        "/api/auth/mfa/settings",
        headers=headers,
        json={"is_enabled": True, "enabled_methods": ["email"]},
    )
    assert put_settings.status_code == 200
    assert put_settings.json().get("is_enabled") is True

    login_mfa = client.post("/api/auth/login/user", json={"email": email, "password": password})
    assert login_mfa.status_code == 200
    body = login_mfa.json()
    assert body.get("mfa_required") is True
    assert "email" in (body.get("mfa_methods") or [])
    challenge_token = body.get("mfa_challenge_token")
    preview_code = body.get("email_code_preview")
    assert challenge_token
    assert preview_code

    verify = client.post(
        "/api/auth/mfa/challenge/verify",
        json={
            "challenge_token": challenge_token,
            "method": "email",
            "code": preview_code,
        },
    )
    assert verify.status_code == 200
    assert verify.json().get("access_token")
