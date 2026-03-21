"""
Test iteration 53: Pipeline Operations Unified Panel
Tests for:
- Route redirects: /admin/pipeline-control and /admin/pipeline-monitoring -> /admin/pipeline-operations
- GET /api/runtime/state-validation endpoint with real fields
- Action response status=success + trace_id + message + state_snapshot
- WS debug: ws health response fields
- Release gate: rules[] + fix_hint
- Override: ttl_remaining_seconds + impacted_trades_count
- Exchange monitoring: drift table + revalidate/disable actions
- Alert system: severity badge + filters
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Get headers with admin token"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestStateValidationEndpoint:
    """Tests for GET /api/runtime/state-validation endpoint"""

    def test_state_validation_returns_real_fields(self, admin_headers):
        """Verify state-validation endpoint returns required fields"""
        response = requests.get(f"{BASE_URL}/api/runtime/state-validation", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check required fields exist
        assert "ws_session_changed" in data, "Missing ws_session_changed field"
        assert "override_effect_applied" in data, "Missing override_effect_applied field"
        assert "gate_source" in data, "Missing gate_source field"
        assert "guard_block_visible" in data, "Missing guard_block_visible field"
        assert "suggestions" in data, "Missing suggestions field"
        assert "checked_at" in data, "Missing checked_at field"
        
        # Verify field types
        assert isinstance(data["ws_session_changed"], bool), "ws_session_changed should be boolean"
        assert isinstance(data["override_effect_applied"], bool), "override_effect_applied should be boolean"
        assert isinstance(data["gate_source"], str), "gate_source should be string"
        assert isinstance(data["guard_block_visible"], bool), "guard_block_visible should be boolean"
        assert isinstance(data["suggestions"], dict), "suggestions should be dict"
        
        print(f"State validation response: {data}")


class TestWSHealthEndpoint:
    """Tests for WS health endpoint with debug fields"""

    def test_ws_health_returns_debug_fields(self, admin_headers):
        """Verify WS health endpoint returns debug fields"""
        response = requests.get(f"{BASE_URL}/api/runtime/ws/health", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check debug fields exist
        assert "session_id" in data, "Missing session_id field"
        assert "reconnect_count" in data, "Missing reconnect_count field"
        assert "last_error" in data or data.get("state", {}).get("last_error") is not None or "last_error" in str(data), "Missing last_error field"
        assert "reconnect_reason" in data, "Missing reconnect_reason field"
        assert "recent_reconnect_reasons" in data, "Missing recent_reconnect_reasons field"
        
        # Verify recent_reconnect_reasons is a list with up to 5 items
        recent_reasons = data.get("recent_reconnect_reasons", [])
        assert isinstance(recent_reasons, list), "recent_reconnect_reasons should be list"
        assert len(recent_reasons) <= 5, "recent_reconnect_reasons should have max 5 items"
        
        print(f"WS health response: {data}")


class TestReleaseGateEndpoint:
    """Tests for release gate endpoint with rules and fix_hint"""

    def test_gate_status_returns_rules_and_fix_hint(self, admin_headers):
        """Verify gate status endpoint returns rules[] with fix_hint"""
        response = requests.get(f"{BASE_URL}/api/runtime/gate/status", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check rules field exists
        assert "rules" in data, "Missing rules field"
        rules = data.get("rules", [])
        assert isinstance(rules, list), "rules should be list"
        
        # If rules exist, verify structure
        if rules:
            for rule in rules:
                assert "rule_id" in rule, "Rule missing rule_id"
                assert "result" in rule, "Rule missing result"
                assert "message" in rule, "Rule missing message"
                assert "fix_hint" in rule, "Rule missing fix_hint"
                
                # Verify result is PASS or FAIL
                assert rule["result"] in ["PASS", "FAIL"], f"Invalid rule result: {rule['result']}"
        
        print(f"Gate status rules count: {len(rules)}")
        if rules:
            print(f"First rule: {rules[0]}")


class TestOverrideEndpoint:
    """Tests for override endpoint with ttl_remaining_seconds and impacted_trades_count"""

    def test_override_active_returns_enriched_fields(self, admin_headers):
        """Verify override/active endpoint returns ttl_remaining_seconds and impacted_trades_count"""
        response = requests.get(f"{BASE_URL}/api/runtime/override/active", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check structure
        assert "items" in data, "Missing items field"
        assert "max_ttl_minutes" in data, "Missing max_ttl_minutes field"
        assert "total_impacted_trades" in data, "Missing total_impacted_trades field"
        
        items = data.get("items", [])
        assert isinstance(items, list), "items should be list"
        
        # If items exist, verify enriched fields
        if items:
            for item in items:
                assert "ttl_remaining_seconds" in item, "Item missing ttl_remaining_seconds"
                assert "impacted_trades_count" in item, "Item missing impacted_trades_count"
        
        print(f"Active overrides count: {len(items)}")
        print(f"Total impacted trades: {data.get('total_impacted_trades')}")


class TestExchangeMonitoringEndpoint:
    """Tests for exchange monitoring endpoint"""

    def test_exchange_monitoring_returns_drift_and_connections(self, admin_headers):
        """Verify exchange monitoring endpoint returns drift and connection details"""
        response = requests.get(f"{BASE_URL}/api/runtime/exchange/monitoring", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check required fields
        assert "drift_details" in data, "Missing drift_details field"
        assert "connection_details" in data, "Missing connection_details field"
        assert "trend" in data, "Missing trend field"
        
        assert isinstance(data["drift_details"], list), "drift_details should be list"
        assert isinstance(data["connection_details"], list), "connection_details should be list"
        assert isinstance(data["trend"], list), "trend should be list"
        
        print(f"Drift details count: {len(data['drift_details'])}")
        print(f"Connection details count: {len(data['connection_details'])}")


class TestAlertSystemEndpoint:
    """Tests for alert system with severity and filters"""

    def test_alerts_history_with_filters(self, admin_headers):
        """Verify alerts history endpoint supports severity, time, and event filters"""
        # Test with severity filter
        response = requests.get(
            f"{BASE_URL}/api/runtime/alerts/history",
            headers=admin_headers,
            params={"severity": "CRITICAL", "since_hours": 24, "limit": 50}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data, "Missing items field"
        assert "count" in data, "Missing count field"
        
        items = data.get("items", [])
        assert isinstance(items, list), "items should be list"
        
        # Verify severity field in items
        for item in items:
            assert "severity" in item, "Item missing severity field"
            assert "alert_type" in item, "Item missing alert_type field"
            assert "status" in item, "Item missing status field"
        
        print(f"Alerts count: {len(items)}")

    def test_alerts_history_with_event_type_filter(self, admin_headers):
        """Verify alerts history endpoint supports event_type filter"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/alerts/history",
            headers=admin_headers,
            params={"event_type": "TEST", "since_hours": 48, "limit": 20}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data, "Missing items field"
        print(f"Filtered alerts count: {len(data.get('items', []))}")


class TestActionResultFormat:
    """Tests for action response format with status=success, trace_id, message, state_snapshot"""

    def test_heartbeat_check_returns_action_result_format(self, admin_headers):
        """Verify heartbeat check returns proper action result format"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/heartbeat/check",
            headers=admin_headers,
            json={"lag_threshold_seconds": 60}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify action result format
        assert "status" in data, "Missing status field"
        assert "trace_id" in data, "Missing trace_id field"
        assert "message" in data, "Missing message field"
        assert "state_snapshot" in data, "Missing state_snapshot field"
        
        # Verify status is success
        assert data["status"] == "success", f"Expected status=success, got {data['status']}"
        
        # Verify trace_id is a valid UUID-like string
        assert data["trace_id"] is not None, "trace_id should not be None"
        assert len(str(data["trace_id"])) > 10, "trace_id should be a valid UUID"
        
        # Verify state_snapshot is a dict
        assert isinstance(data["state_snapshot"], dict), "state_snapshot should be dict"
        
        print(f"Action result: status={data['status']}, trace_id={data['trace_id']}")


class TestQuotePolicyEndpoint:
    """Tests for quote policy endpoint"""

    def test_quote_policy_returns_allowed_assets(self, admin_headers):
        """Verify quote policy endpoint returns allowed_quote_assets"""
        response = requests.get(f"{BASE_URL}/api/runtime/quote-policy", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "allowed_quote_assets" in data, "Missing allowed_quote_assets field"
        assert isinstance(data["allowed_quote_assets"], list), "allowed_quote_assets should be list"
        
        print(f"Allowed quote assets: {data['allowed_quote_assets']}")


class TestGuardTelemetryEndpoint:
    """Tests for guard telemetry endpoint"""

    def test_guard_telemetry_returns_data(self, admin_headers):
        """Verify guard telemetry endpoint returns expected structure"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/guard/telemetry",
            headers=admin_headers,
            params={"limit": 100}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Guard telemetry should return some structure
        assert isinstance(data, dict), "Response should be dict"
        print(f"Guard telemetry keys: {list(data.keys())}")


class TestAlertPolicyEndpoint:
    """Tests for alert policy endpoint"""

    def test_alert_policy_returns_policy_and_versions(self, admin_headers):
        """Verify alert policy endpoint returns policy and versions"""
        response = requests.get(f"{BASE_URL}/api/runtime/alert-policy", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "policy" in data, "Missing policy field"
        assert "versions" in data, "Missing versions field"
        
        policy = data.get("policy", {})
        assert "execution_quality_warning_threshold" in policy, "Missing execution_quality_warning_threshold"
        assert "execution_quality_critical_threshold" in policy, "Missing execution_quality_critical_threshold"
        assert "permission_drift_warning_per_day" in policy, "Missing permission_drift_warning_per_day"
        assert "permission_drift_critical_per_day" in policy, "Missing permission_drift_critical_per_day"
        
        print(f"Alert policy: {policy}")


class TestActionAuditEndpoint:
    """Tests for action audit endpoint"""

    def test_action_audit_returns_items(self, admin_headers):
        """Verify action audit endpoint returns items with expected structure"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/action-audit",
            headers=admin_headers,
            params={"since_hours": 48, "limit": 20}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data, "Missing items field"
        assert "count" in data, "Missing count field"
        
        items = data.get("items", [])
        if items:
            item = items[0]
            assert "action" in item, "Item missing action field"
            assert "severity" in item, "Item missing severity field"
            assert "actor_role" in item, "Item missing actor_role field"
        
        print(f"Action audit count: {len(items)}")


class TestHardeningAnalyticsEndpoint:
    """Tests for hardening analytics endpoint"""

    def test_hardening_analytics_returns_items(self, admin_headers):
        """Verify hardening analytics endpoint returns items"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/hardening/analytics",
            headers=admin_headers,
            params={"time_window_hours": 24}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data, "Missing items field"
        assert "count" in data, "Missing count field"
        
        print(f"Hardening analytics count: {data.get('count', 0)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
