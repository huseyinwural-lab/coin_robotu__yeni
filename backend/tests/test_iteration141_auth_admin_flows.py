"""
Iteration 141 - Tests for auth login (P0 blocker fix), admin system alerts, and audit logs
Validates the regression fix around auth login 500 and critical admin flows.
"""

import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL is required for integration tests")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@platform.local", "password": "Admin12345!"},
        timeout=30,
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin authentication failed: {response.status_code} - {response.text[:200]}")


@pytest.fixture
def admin_headers(admin_token):
    """Headers with admin auth"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestAuthLogin:
    """Auth login endpoint tests - P0 blocker regression"""

    def test_login_returns_200_with_valid_credentials(self):
        """Previous P0 blocker was 500 on login - must return 200"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@platform.local", "password": "Admin12345!"},
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == "admin@platform.local"
        assert data["user"]["role"] == "super_admin"
        assert data["token_type"] == "bearer"

    def test_login_returns_401_with_invalid_credentials(self):
        """Should return 401 for invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "invalid@test.com", "password": "wrongpassword"},
            timeout=30,
        )
        assert response.status_code == 401


class TestAdminSystemAlerts:
    """Admin system alerts burn-in endpoint tests"""

    def test_burn_in_returns_200_with_admin_auth(self, admin_headers):
        """GET /api/admin/system-alerts/burn-in should work with admin auth"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts/burn-in",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        assert "window_days" in data
        assert "generated_at" in data
        assert "total_alerts" in data
        assert "severity_breakdown" in data
        assert "status_breakdown" in data
        assert "recommendation" in data

    def test_burn_in_requires_auth(self):
        """Burn-in endpoint should require authentication"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts/burn-in",
            timeout=30,
        )
        # Should be 401 or 403 without auth
        assert response.status_code in [401, 403]


class TestAuditLogsTimeline:
    """Audit logs timeline endpoint tests"""

    def test_timeline_returns_200_with_admin_auth(self, admin_headers):
        """GET /api/audit-logs/timeline should work with admin auth"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        assert "total" in data
        assert "items" in data
        assert isinstance(data["items"], list)
        
        if data["items"]:
            item = data["items"][0]
            assert "id" in item
            assert "action" in item
            assert "entity_type" in item
            assert "created_at" in item

    def test_timeline_requires_auth(self):
        """Timeline endpoint should require authentication"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline",
            timeout=30,
        )
        assert response.status_code in [401, 403]


class TestAuditLogsIncidentExport:
    """Audit logs incident export endpoint tests"""

    def test_incident_export_returns_zip(self, admin_headers):
        """GET /api/audit-logs/admin/incident-export?window_days=7 should return ZIP"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/admin/incident-export?window_days=7",
            headers=admin_headers,
            timeout=60,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "application/zip" in response.headers.get("content-type", "")
        assert len(response.content) > 0

    def test_incident_export_requires_auth(self):
        """Incident export should require authentication"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/admin/incident-export?window_days=7",
            timeout=30,
        )
        assert response.status_code in [401, 403]


class TestHealthEndpoint:
    """Basic health check"""

    def test_health_returns_200(self):
        """Health endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert response.status_code == 200
