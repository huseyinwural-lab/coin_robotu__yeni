import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL is required")


def _admin_headers():
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": "admin@platform.local", "password": "Admin12345!"},
        timeout=30,
    )
    assert response.status_code == 200
    token = response.json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def test_validate_order_api_returns_contract_and_violations():
    headers_admin = _admin_headers()
    email = f"validate-api-{uuid.uuid4().hex[:8]}@example.com"
    password = "ValidateApi123!"

    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert register.status_code == 200
    user_id = register.json().get("id")

    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=headers_admin,
        timeout=30,
    )
    assert approve.status_code == 200

    login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert login.status_code == 200
    token = login.json().get("access_token")
    headers_user = {"Authorization": f"Bearer {token}"}

    response = requests.post(
        f"{BASE_URL}/api/user/validate-order",
        headers=headers_user,
        json={
            "symbol": "BTCUSDT",
            "market_type": "futures",
            "order_type": "market",
            "side": "buy",
            "price": 100,
            "size": 0.0001,
            "leverage": 100,
            "margin_mode": "isolated",
        },
        timeout=30,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("valid") is False
    assert isinstance(payload.get("violations"), list)
    assert len(payload.get("violations") or []) > 0
    assert payload.get("execution_mode") in {"mocked", "live"}
