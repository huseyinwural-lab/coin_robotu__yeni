"""
Test Email-Only Alert Channel Configuration (Option C)
Testing Resend email-only activation with slack disabled.
Expectations:
- channel_status_overall: READY
- channel_status.email: ACTIVE  
- channel_status.slack: DISABLED
- simulate alert: email SENT, slack CHANNEL_DISABLED
- audit log: ALERT_DELIVERY_SUCCESS (channel=email)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@platform.dev", "password": "Admin12345!"},
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Returns headers with authorization"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestAlertChannelConfig:
    """Test alert channel configuration endpoint"""

    def test_config_returns_channel_status_overall_ready(self, auth_headers):
        """POST /api/admin/system-alerts/config sonrası channel_status_overall READY olmalı"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts/config",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify channel_status_overall is READY
        assert data["channels"]["channel_status_overall"] == "READY"
        
    def test_config_email_channel_active(self, auth_headers):
        """channel_status.email ACTIVE olmalı"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts/config",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify email channel is ACTIVE
        assert data["channels"]["channel_status"]["email"] == "ACTIVE"
        
    def test_config_slack_channel_disabled(self, auth_headers):
        """channel_status.slack DISABLED olmalı"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts/config",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify slack channel is DISABLED
        assert data["channels"]["channel_status"]["slack"] == "DISABLED"
        
    def test_config_source_is_admin_config(self, auth_headers):
        """Config source should be admin_config (database)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts/config",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify config source
        assert data["channels"]["config_source"] == "admin_config"


class TestAlertSimulation:
    """Test ops alert simulation endpoint"""

    def test_simulate_returns_email_sent(self, auth_headers):
        """POST /api/ops-alerts/simulate sonrası delivery_status.email.status SENT olmalı"""
        response = requests.post(
            f"{BASE_URL}/api/ops-alerts/simulate",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify email delivery status is SENT
        assert data["delivery_status"]["email"]["status"] == "SENT"
        assert "provider_id" in data["delivery_status"]["email"]
        
    def test_simulate_returns_slack_channel_disabled(self, auth_headers):
        """POST /api/ops-alerts/simulate sonrası delivery_status.slack.status CHANNEL_DISABLED olmalı"""
        response = requests.post(
            f"{BASE_URL}/api/ops-alerts/simulate",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify slack delivery status is CHANNEL_DISABLED
        assert data["delivery_status"]["slack"]["status"] == "CHANNEL_DISABLED"
        
    def test_simulate_creates_alert_id(self, auth_headers):
        """Simulate should return alert_id"""
        response = requests.post(
            f"{BASE_URL}/api/ops-alerts/simulate",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify alert_id is returned
        assert "alert_id" in data
        assert isinstance(data["alert_id"], str)
        assert len(data["alert_id"]) > 0


class TestAuditLog:
    """Test audit log creation for alert delivery"""

    def test_audit_log_alert_delivery_success_email_exists(self, auth_headers):
        """audit-logs içinde ALERT_DELIVERY_SUCCESS (channel=email) oluşmalı
        
        Note: Due to rate limiting (3 critical alerts per 30 min), we verify that
        at least one ALERT_DELIVERY_SUCCESS with channel=email exists in the logs.
        """
        # Check audit logs for existing ALERT_DELIVERY_SUCCESS
        audit_response = requests.get(
            f"{BASE_URL}/api/audit-logs?limit=100",
            headers=auth_headers
        )
        assert audit_response.status_code == 200
        logs = audit_response.json()
        
        # Find ALERT_DELIVERY_SUCCESS logs with channel=email
        email_success_logs = [
            log for log in logs 
            if log["action"] == "ALERT_DELIVERY_SUCCESS" 
            and log.get("details", {}).get("channel") == "email"
        ]
        
        assert len(email_success_logs) > 0, "No ALERT_DELIVERY_SUCCESS (channel=email) log found"
        
        # Verify the log details
        latest_log = email_success_logs[0]
        assert latest_log["details"]["provider_status"] == "SENT"
        assert latest_log["entity_type"] == "system_alert"
        assert latest_log["severity"] == "info"


    def test_simulate_email_delivery_behavior(self, auth_headers):
        """Verify simulate endpoint handles email delivery (success or rate limit)"""
        simulate_response = requests.post(
            f"{BASE_URL}/api/ops-alerts/simulate",
            headers=auth_headers
        )
        assert simulate_response.status_code == 200
        data = simulate_response.json()
        
        # Email should either be SENT or RATE_LIMITED (due to critical_rate_limit)
        email_status = data["delivery_status"]["email"]["status"]
        assert email_status in ["SENT", "RATE_LIMITED"], f"Unexpected email status: {email_status}"
        
        # If SENT, verify provider_id exists
        if email_status == "SENT":
            assert "provider_id" in data["delivery_status"]["email"]
        
        # Slack should always be CHANNEL_DISABLED since it's not configured
        assert data["delivery_status"]["slack"]["status"] == "CHANNEL_DISABLED"
