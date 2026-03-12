import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


@pytest.fixture(scope="module")
def admin_headers():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL tanımlı değil")
    login_response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if login_response.status_code != 200:
        pytest.skip(f"Admin login başarısız: {login_response.text}")
    token = login_response.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_strategy_health_endpoint_contract(admin_headers):
    requests.post(
        f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
        headers=admin_headers,
        timeout=20,
    )
    response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-health", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    assert "strategy_health_score" in payload
    assert "health_components" in payload
    assert "lifecycle_state" in payload
    assert "drawdown_state" in payload


def test_strategy_governance_endpoint_contract(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-governance", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    expected_fields = [
        "strategy_health_score",
        "throttle_state",
        "disable_state",
        "decay_events",
        "health_components",
        "decay_reason_codes",
        "lifecycle_state",
        "last_transition_at",
        "drawdown_state",
        "strategy_compare_mode",
    ]
    for field in expected_fields:
        assert field in payload

    compare_mode = payload.get("strategy_compare_mode") or {}
    assert "weekly_auto_summary" in compare_mode
    assert "metrics" in compare_mode
