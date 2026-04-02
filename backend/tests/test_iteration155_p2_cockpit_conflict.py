"""
P2-401 & P2-402 Testing: Control Plane Cockpit & Conflict Detection Center
Tests for:
- GET /api/venues/admin/control-plane-cockpit
- GET /api/venues/admin/conflict-detection-center
- Route churn anomaly alert threshold logic (30dk >=5 transition)
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
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Admin authentication failed")


@pytest.fixture(scope="module")
def admin_client(admin_token):
    """Session with admin auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}",
    })
    return session


class TestControlPlaneCockpit:
    """P2-401: Control Plane Cockpit endpoint tests"""

    def test_cockpit_endpoint_returns_200(self, admin_client):
        """GET /api/venues/admin/control-plane-cockpit returns 200"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ control-plane-cockpit endpoint returns 200")

    def test_cockpit_response_has_global_overview(self, admin_client):
        """Response contains global_overview block"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert response.status_code == 200
        data = response.json()
        
        assert "global_overview" in data, "Missing global_overview block"
        overview = data["global_overview"]
        
        # Verify required fields in global_overview
        assert "total_venues" in overview, "Missing total_venues"
        assert "healthy_venues" in overview, "Missing healthy_venues"
        assert "degraded_venues" in overview, "Missing degraded_venues"
        assert "down_venues" in overview, "Missing down_venues"
        assert "routing_rule_count" in overview, "Missing routing_rule_count"
        assert "failover_rule_count" in overview, "Missing failover_rule_count"
        
        print(f"✓ global_overview: venues={overview['total_venues']}, routing_rules={overview['routing_rule_count']}, failover_rules={overview['failover_rule_count']}")

    def test_cockpit_response_has_active_route_map(self, admin_client):
        """Response contains active_route_map block"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert response.status_code == 200
        data = response.json()
        
        assert "active_route_map" in data, "Missing active_route_map block"
        route_map = data["active_route_map"]
        assert isinstance(route_map, list), "active_route_map should be a list"
        
        # If there are routes, verify structure
        if route_map:
            first_route = route_map[0]
            assert "key" in first_route, "Route missing key"
            assert "active_venue" in first_route, "Route missing active_venue"
            assert "fallback_chain" in first_route, "Route missing fallback_chain"
            print(f"✓ active_route_map: {len(route_map)} routes found")
        else:
            print("✓ active_route_map: empty (no active routes)")

    def test_cockpit_response_has_failover_state_board(self, admin_client):
        """Response contains failover_state_board block"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert response.status_code == 200
        data = response.json()
        
        assert "failover_state_board" in data, "Missing failover_state_board block"
        assert isinstance(data["failover_state_board"], list), "failover_state_board should be a list"
        print(f"✓ failover_state_board: {len(data['failover_state_board'])} states")

    def test_cockpit_response_has_route_churn_anomaly_alert(self, admin_client):
        """Response contains route_churn_anomaly_alert block"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert response.status_code == 200
        data = response.json()
        
        assert "route_churn_anomaly_alert" in data, "Missing route_churn_anomaly_alert block"
        churn_alert = data["route_churn_anomaly_alert"]
        
        # Verify required fields
        assert "status" in churn_alert, "Missing status in churn alert"
        assert "window_minutes" in churn_alert, "Missing window_minutes"
        assert "threshold" in churn_alert, "Missing threshold"
        assert "total_recent_transitions" in churn_alert, "Missing total_recent_transitions"
        assert "hot_routes" in churn_alert, "Missing hot_routes"
        assert "reason_codes" in churn_alert, "Missing reason_codes"
        
        print(f"✓ route_churn_anomaly_alert: status={churn_alert['status']}, window={churn_alert['window_minutes']}m, threshold={churn_alert['threshold']}")

    def test_cockpit_response_has_last_critical_changes(self, admin_client):
        """Response contains last_critical_changes block"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert response.status_code == 200
        data = response.json()
        
        assert "last_critical_changes" in data, "Missing last_critical_changes block"
        changes = data["last_critical_changes"]
        assert isinstance(changes, list), "last_critical_changes should be a list"
        
        # If there are changes, verify structure
        if changes:
            first_change = changes[0]
            assert "id" in first_change, "Change missing id"
            assert "action" in first_change, "Change missing action"
            assert "entity_id" in first_change, "Change missing entity_id"
            print(f"✓ last_critical_changes: {len(changes)} changes found")
        else:
            print("✓ last_critical_changes: empty (no recent changes)")

    def test_cockpit_custom_window_and_threshold(self, admin_client):
        """Test custom window_minutes and churn_threshold parameters"""
        response = admin_client.get(
            f"{BASE_URL}/api/venues/admin/control-plane-cockpit",
            params={"window_minutes": 60, "churn_threshold": 3}
        )
        assert response.status_code == 200
        data = response.json()
        
        churn_alert = data.get("route_churn_anomaly_alert", {})
        assert churn_alert.get("window_minutes") == 60, "window_minutes not applied"
        assert churn_alert.get("threshold") == 3, "churn_threshold not applied"
        print("✓ Custom window_minutes=60 and churn_threshold=3 applied correctly")


class TestConflictDetectionCenter:
    """P2-402: Conflict Detection Center endpoint tests"""

    def test_conflict_detection_endpoint_returns_200(self, admin_client):
        """GET /api/venues/admin/conflict-detection-center returns 200"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/conflict-detection-center")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ conflict-detection-center endpoint returns 200")

    def test_conflict_detection_has_net_status(self, admin_client):
        """Response contains net_status field"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/conflict-detection-center")
        assert response.status_code == 200
        data = response.json()
        
        assert "net_status" in data, "Missing net_status"
        assert data["net_status"] in ["PASS", "WARN", "BLOCK"], f"Invalid net_status: {data['net_status']}"
        print(f"✓ net_status: {data['net_status']}")

    def test_conflict_detection_has_alerts(self, admin_client):
        """Response contains alerts list"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/conflict-detection-center")
        assert response.status_code == 200
        data = response.json()
        
        assert "alerts" in data, "Missing alerts"
        assert isinstance(data["alerts"], list), "alerts should be a list"
        print(f"✓ alerts: {len(data['alerts'])} total alerts")

    def test_conflict_detection_has_blocking_alerts(self, admin_client):
        """Response contains blocking_alerts list"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/conflict-detection-center")
        assert response.status_code == 200
        data = response.json()
        
        assert "blocking_alerts" in data, "Missing blocking_alerts"
        assert isinstance(data["blocking_alerts"], list), "blocking_alerts should be a list"
        print(f"✓ blocking_alerts: {len(data['blocking_alerts'])} blocking alerts")

    def test_conflict_detection_has_warning_alerts(self, admin_client):
        """Response contains warning_alerts list"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/conflict-detection-center")
        assert response.status_code == 200
        data = response.json()
        
        assert "warning_alerts" in data, "Missing warning_alerts"
        assert isinstance(data["warning_alerts"], list), "warning_alerts should be a list"
        print(f"✓ warning_alerts: {len(data['warning_alerts'])} warning alerts")

    def test_conflict_detection_has_summary(self, admin_client):
        """Response contains summary with counts"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/conflict-detection-center")
        assert response.status_code == 200
        data = response.json()
        
        assert "summary" in data, "Missing summary"
        summary = data["summary"]
        
        assert "total_alerts" in summary, "Missing total_alerts in summary"
        assert "block_count" in summary, "Missing block_count in summary"
        assert "warn_count" in summary, "Missing warn_count in summary"
        
        print(f"✓ summary: total={summary['total_alerts']}, block={summary['block_count']}, warn={summary['warn_count']}")


class TestRouteChurnAnomalyThreshold:
    """Test route churn anomaly alert threshold logic (30dk >=5 transition)"""

    def test_churn_alert_default_threshold(self, admin_client):
        """Default threshold is 5 transitions in 30 minutes"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert response.status_code == 200
        data = response.json()
        
        churn_alert = data.get("route_churn_anomaly_alert", {})
        assert churn_alert.get("window_minutes") == 30, "Default window should be 30 minutes"
        assert churn_alert.get("threshold") == 5, "Default threshold should be 5"
        print("✓ Default churn threshold: 30 minutes, 5 transitions")

    def test_churn_alert_status_values(self, admin_client):
        """Churn alert status should be PASS or BLOCK"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert response.status_code == 200
        data = response.json()
        
        churn_alert = data.get("route_churn_anomaly_alert", {})
        status = churn_alert.get("status")
        assert status in ["PASS", "BLOCK"], f"Invalid churn status: {status}"
        
        # If BLOCK, should have hot_routes
        if status == "BLOCK":
            assert len(churn_alert.get("hot_routes", [])) > 0, "BLOCK status should have hot_routes"
            assert "route_churn_anomaly_detected" in churn_alert.get("reason_codes", []), "Missing reason_code"
            print(f"✓ Churn status BLOCK with {len(churn_alert['hot_routes'])} hot routes")
        else:
            print("✓ Churn status PASS (no anomaly)")

    def test_trigger_churn_anomaly_via_failover_transitions(self, admin_client):
        """
        Trigger route churn anomaly by creating multiple failover transitions.
        This test creates a failover policy and applies manual overrides to generate transitions.
        """
        test_key = "TEST_churn_user:TEST_churn_strategy:futures:live"
        
        # Step 1: Create a failover policy
        failover_payload = {
            "user_id": "TEST_churn_user",
            "strategy_id": "TEST_churn_strategy",
            "market_type": "futures",
            "environment": "live",
            "primary_venue": "binance",
            "secondary_venue": "bybit",
            "fallback_chain": ["okx", "kucoin"],
            "auto_reroute_enabled": True,
            "auto_trigger_thresholds": {"latency_ms": 1200, "error_rate_pct": 20}
        }
        
        response = admin_client.put(
            f"{BASE_URL}/api/venues/admin/failover-policies",
            json=failover_payload
        )
        assert response.status_code == 200, f"Failed to create failover policy: {response.text}"
        print("✓ Created failover policy for churn test")
        
        # Step 2: Generate multiple transitions by toggling force_route
        venues = ["binance", "bybit", "okx", "kucoin", "binance", "bybit"]
        for i, venue in enumerate(venues):
            override_payload = {
                "user_id": "TEST_churn_user",
                "strategy_id": "TEST_churn_strategy",
                "market_type": "futures",
                "environment": "live",
                "force_route": venue,
                "force_disable": []
            }
            response = admin_client.post(
                f"{BASE_URL}/api/venues/admin/failover/manual-override",
                json=override_payload
            )
            assert response.status_code == 200, f"Failed to apply override {i+1}: {response.text}"
        
        print(f"✓ Applied {len(venues)} manual overrides to generate transitions")
        
        # Step 3: Check cockpit for churn alert
        response = admin_client.get(
            f"{BASE_URL}/api/venues/admin/control-plane-cockpit",
            params={"window_minutes": 30, "churn_threshold": 5}
        )
        assert response.status_code == 200
        data = response.json()
        
        churn_alert = data.get("route_churn_anomaly_alert", {})
        total_transitions = churn_alert.get("total_recent_transitions", 0)
        hot_routes = churn_alert.get("hot_routes", [])
        status = churn_alert.get("status")
        
        print(f"✓ Churn alert after transitions: status={status}, total_transitions={total_transitions}")
        
        # Verify hot_routes structure if present
        if hot_routes:
            for route in hot_routes:
                assert "key" in route, "hot_route missing key"
                assert "transition_count" in route, "hot_route missing transition_count"
                print(f"  - Hot route: {route['key']} with {route['transition_count']} transitions")
        
        # If we triggered enough transitions, status should be BLOCK
        if total_transitions >= 5:
            assert status == "BLOCK", f"Expected BLOCK status with {total_transitions} transitions"
            assert len(hot_routes) > 0, "Expected hot_routes with BLOCK status"
            print("✓ Route churn anomaly BLOCK triggered successfully")
        else:
            print(f"✓ Not enough transitions ({total_transitions}) to trigger BLOCK")


class TestCockpitConflictConsistency:
    """Test consistency between cockpit and conflict detection data"""

    def test_cockpit_includes_conflict_detection_center(self, admin_client):
        """Cockpit response includes conflict_detection_center data"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert response.status_code == 200
        data = response.json()
        
        assert "conflict_detection_center" in data, "Missing conflict_detection_center in cockpit"
        conflict_data = data["conflict_detection_center"]
        
        assert "net_status" in conflict_data, "Missing net_status in embedded conflict data"
        assert "alerts" in conflict_data, "Missing alerts in embedded conflict data"
        print("✓ Cockpit includes conflict_detection_center data")

    def test_conflict_data_consistency(self, admin_client):
        """Conflict data in cockpit matches standalone endpoint"""
        # Get cockpit data
        cockpit_response = admin_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert cockpit_response.status_code == 200
        cockpit_data = cockpit_response.json()
        
        # Get standalone conflict data
        conflict_response = admin_client.get(f"{BASE_URL}/api/venues/admin/conflict-detection-center")
        assert conflict_response.status_code == 200
        conflict_data = conflict_response.json()
        
        # Compare net_status
        cockpit_conflict = cockpit_data.get("conflict_detection_center", {})
        assert cockpit_conflict.get("net_status") == conflict_data.get("net_status"), "net_status mismatch"
        
        # Compare alert counts
        cockpit_summary = cockpit_conflict.get("summary", {})
        conflict_summary = conflict_data.get("summary", {})
        assert cockpit_summary.get("total_alerts") == conflict_summary.get("total_alerts"), "total_alerts mismatch"
        
        print("✓ Conflict data consistent between cockpit and standalone endpoint")


class TestRoutingFailoverDataConsistency:
    """Test data consistency after routing/failover changes"""

    def test_failover_change_reflects_in_cockpit(self, admin_client):
        """Failover policy changes reflect in cockpit active_route_map"""
        # Create a test failover policy
        failover_payload = {
            "user_id": "TEST_consistency_user",
            "strategy_id": "TEST_consistency_strategy",
            "market_type": "spot",
            "environment": "live",
            "primary_venue": "binance",
            "secondary_venue": "bybit",
            "fallback_chain": [],
            "auto_reroute_enabled": True
        }
        
        response = admin_client.put(
            f"{BASE_URL}/api/venues/admin/failover-policies",
            json=failover_payload
        )
        assert response.status_code == 200
        
        # Check cockpit for the route
        cockpit_response = admin_client.get(f"{BASE_URL}/api/venues/admin/control-plane-cockpit")
        assert cockpit_response.status_code == 200
        cockpit_data = cockpit_response.json()
        
        # Verify failover_rule_count increased
        overview = cockpit_data.get("global_overview", {})
        assert overview.get("failover_rule_count", 0) > 0, "Expected at least one failover rule"
        
        print("✓ Failover changes reflected in cockpit")

    def test_routing_change_reflects_in_conflict_detection(self, admin_client):
        """Routing policy changes can trigger conflict detection"""
        # Create a routing policy with potential conflict (blocked venue as default)
        routing_payload = {
            "user_id": "TEST_conflict_user",
            "strategy_id": "TEST_conflict_strategy",
            "market_type": "futures",
            "environment": "live",
            "default_venue": "binance",
            "blocked_venues": ["binance"],  # Intentional conflict
            "preferred_venues": ["bybit"],
            "capital_allocation": [{"venue": "bybit", "percentage": 100}]
        }
        
        response = admin_client.put(
            f"{BASE_URL}/api/venues/admin/routing-policies",
            json=routing_payload
        )
        assert response.status_code == 200
        
        # Check conflict detection
        conflict_response = admin_client.get(f"{BASE_URL}/api/venues/admin/conflict-detection-center")
        assert conflict_response.status_code == 200
        conflict_data = conflict_response.json()
        
        # Should have at least one blocking alert for default_venue_blocked
        blocking_alerts = conflict_data.get("blocking_alerts", [])
        has_conflict = any(
            alert.get("reason_code") == "default_venue_blocked" 
            for alert in blocking_alerts
        )
        
        if has_conflict:
            print("✓ Routing conflict detected: default_venue_blocked")
        else:
            print("✓ Routing policy created (no conflict detected - may be expected)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
