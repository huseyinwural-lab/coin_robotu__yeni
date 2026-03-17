import os
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            if raw_line.startswith("REACT_APP_BACKEND_URL="):
                return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


@pytest.fixture(scope="module")
def admin_headers() -> dict:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, response.text
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


def test_futures_live_path_check_summary(admin_headers: dict):
    response = requests.get(
        f"{BASE_URL}/api/admin/users/futures-live-path-check",
        params={"limit": 100},
        headers=admin_headers,
        timeout=20,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "total_users" in payload
    assert "pass_count" in payload
    assert "fail_count" in payload
    assert "items" in payload


def test_futures_live_path_check_single_user(admin_headers: dict):
    users = requests.get(
        f"{BASE_URL}/api/admin/users",
        params={"scope": "user", "status": "all", "limit": 20},
        headers=admin_headers,
        timeout=20,
    )
    assert users.status_code == 200, users.text
    rows = users.json()
    if not rows:
        pytest.skip("No approved users available")

    user_id = rows[0]["id"]
    response = requests.get(
        f"{BASE_URL}/api/admin/users/{user_id}/futures-live-path-check",
        headers=admin_headers,
        timeout=20,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("user_id") == user_id
    assert payload.get("status") in {"PASS", "FAIL"}


def test_system_alert_burn_in_endpoint(admin_headers: dict):
    response = requests.get(
        f"{BASE_URL}/api/admin/system-alerts/burn-in",
        params={"days": 7},
        headers=admin_headers,
        timeout=20,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("window_days") == 7
    assert "total_alerts" in payload
    assert "critical_ratio" in payload
    assert "delivery" in payload


def test_system_alert_test_delivery_invalid_channel(admin_headers: dict):
    response = requests.post(
        f"{BASE_URL}/api/admin/system-alerts/test-delivery",
        json={"channel": "webhook", "severity": "WARNING"},
        headers=admin_headers,
        timeout=20,
    )
    assert response.status_code == 400, response.text


def test_system_alert_test_delivery_slack(admin_headers: dict):
    response = requests.post(
        f"{BASE_URL}/api/admin/system-alerts/test-delivery",
        json={"channel": "slack", "severity": "WARNING"},
        headers=admin_headers,
        timeout=20,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("channel") == "slack"
    assert "result" in payload