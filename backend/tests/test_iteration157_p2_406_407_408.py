"""
Test suite for P2-406, P2-407, P2-408 features:
- P2-406: Validation Center (check_level_trends, top_reason_codes, drift_alerts with root_cause_hints)
- P2-407: Strategy-Venue Heatmap (24h vs 30d comparison, strategy_deltas)
- P2-408: Conflict Auto-Remediation (dry_run, submit, approve_apply modes, approval_requests)
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
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ============================================================================
# P2-406: Validation Center Tests
# ============================================================================

class TestValidationCenterGet:
    """GET /api/venues/admin/validation-center tests"""

    def test_validation_center_returns_check_level_trends(self, auth_headers):
        """Test that validation center returns check_level_trends field"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/validation-center",
            headers=auth_headers,
            params={"window_hours": 24, "limit": 200},
        )
        assert response.status_code == 200
        data = response.json()
        assert "check_level_trends" in data
        assert isinstance(data["check_level_trends"], list)
        print(f"check_level_trends count: {len(data['check_level_trends'])}")

    def test_validation_center_returns_top_reason_codes(self, auth_headers):
        """Test that validation center returns top_reason_codes field"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/validation-center",
            headers=auth_headers,
            params={"window_hours": 24, "limit": 200},
        )
        assert response.status_code == 200
        data = response.json()
        assert "top_reason_codes" in data
        assert isinstance(data["top_reason_codes"], list)
        print(f"top_reason_codes count: {len(data['top_reason_codes'])}")

    def test_validation_center_returns_drift_alerts(self, auth_headers):
        """Test that validation center returns drift_alerts field"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/validation-center",
            headers=auth_headers,
            params={"window_hours": 24, "limit": 200},
        )
        assert response.status_code == 200
        data = response.json()
        assert "drift_alerts" in data
        assert isinstance(data["drift_alerts"], list)
        print(f"drift_alerts count: {len(data['drift_alerts'])}")

    def test_drift_alerts_contain_root_cause_hints(self, auth_headers):
        """Test that drift_alerts contain root_cause_hints field"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/validation-center",
            headers=auth_headers,
            params={"window_hours": 24, "limit": 200},
        )
        assert response.status_code == 200
        data = response.json()
        drift_alerts = data.get("drift_alerts", [])
        # If there are drift alerts, verify they have root_cause_hints
        for alert in drift_alerts[:5]:
            assert "root_cause_hints" in alert, f"Missing root_cause_hints in drift alert: {alert}"
            assert isinstance(alert["root_cause_hints"], list)
            print(f"Drift alert {alert.get('strategy_key')}: hints={alert['root_cause_hints']}")

    def test_check_level_trends_structure(self, auth_headers):
        """Test check_level_trends item structure"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/validation-center",
            headers=auth_headers,
            params={"window_hours": 24, "limit": 200},
        )
        assert response.status_code == 200
        data = response.json()
        trends = data.get("check_level_trends", [])
        for trend in trends[:5]:
            assert "check_name" in trend
            assert "pass_count" in trend
            assert "warn_count" in trend
            assert "block_count" in trend
            print(f"Check trend: {trend['check_name']} - pass/warn/block={trend['pass_count']}/{trend['warn_count']}/{trend['block_count']}")


class TestValidationCenterRerun:
    """POST /api/venues/admin/validation-center/rerun tests"""

    def test_validation_center_rerun_produces_timeline_event(self, auth_headers):
        """Test that rerun produces a timeline_event"""
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/validation-center/rerun",
            headers=auth_headers,
            json={"market_type": "spot", "environment": "live"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "timeline_event" in data
        assert data["timeline_event"] is not None
        assert "id" in data["timeline_event"]
        assert "created_at" in data["timeline_event"]
        print(f"Timeline event created: {data['timeline_event']['id']}")

    def test_validation_center_rerun_returns_validation_report(self, auth_headers):
        """Test that rerun returns validation_report"""
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/validation-center/rerun",
            headers=auth_headers,
            json={"market_type": "spot", "environment": "live"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "validation_report" in data
        report = data["validation_report"]
        assert "net_status" in report
        assert "checks" in report
        print(f"Validation report net_status: {report['net_status']}")

    def test_validation_center_rerun_returns_validation_center(self, auth_headers):
        """Test that rerun returns updated validation_center"""
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/validation-center/rerun",
            headers=auth_headers,
            json={"market_type": "spot", "environment": "live"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "validation_center" in data
        vc = data["validation_center"]
        assert "check_level_trends" in vc
        assert "top_reason_codes" in vc
        assert "drift_alerts" in vc
        print(f"Validation center updated with {len(vc.get('timeline', []))} timeline items")


class TestValidationDriftAlertRule:
    """Test 24h PASS->WARN/BLOCK drift alert rule"""

    def test_drift_alert_structure(self, auth_headers):
        """Test drift alert structure contains required fields"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/validation-center",
            headers=auth_headers,
            params={"window_hours": 24, "limit": 200},
        )
        assert response.status_code == 200
        data = response.json()
        drift_alerts = data.get("drift_alerts", [])
        for alert in drift_alerts[:5]:
            assert "strategy_key" in alert
            assert "from_status" in alert
            assert "to_status" in alert
            assert "root_cause_hints" in alert
            assert "latest_reason_codes" in alert
            assert "severity" in alert
            print(f"Drift alert: {alert['strategy_key']} {alert['from_status']}->{alert['to_status']}")


# ============================================================================
# P2-407: Strategy-Venue Heatmap Tests (24h vs 30d comparison)
# ============================================================================

class TestStrategyVenueHeatmap:
    """GET /api/venues/admin/strategy-venue-heatmap tests"""

    def test_heatmap_returns_24h_window(self, auth_headers):
        """Test heatmap returns data for 24h window"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap",
            headers=auth_headers,
            params={"window_hours": 24, "compare_window_hours": 720},
        )
        assert response.status_code == 200
        data = response.json()
        assert "window_hours" in data
        assert data["window_hours"] == 24
        print(f"Heatmap window_hours: {data['window_hours']}")

    def test_heatmap_returns_compare_window(self, auth_headers):
        """Test heatmap returns compare_window (30d = 720h)"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap",
            headers=auth_headers,
            params={"window_hours": 24, "compare_window_hours": 720},
        )
        assert response.status_code == 200
        data = response.json()
        assert "compare_window" in data
        compare = data["compare_window"]
        assert "window_hours" in compare
        assert compare["window_hours"] == 720
        print(f"Compare window_hours: {compare['window_hours']}")

    def test_heatmap_returns_comparison_with_strategy_deltas(self, auth_headers):
        """Test heatmap returns comparison.strategy_deltas"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap",
            headers=auth_headers,
            params={"window_hours": 24, "compare_window_hours": 720},
        )
        assert response.status_code == 200
        data = response.json()
        assert "comparison" in data
        comparison = data["comparison"]
        assert "strategy_deltas" in comparison
        assert isinstance(comparison["strategy_deltas"], list)
        print(f"strategy_deltas count: {len(comparison['strategy_deltas'])}")

    def test_strategy_deltas_structure(self, auth_headers):
        """Test strategy_deltas item structure"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap",
            headers=auth_headers,
            params={"window_hours": 24, "compare_window_hours": 720},
        )
        assert response.status_code == 200
        data = response.json()
        deltas = data.get("comparison", {}).get("strategy_deltas", [])
        for delta in deltas[:5]:
            assert "key" in delta
            assert "primary_window_hours" in delta
            assert "compare_window_hours" in delta
            assert "primary_route_churn" in delta
            assert "compare_route_churn" in delta
            assert "route_churn_delta" in delta
            assert "primary_max_allocation_drift" in delta
            assert "compare_max_allocation_drift" in delta
            assert "allocation_drift_delta" in delta
            print(f"Delta: {delta['key']} drift_delta={delta['allocation_drift_delta']} churn_delta={delta['route_churn_delta']}")

    def test_comparison_window_hours_match(self, auth_headers):
        """Test comparison window hours match request params"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap",
            headers=auth_headers,
            params={"window_hours": 24, "compare_window_hours": 720},
        )
        assert response.status_code == 200
        data = response.json()
        comparison = data.get("comparison", {})
        assert comparison.get("primary_window_hours") == 24
        assert comparison.get("compare_window_hours") == 720
        print(f"Comparison windows: primary={comparison.get('primary_window_hours')}h, compare={comparison.get('compare_window_hours')}h")


# ============================================================================
# P2-408: Conflict Auto-Remediation Tests
# ============================================================================

class TestConflictAutoRemediationDrafts:
    """GET /api/venues/admin/conflict-auto-remediation-drafts tests"""

    def test_remediation_drafts_returns_approval_requests(self, auth_headers):
        """Test that drafts endpoint returns approval_requests"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "approval_requests" in data
        assert isinstance(data["approval_requests"], list)
        print(f"approval_requests count: {len(data['approval_requests'])}")

    def test_remediation_drafts_returns_pending_approval_count(self, auth_headers):
        """Test that drafts endpoint returns pending_approval_count in summary"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        summary = data["summary"]
        assert "pending_approval_count" in summary
        assert isinstance(summary["pending_approval_count"], int)
        print(f"pending_approval_count: {summary['pending_approval_count']}")

    def test_remediation_drafts_structure(self, auth_headers):
        """Test remediation draft structure"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        drafts = data.get("drafts", [])
        for draft in drafts[:5]:
            assert "draft_id" in draft
            assert "reason_code" in draft
            assert "entity_id" in draft
            assert "severity" in draft
            assert "endpoint" in draft
            assert "payload" in draft
            assert "action_summary" in draft
            print(f"Draft: {draft['draft_id']} severity={draft['severity']}")


class TestConflictAutoRemediationApprovals:
    """GET /api/venues/admin/conflict-auto-remediation-approvals tests"""

    def test_approvals_endpoint_exists(self, auth_headers):
        """Test that approvals endpoint exists and returns data"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-approvals",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "requests" in data
        assert "count" in data
        print(f"Approvals count: {data['count']}")

    def test_approvals_filter_by_status(self, auth_headers):
        """Test approvals can be filtered by status"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-approvals",
            headers=auth_headers,
            params={"status_filter": "pending"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "requests" in data
        # All returned requests should be pending
        for req in data["requests"]:
            assert req.get("status") == "pending"
        print(f"Pending approvals: {data['count']}")


class TestConflictAutoRemediationApply:
    """POST /api/venues/admin/conflict-auto-remediation-apply tests"""

    def test_remediation_apply_dry_run_mode(self, auth_headers):
        """Test dry_run mode returns simulated result"""
        # First get drafts to find a valid one
        drafts_response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts",
            headers=auth_headers,
        )
        assert drafts_response.status_code == 200
        drafts = drafts_response.json().get("drafts", [])
        
        if not drafts:
            pytest.skip("No remediation drafts available for testing")
        
        draft = drafts[0]
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-apply",
            headers=auth_headers,
            json={
                "reason_code": draft["reason_code"],
                "entity_id": draft["entity_id"],
                "mode": "dry_run",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "dry_run"
        assert data["applied"] == False
        assert "simulated_result" in data
        assert "requires_approval" in data
        print(f"Dry run result: draft_id={data['draft_id']}, requires_approval={data['requires_approval']}")

    def test_remediation_apply_submit_mode(self, auth_headers):
        """Test submit mode creates approval request"""
        # First get drafts to find a valid one
        drafts_response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts",
            headers=auth_headers,
        )
        assert drafts_response.status_code == 200
        drafts = drafts_response.json().get("drafts", [])
        
        if not drafts:
            pytest.skip("No remediation drafts available for testing")
        
        draft = drafts[0]
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-apply",
            headers=auth_headers,
            json={
                "reason_code": draft["reason_code"],
                "entity_id": draft["entity_id"],
                "mode": "submit",
                "comment": "test_submit_from_pytest",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "submit"
        assert data["submitted"] == True
        assert data["applied"] == False
        assert "approval_request" in data
        approval_req = data["approval_request"]
        assert approval_req["status"] == "pending"
        print(f"Submit result: approval_request_id={approval_req['id']}")

    def test_remediation_apply_approve_apply_mode(self, auth_headers):
        """Test approve_apply mode with approval_request_id"""
        # First get drafts and submit one
        drafts_response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts",
            headers=auth_headers,
        )
        assert drafts_response.status_code == 200
        drafts = drafts_response.json().get("drafts", [])
        
        if not drafts:
            pytest.skip("No remediation drafts available for testing")
        
        draft = drafts[0]
        
        # Submit first
        submit_response = requests.post(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-apply",
            headers=auth_headers,
            json={
                "reason_code": draft["reason_code"],
                "entity_id": draft["entity_id"],
                "mode": "submit",
                "comment": "test_submit_for_approve",
            },
        )
        assert submit_response.status_code == 200
        approval_request_id = submit_response.json()["approval_request"]["id"]
        
        # Now approve and apply
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-apply",
            headers=auth_headers,
            json={
                "reason_code": draft["reason_code"],
                "entity_id": draft["entity_id"],
                "mode": "approve_apply",
                "approval_request_id": approval_request_id,
                "comment": "test_approve_from_pytest",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "approve_apply"
        assert data["applied"] == True
        assert "apply_result" in data
        assert "approval_request" in data
        assert data["approval_request"]["status"] == "approved_applied"
        print(f"Approve apply result: applied={data['applied']}")

    def test_remediation_apply_not_found(self, auth_headers):
        """Test apply with non-existent draft returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-apply",
            headers=auth_headers,
            json={
                "reason_code": "nonexistent_reason",
                "entity_id": "nonexistent:entity",
                "mode": "dry_run",
            },
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "remediation_draft_not_found"
        print("Not found test passed")

    def test_remediation_apply_invalid_mode(self, auth_headers):
        """Test apply with invalid mode returns 400"""
        # First get drafts to find a valid one
        drafts_response = requests.get(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts",
            headers=auth_headers,
        )
        assert drafts_response.status_code == 200
        drafts = drafts_response.json().get("drafts", [])
        
        if not drafts:
            pytest.skip("No remediation drafts available for testing")
        
        draft = drafts[0]
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-apply",
            headers=auth_headers,
            json={
                "reason_code": draft["reason_code"],
                "entity_id": draft["entity_id"],
                "mode": "invalid_mode",
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "invalid_remediation_mode"
        print("Invalid mode test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
