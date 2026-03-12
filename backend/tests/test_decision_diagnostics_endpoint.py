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
            timeout=25,
        )
    except requests.RequestException as exc:
        pytest.skip(f"Auth endpoint erişilemedi: {exc}")
    if response.status_code != 200:
        pytest.skip(f"Admin login başarısız: {response.text}")
    return response.json()["access_token"]


def test_decision_diagnostics_endpoint_contract(admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = requests.get(
        f"{BASE_URL}/api/admin/futures/decision-diagnostics",
        headers=headers,
        timeout=25,
    )
    assert response.status_code == 200
    payload = response.json()

    assert "false_allow_count" in payload
    assert "false_reject_count" in payload
    assert "gate_reason_distribution" in payload
    assert "confidence_vs_result" in payload
    assert "decision_layer_distribution" in payload
    assert "updated_at" in payload
