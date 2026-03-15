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
    assert token, "admin access_token missing"
    return {"Authorization": f"Bearer {token}"}


def _register_approve_login(prefix: str, admin_headers: dict) -> dict:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    password = "UserLiveDash123!"

    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert register.status_code == 200, register.text
    user_id = register.json()["id"]

    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=20,
    )
    assert approve.status_code == 200, approve.text

    login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "email": email}


def _create_user_bot(headers: dict, bot_name: str, symbol: str):
    response = requests.post(
        f"{BASE_URL}/api/bot-profiles",
        headers=headers,
        json={
            "name": bot_name,
            "exchange": "binance",
            "market_type": "spot",
            "symbols": [symbol],
            "strategy_type": "spot_pullback_v1",
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 1,
            "is_enabled": True,
        },
        timeout=20,
    )
    assert response.status_code == 200, response.text


@pytest.fixture(scope="module")
def scope_context():
    admin_headers = _admin_headers()
    user_a = _register_approve_login("scope_a", admin_headers)
    user_b = _register_approve_login("scope_b", admin_headers)

    _create_user_bot(user_a["headers"], "scope-bot-a", "SCOPEAUSDT")
    _create_user_bot(user_b["headers"], "scope-bot-b", "SCOPEBUSDT")

    return {
        "user_a_headers": user_a["headers"],
        "user_b_headers": user_b["headers"],
    }


def test_user_only_sees_own_trade_payload(scope_context):
    response = requests.get(
        f"{BASE_URL}/api/user/live/trades",
        params={"window": "24h"},
        headers=scope_context["user_a_headers"],
        timeout=30,
    )
    assert response.status_code == 200, response.text
    payload_text = str(response.json())
    assert "SCOPEBUSDT" not in payload_text


def test_user_cannot_see_other_users_bot_scope(scope_context):
    response_a = requests.get(
        f"{BASE_URL}/api/user/live/summary",
        params={"window": "1h"},
        headers=scope_context["user_a_headers"],
        timeout=30,
    )
    response_b = requests.get(
        f"{BASE_URL}/api/user/live/summary",
        params={"window": "1h"},
        headers=scope_context["user_b_headers"],
        timeout=30,
    )

    assert response_a.status_code == 200, response_a.text
    assert response_b.status_code == 200, response_b.text

    payload_a = response_a.json()
    payload_b = response_b.json()

    assert payload_a["bots"]["total_bots"] >= 1
    assert payload_b["bots"]["total_bots"] >= 1

    assert "scope-bot-a" in str(payload_a["bots"].get("bot_names", []))
    assert "scope-bot-b" not in str(payload_a["bots"].get("bot_names", []))