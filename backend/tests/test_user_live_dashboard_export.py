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
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _register_approve_login(prefix: str, admin_headers: dict) -> dict:
    password = "UserLiveExport123!"
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"

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
    return {"email": email, "headers": {"Authorization": f"Bearer {login.json()['access_token']}"}}


def _create_bot(headers: dict, bot_name: str, symbol: str):
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
def export_context():
    admin_headers = _admin_headers()
    user_a = _register_approve_login("export_a", admin_headers)
    user_b = _register_approve_login("export_b", admin_headers)

    _create_bot(user_a["headers"], "export-bot-a", "EXPAUSDT")
    _create_bot(user_b["headers"], "export-bot-b", "EXPBUSDT")

    return {
        "user_a_headers": user_a["headers"],
        "user_b_email": user_b["email"],
    }


def test_user_export_contains_only_user_scope_data(export_context):
    json_response = requests.get(
        f"{BASE_URL}/api/user/live/daily-report/export",
        params={"format": "json", "window": "24h"},
        headers=export_context["user_a_headers"],
        timeout=30,
    )
    assert json_response.status_code == 200, json_response.text
    json_payload_text = str(json_response.json())
    assert export_context["user_b_email"] not in json_payload_text

    csv_response = requests.get(
        f"{BASE_URL}/api/user/live/daily-report/export",
        params={"format": "csv", "window": "24h"},
        headers=export_context["user_a_headers"],
        timeout=30,
    )
    assert csv_response.status_code == 200, csv_response.text
    assert "text/csv" in csv_response.headers.get("content-type", "")
    assert export_context["user_b_email"] not in csv_response.text