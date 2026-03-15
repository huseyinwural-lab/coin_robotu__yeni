import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


@pytest.fixture(scope="module")
def admin_token():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL tanımlı değil")
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=25,
        )
    except requests.RequestException as exc:
        pytest.skip(f"Auth endpoint erişilemedi: {exc}")
    if response.status_code != 200:
        pytest.skip(f"Admin login başarısız: {response.text}")
    return response.json()["access_token"]


def test_diagnostics_metrics_are_present_after_strategy_cycle(admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    run_response = requests.post(
        f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
        headers=headers,
        timeout=25,
    )
    assert run_response.status_code == 200

    strategy_status = requests.get(
        f"{BASE_URL}/api/admin/futures/strategy/status",
        headers=headers,
        timeout=25,
    )
    assert strategy_status.status_code == 200
    payload = strategy_status.json()
    diagnostics = payload.get("decision_diagnostics") or {}

    assert "false_allow_count" in diagnostics
    assert "false_reject_count" in diagnostics
    assert "gate_reason_distribution" in diagnostics
    assert "confidence_vs_result" in diagnostics
    assert "decision_layer_distribution" in diagnostics
