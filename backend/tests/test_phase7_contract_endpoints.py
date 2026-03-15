import os
import random
import string
from pathlib import Path

import pytest
import requests

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        if raw.strip().startswith("REACT_APP_BACKEND_URL="):
            return raw.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _resolve_base_url()


def _create_user_token() -> str:
    email = f"phase7ct_{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}@example.com"
    password = "Phase7Ct123!"
    register = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": password}, timeout=20)
    assert register.status_code == 200
    user_id = register.json()["id"]

    admin_login = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    admin_token = admin_login.json()["access_token"]
    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert approve.status_code == 200

    login = requests.post(f"{BASE_URL}/api/auth/login/user", json={"email": email, "password": password}, timeout=20)
    assert login.status_code == 200
    return login.json()["access_token"]


@pytest.fixture(scope="module")
def user_headers():
    token = _create_user_token()
    return {"Authorization": f"Bearer {token}"}


def test_user_dashboard_contract_endpoint(user_headers):
    response = requests.get(f"{BASE_URL}/api/user/dashboard", headers=user_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    required = {
        "bot_count",
        "running_bot_count",
        "risk_policy_count",
        "current_capital",
        "available_balance",
        "open_positions_count",
        "pending_signals_count",
        "heartbeat",
    }
    assert required.issubset(set(payload.keys()))


def test_user_scanner_contract_endpoint(user_headers):
    response = requests.get(f"{BASE_URL}/api/user/scanner", headers=user_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    assert {"mode", "total_results", "pending_signals", "latest_run_id", "latest_generated_at"}.issubset(set(payload.keys()))


def test_user_reports_weekly_live_returns_200(user_headers):
    response = requests.get(f"{BASE_URL}/api/user/reports/weekly", headers=user_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    assert "report_id" in payload
    assert "download_links" in payload