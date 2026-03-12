import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


@pytest.fixture(scope="module")
def admin_token():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL tanımlı değil")
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login başarısız: {response.text}")
    return response.json()["access_token"]


def test_strategy_run_paper_cycle_endpoint(admin_token):
    response = requests.post(
        f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("strategy") == "futures_trend_follow_v1"
    assert "metrics" in data
    assert "decision_trace" in data


def test_strategy_status_endpoint_returns_required_sections(admin_token):
    response = requests.get(
        f"{BASE_URL}/api/admin/futures/strategy/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert response.status_code == 200
    data = response.json()
    assert "signal_feed" in data
    assert "decision_trace" in data
    assert "paper_pnl_series" in data
    assert "reject_reason_breakdown" in data
    assert "confidence_distribution" in data
