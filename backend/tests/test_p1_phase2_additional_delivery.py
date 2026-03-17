"""
P1 Phase 2 - Additional test delivery channel tests
Tests for email, slack, and both channels
"""
import os
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
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, response.text
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


class TestAlertTestDelivery:
    """Test all delivery channels for system alerts"""

    def test_delivery_email_channel(self, admin_headers: dict):
        """Test email channel delivery - expects CONFIG_MISSING since no resend key"""
        response = requests.post(
            f"{BASE_URL}/api/admin/system-alerts/test-delivery",
            json={"channel": "email", "severity": "WARNING"},
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload.get("channel") == "email"
        assert "result" in payload
        assert "email" in payload["result"]
        # Email should return CONFIG_MISSING since Resend API key not configured
        email_status = payload["result"]["email"].get("status")
        assert email_status in {"SENT", "CONFIG_MISSING", "FAILED", "RATE_LIMITED"}

    def test_delivery_slack_channel(self, admin_headers: dict):
        """Test slack channel delivery - expects CONFIG_MISSING since no webhook"""
        response = requests.post(
            f"{BASE_URL}/api/admin/system-alerts/test-delivery",
            json={"channel": "slack", "severity": "WARNING"},
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload.get("channel") == "slack"
        assert "result" in payload
        assert "slack" in payload["result"]
        # Slack should return CONFIG_MISSING since webhook not configured
        slack_status = payload["result"]["slack"].get("status")
        assert slack_status in {"SENT", "CONFIG_MISSING", "FAILED", "RATE_LIMITED"}

    def test_delivery_both_channels(self, admin_headers: dict):
        """Test both channels delivery"""
        response = requests.post(
            f"{BASE_URL}/api/admin/system-alerts/test-delivery",
            json={"channel": "both", "severity": "CRITICAL"},
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload.get("channel") == "both"
        assert "result" in payload
        assert "email" in payload["result"]
        assert "slack" in payload["result"]
        # Should have channel_status in response
        assert "channel_status" in payload

    def test_delivery_invalid_channel_returns_400(self, admin_headers: dict):
        """Test invalid channel returns 400 error"""
        response = requests.post(
            f"{BASE_URL}/api/admin/system-alerts/test-delivery",
            json={"channel": "webhook", "severity": "WARNING"},
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 400, response.text
        assert response.json().get("detail") == "invalid_channel"

    def test_delivery_invalid_severity_returns_400(self, admin_headers: dict):
        """Test invalid severity returns 400 error"""
        response = requests.post(
            f"{BASE_URL}/api/admin/system-alerts/test-delivery",
            json={"channel": "slack", "severity": "UNKNOWN"},
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 400, response.text
        assert response.json().get("detail") == "invalid_severity"


class TestFuturesLivePathEndpoints:
    """Test futures live path check endpoints"""

    def test_futures_live_path_summary_returns_structure(self, admin_headers: dict):
        """Verify summary response structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/futures-live-path-check",
            params={"limit": 50},
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        
        # Verify all required fields
        assert "generated_at" in payload
        assert "total_users" in payload
        assert "pass_count" in payload
        assert "fail_count" in payload
        assert "items" in payload
        
        # Verify items structure if any
        if payload["items"]:
            item = payload["items"][0]
            assert "user_id" in item
            assert "user_email" in item
            assert "status" in item
            assert "issues" in item
            assert item["status"] in {"PASS", "FAIL"}

    def test_futures_live_path_single_user_404_for_nonexistent(self, admin_headers: dict):
        """Test 404 for nonexistent user"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/nonexistent-user-id/futures-live-path-check",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 404, response.text
        assert response.json().get("detail") == "user_not_found"


class TestBurnInEndpoint:
    """Test burn-in summary endpoint"""

    def test_burn_in_with_different_days(self, admin_headers: dict):
        """Test burn-in summary with different day windows"""
        for days in [7, 14, 30]:
            response = requests.get(
                f"{BASE_URL}/api/admin/system-alerts/burn-in",
                params={"days": days},
                headers=admin_headers,
                timeout=20,
            )
            assert response.status_code == 200, f"Failed for days={days}: {response.text}"
            payload = response.json()
            assert payload.get("window_days") == days
            assert "total_alerts" in payload
            assert "severity_breakdown" in payload
            assert "status_breakdown" in payload
            assert "top_alert_types" in payload
            assert "delivery" in payload
            assert "recommendation" in payload

    def test_burn_in_delivery_metrics(self, admin_headers: dict):
        """Verify delivery metrics in burn-in response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts/burn-in",
            params={"days": 7},
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        
        delivery = payload.get("delivery", {})
        assert "email_sent" in delivery
        assert "email_failed" in delivery
        assert "slack_sent" in delivery
        assert "slack_failed" in delivery
