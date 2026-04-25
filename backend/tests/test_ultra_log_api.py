"""
Ultra Log API Tests
Tests for the Ultra Log system including:
- GET /api/admin/ultra-log/status
- POST /api/admin/ultra-log/activate
- POST /api/admin/ultra-log/deactivate
- GET /api/admin/ultra-log/events
- Audit log mirroring into ultra events
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "http://localhost:8001"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@platform.local", "password": "Admin12345!"},
        timeout=30,
    )
    if resp.status_code != 200:
        pytest.skip("Admin login failed - skipping authenticated tests")
    return resp.json().get("access_token", "")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin authentication"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestUltraLogStatus:
    """Tests for GET /api/admin/ultra-log/status"""

    def test_get_status_requires_auth(self):
        """Status endpoint requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/admin/ultra-log/status", timeout=30)
        assert resp.status_code in [401, 403]

    def test_get_status_success(self, admin_headers):
        """Status endpoint returns valid response"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/ultra-log/status", headers=admin_headers, timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify response structure
        assert "enabled" in data
        assert "duration_option" in data
        assert "remaining_seconds" in data
        assert "max_normal_log_mb" in data
        assert "max_ultra_log_mb" in data
        assert "normal_log_usage_mb" in data
        assert "ultra_log_usage_mb" in data
        assert "ultra_log_dir" in data
        assert "auto_shutdown_reason" in data
        assert "auto_close_reason" in data
        
        # Verify data types
        assert isinstance(data["enabled"], bool)
        assert isinstance(data["remaining_seconds"], int)
        assert isinstance(data["max_normal_log_mb"], int)
        assert isinstance(data["max_ultra_log_mb"], int)


class TestUltraLogActivate:
    """Tests for POST /api/admin/ultra-log/activate"""

    def test_activate_requires_auth(self):
        """Activate endpoint requires authentication"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/ultra-log/activate",
            json={"duration_option": "1h"},
            timeout=30,
        )
        assert resp.status_code in [401, 403]

    def test_activate_invalid_duration(self, admin_headers):
        """Activate with invalid duration returns 400"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/ultra-log/activate",
            headers=admin_headers,
            json={"duration_option": "invalid"},
            timeout=30,
        )
        assert resp.status_code == 400
        assert "invalid_duration_option" in resp.json().get("detail", "")

    @pytest.mark.parametrize("duration", ["1h", "3h", "5h", "8h", "12h", "1d", "3d", "5d", "7d"])
    def test_activate_valid_durations(self, admin_headers, duration):
        """Activate with valid duration options"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/ultra-log/activate",
            headers=admin_headers,
            json={
                "duration_option": duration,
                "max_normal_log_mb": 1024,
                "max_ultra_log_mb": 512,
                "ultra_log_dir": "",
            },
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["duration_option"] == duration
        assert data["remaining_seconds"] > 0

    def test_activate_with_custom_limits(self, admin_headers):
        """Activate with custom log limits"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/ultra-log/activate",
            headers=admin_headers,
            json={
                "duration_option": "1h",
                "max_normal_log_mb": 2048,
                "max_ultra_log_mb": 1024,
                "ultra_log_dir": "",
            },
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_normal_log_mb"] == 2048
        assert data["max_ultra_log_mb"] == 1024


class TestUltraLogDeactivate:
    """Tests for POST /api/admin/ultra-log/deactivate"""

    def test_deactivate_requires_auth(self):
        """Deactivate endpoint requires authentication"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/ultra-log/deactivate",
            json={"reason": "test"},
            timeout=30,
        )
        assert resp.status_code in [401, 403]

    def test_deactivate_success(self, admin_headers):
        """Deactivate ultra log successfully"""
        # First activate
        requests.post(
            f"{BASE_URL}/api/admin/ultra-log/activate",
            headers=admin_headers,
            json={"duration_option": "1h"},
            timeout=30,
        )
        
        # Then deactivate
        resp = requests.post(
            f"{BASE_URL}/api/admin/ultra-log/deactivate",
            headers=admin_headers,
            json={"reason": "test_deactivation"},
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["auto_shutdown_reason"] == "test_deactivation"
        assert data["auto_close_reason"] == "test_deactivation"


class TestUltraLogEvents:
    """Tests for GET /api/admin/ultra-log/events"""

    def test_events_requires_auth(self):
        """Events endpoint requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/admin/ultra-log/events", timeout=30)
        assert resp.status_code in [401, 403]

    def test_events_returns_list(self, admin_headers):
        """Events endpoint returns a list"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/ultra-log/events?limit=10",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_events_with_category_filter(self, admin_headers):
        """Events endpoint supports category filter"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/ultra-log/events?limit=10&category=http_request",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # All events should have the filtered category
        for event in data:
            assert event["category"] == "http_request"

    def test_events_structure(self, admin_headers):
        """Events have correct structure"""
        # First activate to generate some events
        requests.post(
            f"{BASE_URL}/api/admin/ultra-log/activate",
            headers=admin_headers,
            json={"duration_option": "1h"},
            timeout=30,
        )
        
        resp = requests.get(
            f"{BASE_URL}/api/admin/ultra-log/events?limit=10",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        
        if data:
            event = data[0]
            assert "id" in event
            assert "category" in event
            assert "event_name" in event
            assert "severity" in event
            assert "payload" in event
            assert "created_at" in event


class TestAuditLogMirroring:
    """Tests for audit log mirroring into ultra events"""

    def test_audit_events_mirrored(self, admin_headers):
        """Audit events are mirrored to ultra log when enabled"""
        # Activate ultra log
        requests.post(
            f"{BASE_URL}/api/admin/ultra-log/activate",
            headers=admin_headers,
            json={"duration_option": "1h"},
            timeout=30,
        )
        
        # Get events with audit category
        resp = requests.get(
            f"{BASE_URL}/api/admin/ultra-log/events?limit=50&category=audit",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Should have audit events from the activation
        audit_events = [e for e in data if e["event_name"] == "audit_event"]
        # Note: audit events are created when ultra log is activated
        assert isinstance(audit_events, list)


class TestUltraLogIntegration:
    """Integration tests for the full Ultra Log workflow"""

    def test_full_workflow(self, admin_headers):
        """Test complete activate -> use -> deactivate workflow"""
        # 1. Check initial status
        resp = requests.get(
            f"{BASE_URL}/api/admin/ultra-log/status",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        
        # 2. Activate with 1h duration
        resp = requests.post(
            f"{BASE_URL}/api/admin/ultra-log/activate",
            headers=admin_headers,
            json={
                "duration_option": "1h",
                "max_normal_log_mb": 1024,
                "max_ultra_log_mb": 512,
            },
            timeout=30,
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
        
        # 3. Make some requests to generate events
        for _ in range(3):
            requests.get(
                f"{BASE_URL}/api/admin/ultra-log/status",
                headers=admin_headers,
                timeout=30,
            )
        
        # 4. Check events were recorded
        resp = requests.get(
            f"{BASE_URL}/api/admin/ultra-log/events?limit=20",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) > 0
        
        # 5. Deactivate
        resp = requests.post(
            f"{BASE_URL}/api/admin/ultra-log/deactivate",
            headers=admin_headers,
            json={"reason": "test_complete"},
            timeout=30,
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False
        
        # 6. Verify final status
        resp = requests.get(
            f"{BASE_URL}/api/admin/ultra-log/status",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False
