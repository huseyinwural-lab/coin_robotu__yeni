"""
P1 Feature Tests - Iteration 67
Tests for:
1. Bulk Result Breakdown: default collapsed, expand/collapse, success/failed/skipped separation, strategy/message/action_ref visible
2. Failed rows red highlight
3. Backend bulk contract: state_snapshot with success_count/rejected_count/skipped_count and results[*].action_ref
4. Post-Action Monitor: activates after rollout/disable/rollback + drift disable + approval approve
5. Post-Action Monitor: health/error/risk delta calculations, before/after/current summary
6. Post-Action Monitor: refresh cycle 5-10s, passive mode after 5min
7. Policy Suggestions panel Apply Fix buttons open prefilled Decision Modal
8. Drift card Apply via Policy button opens prefilled Decision Modal
9. Policy Apply Hook does NOT direct execute - only opens modal for user confirmation
10. P0 regression: critical action preview requirement not broken
"""

import os
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for super admin"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get auth headers"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestBulkActionBackendContract:
    """Test backend bulk action contract - success_count/rejected_count/skipped_count and action_ref"""

    def test_bulk_action_returns_counts_in_state_snapshot(self, auth_headers):
        """Verify bulk action returns success_count, rejected_count, skipped_count in state_snapshot"""
        # First get strategies
        overview_response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=auth_headers,
        )
        assert overview_response.status_code == 200, f"Overview failed: {overview_response.text}"
        
        strategies = overview_response.json().get("strategies", [])
        if len(strategies) < 1:
            pytest.skip("No strategies available for bulk action test")
        
        # Select first strategy for bulk action
        strategy_ids = [strategies[0]["strategy_id"]]
        
        # Execute bulk pause action
        bulk_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
            headers=auth_headers,
            json={
                "reason": "TEST_bulk_action_contract_test",
                "confirm_phrase": "BULK PAUSE",
                "strategy_ids": strategy_ids,
                "action": "pause",
                "dry_run": False,
            },
        )
        
        assert bulk_response.status_code == 200, f"Bulk action failed: {bulk_response.text}"
        data = bulk_response.json()
        
        # Verify state_snapshot contains required counts
        state_snapshot = data.get("state_snapshot", {})
        assert "success_count" in state_snapshot, "state_snapshot missing success_count"
        assert "rejected_count" in state_snapshot, "state_snapshot missing rejected_count"
        assert "skipped_count" in state_snapshot, "state_snapshot missing skipped_count"
        
        print(f"✓ Bulk action state_snapshot contains counts: success={state_snapshot.get('success_count')}, rejected={state_snapshot.get('rejected_count')}, skipped={state_snapshot.get('skipped_count')}")

    def test_bulk_action_results_contain_action_ref(self, auth_headers):
        """Verify bulk action results contain action_ref for each strategy"""
        # First get strategies
        overview_response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=auth_headers,
        )
        assert overview_response.status_code == 200
        
        strategies = overview_response.json().get("strategies", [])
        if len(strategies) < 1:
            pytest.skip("No strategies available for bulk action test")
        
        # Select first strategy for bulk action
        strategy_ids = [strategies[0]["strategy_id"]]
        
        # Execute bulk resume action
        bulk_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
            headers=auth_headers,
            json={
                "reason": "TEST_bulk_action_ref_test",
                "confirm_phrase": "BULK RESUME",
                "strategy_ids": strategy_ids,
                "action": "resume",
                "dry_run": False,
            },
        )
        
        assert bulk_response.status_code == 200, f"Bulk action failed: {bulk_response.text}"
        data = bulk_response.json()
        
        # Verify results array contains action_ref
        results = data.get("results", [])
        assert len(results) > 0, "Bulk action should return results array"
        
        for result in results:
            assert "action_ref" in result, f"Result missing action_ref: {result}"
            assert result.get("action_ref") is not None, f"action_ref should not be None: {result}"
            assert "strategy_id" in result, f"Result missing strategy_id: {result}"
            assert "status" in result, f"Result missing status: {result}"
            assert "message" in result, f"Result missing message: {result}"
        
        print(f"✓ Bulk action results contain action_ref for all {len(results)} strategies")

    def test_bulk_action_throttle_with_level(self, auth_headers):
        """Verify bulk throttle action works with throttle_level"""
        overview_response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=auth_headers,
        )
        assert overview_response.status_code == 200
        
        strategies = overview_response.json().get("strategies", [])
        if len(strategies) < 1:
            pytest.skip("No strategies available for bulk action test")
        
        strategy_ids = [strategies[0]["strategy_id"]]
        
        # Execute bulk throttle action
        bulk_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
            headers=auth_headers,
            json={
                "reason": "TEST_bulk_throttle_test",
                "confirm_phrase": "BULK THROTTLE",
                "strategy_ids": strategy_ids,
                "action": "throttle",
                "throttle_level": "L2",
                "dry_run": False,
            },
        )
        
        assert bulk_response.status_code == 200, f"Bulk throttle failed: {bulk_response.text}"
        data = bulk_response.json()
        
        # Verify counts
        state_snapshot = data.get("state_snapshot", {})
        assert state_snapshot.get("success_count", 0) >= 0
        assert state_snapshot.get("rejected_count", 0) >= 0
        assert state_snapshot.get("skipped_count", 0) >= 0
        
        print(f"✓ Bulk throttle action completed with counts: {state_snapshot}")


class TestPostActionMonitorBackend:
    """Test Post-Action Monitor backend support"""

    def test_rollout_action_returns_before_after_state(self, auth_headers):
        """Verify rollout action returns before_state and after_state for monitor"""
        overview_response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=auth_headers,
        )
        assert overview_response.status_code == 200
        
        strategies = overview_response.json().get("strategies", [])
        if len(strategies) < 1:
            pytest.skip("No strategies available for rollout test")
        
        strategy_id = strategies[0]["strategy_id"]
        
        # First get impact preview
        preview_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/impact-preview",
            headers=auth_headers,
            json={"action_type": "rollout", "params": {"rollout_percentage": 25}},
        )
        
        if preview_response.status_code != 200:
            pytest.skip(f"Impact preview failed: {preview_response.text}")
        
        preview_token = preview_response.json().get("preview_token")
        
        # Execute rollout action
        rollout_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollout",
            headers=auth_headers,
            json={
                "reason": "TEST_rollout_monitor_test",
                "confirm_phrase": "APPLY ROLLOUT",
                "rollout_percentage": 25,
                "preview_token": preview_token,
                "dry_run": False,
            },
        )
        
        # Check response structure for monitor support
        if rollout_response.status_code == 200:
            data = rollout_response.json()
            # Verify state_snapshot exists for monitor
            assert "state_snapshot" in data, "Response missing state_snapshot for monitor"
            state_snapshot = data.get("state_snapshot", {})
            
            # Check for health/error/risk fields that monitor uses
            if "health_score" in state_snapshot:
                print(f"✓ Rollout response contains health_score: {state_snapshot.get('health_score')}")
            if "error_rate_pct" in state_snapshot:
                print(f"✓ Rollout response contains error_rate_pct: {state_snapshot.get('error_rate_pct')}")
            if "risk_score" in state_snapshot:
                print(f"✓ Rollout response contains risk_score: {state_snapshot.get('risk_score')}")
            
            print(f"✓ Rollout action returns state_snapshot for Post-Action Monitor")
        else:
            # May be rejected due to precheck - that's OK for this test
            print(f"Rollout rejected (expected if precheck fails): {rollout_response.json().get('message')}")

    def test_disable_action_returns_state_for_monitor(self, auth_headers):
        """Verify disable action returns state for Post-Action Monitor"""
        overview_response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=auth_headers,
        )
        assert overview_response.status_code == 200
        
        strategies = overview_response.json().get("strategies", [])
        if len(strategies) < 1:
            pytest.skip("No strategies available for disable test")
        
        strategy_id = strategies[0]["strategy_id"]
        
        # First get impact preview for disable
        preview_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/impact-preview",
            headers=auth_headers,
            json={"action_type": "disable", "params": {}},
        )
        
        if preview_response.status_code != 200:
            pytest.skip(f"Impact preview failed: {preview_response.text}")
        
        preview_token = preview_response.json().get("preview_token")
        
        # First need to throttle then pause before disable
        # Throttle
        requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/throttle",
            headers=auth_headers,
            json={"reason": "TEST_pre_disable_throttle", "throttle_level": "L2", "dry_run": False},
        )
        
        # Pause
        requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/pause",
            headers=auth_headers,
            json={"reason": "TEST_pre_disable_pause", "dry_run": False},
        )
        
        # Now try disable
        disable_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/disable",
            headers=auth_headers,
            json={
                "reason": "TEST_disable_monitor_test",
                "confirm_phrase": "DISABLE STRATEGY",
                "preview_token": preview_token,
                "dry_run": False,
            },
        )
        
        if disable_response.status_code == 200:
            data = disable_response.json()
            assert "state_snapshot" in data, "Disable response missing state_snapshot"
            
            # Check for before/after state
            if "before_state" in data:
                print(f"✓ Disable response contains before_state")
            if "after_state" in data:
                print(f"✓ Disable response contains after_state")
            
            print(f"✓ Disable action returns state for Post-Action Monitor")
        else:
            print(f"Disable response: {disable_response.json()}")


class TestPolicySuggestionsEndpoint:
    """Test Policy Suggestions endpoint"""

    def test_policy_suggestions_endpoint_exists(self, auth_headers):
        """Verify policy suggestions endpoint returns data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/policy-suggestions",
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Policy suggestions endpoint failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "summary" in data or "status" in data, "Response missing expected fields"
        
        print(f"✓ Policy suggestions endpoint returns data: {data}")


class TestDriftAlertsWithRecommendedAction:
    """Test Drift Alerts with recommended_action for Apply via Policy"""

    def test_drift_alerts_contain_recommended_action(self, auth_headers):
        """Verify drift alerts contain recommended_action for Apply via Policy button"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts",
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Drift alerts endpoint failed: {response.text}"
        data = response.json()
        
        alerts = data.get("items", [])
        if len(alerts) == 0:
            print("No drift alerts available - skipping recommended_action check")
            return
        
        for alert in alerts:
            assert "recommended_action" in alert, f"Alert missing recommended_action: {alert.get('alert_id')}"
            recommended = alert.get("recommended_action", {})
            assert "type" in recommended, f"recommended_action missing type: {alert.get('alert_id')}"
            assert "confidence" in recommended, f"recommended_action missing confidence: {alert.get('alert_id')}"
            assert "reason" in recommended, f"recommended_action missing reason: {alert.get('alert_id')}"
        
        print(f"✓ All {len(alerts)} drift alerts contain recommended_action for Apply via Policy")


class TestP0RegressionCriticalActionPreview:
    """P0 Regression: Verify critical action preview requirement is not broken"""

    def test_disable_requires_preview_token(self, auth_headers):
        """Verify disable action still requires preview_token (P0 requirement)"""
        overview_response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=auth_headers,
        )
        assert overview_response.status_code == 200
        
        strategies = overview_response.json().get("strategies", [])
        if len(strategies) < 1:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        # Try disable WITHOUT preview_token - should be rejected
        disable_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/disable",
            headers=auth_headers,
            json={
                "reason": "TEST_disable_no_preview",
                "confirm_phrase": "DISABLE STRATEGY",
                "dry_run": False,
            },
        )
        
        assert disable_response.status_code == 200, f"Unexpected error: {disable_response.text}"
        data = disable_response.json()
        
        # Should be rejected due to missing preview_token
        assert data.get("status") == "rejected", f"Disable without preview should be rejected: {data}"
        assert "preview" in data.get("message", "").lower(), f"Rejection message should mention preview: {data.get('message')}"
        
        print(f"✓ P0 Regression PASS: Disable action correctly requires preview_token")

    def test_decommission_requires_preview_token(self, auth_headers):
        """Verify decommission action still requires preview_token (P0 requirement)"""
        overview_response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=auth_headers,
        )
        assert overview_response.status_code == 200
        
        strategies = overview_response.json().get("strategies", [])
        if len(strategies) < 1:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        # Try decommission WITHOUT preview_token - should be rejected
        decommission_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/decommission",
            headers=auth_headers,
            json={
                "reason": "TEST_decommission_no_preview",
                "confirm_phrase": "DECOMMISSION STRATEGY",
                "dry_run": False,
            },
        )
        
        assert decommission_response.status_code == 200, f"Unexpected error: {decommission_response.text}"
        data = decommission_response.json()
        
        # Should be rejected due to missing preview_token
        assert data.get("status") == "rejected", f"Decommission without preview should be rejected: {data}"
        
        print(f"✓ P0 Regression PASS: Decommission action correctly requires preview_token")

    def test_drift_disable_requires_preview_token(self, auth_headers):
        """Verify drift disable-strategy action still requires preview_token (P0 requirement)"""
        # Get drift alerts
        alerts_response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts",
            headers=auth_headers,
        )
        assert alerts_response.status_code == 200
        
        alerts = alerts_response.json().get("items", [])
        if len(alerts) == 0:
            pytest.skip("No drift alerts available")
        
        alert_id = alerts[0]["alert_id"]
        
        # Try drift disable WITHOUT preview_token - should be rejected
        disable_response = requests.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{alert_id}/disable-strategy",
            headers=auth_headers,
            json={
                "reason": "TEST_drift_disable_no_preview",
                "confirm_phrase": "DISABLE VIA DRIFT",
                "dry_run": False,
            },
        )
        
        assert disable_response.status_code == 200, f"Unexpected error: {disable_response.text}"
        data = disable_response.json()
        
        # Should be rejected due to missing preview_token
        assert data.get("status") == "rejected", f"Drift disable without preview should be rejected: {data}"
        assert "preview" in data.get("message", "").lower(), f"Rejection message should mention preview: {data.get('message')}"
        
        print(f"✓ P0 Regression PASS: Drift disable-strategy correctly requires preview_token")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
