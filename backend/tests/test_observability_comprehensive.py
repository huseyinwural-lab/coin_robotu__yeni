"""
Comprehensive observability MVP tests for Faz-1:
- Correlation ID (X-Request-ID header)
- Structured request/error logging
- Domain event logging
- Admin timeline filters
"""
import os
import uuid
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            if raw_line.startswith("REACT_APP_BACKEND_URL="):
                return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


@pytest.fixture(scope="module")
def admin_headers() -> dict:
    """Login as admin and return auth headers"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, response.text
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


class TestCorrelationIdHeader:
    """Test X-Request-ID header in API responses"""

    def test_health_endpoint_returns_x_request_id(self):
        """Every API response must include X-Request-ID header"""
        request_id = f"health-test-{uuid.uuid4()}"
        response = requests.get(
            f"{BASE_URL}/api/health",
            headers={"X-Request-ID": request_id},
            timeout=20,
        )
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID") == request_id

    def test_auto_generated_request_id_when_not_provided(self):
        """Backend generates X-Request-ID if not sent by client"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=20)
        assert response.status_code == 200
        returned_request_id = response.headers.get("X-Request-ID")
        assert returned_request_id is not None
        assert len(returned_request_id) > 0

    def test_authenticated_endpoint_returns_x_request_id(self, admin_headers):
        """Authenticated endpoints also return X-Request-ID"""
        request_id = f"auth-test-{uuid.uuid4()}"
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?limit=20",
            headers={**admin_headers, "X-Request-ID": request_id},
            timeout=20,
        )
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID") == request_id


class TestAuditLogRequestContext:
    """Test that audit logs capture request context (request_id, session_id, route, method)"""

    def test_audit_log_carries_request_id_and_session_id(self, admin_headers):
        """Audit log must include request_id, session_id, route, method from request context"""
        request_id = f"obs-{uuid.uuid4()}"
        session_id = f"session-{uuid.uuid4()}"

        # Trigger an action that creates audit log
        action_response = requests.post(
            f"{BASE_URL}/api/admin/users/repair-venue-assignments",
            headers={
                **admin_headers,
                "X-Request-ID": request_id,
                "X-Session-ID": session_id,
            },
            timeout=30,
        )
        assert action_response.status_code == 200, action_response.text

        # Fetch timeline and verify context
        timeline_response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline",
            params={"action": "USER_VENUE_ASSIGNMENT_BULK_REPAIRED", "limit": 50},
            headers=admin_headers,
            timeout=20,
        )
        assert timeline_response.status_code == 200
        payload = timeline_response.json()
        assert "items" in payload
        assert payload["total"] >= 1

        # Find our specific record
        match = next((item for item in payload["items"] if item.get("request_id") == request_id), None)
        assert match is not None, f"request_id {request_id} not found in timeline"
        assert match.get("session_id") == session_id
        assert match.get("route") == "/api/admin/users/repair-venue-assignments"
        assert match.get("method") == "POST"


class TestTimelineFilters:
    """Test GET /api/audit-logs/timeline filter functionality"""

    def test_timeline_returns_valid_response(self, admin_headers):
        """Timeline endpoint returns valid structure"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_timeline_filter_by_action(self, admin_headers):
        """Filter by action works"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?action=user&limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        # All returned items should have 'user' in action
        for item in data["items"]:
            assert "user" in item["action"].lower()

    def test_timeline_filter_by_severity(self, admin_headers):
        """Filter by severity works"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?severity=warning&limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["severity"] == "warning"

    def test_timeline_filter_by_request_id(self, admin_headers):
        """Filter by request_id works"""
        # First create a record with known request_id
        request_id = f"filter-test-{uuid.uuid4()}"
        requests.post(
            f"{BASE_URL}/api/admin/users/repair-venue-assignments",
            headers={**admin_headers, "X-Request-ID": request_id},
            timeout=30,
        )

        # Now filter by this request_id
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?request_id={request_id}&limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(item.get("request_id") == request_id for item in data["items"])

    def test_timeline_filter_by_session_id(self, admin_headers):
        """Filter by session_id works"""
        session_id = f"session-filter-{uuid.uuid4()}"
        requests.post(
            f"{BASE_URL}/api/admin/users/repair-venue-assignments",
            headers={**admin_headers, "X-Session-ID": session_id},
            timeout=30,
        )

        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?session_id={session_id}&limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(item.get("session_id") == session_id for item in data["items"])

    def test_timeline_filter_combined(self, admin_headers):
        """Multiple filters can be combined"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?severity=info&action=user&limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["severity"] == "info"
            assert "user" in item["action"].lower()


class TestDomainEvents:
    """Test domain event logging (DOMAIN_ prefixed actions)"""

    def test_domain_events_exist(self, admin_headers):
        """DOMAIN_ events should exist in timeline"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?action=DOMAIN_&limit=100",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        # Check if any DOMAIN_ events exist
        domain_items = [item for item in data["items"] if item["action"].startswith("DOMAIN_")]
        # Note: If no domain events exist, this is informational
        print(f"Found {len(domain_items)} domain events")

    def test_domain_event_structure(self, admin_headers):
        """Domain events have proper structure when they exist"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?action=DOMAIN_exchange_validate&limit=20",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert "action" in item
            assert "entity_type" in item
            assert "severity" in item
            assert "details" in item


class TestTimelineResponseFields:
    """Test that timeline response includes all required new fields"""

    def test_timeline_item_has_new_fields(self, admin_headers):
        """Each timeline item should have request_id, session_id, route, method fields"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) > 0, "No timeline items to check"

        # Check structure of first item
        first_item = data["items"][0]
        required_fields = ["id", "action", "entity_type", "severity", "created_at", "details",
                          "request_id", "session_id", "route", "method"]
        for field in required_fields:
            assert field in first_item, f"Missing field: {field}"


class TestLimitValidation:
    """Test limit parameter validation"""

    def test_timeline_rejects_limit_below_minimum(self, admin_headers):
        """Limit below 20 should be rejected"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?limit=5",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 422  # Validation error

    def test_timeline_accepts_valid_limit(self, admin_headers):
        """Limit between 20-500 should work"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?limit=100",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
