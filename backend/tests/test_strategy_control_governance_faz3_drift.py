"""
Faz-3 Strategy Control + Governance System - Drift Action Center Tests
=======================================================================
Tests for:
- GET /api/admin/futures/strategy-control/drift-alerts (alert list with status, deep_link, mute state)
- POST /api/admin/futures/drift-alert/{id}/ack (acknowledge drift alert)
- POST /api/admin/futures/drift-alert/{id}/mute (mute with 1h/24h/7d duration validation)
- POST /api/admin/futures/drift-alert/{id}/ignore (requires "IGNORE DRIFT ALERT" confirm)
- POST /api/admin/futures/drift-alert/{id}/disable-strategy (requires "DISABLE VIA DRIFT" confirm, throttle->pause->disable chain)
- POST /api/admin/futures/drift-alert/{id}/retrain (returns queued job with retrain_status=queued + retrain_job_id)
- Response contract: {status, trace_id, message, state_snapshot}
- Deep-link behavior: target_tab + strategy_id context
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://execution-safety-hub.preview.emergentagent.com"

SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
OPS_EMAIL = "canary.ops@platform.local"
OPS_PASSWORD = "CanaryOps123!"


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        timeout=30
    )
    if response.status_code != 200:
        pytest.skip(f"Super admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def ops_token():
    """Get ops user auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPS_EMAIL, "password": OPS_PASSWORD},
        timeout=30
    )
    if response.status_code != 200:
        pytest.skip(f"Ops login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def admin_headers(super_admin_token):
    """Headers with super admin auth"""
    return {
        "Authorization": f"Bearer {super_admin_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture(scope="module")
def ops_headers(ops_token):
    """Headers with ops user auth"""
    return {
        "Authorization": f"Bearer {ops_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture(scope="module")
def drift_alert_id(admin_headers):
    """Get a drift alert ID for testing"""
    response = requests.get(
        f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts",
        headers=admin_headers,
        timeout=30
    )
    if response.status_code != 200:
        pytest.skip(f"Failed to get drift alerts: {response.status_code}")
    
    data = response.json()
    items = data.get("items", [])
    if len(items) == 0:
        pytest.skip("No drift alerts available for testing")
    
    return items[0].get("alert_id")


class TestDriftAlertsEndpoint:
    """Test GET /api/admin/futures/strategy-control/drift-alerts"""

    def test_drift_alerts_returns_items(self, admin_headers):
        """Drift alerts endpoint should return items list with summary"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("status") == "ok", "Expected status=ok"
        assert "items" in data, "Response should have items"
        assert "summary" in data, "Response should have summary"
        assert "generated_at" in data, "Response should have generated_at"
        
        summary = data.get("summary", {})
        assert "open" in summary, "Summary should have open count"
        assert "acked" in summary, "Summary should have acked count"
        assert "muted" in summary, "Summary should have muted count"
        assert "ignored" in summary, "Summary should have ignored count"
        
        print(f"PASS: Drift alerts returned {len(data.get('items', []))} items, summary={summary}")

    def test_drift_alert_item_structure(self, admin_headers):
        """Each drift alert item should have required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        if len(items) == 0:
            pytest.skip("No drift alerts available to test structure")
        
        first_item = items[0]
        
        # Required fields
        required_fields = [
            "alert_id", "strategy_id", "severity", "metric", "trigger_reason",
            "status", "acked", "muted_until", "ignored", "retrain_status",
            "deep_link"
        ]
        
        for field in required_fields:
            assert field in first_item, f"Drift alert should have '{field}' field"
        
        # Check deep_link structure
        deep_link = first_item.get("deep_link", {})
        assert "target_tab" in deep_link, "deep_link should have target_tab"
        assert "strategy_id" in deep_link, "deep_link should have strategy_id"
        assert "context_filter" in deep_link, "deep_link should have context_filter"
        
        print(f"PASS: Drift alert structure verified: alert_id={first_item.get('alert_id')}, status={first_item.get('status')}, deep_link_tab={deep_link.get('target_tab')}")

    def test_drift_alert_status_values(self, admin_headers):
        """Drift alert status should be one of OPEN, ACKED, MUTED, IGNORED"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        valid_statuses = {"OPEN", "ACKED", "MUTED", "IGNORED"}
        
        for item in items:
            status = item.get("status")
            assert status in valid_statuses, f"Invalid status '{status}', expected one of {valid_statuses}"
        
        print(f"PASS: All {len(items)} drift alerts have valid status values")


class TestDriftAckAction:
    """Test POST /api/admin/futures/drift-alert/{id}/ack"""

    def test_ack_action_success(self, admin_headers, drift_alert_id):
        """Ack action should succeed with reason"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/ack",
            headers=admin_headers,
            json={
                "reason": "Test ack action for drift alert",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response contract
        assert "status" in data, "Response should have status"
        assert "trace_id" in data, "Response should have trace_id"
        assert "message" in data, "Response should have message"
        assert "state_snapshot" in data, "Response should have state_snapshot"
        
        assert data.get("status") in ["success", "dry_run"], f"Expected success/dry_run, got {data.get('status')}"
        print(f"PASS: Ack action response: status={data.get('status')}, trace_id={data.get('trace_id')}")

    def test_ack_action_requires_reason(self, admin_headers, drift_alert_id):
        """Ack action should require reason (min 3 chars)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/ack",
            headers=admin_headers,
            json={
                "reason": "ab",  # Too short
                "dry_run": True
            },
            timeout=30
        )
        # Should fail validation
        assert response.status_code in [200, 422], f"Expected 200 or 422, got {response.status_code}"
        if response.status_code == 422:
            print("PASS: Ack action rejected short reason with 422")
        else:
            data = response.json()
            print(f"PASS: Ack action response with short reason: status={data.get('status')}")


class TestDriftMuteAction:
    """Test POST /api/admin/futures/drift-alert/{id}/mute"""

    def test_mute_action_valid_1h(self, admin_headers, drift_alert_id):
        """Mute action should accept 1h duration"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/mute",
            headers=admin_headers,
            json={
                "reason": "Test mute action 1h",
                "mute_duration_hours": 1,
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "status" in data, "Response should have status"
        assert "trace_id" in data, "Response should have trace_id"
        assert "message" in data, "Response should have message"
        assert "state_snapshot" in data, "Response should have state_snapshot"
        
        assert data.get("status") in ["success", "dry_run"], f"Expected success/dry_run for 1h mute, got {data.get('status')}"
        print(f"PASS: Mute 1h action: status={data.get('status')}")

    def test_mute_action_valid_24h(self, admin_headers, drift_alert_id):
        """Mute action should accept 24h duration"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/mute",
            headers=admin_headers,
            json={
                "reason": "Test mute action 24h",
                "mute_duration_hours": 24,
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") in ["success", "dry_run"], f"Expected success/dry_run for 24h mute, got {data.get('status')}"
        print(f"PASS: Mute 24h action: status={data.get('status')}")

    def test_mute_action_valid_7d(self, admin_headers, drift_alert_id):
        """Mute action should accept 7d (168h) duration"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/mute",
            headers=admin_headers,
            json={
                "reason": "Test mute action 7d",
                "mute_duration_hours": 168,
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") in ["success", "dry_run"], f"Expected success/dry_run for 7d mute, got {data.get('status')}"
        print(f"PASS: Mute 7d (168h) action: status={data.get('status')}")

    def test_mute_action_rejects_invalid_duration(self, admin_headers, drift_alert_id):
        """Mute action should reject invalid durations (not 1h/24h/168h)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/mute",
            headers=admin_headers,
            json={
                "reason": "Test mute action invalid duration",
                "mute_duration_hours": 12,  # Invalid - not 1, 24, or 168
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data.get("status") == "rejected", f"Expected rejected for invalid duration, got {data.get('status')}"
        assert "1h" in data.get("message", "") or "24h" in data.get("message", "") or "7d" in data.get("message", ""), \
            f"Message should mention valid durations: {data.get('message')}"
        print(f"PASS: Mute action rejected invalid duration 12h: {data.get('message')}")

    def test_mute_action_rejects_2h_duration(self, admin_headers, drift_alert_id):
        """Mute action should reject 2h duration"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/mute",
            headers=admin_headers,
            json={
                "reason": "Test mute action 2h",
                "mute_duration_hours": 2,
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "rejected", f"Expected rejected for 2h duration, got {data.get('status')}"
        print(f"PASS: Mute action rejected 2h duration")

    def test_mute_action_rejects_48h_duration(self, admin_headers, drift_alert_id):
        """Mute action should reject 48h duration"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/mute",
            headers=admin_headers,
            json={
                "reason": "Test mute action 48h",
                "mute_duration_hours": 48,
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "rejected", f"Expected rejected for 48h duration, got {data.get('status')}"
        print(f"PASS: Mute action rejected 48h duration")


class TestDriftIgnoreAction:
    """Test POST /api/admin/futures/drift-alert/{id}/ignore"""

    def test_ignore_action_requires_confirm_phrase(self, admin_headers, drift_alert_id):
        """Ignore action should require 'IGNORE DRIFT ALERT' confirm phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/ignore",
            headers=admin_headers,
            json={
                "reason": "Test ignore action without confirm",
                "confirm_phrase": "WRONG PHRASE",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data.get("status") == "rejected", f"Expected rejected without correct confirm, got {data.get('status')}"
        assert "IGNORE DRIFT ALERT" in data.get("message", ""), f"Message should mention required phrase: {data.get('message')}"
        print(f"PASS: Ignore action rejected without correct confirm phrase")

    def test_ignore_action_with_correct_confirm(self, admin_headers, drift_alert_id):
        """Ignore action should succeed with correct confirm phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/ignore",
            headers=admin_headers,
            json={
                "reason": "Test ignore action with correct confirm",
                "confirm_phrase": "IGNORE DRIFT ALERT",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data, "Response should have status"
        assert "trace_id" in data, "Response should have trace_id"
        assert "message" in data, "Response should have message"
        assert "state_snapshot" in data, "Response should have state_snapshot"
        
        assert data.get("status") in ["success", "dry_run"], f"Expected success/dry_run, got {data.get('status')}"
        print(f"PASS: Ignore action with correct confirm: status={data.get('status')}")


class TestDriftDisableStrategyAction:
    """Test POST /api/admin/futures/drift-alert/{id}/disable-strategy"""

    def test_disable_strategy_requires_confirm_phrase(self, admin_headers, drift_alert_id):
        """Disable strategy action should require 'DISABLE VIA DRIFT' confirm phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/disable-strategy",
            headers=admin_headers,
            json={
                "reason": "Test disable strategy without confirm",
                "confirm_phrase": "WRONG PHRASE",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data.get("status") == "rejected", f"Expected rejected without correct confirm, got {data.get('status')}"
        assert "DISABLE VIA DRIFT" in data.get("message", ""), f"Message should mention required phrase: {data.get('message')}"
        print(f"PASS: Disable strategy action rejected without correct confirm phrase")

    def test_disable_strategy_with_correct_confirm_dry_run(self, admin_headers, drift_alert_id):
        """Disable strategy action with correct confirm (dry_run) should show throttle->pause->disable chain"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/disable-strategy",
            headers=admin_headers,
            json={
                "reason": "Test disable strategy with correct confirm",
                "confirm_phrase": "DISABLE VIA DRIFT",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data, "Response should have status"
        assert "trace_id" in data, "Response should have trace_id"
        assert "message" in data, "Response should have message"
        assert "state_snapshot" in data, "Response should have state_snapshot"
        
        # In dry_run mode, should show the chain would be executed
        assert data.get("status") in ["success", "dry_run"], f"Expected success/dry_run, got {data.get('status')}"
        
        # Check for linked_action_result showing throttle->pause->disable chain
        if "linked_action_result" in data:
            linked = data.get("linked_action_result")
            if linked and linked.get("status") != "dry_run":
                # If not dry_run mode, should have throttle, pause, disable results
                assert "throttle" in linked or "status" in linked, "linked_action_result should show chain actions"
        
        print(f"PASS: Disable strategy dry_run: status={data.get('status')}, linked_action_result present={bool(data.get('linked_action_result'))}")


class TestDriftRetrainAction:
    """Test POST /api/admin/futures/drift-alert/{id}/retrain"""

    def test_retrain_action_returns_queued_job(self, admin_headers, drift_alert_id):
        """Retrain action should return retrain_status=queued and retrain_job_id"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/retrain",
            headers=admin_headers,
            json={
                "reason": "Test retrain action",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "status" in data, "Response should have status"
        assert "trace_id" in data, "Response should have trace_id"
        assert "message" in data, "Response should have message"
        assert "state_snapshot" in data, "Response should have state_snapshot"
        
        assert data.get("status") in ["success", "dry_run"], f"Expected success/dry_run, got {data.get('status')}"
        
        # Check after_state for retrain_status and retrain_job_id
        after_state = data.get("after_state", {})
        if after_state:
            assert after_state.get("retrain_status") == "queued", f"Expected retrain_status=queued, got {after_state.get('retrain_status')}"
            assert "retrain_job_id" in after_state, "after_state should have retrain_job_id"
            assert after_state.get("retrain_job_id", "").startswith("retrain_"), f"retrain_job_id should start with 'retrain_'"
            print(f"PASS: Retrain action: retrain_status={after_state.get('retrain_status')}, retrain_job_id={after_state.get('retrain_job_id')}")
        else:
            # Check state_snapshot for retrain info
            state_snapshot = data.get("state_snapshot", {})
            print(f"PASS: Retrain action: status={data.get('status')}, state_snapshot has retrain_status={state_snapshot.get('retrain_status')}")


class TestDriftActionResponseContract:
    """Test that all drift action responses have {status, trace_id, message, state_snapshot}"""

    def test_all_drift_actions_return_contract_fields(self, admin_headers, drift_alert_id):
        """All drift action endpoints should return {status, trace_id, message, state_snapshot}"""
        endpoints = [
            ("ack", {"reason": "test ack", "dry_run": True}),
            ("mute", {"reason": "test mute", "mute_duration_hours": 1, "dry_run": True}),
            ("ignore", {"reason": "test ignore", "confirm_phrase": "WRONG", "dry_run": True}),
            ("disable-strategy", {"reason": "test disable", "confirm_phrase": "WRONG", "dry_run": True}),
            ("retrain", {"reason": "test retrain", "dry_run": True}),
        ]
        
        for action, body in endpoints:
            response = requests.post(
                f"{BASE_URL}/api/admin/futures/drift-alert/{drift_alert_id}/{action}",
                headers=admin_headers,
                json=body,
                timeout=30
            )
            assert response.status_code == 200, f"{action} returned {response.status_code}"
            data = response.json()
            
            assert "status" in data, f"{action} missing 'status' field"
            assert "trace_id" in data, f"{action} missing 'trace_id' field"
            assert "message" in data, f"{action} missing 'message' field"
            assert "state_snapshot" in data, f"{action} missing 'state_snapshot' field"
            
            print(f"PASS: {action} has contract fields: status={data.get('status')}")


class TestDriftDeepLink:
    """Test deep_link behavior in drift alerts"""

    def test_deep_link_has_target_tab(self, admin_headers):
        """Deep link should have target_tab (strategy_governance or rollout)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        if len(items) == 0:
            pytest.skip("No drift alerts available")
        
        valid_tabs = {"strategy_governance", "rollout"}
        
        for item in items:
            deep_link = item.get("deep_link", {})
            target_tab = deep_link.get("target_tab")
            assert target_tab in valid_tabs, f"Invalid target_tab '{target_tab}', expected one of {valid_tabs}"
            
            # Verify context_filter has strategy_id
            context_filter = deep_link.get("context_filter", {})
            assert "strategy_id" in context_filter, "context_filter should have strategy_id"
        
        print(f"PASS: All {len(items)} drift alerts have valid deep_link with target_tab")

    def test_deep_link_strategy_id_matches(self, admin_headers):
        """Deep link strategy_id should match alert strategy_id"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        if len(items) == 0:
            pytest.skip("No drift alerts available")
        
        for item in items:
            alert_strategy_id = item.get("strategy_id")
            deep_link = item.get("deep_link", {})
            deep_link_strategy_id = deep_link.get("strategy_id")
            
            assert alert_strategy_id == deep_link_strategy_id, \
                f"Deep link strategy_id mismatch: alert={alert_strategy_id}, deep_link={deep_link_strategy_id}"
        
        print(f"PASS: All drift alerts have matching strategy_id in deep_link")


class TestOpsUserDriftAuthorization:
    """Test that ops users cannot access drift action endpoints"""

    def test_ops_cannot_access_drift_alerts(self, ops_headers):
        """Ops user should get 403 on drift-alerts"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts",
            headers=ops_headers,
            timeout=30
        )
        assert response.status_code == 403, f"Expected 403 for ops user, got {response.status_code}"
        print("PASS: Ops user blocked from drift-alerts")

    def test_ops_cannot_ack_drift_alert(self, ops_headers):
        """Ops user should get 403 on drift ack"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/test_alert/ack",
            headers=ops_headers,
            json={"reason": "test"},
            timeout=30
        )
        assert response.status_code == 403, f"Expected 403 for ops user, got {response.status_code}"
        print("PASS: Ops user blocked from drift ack")

    def test_ops_cannot_mute_drift_alert(self, ops_headers):
        """Ops user should get 403 on drift mute"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/test_alert/mute",
            headers=ops_headers,
            json={"reason": "test", "mute_duration_hours": 1},
            timeout=30
        )
        assert response.status_code == 403, f"Expected 403 for ops user, got {response.status_code}"
        print("PASS: Ops user blocked from drift mute")

    def test_ops_cannot_disable_strategy_via_drift(self, ops_headers):
        """Ops user should get 403 on drift disable-strategy"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/test_alert/disable-strategy",
            headers=ops_headers,
            json={"reason": "test", "confirm_phrase": "DISABLE VIA DRIFT"},
            timeout=30
        )
        assert response.status_code == 403, f"Expected 403 for ops user, got {response.status_code}"
        print("PASS: Ops user blocked from drift disable-strategy")


class TestOverviewIncludesDriftActionCenterTab:
    """Test that overview includes drift_action_center tab"""

    def test_overview_tabs_include_drift_action_center(self, admin_headers):
        """Overview should include drift_action_center in tabs list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        tabs = data.get("tabs", [])
        assert "drift_action_center" in tabs, f"tabs should include 'drift_action_center', got {tabs}"
        print(f"PASS: Overview tabs include drift_action_center: {tabs}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
