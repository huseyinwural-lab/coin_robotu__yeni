import os
import uuid
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    env_base = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if env_base:
        return env_base
    frontend_env = Path("/app/frontend/.env")
    if frontend_env.exists():
        for line in frontend_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL bulunamadı")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


def _admin_headers() -> dict:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


def _new_user_headers() -> dict:
    email = f"live_pag_{uuid.uuid4().hex[:8]}@example.com"
    password = "LivePagination123!"
    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert register.status_code == 200, register.text
    user_id = register.json()["id"]

    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=_admin_headers(),
        timeout=20,
    )
    assert approve.status_code == 200, approve.text

    login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert login.status_code == 200, login.text
    token = login.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def user_headers():
    return _new_user_headers()


def test_live_dashboard_trades_pagination_contract(user_headers):
    response = requests.get(
        f"{BASE_URL}/api/user/live/trades",
        params={"window": "24h", "limit": 5, "offset": 0},
        headers=user_headers,
        timeout=30,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("limit") == 5
    assert payload.get("offset") == 0
    assert "trades_count" in payload
    assert "total_trades_count" in payload
    assert isinstance(payload.get("items"), list)
    assert payload.get("trades_count") <= 5


def test_live_dashboard_positions_pagination_contract(user_headers):
    response = requests.get(
        f"{BASE_URL}/api/user/live/positions",
        params={"limit": 3, "offset": 0},
        headers=user_headers,
        timeout=30,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("limit") == 3
    assert payload.get("offset") == 0
    assert "positions_count" in payload
    assert "total_positions_count" in payload
    assert isinstance(payload.get("positions"), list)
    assert payload.get("positions_count") <= 3


def test_live_dashboard_strategies_pagination_contract(user_headers):
    response = requests.get(
        f"{BASE_URL}/api/user/live/strategies",
        params={"window": "24h", "limit": 2, "offset": 0},
        headers=user_headers,
        timeout=30,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("limit") == 2
    assert payload.get("offset") == 0
    assert "strategy_count" in payload
    assert "total_strategy_count" in payload
    assert isinstance(payload.get("items"), list)
    assert payload.get("strategy_count") <= 2