"""
Test suite for Admin Action Center endpoints (admin_action_center.py)
Tests: Global Kill Switch, Restart Services, Clear All Alerts, Bulk Ack, RBAC for OPS user
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
OPS_EMAIL = "canary.ops@platform.local"
OPS_PASSWORD = "CanaryOps123!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def super_admin_token(api_client):
    """Get super_admin authentication token"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Super admin authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def ops_token(api_client):
    """Get OPS user authentication token"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPS_EMAIL, "password": OPS_PASSWORD},
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"OPS user authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def super_admin_client(api_client, super_admin_token):
    """Session with super_admin auth header"""
    api_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
    return api_client


@pytest.fixture(scope="module")
def ops_client(api_client, ops_token):
    """Session with OPS auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ops_token}"
    })
    return session


class TestActionCenterSummary:
    """Test /api/admin/action-center/summary endpoint"""

    def test_summary_endpoint_returns_200(self, super_admin_client):
        """Summary endpoint should return 200 with expected fields"""
        response = super_admin_client.get(f"{BASE_URL}/api/admin/action-center/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify expected fields exist
        expected_fields = [
            "pending_approvals", "stale_pending_approvals", "open_alerts",
            "queued_intents", "rejected_intents", "timeout_rejected_intents",
            "kill_switch_active", "kill_switch_reasons", "emergency_mode",
            "disable_futures", "generated_at"
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        print(f"Summary data: {data}")


class TestGlobalKillSwitch:
    """Test /api/admin/action-center/global-kill-switch/toggle endpoint"""

    def test_kill_switch_toggle_invalid_phrase_rejected(self, super_admin_client):
        """Kill switch toggle should reject invalid confirmation phrase"""
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/action-center/global-kill-switch/toggle",
            json={
                "active": True,
                "reason": "test_invalid_phrase_rejection",
                "confirmation_phrase": "WRONG PHRASE",
                "requested_by": SUPER_ADMIN_EMAIL,
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "invalid_confirmation_phrase" in str(data.get("detail", {})), f"Expected phrase error: {data}"
        print(f"Invalid phrase correctly rejected: {data}")

    def test_kill_switch_activate_with_correct_phrase(self, super_admin_client):
        """Kill switch activate should work with correct phrase DISABLE TRADING"""
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/action-center/global-kill-switch/toggle",
            json={
                "active": True,
                "reason": "test_kill_switch_activate_action_center",
                "confirmation_phrase": "DISABLE TRADING",
                "requested_by": SUPER_ADMIN_EMAIL,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status ok: {data}"
        assert data.get("kill_switch_active") is True, f"Expected kill_switch_active=True: {data}"
        print(f"Kill switch activated: {data}")

    def test_kill_switch_deactivate_with_correct_phrase(self, super_admin_client):
        """Kill switch deactivate should work with correct phrase ENABLE TRADING"""
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/action-center/global-kill-switch/toggle",
            json={
                "active": False,
                "reason": "test_kill_switch_deactivate_action_center",
                "confirmation_phrase": "ENABLE TRADING",
                "requested_by": SUPER_ADMIN_EMAIL,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status ok: {data}"
        assert data.get("kill_switch_active") is False, f"Expected kill_switch_active=False: {data}"
        print(f"Kill switch deactivated: {data}")


class TestRestartServices:
    """Test /api/admin/action-center/restart-services endpoint"""

    def test_restart_services_invalid_phrase_rejected(self, super_admin_client):
        """Restart services should reject invalid confirmation phrase"""
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/action-center/restart-services",
            json={
                "targets": ["backend"],
                "reason": "test_invalid_phrase_restart",
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "invalid_confirmation_phrase" in str(data.get("detail", {})), f"Expected phrase error: {data}"
        print(f"Invalid phrase correctly rejected for restart: {data}")

    def test_restart_services_with_correct_phrase(self, super_admin_client):
        """Restart services should return scheduled operation with correct phrase"""
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/action-center/restart-services",
            json={
                "targets": ["backend", "frontend"],
                "reason": "test_restart_services_action_center",
                "confirmation_phrase": "RESTART SERVICES",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "scheduled", f"Expected status scheduled: {data}"
        assert "operation_id" in data, f"Expected operation_id: {data}"
        assert "targets" in data, f"Expected targets: {data}"
        print(f"Restart services scheduled: {data}")


class TestClearAllAlerts:
    """Test /api/admin/action-center/alerts/clear-all endpoint"""

    def test_clear_all_alerts_invalid_phrase_rejected(self, super_admin_client):
        """Clear all alerts should reject invalid confirmation phrase"""
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/action-center/alerts/clear-all",
            json={
                "status_filter": "open",
                "reason": "test_invalid_phrase_clear_alerts",
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "invalid_confirmation_phrase" in str(data.get("detail", {})), f"Expected phrase error: {data}"
        print(f"Invalid phrase correctly rejected for clear alerts: {data}")

    def test_clear_all_alerts_with_correct_phrase(self, super_admin_client):
        """Clear all alerts should work with correct phrase CLEAR ALL ALERTS"""
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/action-center/alerts/clear-all",
            json={
                "status_filter": "open",
                "reason": "test_clear_all_alerts_action_center",
                "confirmation_phrase": "CLEAR ALL ALERTS",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status ok: {data}"
        assert "acked_count" in data, f"Expected acked_count: {data}"
        print(f"Clear all alerts completed: {data}")


class TestAlertsEndpoints:
    """Test /api/admin/action-center/alerts endpoints"""

    def test_alerts_list_with_filters(self, super_admin_client):
        """Alerts list should support filters: severity, type, source, time, status"""
        response = super_admin_client.get(
            f"{BASE_URL}/api/admin/action-center/alerts",
            params={
                "status_filter": "open",
                "severity": "CRITICAL",
                "window_hours": 24,
                "limit": 50,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data, f"Expected items: {data}"
        assert "filters" in data, f"Expected filters: {data}"
        print(f"Alerts list with filters: {len(data.get('items', []))} items")

    def test_alerts_list_all_status(self, super_admin_client):
        """Alerts list should work with status_filter=all"""
        response = super_admin_client.get(
            f"{BASE_URL}/api/admin/action-center/alerts",
            params={"status_filter": "all", "window_hours": 168, "limit": 100},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data, f"Expected items: {data}"
        print(f"All alerts: {len(data.get('items', []))} items")


class TestIncidentHistory:
    """Test /api/admin/action-center/incident-history endpoint"""

    def test_incident_history_returns_audit_and_alerts(self, super_admin_client):
        """Incident history should return audit_events and recent_alerts"""
        response = super_admin_client.get(
            f"{BASE_URL}/api/admin/action-center/incident-history",
            params={"limit": 25},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "audit_events" in data, f"Expected audit_events: {data}"
        assert "recent_alerts" in data, f"Expected recent_alerts: {data}"
        print(f"Incident history: {len(data.get('audit_events', []))} audit events, {len(data.get('recent_alerts', []))} alerts")


class TestCloseNextActions:
    """Test /api/admin/action-center/close-next-actions endpoint"""

    def test_close_next_actions_returns_result(self, super_admin_client):
        """Close next actions should return completed status with counts"""
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/action-center/close-next-actions",
            json={
                "ack_open_alerts": True,
                "reject_stale_approvals": False,
                "stale_days": 30,
                "retry_timeout_rejections": False,
                "clear_kill_switch": False,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "completed", f"Expected status completed: {data}"
        assert "acked_alerts" in data, f"Expected acked_alerts: {data}"
        assert "rejected_approvals" in data, f"Expected rejected_approvals: {data}"
        assert "retried_intents" in data, f"Expected retried_intents: {data}"
        print(f"Close next actions result: {data}")


class TestOpsRBACRestriction:
    """Test that OPS user is blocked (403) for critical endpoints"""

    def test_ops_blocked_from_kill_switch_toggle(self, ops_client):
        """OPS user should get 403 when trying to toggle kill switch"""
        response = ops_client.post(
            f"{BASE_URL}/api/admin/action-center/global-kill-switch/toggle",
            json={
                "active": True,
                "reason": "test_ops_rbac_kill_switch",
                "confirmation_phrase": "DISABLE TRADING",
                "requested_by": OPS_EMAIL,
            },
        )
        assert response.status_code == 403, f"Expected 403 for OPS user, got {response.status_code}: {response.text}"
        print(f"OPS correctly blocked from kill switch: {response.status_code}")

    def test_ops_blocked_from_restart_services(self, ops_client):
        """OPS user should get 403 when trying to restart services"""
        response = ops_client.post(
            f"{BASE_URL}/api/admin/action-center/restart-services",
            json={
                "targets": ["backend"],
                "reason": "test_ops_rbac_restart",
                "confirmation_phrase": "RESTART SERVICES",
            },
        )
        assert response.status_code == 403, f"Expected 403 for OPS user, got {response.status_code}: {response.text}"
        print(f"OPS correctly blocked from restart services: {response.status_code}")

    def test_ops_blocked_from_clear_all_alerts(self, ops_client):
        """OPS user should get 403 when trying to clear all alerts"""
        response = ops_client.post(
            f"{BASE_URL}/api/admin/action-center/alerts/clear-all",
            json={
                "status_filter": "open",
                "reason": "test_ops_rbac_clear_alerts",
                "confirmation_phrase": "CLEAR ALL ALERTS",
            },
        )
        assert response.status_code == 403, f"Expected 403 for OPS user, got {response.status_code}: {response.text}"
        print(f"OPS correctly blocked from clear all alerts: {response.status_code}")

    def test_ops_blocked_from_close_next_actions(self, ops_client):
        """OPS user should get 403 when trying to run close-next-actions"""
        response = ops_client.post(
            f"{BASE_URL}/api/admin/action-center/close-next-actions",
            json={
                "ack_open_alerts": True,
                "reject_stale_approvals": False,
            },
        )
        assert response.status_code == 403, f"Expected 403 for OPS user, got {response.status_code}: {response.text}"
        print(f"OPS correctly blocked from close-next-actions: {response.status_code}")

    def test_ops_can_read_summary(self, ops_client):
        """OPS user should be able to read summary (read-only)"""
        response = ops_client.get(f"{BASE_URL}/api/admin/action-center/summary")
        assert response.status_code == 200, f"Expected 200 for OPS read, got {response.status_code}: {response.text}"
        print(f"OPS can read summary: {response.status_code}")

    def test_ops_can_read_alerts(self, ops_client):
        """OPS user should be able to read alerts (read-only)"""
        response = ops_client.get(
            f"{BASE_URL}/api/admin/action-center/alerts",
            params={"status_filter": "open", "limit": 10},
        )
        assert response.status_code == 200, f"Expected 200 for OPS read, got {response.status_code}: {response.text}"
        print(f"OPS can read alerts: {response.status_code}")


class TestKillSwitchStateEndpoint:
    """Test /api/admin/kill-switch GET endpoint"""

    def test_kill_switch_state_returns_expected_fields(self, super_admin_client):
        """Kill switch state should return trading_enabled and reason_code"""
        response = super_admin_client.get(f"{BASE_URL}/api/admin/kill-switch")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "trading_enabled" in data, f"Expected trading_enabled: {data}"
        assert "reason_code" in data, f"Expected reason_code: {data}"
        print(f"Kill switch state: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
