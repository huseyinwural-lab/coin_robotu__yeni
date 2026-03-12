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


def test_strategy_performance_endpoint_contract(admin_headers):
    requests.post(
        f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
        headers=admin_headers,
        timeout=20,
    )
    response = requests.get(
        f"{BASE_URL}/api/admin/futures/strategy-performance",
        headers=admin_headers,
        timeout=20,
    )
    assert response.status_code == 200
    payload = response.json()
    required_fields = [
        "strategy_registry",
        "strategy_pnl_contribution",
        "strategy_signal_distribution",
        "exposure_tracking",
        "interaction_guard",
        "strategy_attribution",
        "strategy_drift_alerts",
    ]
    for field in required_fields:
        assert field in payload


def test_strategy_execution_quality_endpoint_contract(admin_headers):
    response = requests.get(
        f"{BASE_URL}/api/admin/futures/strategy-execution-quality",
        headers=admin_headers,
        timeout=20,
    )
    assert response.status_code == 200
    payload = response.json()
    required_fields = [
        "strategy_execution_quality",
        "strategy_slippage",
        "strategy_latency",
        "strategy_reject_rate",
        "strategy_confidence_vs_result",
        "rolling_7d_tuning_score",
        "strategy_drift_alerts",
        "false_allow_reject_comparison_by_strategy",
        "gate_reason_trend_7d",
        "architecture_checklist_15",
    ]
    for field in required_fields:
        assert field in payload
    assert len(payload.get("gate_reason_trend_7d") or []) == 7
    assert len(payload.get("architecture_checklist_15") or []) == 15
