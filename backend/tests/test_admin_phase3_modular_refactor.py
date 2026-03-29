"""
Test suite for admin_phase3 modular refactor (E tur kapsamı):
- Backward compatibility: existing routes still work
- New module endpoints: playbook preview/apply, auto-ack policy, kpi-before-after
- Strategy timeline KPI cards
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://unified-orchestrator.preview.emergentagent.com"

# Test credentials
TEST_EMAIL = "canary.admin@platform.local"
TEST_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for super_admin"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30,
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in auth response")
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestBackwardCompatibility:
    """Test that existing admin_phase3 routes still work after modular refactor"""

    def test_execution_policies_list(self, auth_headers):
        """GET /admin-phase3/execution-policies - backward compat"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-policies",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"

    def test_failed_events_list(self, auth_headers):
        """GET /admin-phase3/failed-events - backward compat"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/failed-events",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"

    def test_execution_state_transitions_control(self, auth_headers):
        """GET /admin-phase3/execution-state-transitions/control - backward compat"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "rows" in data, "Expected 'rows' in response"
        assert "summary_counts" in data, "Expected 'summary_counts' in response"
        assert "state_counters" in data, "Expected 'state_counters' in response"

    def test_execution_analytics_summary(self, auth_headers):
        """GET /admin-phase3/execution-analytics/summary - backward compat"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "snapshot_at" in data, "Expected 'snapshot_at' in response"
        assert "totals" in data, "Expected 'totals' in response"

    def test_execution_alerts_list(self, auth_headers):
        """GET /admin-phase3/execution-alerts - backward compat"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-alerts",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"

    def test_incident_snapshots_diff(self, auth_headers):
        """POST /admin-phase3/incident-snapshots/diff - backward compat"""
        # Use time_range scope for testing
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "time_from": "2026-01-01T00:00:00+00:00",
                "time_to": "2026-01-02T00:00:00+00:00",
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "state_snapshot" in data, "Expected 'state_snapshot' in response"


class TestNewPlaybookEndpoints:
    """Test new playbook preview/apply endpoints from recovery module"""

    def test_playbook_preview_endpoint_exists(self, auth_headers):
        """POST /admin-phase3/incident-snapshots/playbook/preview - new endpoint"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=auth_headers,
            json={
                "recommended_actions": [
                    {"action": "test_action", "severity": "INFO", "reason": "test_reason"}
                ],
                "anomaly_notes": ["test note"],
                "scope": {"test": "scope"},
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success", f"Expected status=success, got {data}"
        assert "preview_token" in data, "Expected 'preview_token' in response"
        assert "preview" in data, "Expected 'preview' in response"
        preview = data["preview"]
        assert preview.get("non_destructive") is True, "Expected non_destructive=True"
        assert "highest_severity" in preview, "Expected 'highest_severity' in preview"
        assert "steps" in preview, "Expected 'steps' in preview"

    def test_playbook_preview_default_action(self, auth_headers):
        """POST /admin-phase3/incident-snapshots/playbook/preview - empty actions defaults"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=auth_headers,
            json={
                "recommended_actions": [],
                "anomaly_notes": [],
                "scope": {},
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        preview = data.get("preview", {})
        steps = preview.get("steps", [])
        # Should have default action when empty
        assert len(steps) >= 1, "Expected at least 1 default step"

    def test_playbook_apply_requires_confirm(self, auth_headers):
        """POST /admin-phase3/incident-snapshots/playbook/apply - confirm required"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/apply",
            headers=auth_headers,
            json={
                "preview_token": "invalid_token",
                "confirm": False,
                "reason": "test reason",
            },
            timeout=30,
        )
        assert response.status_code == 422, f"Expected 422 for confirm=False, got {response.status_code}"
        data = response.json()
        assert "confirm_required" in str(data.get("detail", "")), f"Expected confirm_required error: {data}"

    def test_playbook_apply_requires_valid_token(self, auth_headers):
        """POST /admin-phase3/incident-snapshots/playbook/apply - token validation"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/apply",
            headers=auth_headers,
            json={
                "preview_token": "invalid_token_12345",
                "confirm": True,
                "reason": "test reason for apply",
            },
            timeout=30,
        )
        assert response.status_code == 422, f"Expected 422 for invalid token, got {response.status_code}"
        data = response.json()
        assert "preview_token_invalid_or_expired" in str(data.get("detail", "")), f"Expected token error: {data}"

    def test_playbook_full_flow_preview_then_apply(self, auth_headers):
        """Full flow: preview -> apply with valid token"""
        # Step 1: Get preview token
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=auth_headers,
            json={
                "recommended_actions": [
                    {"action": "review_failed_events", "severity": "WARNING", "reason": "high_failure_rate"}
                ],
                "anomaly_notes": ["Failure rate increased"],
                "scope": {"test_flow": True},
            },
            timeout=30,
        )
        assert preview_response.status_code == 200, f"Preview failed: {preview_response.text}"
        preview_data = preview_response.json()
        preview_token = preview_data.get("preview_token")
        assert preview_token, "No preview_token returned"

        # Step 2: Apply with valid token
        apply_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/apply",
            headers=auth_headers,
            json={
                "preview_token": preview_token,
                "confirm": True,
                "reason": "Testing playbook apply flow",
            },
            timeout=30,
        )
        assert apply_response.status_code == 200, f"Apply failed: {apply_response.text}"
        apply_data = apply_response.json()
        assert apply_data.get("status") == "success", f"Expected status=success: {apply_data}"
        assert "playbook_apply_completed" in apply_data.get("message", ""), f"Expected completion message: {apply_data}"
        result = apply_data.get("result", {})
        assert result.get("non_destructive") is True, "Expected non_destructive=True in result"
        assert result.get("confirmed") is True, "Expected confirmed=True in result"


class TestAutoAckPolicyEndpoints:
    """Test new auto-ack policy endpoints from alerts module"""

    def test_auto_ack_policy_get(self, auth_headers):
        """GET /admin-phase3/execution-alerts/auto-ack/policy - new endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-alerts/auto-ack/policy",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success", f"Expected status=success: {data}"
        assert "policy" in data, "Expected 'policy' in response"
        policy = data["policy"]
        assert "enabled" in policy, "Expected 'enabled' in policy"
        assert "threshold_hours" in policy, "Expected 'threshold_hours' in policy"
        assert "only_execution_alerts" in policy, "Expected 'only_execution_alerts' in policy"

    def test_auto_ack_policy_update(self, auth_headers):
        """PUT /admin-phase3/execution-alerts/auto-ack/policy - new endpoint"""
        response = requests.put(
            f"{BASE_URL}/api/admin-phase3/execution-alerts/auto-ack/policy",
            headers=auth_headers,
            json={
                "enabled": True,
                "threshold_hours": 48,
                "only_execution_alerts": True,
                "reason": "Testing policy update",
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success", f"Expected status=success: {data}"
        assert "auto_ack_policy_updated" in data.get("message", ""), f"Expected update message: {data}"
        policy = data.get("policy", {})
        assert policy.get("threshold_hours") == 48, f"Expected threshold_hours=48: {policy}"

    def test_auto_ack_policy_update_requires_reason(self, auth_headers):
        """PUT /admin-phase3/execution-alerts/auto-ack/policy - reason validation"""
        response = requests.put(
            f"{BASE_URL}/api/admin-phase3/execution-alerts/auto-ack/policy",
            headers=auth_headers,
            json={
                "enabled": True,
                "threshold_hours": 24,
                "only_execution_alerts": True,
                "reason": "ab",  # Too short
            },
            timeout=30,
        )
        assert response.status_code == 422, f"Expected 422 for short reason, got {response.status_code}"

    def test_auto_ack_run_dry_run(self, auth_headers):
        """POST /admin-phase3/execution-alerts/auto-ack/run - dry run mode"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-alerts/auto-ack/run",
            headers=auth_headers,
            params={
                "reason": "test_dry_run_execution",
                "dry_run": True,
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success", f"Expected status=success: {data}"
        assert data.get("dry_run") is True, f"Expected dry_run=True: {data}"
        assert "acked_count" in data, "Expected 'acked_count' in response"
        assert "ids" in data, "Expected 'ids' in response"

    def test_auto_ack_run_actual(self, auth_headers):
        """POST /admin-phase3/execution-alerts/auto-ack/run - actual run"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-alerts/auto-ack/run",
            headers=auth_headers,
            params={
                "reason": "test_actual_run_execution",
                "dry_run": False,
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success", f"Expected status=success: {data}"
        # dry_run should be False or not present
        assert data.get("dry_run") is not True or data.get("dry_run") is False, f"Expected dry_run=False: {data}"


class TestKpiBeforeAfterEndpoint:
    """Test new KPI before/after endpoint from analytics module"""

    def test_kpi_before_after_24h(self, auth_headers):
        """GET /admin-phase3/execution-analytics/kpi-before-after - 24h window"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/kpi-before-after",
            headers=auth_headers,
            params={"window": "24h"},
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success", f"Expected status=success: {data}"
        assert data.get("window") == "24h", f"Expected window=24h: {data}"
        assert "range_current" in data, "Expected 'range_current' in response"
        assert "range_previous" in data, "Expected 'range_previous' in response"
        assert "cards" in data, "Expected 'cards' in response"
        
        cards = data["cards"]
        # Check expected KPI card keys
        for key in ["transitions", "failed_events", "manual_actions"]:
            assert key in cards, f"Expected '{key}' in cards"
            card = cards[key]
            assert "before" in card, f"Expected 'before' in {key} card"
            assert "after" in card, f"Expected 'after' in {key} card"
            assert "delta" in card, f"Expected 'delta' in {key} card"

    def test_kpi_before_after_7d(self, auth_headers):
        """GET /admin-phase3/execution-analytics/kpi-before-after - 7d window"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/kpi-before-after",
            headers=auth_headers,
            params={"window": "7d"},
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("window") == "7d", f"Expected window=7d: {data}"

    def test_kpi_before_after_30d(self, auth_headers):
        """GET /admin-phase3/execution-analytics/kpi-before-after - 30d window"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/kpi-before-after",
            headers=auth_headers,
            params={"window": "30d"},
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("window") == "30d", f"Expected window=30d: {data}"


class TestExportFilterOptions:
    """Test export filter options endpoint from export module"""

    def test_export_filter_options(self, auth_headers):
        """GET /admin-phase3/incident-snapshots/export/filter-options - new endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export/filter-options",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success", f"Expected status=success: {data}"
        assert "filter_scope_priority" in data, "Expected 'filter_scope_priority' in response"
        assert "allowed_filter_values" in data, "Expected 'allowed_filter_values' in response"
        assert "compare_mode_rules" in data, "Expected 'compare_mode_rules' in response"


class TestStrategyActionImpactTimeline:
    """Test strategy action-impact-timeline endpoint with KPI cards"""

    def test_action_impact_timeline_with_kpi_cards(self, auth_headers):
        """GET /admin/strategy/action-impact-timeline - KPI cards included"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=auth_headers,
            params={"window": "24h", "limit": 50},
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success", f"Expected status=success: {data}"
        assert "filters" in data, "Expected 'filters' in response"
        assert "summary" in data, "Expected 'summary' in response"
        assert "items" in data, "Expected 'items' in response"
        assert "kpi_cards" in data, "Expected 'kpi_cards' in response"
        
        kpi_cards = data["kpi_cards"]
        # Check expected KPI card keys
        for key in ["selected_signals", "rejected_signals", "risk_breaches"]:
            assert key in kpi_cards, f"Expected '{key}' in kpi_cards"
            card = kpi_cards[key]
            assert "before" in card, f"Expected 'before' in {key} card"
            assert "after" in card, f"Expected 'after' in {key} card"
            assert "delta" in card, f"Expected 'delta' in {key} card"

    def test_action_impact_timeline_with_strategy_filter(self, auth_headers):
        """GET /admin/strategy/action-impact-timeline - with strategy_id filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=auth_headers,
            params={"window": "24h", "strategy_id": "test_strategy", "limit": 20},
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        filters = data.get("filters", {})
        assert filters.get("strategy_id") == "test_strategy", f"Expected strategy_id filter: {filters}"


class TestStrategyObservabilityDetail:
    """Test strategy observability detail endpoint"""

    def test_observability_strategies_list(self, auth_headers):
        """GET /admin/strategy/observability/strategies - list available strategies"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability/strategies",
            headers=auth_headers,
            params={"window": "24h"},
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data, "Expected 'items' in response"
        assert "count" in data, "Expected 'count' in response"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
