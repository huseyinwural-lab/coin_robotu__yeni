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


def test_correlation_matrix_endpoint_contract(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/futures/correlation-matrix", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    assert "correlation_matrix" in payload
    assert "symbols" in payload


def test_correlation_clusters_endpoint_contract(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/futures/correlation-clusters", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    assert "correlation_clusters" in payload
    assert "threshold" in payload


def test_cluster_risk_endpoint_contract(admin_headers):
    response = requests.get(f"{BASE_URL}/api/admin/futures/cluster-risk", headers=admin_headers, timeout=20)
    assert response.status_code == 200
    payload = response.json()
    required_fields = [
        "correlation_clusters",
        "cluster_exposures",
        "cluster_risk_alerts",
        "risk_state",
        "cluster_limits",
        "governance_audit_events",
    ]
    for field in required_fields:
        assert field in payload
