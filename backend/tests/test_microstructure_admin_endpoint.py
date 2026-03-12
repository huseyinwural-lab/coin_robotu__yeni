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
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
    except requests.RequestException as exc:
        pytest.skip(f"Auth endpoint erişilemedi: {exc}")
    if response.status_code != 200:
        pytest.skip(f"Admin login başarısız: {response.text}")
    return response.json()["access_token"]


def test_microstructure_admin_endpoint_contract(admin_token):
    response = requests.get(
        f"{BASE_URL}/api/admin/futures/microstructure/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert response.status_code == 200
    data = response.json()
    assert "portfolio_microstructure_state" in data
    assert "portfolio_microstructure_risk_score" in data
    assert "symbols_at_risk" in data
    assert "gate_rejections" in data
    assert "execution_suitability" in data


def test_strategy_endpoint_still_returns_decision_trace(admin_token):
    requests.post(
        f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    response = requests.get(
        f"{BASE_URL}/api/admin/futures/strategy/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert response.status_code == 200
    data = response.json()
    assert "decision_trace" in data
    assert isinstance(data.get("decision_trace"), list)
