import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


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


def test_capital_budget_endpoint_contract(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/futures/capital-budget", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    assert "portfolio_capital_registry" in payload
    assert "strategy_capital_budget" in payload


def test_capital_usage_endpoint_contract(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/futures/capital-usage", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    assert "strategy_capital_usage" in payload
    assert "portfolio_risk_budget" in payload
    assert "capital_risk_actions" in payload


def test_capital_drift_endpoint_contract(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/futures/capital-drift", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    assert "drift_state" in payload
    assert "capital_drift_events" in payload
    assert "capital_drift_by_strategy" in payload
