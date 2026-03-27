"""
Test suite for P2-409, P2-410, P2-411 features:
- P2-409: Role-based requester/approver separation for conflict auto-remediation workflow
- P2-410: Validation check-level trend chart + drift root-cause hints
- P2-411: Heatmap confidence score + anomaly band + 24h vs 30d comparison
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_EMAIL = "canary.admin@platform.local"
TEST_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in auth response")
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ============================================================================
# P2-409: Workflow Policy Endpoints
# ============================================================================

class TestP2409WorkflowPolicy:
    """P2-409: Role-based requester/approver separation workflow policy"""

    def test_get_workflow_policy_endpoint_exists(self, auth_headers):
        """GET /api/venues/admin/conflict-auto-remediation-workflow-policy returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-workflow-policy",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_get_workflow_policy_returns_required_fields(self, auth_headers):
        """Workflow policy contains requester_roles, approver_roles, strict_actor_separation"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-workflow-policy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "requester_roles" in data, "Missing requester_roles field"
        assert "approver_roles" in data, "Missing approver_roles field"
        assert "strict_actor_separation" in data, "Missing strict_actor_separation field"
        assert isinstance(data["requester_roles"], list), "requester_roles should be a list"
        assert isinstance(data["approver_roles"], list), "approver_roles should be a list"
        assert isinstance(data["strict_actor_separation"], bool), "strict_actor_separation should be bool"

    def test_put_workflow_policy_updates_successfully(self, auth_headers):
        """PUT /api/venues/admin/conflict-auto-remediation-workflow-policy updates policy"""
        payload = {
            "requester_roles": ["ops", "admin", "super_admin"],
            "approver_roles": ["admin", "super_admin"],
            "strict_actor_separation": False,
        }
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-workflow-policy",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("updated") is True, "Expected updated=True"
        assert "workflow_policy" in data, "Missing workflow_policy in response"

    def test_put_workflow_policy_validates_requester_roles(self, auth_headers):
        """PUT workflow policy requires requester_roles"""
        payload = {
            "requester_roles": [],
            "approver_roles": ["admin"],
            "strict_actor_separation": False,
        }
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-workflow-policy",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 400, f"Expected 400 for empty requester_roles, got {response.status_code}"

    def test_put_workflow_policy_validates_approver_roles(self, auth_headers):
        """PUT workflow policy requires approver_roles"""
        payload = {
            "requester_roles": ["admin"],
            "approver_roles": [],
            "strict_actor_separation": False,
        }
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-workflow-policy",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 400, f"Expected 400 for empty approver_roles, got {response.status_code}"


class TestP2409DraftsWithWorkflowPolicy:
    """P2-409: Drafts endpoint includes workflow_policy and pending_approval_count"""

    def test_drafts_returns_workflow_policy(self, auth_headers):
        """GET /api/venues/admin/conflict-auto-remediation-drafts includes workflow_policy"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "workflow_policy" in data, "Missing workflow_policy in drafts response"
        workflow_policy = data["workflow_policy"]
        assert "requester_roles" in workflow_policy, "Missing requester_roles in workflow_policy"
        assert "approver_roles" in workflow_policy, "Missing approver_roles in workflow_policy"
        assert "strict_actor_separation" in workflow_policy, "Missing strict_actor_separation"

    def test_drafts_returns_pending_approval_count(self, auth_headers):
        """GET /api/venues/admin/conflict-auto-remediation-drafts includes pending_approval_count"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "summary" in data, "Missing summary in drafts response"
        summary = data["summary"]
        assert "pending_approval_count" in summary, "Missing pending_approval_count in summary"
        assert isinstance(summary["pending_approval_count"], int), "pending_approval_count should be int"


class TestP2409ApplyModes:
    """P2-409: Apply endpoint modes (dry_run, submit, approve_apply) with workflow_policy"""

    def test_apply_dry_run_returns_workflow_policy(self, auth_headers):
        """POST apply with mode=dry_run returns workflow_policy"""
        # First get drafts to find a valid draft_id
        drafts_response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts",
            headers=auth_headers,
        )
        drafts = drafts_response.json().get("drafts", [])
        
        if not drafts:
            pytest.skip("No drafts available for dry_run test")
        
        draft = drafts[0]
        payload = {
            "reason_code": draft.get("reason_code"),
            "entity_id": draft.get("entity_id"),
            "mode": "dry_run",
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-apply",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("mode") == "dry_run", "Expected mode=dry_run"
        assert "workflow_policy" in data, "Missing workflow_policy in dry_run response"

    def test_apply_submit_returns_workflow_policy(self, auth_headers):
        """POST apply with mode=submit returns workflow_policy"""
        drafts_response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts",
            headers=auth_headers,
        )
        drafts = drafts_response.json().get("drafts", [])
        
        if not drafts:
            pytest.skip("No drafts available for submit test")
        
        draft = drafts[0]
        payload = {
            "reason_code": draft.get("reason_code"),
            "entity_id": draft.get("entity_id"),
            "mode": "submit",
            "comment": "test_submit_from_pytest",
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-apply",
            headers=auth_headers,
            json=payload,
        )
        # May return 200 or 403 depending on role
        if response.status_code == 200:
            data = response.json()
            assert data.get("mode") == "submit", "Expected mode=submit"
            assert "workflow_policy" in data, "Missing workflow_policy in submit response"
        elif response.status_code == 403:
            # Role not allowed - this is expected behavior
            pass
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}: {response.text}")


class TestP2409Approvals:
    """P2-409: Approvals endpoint"""

    def test_approvals_endpoint_exists(self, auth_headers):
        """GET /api/venues/admin/conflict-auto-remediation-approvals returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-approvals",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_approvals_returns_requests_list(self, auth_headers):
        """Approvals endpoint returns requests list and count"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-approvals",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "requests" in data, "Missing requests field"
        assert "count" in data, "Missing count field"
        assert isinstance(data["requests"], list), "requests should be a list"
        assert isinstance(data["count"], int), "count should be int"

    def test_approvals_filter_by_status(self, auth_headers):
        """Approvals endpoint supports status_filter parameter"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-approvals",
            headers=auth_headers,
            params={"status_filter": "pending"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # All returned requests should have status=pending
        for req in data.get("requests", []):
            assert req.get("status") == "pending", f"Expected status=pending, got {req.get('status')}"


# ============================================================================
# P2-410: Validation Center - check_level_trends, top_reason_codes, drift root_cause_hints
# ============================================================================

class TestP2410ValidationCenter:
    """P2-410: Validation center check-level trends and drift root-cause hints"""

    def test_validation_center_returns_check_level_trends(self, auth_headers):
        """GET /api/venues/admin/validation-center returns check_level_trends"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/validation-center",
            headers=auth_headers,
            params={"window_hours": 24, "limit": 200},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "check_level_trends" in data, "Missing check_level_trends field"
        assert isinstance(data["check_level_trends"], list), "check_level_trends should be a list"

    def test_check_level_trends_structure(self, auth_headers):
        """check_level_trends items have required fields for stacked bar chart"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/validation-center",
            headers=auth_headers,
            params={"window_hours": 24, "limit": 200},
        )
        assert response.status_code == 200
        data = response.json()
        
        trends = data.get("check_level_trends", [])
        if trends:
            trend = trends[0]
            required_fields = ["check_name", "pass_count", "warn_count", "block_count", "total", "pass_ratio", "warn_ratio", "block_ratio"]
            for field in required_fields:
                assert field in trend, f"Missing {field} in check_level_trends item"

    def test_validation_center_returns_top_reason_codes(self, auth_headers):
        """GET /api/venues/admin/validation-center returns top_reason_codes"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/validation-center",
            headers=auth_headers,
            params={"window_hours": 24, "limit": 200},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "top_reason_codes" in data, "Missing top_reason_codes field"
        assert isinstance(data["top_reason_codes"], list), "top_reason_codes should be a list"

    def test_drift_alerts_contain_root_cause_hints(self, auth_headers):
        """drift_alerts items contain root_cause_hints field"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/validation-center",
            headers=auth_headers,
            params={"window_hours": 24, "limit": 200},
        )
        assert response.status_code == 200
        data = response.json()
        
        drift_alerts = data.get("drift_alerts", [])
        # If there are drift alerts, they should have root_cause_hints
        for alert in drift_alerts:
            assert "root_cause_hints" in alert, "Missing root_cause_hints in drift_alert"
            assert isinstance(alert["root_cause_hints"], list), "root_cause_hints should be a list"


class TestP2410ValidationRerun:
    """P2-410: Validation rerun produces timeline_event"""

    def test_validation_rerun_endpoint_exists(self, auth_headers):
        """POST /api/venues/admin/validation-center/rerun returns 200"""
        payload = {
            "user_id": None,
            "strategy_id": None,
            "market_type": "spot",
            "environment": "testnet",
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/validation-center/rerun",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_validation_rerun_returns_timeline_event(self, auth_headers):
        """Validation rerun returns timeline_event in response"""
        payload = {
            "user_id": None,
            "strategy_id": None,
            "market_type": "spot",
            "environment": "testnet",
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/validation-center/rerun",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "timeline_event" in data, "Missing timeline_event in rerun response"
        timeline_event = data["timeline_event"]
        assert "id" in timeline_event, "Missing id in timeline_event"
        assert "created_at" in timeline_event, "Missing created_at in timeline_event"


# ============================================================================
# P2-411: Strategy Venue Heatmap - confidence_score, anomaly_band, 24h vs 30d comparison
# ============================================================================

class TestP2411HeatmapConfidenceAndAnomaly:
    """P2-411: Heatmap confidence_score and anomaly_band"""

    def test_heatmap_returns_top_anomalies(self, auth_headers):
        """GET /api/venues/admin/strategy-venue-heatmap returns top_anomalies"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap",
            headers=auth_headers,
            params={"window_hours": 24, "compare_window_hours": 720},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "top_anomalies" in data, "Missing top_anomalies field"
        assert isinstance(data["top_anomalies"], list), "top_anomalies should be a list"

    def test_top_anomalies_structure(self, auth_headers):
        """top_anomalies items have confidence_score and anomaly_band"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap",
            headers=auth_headers,
            params={"window_hours": 24, "compare_window_hours": 720},
        )
        assert response.status_code == 200
        data = response.json()
        
        anomalies = data.get("top_anomalies", [])
        if anomalies:
            anomaly = anomalies[0]
            assert "confidence_score" in anomaly, "Missing confidence_score in top_anomalies item"
            assert "anomaly_band" in anomaly, "Missing anomaly_band in top_anomalies item"
            assert "anomaly_reasons" in anomaly, "Missing anomaly_reasons in top_anomalies item"

    def test_strategies_have_confidence_and_anomaly(self, auth_headers):
        """strategies items have confidence_score and anomaly_band"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap",
            headers=auth_headers,
            params={"window_hours": 24, "compare_window_hours": 720},
        )
        assert response.status_code == 200
        data = response.json()
        
        strategies = data.get("strategies", [])
        if strategies:
            strategy = strategies[0]
            assert "confidence_score" in strategy, "Missing confidence_score in strategy"
            assert "anomaly_band" in strategy, "Missing anomaly_band in strategy"
            assert "anomaly_reasons" in strategy, "Missing anomaly_reasons in strategy"


class TestP2411HeatmapComparison:
    """P2-411: Heatmap 24h vs 30d comparison with confidence_score_delta"""

    def test_heatmap_returns_comparison(self, auth_headers):
        """GET /api/venues/admin/strategy-venue-heatmap returns comparison field"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap",
            headers=auth_headers,
            params={"window_hours": 24, "compare_window_hours": 720},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "comparison" in data, "Missing comparison field"
        comparison = data["comparison"]
        assert "primary_window_hours" in comparison, "Missing primary_window_hours"
        assert "compare_window_hours" in comparison, "Missing compare_window_hours"
        assert "strategy_deltas" in comparison, "Missing strategy_deltas"

    def test_comparison_window_hours_match(self, auth_headers):
        """comparison window hours match request parameters"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap",
            headers=auth_headers,
            params={"window_hours": 24, "compare_window_hours": 720},
        )
        assert response.status_code == 200
        data = response.json()
        
        comparison = data.get("comparison", {})
        assert comparison.get("primary_window_hours") == 24, "primary_window_hours should be 24"
        assert comparison.get("compare_window_hours") == 720, "compare_window_hours should be 720"

    def test_strategy_deltas_have_confidence_score_delta(self, auth_headers):
        """strategy_deltas items have confidence_score_delta"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap",
            headers=auth_headers,
            params={"window_hours": 24, "compare_window_hours": 720},
        )
        assert response.status_code == 200
        data = response.json()
        
        deltas = data.get("comparison", {}).get("strategy_deltas", [])
        if deltas:
            delta = deltas[0]
            required_fields = [
                "key", "primary_window_hours", "compare_window_hours",
                "primary_confidence_score", "compare_confidence_score", "confidence_score_delta",
                "allocation_drift_delta", "route_churn_delta"
            ]
            for field in required_fields:
                assert field in delta, f"Missing {field} in strategy_deltas item"

    def test_heatmap_primary_and_compare_data(self, auth_headers):
        """Heatmap returns both primary (window_hours) and compare_window data"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap",
            headers=auth_headers,
            params={"window_hours": 24, "compare_window_hours": 720},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Primary data (24h) - at root level
        assert "window_hours" in data, "Missing window_hours field"
        assert data.get("window_hours") == 24, "window_hours should be 24"
        assert "strategies" in data, "Missing strategies field"
        
        # Compare data (30d = 720h)
        assert "compare_window" in data, "Missing compare_window field"
        compare_window = data["compare_window"]
        assert "window_hours" in compare_window, "Missing window_hours in compare_window"
        assert compare_window.get("window_hours") == 720, "compare_window window_hours should be 720"


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for P2-409, P2-410, P2-411"""

    def test_all_endpoints_accessible(self, auth_headers):
        """All P2-409/410/411 endpoints are accessible"""
        endpoints = [
            ("GET", "/api/venues/admin/conflict-auto-remediation-workflow-policy"),
            ("GET", "/api/venues/admin/conflict-auto-remediation-drafts"),
            ("GET", "/api/venues/admin/conflict-auto-remediation-approvals"),
            ("GET", "/api/venues/admin/validation-center"),
            ("GET", "/api/venues/admin/strategy-venue-heatmap"),
        ]
        
        for method, endpoint in endpoints:
            if method == "GET":
                response = requests.get(f"{BASE_URL}{endpoint}", headers=auth_headers)
            assert response.status_code == 200, f"{method} {endpoint} failed: {response.status_code}"
