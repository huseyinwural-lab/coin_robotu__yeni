"""
Risk Orchestrator Endpoints Test Suite
Tests for Risk Enforcement + Intervention System endpoints

Endpoints tested:
- POST /api/strategy-domain/admin/risk-orchestrator/policy/simulate
- POST /api/strategy-domain/admin/risk-orchestrator/policy/apply
- GET /api/strategy-domain/admin/risk-orchestrator/policy/history
- POST /api/strategy-domain/admin/risk-orchestrator/policy/revert/{version_id}
- POST /api/strategy-domain/admin/risk-orchestrator/actions/kill-switch
- POST /api/strategy-domain/admin/risk-orchestrator/actions/global-pause
- POST /api/strategy-domain/admin/risk-orchestrator/actions/force-risk-check
- POST/GET /api/strategy-domain/admin/risk-orchestrator/exposure/overrides
- POST /api/strategy-domain/admin/risk-orchestrator/supervisor/run
- GET /api/strategy-domain/admin/risk-orchestrator/supervisor/positions
- POST /api/strategy-domain/admin/risk-orchestrator/supervisor/intervene
- GET /api/strategy-domain/admin/risk-orchestrator/rejects
- GET /api/strategy-domain/admin/risk-orchestrator/rejects/{id}
- GET /api/strategy-domain/admin/risk-orchestrator/audit/timeline
- GET /api/strategy-domain/admin/risk-orchestrator/alerts
- GET /api/strategy-domain/admin/risk-orchestrator/auto-trigger-logs
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_EMAIL = "canary.requester@platform.local"
ADMIN_PASSWORD = "CanaryRequester123!"


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
        return data.get("access_token")
    pytest.skip(f"Super admin authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_token(api_client):
    """Get admin authentication token"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token")
    # If admin user doesn't exist, skip tests requiring admin
    return None


@pytest.fixture(scope="module")
def super_admin_client(api_client, super_admin_token):
    """Session with super_admin auth header"""
    api_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
    return api_client


class TestPolicySimulation:
    """Policy simulation endpoint tests"""

    def test_policy_simulate_returns_simulation_id(self, super_admin_client):
        """POST /api/strategy-domain/admin/risk-orchestrator/policy/simulate returns simulation_id"""
        payload = {
            "candidate_policy": {
                "reference_equity_usd": 10000,
                "account_max_notional_pct": 60,
                "symbol_max_notional_pct": 25,
                "strategy_max_concurrent_positions": 3,
                "strategy_cooldown_seconds": 60,
                "max_order_frequency_per_min": 6,
                "max_order_burst_per_10s": 3,
                "daily_loss_limit_pct": 5,
                "duplicate_suppression_window_seconds": 300,
            }
        }
        response = super_admin_client.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "simulation_id" in data, "Response should contain simulation_id"
        assert data["simulation_id"].startswith("ro-sim-"), "simulation_id should start with 'ro-sim-'"
        assert "result_status" in data, "Response should contain result_status"
        assert "diff_summary" in data, "Response should contain diff_summary"
        print(f"✓ Policy simulation successful: {data['simulation_id']}, status: {data['result_status']}")


class TestPolicyApply:
    """Policy apply endpoint tests"""

    def test_policy_apply_requires_simulation_and_double_confirm(self, super_admin_client):
        """POST /api/strategy-domain/admin/risk-orchestrator/policy/apply enforces simulation + double_confirmed"""
        # First run simulation
        sim_payload = {
            "candidate_policy": {
                "reference_equity_usd": 10000,
                "account_max_notional_pct": 60,
                "symbol_max_notional_pct": 25,
                "strategy_max_concurrent_positions": 3,
                "strategy_cooldown_seconds": 60,
                "max_order_frequency_per_min": 6,
                "max_order_burst_per_10s": 3,
                "daily_loss_limit_pct": 5,
                "duplicate_suppression_window_seconds": 300,
            }
        }
        sim_response = super_admin_client.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            json=sim_payload,
        )
        assert sim_response.status_code == 200
        simulation_id = sim_response.json()["simulation_id"]

        # Try apply without double_confirmed - should fail
        apply_payload = {
            "simulation_id": simulation_id,
            "reason_note": "Test apply without double confirm",
            "double_confirmed": False,
        }
        response = super_admin_client.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
            json=apply_payload,
        )
        assert response.status_code == 400, f"Expected 400 without double_confirmed, got {response.status_code}"
        assert "double_confirmation_required" in response.text
        print("✓ Policy apply correctly rejects without double_confirmed")

        # Try apply with double_confirmed - should succeed
        apply_payload["double_confirmed"] = True
        response = super_admin_client.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
            json=apply_payload,
        )
        assert response.status_code == 200, f"Expected 200 with double_confirmed, got {response.status_code}: {response.text}"
        data = response.json()
        assert "policy_version" in data, "Response should contain policy_version"
        print(f"✓ Policy apply successful with double_confirmed, version: {data.get('policy_version')}")


class TestPolicyHistory:
    """Policy history endpoint tests"""

    def test_policy_history_returns_versions_and_change_requests(self, super_admin_client):
        """GET /api/strategy-domain/admin/risk-orchestrator/policy/history returns versions and change_requests"""
        response = super_admin_client.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/history?limit=20"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "versions" in data, "Response should contain versions"
        assert "change_requests" in data, "Response should contain change_requests"
        assert isinstance(data["versions"], list), "versions should be a list"
        assert isinstance(data["change_requests"], list), "change_requests should be a list"
        print(f"✓ Policy history returned {len(data['versions'])} versions, {len(data['change_requests'])} change_requests")


class TestPolicyRevert:
    """Policy revert endpoint tests"""

    def test_policy_revert_requires_super_admin_and_double_confirm(self, super_admin_client):
        """POST /api/strategy-domain/admin/risk-orchestrator/policy/revert/{version_id} requires super_admin"""
        # First get history to find a version_id
        history_response = super_admin_client.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/history?limit=5"
        )
        assert history_response.status_code == 200
        versions = history_response.json().get("versions", [])
        
        if not versions:
            pytest.skip("No policy versions available for revert test")
        
        version_id = versions[0]["version_id"]
        
        # Try revert without double_confirmed
        revert_payload = {
            "reason_note": "Test revert without double confirm",
            "double_confirmed": False,
        }
        response = super_admin_client.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/revert/{version_id}",
            json=revert_payload,
        )
        assert response.status_code == 400, f"Expected 400 without double_confirmed, got {response.status_code}"
        print("✓ Policy revert correctly rejects without double_confirmed")


class TestControlActions:
    """Control action endpoints tests (kill-switch, global-pause, force-risk-check)"""

    def test_kill_switch_endpoint(self, super_admin_client):
        """POST /api/strategy-domain/admin/risk-orchestrator/actions/kill-switch works"""
        payload = {
            "action_type": "kill_switch",
            "reason_note": "Test kill switch action",
            "context": {},
        }
        response = super_admin_client.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/actions/kill-switch",
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "intervention_id" in data, "Response should contain intervention_id"
        assert data["action_type"] == "kill_switch", "action_type should be kill_switch"
        assert data["status"] == "success", "status should be success"
        print(f"✓ Kill switch action successful: {data['intervention_id']}")

    def test_global_pause_endpoint(self, super_admin_client):
        """POST /api/strategy-domain/admin/risk-orchestrator/actions/global-pause works"""
        payload = {
            "action_type": "global_trading_pause",
            "reason_note": "Test global pause action",
            "context": {},
        }
        response = super_admin_client.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/actions/global-pause",
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "intervention_id" in data, "Response should contain intervention_id"
        assert data["action_type"] == "global_trading_pause", "action_type should be global_trading_pause"
        print(f"✓ Global pause action successful: {data['intervention_id']}")

    def test_force_risk_check_endpoint(self, super_admin_client):
        """POST /api/strategy-domain/admin/risk-orchestrator/actions/force-risk-check works (regression test for datetime JSON serialize fix)"""
        payload = {
            "action_type": "force_risk_check",
            "reason_note": "Test force risk check action",
            "context": {},
        }
        response = super_admin_client.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/actions/force-risk-check",
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "intervention_id" in data, "Response should contain intervention_id"
        assert data["action_type"] == "force_risk_check", "action_type should be force_risk_check"
        assert "effective_state" in data, "Response should contain effective_state"
        print(f"✓ Force risk check action successful: {data['intervention_id']}")


class TestExposureOverrides:
    """Exposure override endpoints tests"""

    def test_create_exposure_override(self, super_admin_client):
        """POST /api/strategy-domain/admin/risk-orchestrator/exposure/overrides creates override"""
        payload = {
            "override_type": "symbol",
            "target_key": "BTCUSDT",
            "reason_note": "Test exposure override creation",
            "max_notional_pct": 10,
            "max_open_count": 2,
            "block_new_adds": False,
            "expires_in_minutes": 60,
        }
        response = super_admin_client.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/exposure/overrides",
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "override_id" in data, "Response should contain override_id"
        assert data["override_type"] == "symbol", "override_type should be symbol"
        assert data["target_key"] == "BTCUSDT", "target_key should be BTCUSDT"
        assert data["status"] == "active", "status should be active"
        print(f"✓ Exposure override created: {data['override_id']}")
        return data["override_id"]

    def test_list_exposure_overrides(self, super_admin_client):
        """GET /api/strategy-domain/admin/risk-orchestrator/exposure/overrides lists overrides"""
        response = super_admin_client.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/exposure/overrides?active_only=true"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Listed {len(data)} active exposure overrides")

    def test_deactivate_exposure_override(self, super_admin_client):
        """POST /api/strategy-domain/admin/risk-orchestrator/exposure/overrides/{id}/deactivate works"""
        # First create an override
        create_payload = {
            "override_type": "strategy",
            "target_key": "TEST_STRATEGY",
            "reason_note": "Test override for deactivation",
            "max_notional_pct": 5,
            "expires_in_minutes": 30,
        }
        create_response = super_admin_client.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/exposure/overrides",
            json=create_payload,
        )
        assert create_response.status_code == 200
        override_id = create_response.json()["override_id"]

        # Deactivate it
        deactivate_payload = {"reason_note": "Test deactivation"}
        response = super_admin_client.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/exposure/overrides/{override_id}/deactivate",
            json=deactivate_payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["status"] == "inactive", "status should be inactive after deactivation"
        print(f"✓ Override deactivated: {override_id}")


class TestSupervisor:
    """Supervisor endpoints tests"""

    def test_supervisor_run(self, super_admin_client):
        """POST /api/strategy-domain/admin/risk-orchestrator/supervisor/run works"""
        response = super_admin_client.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/supervisor/run"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "evaluated_at" in data, "Response should contain evaluated_at"
        assert "breaches" in data, "Response should contain breaches"
        assert isinstance(data["breaches"], list), "breaches should be a list"
        print(f"✓ Supervisor run successful, found {len(data['breaches'])} breaches")

    def test_supervisor_positions(self, super_admin_client):
        """GET /api/strategy-domain/admin/risk-orchestrator/supervisor/positions works"""
        response = super_admin_client.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/supervisor/positions?limit=50"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Listed {len(data)} open positions")


class TestRejects:
    """Rejects endpoints tests (regression test for AuditLog created_at fix)"""

    def test_list_rejects(self, super_admin_client):
        """GET /api/strategy-domain/admin/risk-orchestrator/rejects works (regression test)"""
        response = super_admin_client.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/rejects?limit=50"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Listed {len(data)} risk rejects")

    def test_list_rejects_with_filters(self, super_admin_client):
        """GET /api/strategy-domain/admin/risk-orchestrator/rejects with filters works"""
        response = super_admin_client.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/rejects?reason_code=kill_switch_active&limit=10"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Listed {len(data)} filtered risk rejects")


class TestAuditTimeline:
    """Audit timeline endpoint tests"""

    def test_audit_timeline(self, super_admin_client):
        """GET /api/strategy-domain/admin/risk-orchestrator/audit/timeline works"""
        response = super_admin_client.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/audit/timeline?limit=40"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        if data:
            item = data[0]
            assert "event_id" in item, "Timeline item should contain event_id"
            assert "event_type" in item, "Timeline item should contain event_type"
            assert "created_at" in item, "Timeline item should contain created_at"
        print(f"✓ Audit timeline returned {len(data)} items")


class TestAlerts:
    """Alerts endpoint tests"""

    def test_list_alerts(self, super_admin_client):
        """GET /api/strategy-domain/admin/risk-orchestrator/alerts works"""
        response = super_admin_client.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/alerts?limit=30"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Listed {len(data)} risk alerts")


class TestAutoTriggerLogs:
    """Auto trigger logs endpoint tests"""

    def test_list_auto_trigger_logs(self, super_admin_client):
        """GET /api/strategy-domain/admin/risk-orchestrator/auto-trigger-logs works"""
        response = super_admin_client.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/auto-trigger-logs?limit=30"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Listed {len(data)} auto trigger logs")


class TestRoleGating:
    """Role gating tests - verify super_admin requirement for critical actions"""

    def test_control_actions_require_super_admin(self, api_client, admin_token):
        """Control actions should require super_admin role"""
        if admin_token is None:
            pytest.skip("Admin user not available for role gating test")
        
        api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
        
        payload = {
            "action_type": "kill_switch",
            "reason_note": "Test from admin user",
            "context": {},
        }
        response = api_client.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/actions/kill-switch",
            json=payload,
        )
        # Should be 403 Forbidden for non-super_admin
        assert response.status_code in [401, 403], f"Expected 401/403 for admin user, got {response.status_code}"
        print("✓ Control actions correctly require super_admin role")


class TestPolicyEndpoint:
    """Policy GET endpoint tests"""

    def test_get_policy(self, super_admin_client):
        """GET /api/strategy-domain/admin/risk-orchestrator/policy works"""
        response = super_admin_client.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "reference_equity_usd" in data, "Response should contain reference_equity_usd"
        assert "account_max_notional_pct" in data, "Response should contain account_max_notional_pct"
        assert "policy_version" in data, "Response should contain policy_version"
        print(f"✓ Policy retrieved, version: {data.get('policy_version')}")


class TestStatusEndpoint:
    """Status endpoint tests"""

    def test_get_status(self, super_admin_client):
        """GET /api/strategy-domain/admin/risk-orchestrator/status works"""
        response = super_admin_client.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/status"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "policy" in data, "Response should contain policy"
        assert "kill_switch_active" in data, "Response should contain kill_switch_active"
        assert "trading_enabled" in data, "Response should contain trading_enabled"
        assert "open_intents" in data, "Response should contain open_intents"
        print(f"✓ Status retrieved, kill_switch: {data['kill_switch_active']}, trading: {data['trading_enabled']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
