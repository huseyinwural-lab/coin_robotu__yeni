# ruff: noqa: E402
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from server import app
from core.config import settings


ADMIN_EMAIL = (
    os.getenv("TEST_ADMIN_EMAIL")
    or os.getenv("ADMIN_BOOTSTRAP_EMAIL")
    or settings.bootstrap_admin_email
    or "admin@platform.local"
)
ADMIN_PASSWORD = (
    os.getenv("TEST_ADMIN_PASSWORD")
    or os.getenv("ADMIN_BOOTSTRAP_PASSWORD")
    or settings.bootstrap_admin_password
    or "Admin12345!"
)
USER_EMAIL = os.getenv("TEST_USER_EMAIL") or "testuser1773706589@example.com"
USER_PASSWORD = os.getenv("TEST_USER_PASSWORD") or "TestPassword123!"


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _ensure_user_login_token(client: TestClient) -> str:
    login = client.post(
        "/api/auth/login/user",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
    )
    if login.status_code == 200:
        token = login.json().get("access_token")
        assert token
        return token

    client.post(
        "/api/auth/register",
        json={"email": USER_EMAIL, "password": USER_PASSWORD, "role": "user"},
    )

    admin_login = client.post(
        "/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json().get("access_token")
    assert admin_token

    pending = client.get(
        "/api/auth/admin/user-approval-requests",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"status": "pending"},
    )
    assert pending.status_code == 200
    target_user = next((row for row in pending.json() if row.get("email") == USER_EMAIL), None)
    if target_user:
        approve = client.post(
            f"/api/auth/admin/user-approval-requests/{target_user['id']}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert approve.status_code == 200

    retry = client.post(
        "/api/auth/login/user",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
    )
    assert retry.status_code == 200
    token = retry.json().get("access_token")
    assert token
    return token


def test_prod_gate_health_ok(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json().get("status") == "ok"


def test_prod_gate_admin_login_ok(client: TestClient):
    response = client.post(
        "/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("access_token")


def test_prod_gate_user_login_and_readiness_checklist_ok(client: TestClient):
    token = _ensure_user_login_token(client)

    response = client.get(
        "/api/exchange/readiness-checklist",
        headers={"Authorization": f"Bearer {token}"},
        params={"exchange": "binance", "market_type": "futures", "environment": "testnet"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("exchange") == "binance"
    assert payload.get("market_type") == "futures"
