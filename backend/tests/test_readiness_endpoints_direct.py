import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "canary.admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "CanaryAdmin123!")

if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL tanımlı değil", allow_module_level=True)


@pytest.fixture(scope="module")
def admin_headers():
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login başarısız: {response.status_code}")
    token = response.json().get("access_token")
    if not token:
        pytest.skip("Admin token alınamadı")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_live_readiness_endpoint_contract(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/futures/live-readiness", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()

    required_fields = [
        "readiness_score",
        "readiness_state",
        "go_live_allowed",
        "execution_allowed",
        "summary",
        "steps",
        "scores",
        "by_layer",
        "blocking_failures",
        "warnings",
        "unknowns",
        "reason_codes",
        "data_freshness",
    ]
    for field in required_fields:
        assert field in payload

    expected_layers = ["core", "trading_state", "exchange", "execution", "risk", "infra", "latency", "safety"]
    for layer in expected_layers:
        assert layer in payload.get("scores", {})
        assert layer in payload.get("by_layer", {})


def test_execution_readiness_endpoint_contract(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/execution-readiness", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()

    required_fields = [
        "exchange_connection",
        "permissions",
        "latency_ms",
        "order_test",
        "mode",
        "final_status",
        "mocked_flag",
        "reason_codes",
        "readiness_state",
        "execution_allowed",
        "go_live_allowed",
    ]
    for field in required_fields:
        assert field in payload

    if payload.get("final_status") == "BLOCKED":
        assert payload.get("execution_allowed") is False


def test_strategy_engine_unknown_blocks_readiness(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/futures/live-readiness", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()

    strategy_step = next((s for s in payload.get("steps", []) if s.get("step_key") == "strategy_engine"), None)
    assert strategy_step is not None
    assert strategy_step.get("status") == "UNKNOWN"
    assert payload.get("go_live_allowed") is False
    assert payload.get("execution_allowed") is False
    assert "STRATEGY_ENGINE_UNKNOWN" in (payload.get("reason_codes") or [])
