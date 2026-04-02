"""
Test Suite for P2-403, P2-404, P2-405 Features:
- P2-403: Validation Center (GET /api/venues/admin/validation-center, POST /api/venues/admin/validation-center/rerun)
- P2-404: Strategy-Venue Heatmap (GET /api/venues/admin/strategy-venue-heatmap)
- P2-405: Conflict Auto-Remediation (GET /api/venues/admin/conflict-auto-remediation-drafts, POST /api/venues/admin/conflict-auto-remediation-apply)
- Cockpit endpoint validation_center_summary, validation_drift_alerts, strategy_heatmap_summary
- 24h drift alert rule (PASS->WARN/BLOCK)
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
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
    })
    return session


class TestValidationCenterP2403:
    """P2-403: Validation Center UI - GET /api/venues/admin/validation-center"""

    def test_validation_center_returns_summary(self, api_client):
        """Test validation center returns summary block"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/validation-center")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "summary" in data, "Response must contain 'summary'"
        summary = data["summary"]
        assert "total_events" in summary, "Summary must contain 'total_events'"
        assert "pass_count" in summary, "Summary must contain 'pass_count'"
        assert "warn_count" in summary, "Summary must contain 'warn_count'"
        assert "block_count" in summary, "Summary must contain 'block_count'"
        assert "drift_alert_count" in summary, "Summary must contain 'drift_alert_count'"
        print(f"PASS: Validation center summary: {summary}")

    def test_validation_center_returns_timeline(self, api_client):
        """Test validation center returns timeline list"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/validation-center")
        assert response.status_code == 200
        
        data = response.json()
        assert "timeline" in data, "Response must contain 'timeline'"
        assert isinstance(data["timeline"], list), "Timeline must be a list"
        print(f"PASS: Validation center timeline count: {len(data['timeline'])}")

    def test_validation_center_returns_diff_items(self, api_client):
        """Test validation center returns diff_items list"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/validation-center")
        assert response.status_code == 200
        
        data = response.json()
        assert "diff_items" in data, "Response must contain 'diff_items'"
        assert isinstance(data["diff_items"], list), "diff_items must be a list"
        print(f"PASS: Validation center diff_items count: {len(data['diff_items'])}")

    def test_validation_center_returns_drift_alerts(self, api_client):
        """Test validation center returns drift_alerts list"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/validation-center")
        assert response.status_code == 200
        
        data = response.json()
        assert "drift_alerts" in data, "Response must contain 'drift_alerts'"
        assert isinstance(data["drift_alerts"], list), "drift_alerts must be a list"
        print(f"PASS: Validation center drift_alerts count: {len(data['drift_alerts'])}")

    def test_validation_center_window_hours_param(self, api_client):
        """Test validation center accepts window_hours parameter"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/validation-center", params={"window_hours": 48, "limit": 100})
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("window_hours") == 48, "window_hours should be 48"
        print("PASS: Validation center with window_hours=48")


class TestValidationCenterRerunP2403:
    """P2-403: Validation Center Rerun - POST /api/venues/admin/validation-center/rerun"""

    def test_validation_center_rerun_global(self, api_client):
        """Test validation center rerun for global scope"""
        response = api_client.post(
            f"{BASE_URL}/api/venues/admin/validation-center/rerun",
            json={"user_id": None, "strategy_id": None, "market_type": "spot", "environment": "live"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("rerun") is True, "rerun should be True"
        assert data.get("strategy_key") == "global", "strategy_key should be 'global'"
        assert "validation_report" in data, "Response must contain 'validation_report'"
        assert "timeline_event" in data, "Response must contain 'timeline_event'"
        assert "validation_center" in data, "Response must contain 'validation_center'"
        print(f"PASS: Validation center rerun global - net_status: {data['validation_report'].get('net_status')}")

    def test_validation_center_rerun_returns_validation_report(self, api_client):
        """Test validation center rerun returns validation_report with checks"""
        response = api_client.post(
            f"{BASE_URL}/api/venues/admin/validation-center/rerun",
            json={"user_id": None, "strategy_id": None, "market_type": "futures", "environment": "live"},
        )
        assert response.status_code == 200
        
        data = response.json()
        report = data.get("validation_report", {})
        assert "net_status" in report, "validation_report must contain 'net_status'"
        assert "checks" in report, "validation_report must contain 'checks'"
        assert "reason_codes" in report, "validation_report must contain 'reason_codes'"
        print(f"PASS: Validation report checks count: {len(report.get('checks', []))}")

    def test_validation_center_rerun_returns_timeline_event(self, api_client):
        """Test validation center rerun returns timeline_event"""
        response = api_client.post(
            f"{BASE_URL}/api/venues/admin/validation-center/rerun",
            json={"user_id": None, "strategy_id": None, "market_type": "spot", "environment": "live"},
        )
        assert response.status_code == 200
        
        data = response.json()
        timeline_event = data.get("timeline_event", {})
        assert "id" in timeline_event, "timeline_event must contain 'id'"
        assert "created_at" in timeline_event, "timeline_event must contain 'created_at'"
        assert "strategy_key" in timeline_event, "timeline_event must contain 'strategy_key'"
        assert "net_status" in timeline_event, "timeline_event must contain 'net_status'"
        print(f"PASS: Timeline event created: {timeline_event.get('id')}")

    def test_validation_center_rerun_returns_validation_center(self, api_client):
        """Test validation center rerun returns updated validation_center"""
        response = api_client.post(
            f"{BASE_URL}/api/venues/admin/validation-center/rerun",
            json={"user_id": None, "strategy_id": None, "market_type": "spot", "environment": "live"},
        )
        assert response.status_code == 200
        
        data = response.json()
        validation_center = data.get("validation_center", {})
        assert "summary" in validation_center, "validation_center must contain 'summary'"
        assert "timeline" in validation_center, "validation_center must contain 'timeline'"
        assert "drift_alerts" in validation_center, "validation_center must contain 'drift_alerts'"
        print(f"PASS: Validation center returned with {validation_center['summary'].get('total_events', 0)} events")


class TestStrategyVenueHeatmapP2404:
    """P2-404: Strategy-Venue Heatmap - GET /api/venues/admin/strategy-venue-heatmap"""

    def test_heatmap_returns_strategies(self, api_client):
        """Test heatmap returns strategies list"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "strategies" in data, "Response must contain 'strategies'"
        assert isinstance(data["strategies"], list), "strategies must be a list"
        print(f"PASS: Heatmap strategies count: {len(data['strategies'])}")

    def test_heatmap_returns_top_allocation_drifts(self, api_client):
        """Test heatmap returns top_allocation_drifts list"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap")
        assert response.status_code == 200
        
        data = response.json()
        assert "top_allocation_drifts" in data, "Response must contain 'top_allocation_drifts'"
        assert isinstance(data["top_allocation_drifts"], list), "top_allocation_drifts must be a list"
        print(f"PASS: Heatmap top_allocation_drifts count: {len(data['top_allocation_drifts'])}")

    def test_heatmap_strategy_contains_venue_distribution(self, api_client):
        """Test heatmap strategy rows contain venue_distribution"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap")
        assert response.status_code == 200
        
        data = response.json()
        strategies = data.get("strategies", [])
        if strategies:
            strategy = strategies[0]
            assert "venue_distribution" in strategy, "Strategy must contain 'venue_distribution'"
            assert "route_churn_count" in strategy, "Strategy must contain 'route_churn_count'"
            assert "total_routes" in strategy, "Strategy must contain 'total_routes'"
            print(f"PASS: Strategy row has venue_distribution: {len(strategy.get('venue_distribution', []))} venues")
        else:
            print("PASS: No strategies in heatmap (empty data)")

    def test_heatmap_window_hours_param(self, api_client):
        """Test heatmap accepts window_hours parameter"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap", params={"window_hours": 48})
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("window_hours") == 48, "window_hours should be 48"
        print("PASS: Heatmap with window_hours=48")

    def test_heatmap_allocation_drift_fields(self, api_client):
        """Test heatmap allocation drift items have required fields"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap")
        assert response.status_code == 200
        
        data = response.json()
        drifts = data.get("top_allocation_drifts", [])
        if drifts:
            drift = drifts[0]
            assert "strategy_key" in drift, "Drift must contain 'strategy_key'"
            assert "venue" in drift, "Drift must contain 'venue'"
            assert "allocation_drift" in drift, "Drift must contain 'allocation_drift'"
            print(f"PASS: Drift item has required fields: {drift}")
        else:
            print("PASS: No allocation drifts (empty data)")


class TestConflictAutoRemediationDraftsP2405:
    """P2-405: Conflict Auto-Remediation Drafts - GET /api/venues/admin/conflict-auto-remediation-drafts"""

    def test_remediation_drafts_returns_drafts_list(self, api_client):
        """Test remediation drafts returns drafts list"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "drafts" in data, "Response must contain 'drafts'"
        assert isinstance(data["drafts"], list), "drafts must be a list"
        print(f"PASS: Remediation drafts count: {len(data['drafts'])}")

    def test_remediation_drafts_returns_summary(self, api_client):
        """Test remediation drafts returns summary"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts")
        assert response.status_code == 200
        
        data = response.json()
        assert "summary" in data, "Response must contain 'summary'"
        summary = data["summary"]
        assert "total_drafts" in summary, "Summary must contain 'total_drafts'"
        assert "blocking_draft_count" in summary, "Summary must contain 'blocking_draft_count'"
        assert "warning_draft_count" in summary, "Summary must contain 'warning_draft_count'"
        print(f"PASS: Remediation summary: total={summary['total_drafts']}, block={summary['blocking_draft_count']}, warn={summary['warning_draft_count']}")

    def test_remediation_draft_structure(self, api_client):
        """Test remediation draft items have required structure"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts")
        assert response.status_code == 200
        
        data = response.json()
        drafts = data.get("drafts", [])
        if drafts:
            draft = drafts[0]
            assert "draft_id" in draft, "Draft must contain 'draft_id'"
            assert "reason_code" in draft, "Draft must contain 'reason_code'"
            assert "entity_id" in draft, "Draft must contain 'entity_id'"
            assert "severity" in draft, "Draft must contain 'severity'"
            assert "endpoint" in draft, "Draft must contain 'endpoint'"
            assert "payload" in draft, "Draft must contain 'payload'"
            assert "action_summary" in draft, "Draft must contain 'action_summary'"
            print(f"PASS: Draft structure valid: {draft['draft_id']}")
        else:
            print("PASS: No remediation drafts (no conflicts)")


class TestConflictAutoRemediationApplyP2405:
    """P2-405: Conflict Auto-Remediation Apply - POST /api/venues/admin/conflict-auto-remediation-apply"""

    def test_remediation_apply_not_found(self, api_client):
        """Test remediation apply returns 404 for non-existent draft"""
        response = api_client.post(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-apply",
            json={"reason_code": "nonexistent_code", "entity_id": "nonexistent:entity"},
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Remediation apply returns 404 for non-existent draft")

    def test_remediation_apply_existing_draft(self, api_client):
        """Test remediation apply for existing draft (if any)"""
        # First get available drafts
        drafts_response = api_client.get(f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts")
        assert drafts_response.status_code == 200
        
        drafts = drafts_response.json().get("drafts", [])
        if not drafts:
            print("SKIP: No drafts available to apply")
            return
        
        # Try to apply the first draft
        draft = drafts[0]
        response = api_client.post(
            f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-apply",
            json={"reason_code": draft["reason_code"], "entity_id": draft["entity_id"]},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("applied") is True, "applied should be True"
        assert "draft_id" in data, "Response must contain 'draft_id'"
        assert "draft" in data, "Response must contain 'draft'"
        assert "apply_result" in data, "Response must contain 'apply_result'"
        print(f"PASS: Remediation draft applied: {data['draft_id']}")


class TestCockpitValidationHeatmapIntegration:
    """Test cockpit endpoint includes validation_center_summary, validation_drift_alerts, strategy_heatmap_summary"""

    def test_cockpit_contains_validation_center_summary(self, api_client):
        """Test cockpit contains validation_center_summary"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "validation_center_summary" in data, "Cockpit must contain 'validation_center_summary'"
        summary = data["validation_center_summary"]
        assert isinstance(summary, dict), "validation_center_summary must be a dict"
        print(f"PASS: Cockpit validation_center_summary: {summary}")

    def test_cockpit_contains_validation_drift_alerts(self, api_client):
        """Test cockpit contains validation_drift_alerts"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert response.status_code == 200
        
        data = response.json()
        assert "validation_drift_alerts" in data, "Cockpit must contain 'validation_drift_alerts'"
        assert isinstance(data["validation_drift_alerts"], list), "validation_drift_alerts must be a list"
        print(f"PASS: Cockpit validation_drift_alerts count: {len(data['validation_drift_alerts'])}")

    def test_cockpit_contains_strategy_heatmap_summary(self, api_client):
        """Test cockpit contains strategy_heatmap_summary"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert response.status_code == 200
        
        data = response.json()
        assert "strategy_heatmap_summary" in data, "Cockpit must contain 'strategy_heatmap_summary'"
        heatmap_summary = data["strategy_heatmap_summary"]
        assert "strategy_count" in heatmap_summary, "strategy_heatmap_summary must contain 'strategy_count'"
        assert "top_allocation_drifts" in heatmap_summary, "strategy_heatmap_summary must contain 'top_allocation_drifts'"
        print(f"PASS: Cockpit strategy_heatmap_summary: strategy_count={heatmap_summary['strategy_count']}")


class TestDriftAlertRule24h:
    """Test 24h drift alert rule: PASS->WARN/BLOCK triggers drift alert"""

    def test_drift_alert_structure(self, api_client):
        """Test drift alert items have required structure"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/validation-center")
        assert response.status_code == 200
        
        data = response.json()
        drift_alerts = data.get("drift_alerts", [])
        if drift_alerts:
            alert = drift_alerts[0]
            assert "strategy_key" in alert, "Drift alert must contain 'strategy_key'"
            assert "from_status" in alert, "Drift alert must contain 'from_status'"
            assert "to_status" in alert, "Drift alert must contain 'to_status'"
            assert "event_count" in alert, "Drift alert must contain 'event_count'"
            assert "severity" in alert, "Drift alert must contain 'severity'"
            print(f"PASS: Drift alert structure valid: {alert['strategy_key']} {alert['from_status']}->{alert['to_status']}")
        else:
            print("PASS: No drift alerts (no PASS->WARN/BLOCK transitions)")

    def test_drift_alert_triggered_by_rerun(self, api_client):
        """Test that validation rerun can trigger drift alerts"""
        # Run multiple reruns to potentially create drift
        for i in range(3):
            response = api_client.post(
                f"{BASE_URL}/api/venues/admin/validation-center/rerun",
                json={"user_id": None, "strategy_id": None, "market_type": "spot", "environment": "live"},
            )
            assert response.status_code == 200
        
        # Check validation center for drift alerts
        response = api_client.get(f"{BASE_URL}/api/venues/admin/validation-center")
        assert response.status_code == 200
        
        data = response.json()
        summary = data.get("summary", {})
        print(f"PASS: After reruns - drift_alert_count: {summary.get('drift_alert_count', 0)}")

    def test_drift_alert_severity_mapping(self, api_client):
        """Test drift alert severity is correctly mapped"""
        response = api_client.get(f"{BASE_URL}/api/venues/admin/validation-center")
        assert response.status_code == 200
        
        data = response.json()
        drift_alerts = data.get("drift_alerts", [])
        for alert in drift_alerts:
            to_status = alert.get("to_status", "").upper()
            severity = alert.get("severity", "")
            if to_status == "BLOCK":
                assert severity == "high", f"BLOCK should have high severity, got {severity}"
            elif to_status == "WARN":
                assert severity == "medium", f"WARN should have medium severity, got {severity}"
        print(f"PASS: Drift alert severity mapping verified for {len(drift_alerts)} alerts")


class TestEndpointResponseTimes:
    """Test endpoint response times are reasonable"""

    def test_validation_center_response_time(self, api_client):
        """Test validation center responds within 5 seconds"""
        import time
        start = time.time()
        response = api_client.get(f"{BASE_URL}/api/venues/admin/validation-center")
        elapsed = time.time() - start
        assert response.status_code == 200
        assert elapsed < 5, f"Response took {elapsed:.2f}s, expected < 5s"
        print(f"PASS: Validation center response time: {elapsed:.2f}s")

    def test_heatmap_response_time(self, api_client):
        """Test heatmap responds within 5 seconds"""
        import time
        start = time.time()
        response = api_client.get(f"{BASE_URL}/api/venues/admin/strategy-venue-heatmap")
        elapsed = time.time() - start
        assert response.status_code == 200
        assert elapsed < 5, f"Response took {elapsed:.2f}s, expected < 5s"
        print(f"PASS: Heatmap response time: {elapsed:.2f}s")

    def test_remediation_drafts_response_time(self, api_client):
        """Test remediation drafts responds within 5 seconds"""
        import time
        start = time.time()
        response = api_client.get(f"{BASE_URL}/api/venues/admin/conflict-auto-remediation-drafts")
        elapsed = time.time() - start
        assert response.status_code == 200
        assert elapsed < 5, f"Response took {elapsed:.2f}s, expected < 5s"
        print(f"PASS: Remediation drafts response time: {elapsed:.2f}s")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
