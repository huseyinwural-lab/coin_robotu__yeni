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


def test_scaling_validation_endpoint_contract(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/futures/scaling-validation", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    for field in ["scaling_performance_report", "scaling_robustness_score", "stress_replay_dashboard"]:
        assert field in payload


def test_scaling_report_endpoint_contract(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/futures/scaling-report", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    for field in ["scaling_performance_report", "scaling_robustness_score", "robustness_state"]:
        assert field in payload
