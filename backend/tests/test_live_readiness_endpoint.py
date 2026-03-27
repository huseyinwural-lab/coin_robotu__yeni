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


def test_live_readiness_endpoint_contract(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/futures/live-readiness", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    fields = [
        "readiness_score",
        "readiness_state",
        "go_live_allowed",
        "execution_allowed",
        "summary",
        "steps",
        "reason_codes",
        "data_freshness",
        "position_sync_state",
        "order_reconciliation_state",
        "balance_integrity_state",
        "exchange_latency_state",
        "alerts",
    ]
    for field in fields:
        assert field in payload


def test_readiness_score_endpoint_contract(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/futures/readiness-score", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    assert "readiness_score" in payload
    assert "readiness_state" in payload
