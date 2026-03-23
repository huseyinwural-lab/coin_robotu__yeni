"""
P0 Pipeline Operations Fix Actions Test Suite
Tests:
1. State Validation fix buttons (Fix WS / Re-sync Override / Run Gate Re-check / Rebuild Guard List)
2. Gate rule FAIL suggested fix flow
3. Guard panel actions (Unblock/Ignore/Inspect)
4. Backend action contract: {status, trace_id, message, state_snapshot}
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://execution-safety-hub.preview.emergentagent.com"

# Test credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


class TestP0PipelineOpsFixActions:
    """P0 Pipeline Operations Fix Actions Tests"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for admin user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

    # ============ State Validation Endpoint Tests ============

    def test_state_validation_endpoint_returns_checks(self, auth_headers):
        """Test /runtime/state-validation returns checks with fix_action fields"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/state-validation",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "overall_status" in data, "Missing overall_status"
        assert "checks" in data, "Missing checks"
        assert "suggestions" in data, "Missing suggestions"
        assert "checked_at" in data, "Missing checked_at"
        
        # Verify checks have fix_action fields
        checks = data.get("checks", {})
        for key, check in checks.items():
            assert "status" in check, f"Check {key} missing status"
            assert "fix_action" in check, f"Check {key} missing fix_action"
            print(f"Check {key}: status={check['status']}, fix_action={check['fix_action']}")

    # ============ Fix WS Action Test ============

    def test_fix_ws_reconnect_action(self, auth_headers):
        """Test WS reconnect action returns proper contract"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/ws/reconnect",
            headers=auth_headers,
            json={
                "reason": "P0 test: state_validation_fix:Fix WS",
                "confirmation_phrase": "RECONNECT WS",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify action contract: {status, trace_id, message, state_snapshot}
        assert "status" in data, "Missing status in response"
        assert "trace_id" in data, "Missing trace_id in response"
        assert "message" in data, "Missing message in response"
        assert "state_snapshot" in data, "Missing state_snapshot in response"
        assert "timestamp" in data, "Missing timestamp in response"
        
        assert data["status"] == "success", f"Expected success, got {data['status']}"
        assert data["trace_id"] is not None and data["trace_id"] != "-", "trace_id should be valid UUID"
        print(f"Fix WS: trace_id={data['trace_id']}, message={data['message']}")

    # ============ Gate Re-check Action Test ============

    def test_gate_recheck_action(self, auth_headers):
        """Test Gate Re-check action returns proper contract"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/gate/recheck",
            headers=auth_headers,
            json={
                "reason": "P0 test: state_validation_fix:Run Gate Re-check",
                "confirmation_phrase": "RECHECK RELEASE GATE",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify action contract
        assert "status" in data, "Missing status"
        assert "trace_id" in data, "Missing trace_id"
        assert "message" in data, "Missing message"
        assert "state_snapshot" in data, "Missing state_snapshot"
        
        assert data["status"] == "success"
        print(f"Gate Re-check: trace_id={data['trace_id']}, message={data['message']}")

    # ============ Gate Status with Suggested Fixes Test ============

    def test_gate_status_returns_suggested_fixes(self, auth_headers):
        """Test /runtime/gate/status returns rules with suggested_fix and run_fix_action"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/gate/status",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "status" in data, "Missing status"
        assert "rules" in data, "Missing rules"
        
        rules = data.get("rules", [])
        print(f"Gate status: {data.get('status')}, rules_count={len(rules)}")
        
        for rule in rules:
            assert "rule_id" in rule, "Rule missing rule_id"
            assert "result" in rule, "Rule missing result"
            # Check for suggested_fix fields
            if rule.get("result") == "FAIL":
                assert "suggested_fix" in rule or "fix_hint" in rule, f"FAIL rule {rule['rule_id']} missing suggested_fix"
                assert "run_fix_action" in rule, f"FAIL rule {rule['rule_id']} missing run_fix_action"
                print(f"  FAIL rule: {rule['rule_id']}, run_fix_action={rule.get('run_fix_action')}")

    # ============ Guard Telemetry Test ============

    def test_guard_telemetry_endpoint(self, auth_headers):
        """Test /runtime/guard/telemetry returns blocked trades"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/guard/telemetry",
            headers=auth_headers,
            params={"limit": 100},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "blocked_trade_list" in data or "top_reasons" in data, "Missing guard telemetry data"
        print(f"Guard telemetry: blocked_count={len(data.get('blocked_trade_list', []))}")

    # ============ Guard Action: Unblock (force_allow) Test ============

    def test_guard_action_unblock(self, auth_headers):
        """Test Guard Unblock action via exposure-override with force_allow"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/risk/exposure-override",
            headers=auth_headers,
            json={
                "override_type": "force_allow",
                "scope": "BTCUSDT",
                "ttl_minutes": 30,
                "reason": "P0 test: guard_action:unblock BTCUSDT",
                "confirmation_phrase": "APPLY EXPOSURE OVERRIDE",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify action contract
        assert "status" in data, "Missing status"
        assert "trace_id" in data, "Missing trace_id"
        assert "message" in data, "Missing message"
        assert "state_snapshot" in data, "Missing state_snapshot"
        
        assert data["status"] == "success"
        print(f"Guard Unblock: trace_id={data['trace_id']}, message={data['message']}")

    # ============ Guard Action: Ignore (force_reject) Test ============

    def test_guard_action_ignore(self, auth_headers):
        """Test Guard Ignore action via exposure-override with force_reject"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/risk/exposure-override",
            headers=auth_headers,
            json={
                "override_type": "force_reject",
                "scope": "ETHUSDT",
                "ttl_minutes": 30,
                "reason": "P0 test: guard_action:ignore ETHUSDT",
                "confirmation_phrase": "APPLY EXPOSURE OVERRIDE",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify action contract
        assert "status" in data, "Missing status"
        assert "trace_id" in data, "Missing trace_id"
        assert "message" in data, "Missing message"
        assert "state_snapshot" in data, "Missing state_snapshot"
        
        assert data["status"] == "success"
        # Verify override_type is correctly set
        state_snapshot = data.get("state_snapshot", {})
        override = state_snapshot.get("override", {})
        assert override.get("override_type") == "force_reject", f"Expected force_reject, got {override.get('override_type')}"
        print(f"Guard Ignore: trace_id={data['trace_id']}, override_type={override.get('override_type')}")

    # ============ Active Exposure Overrides Test ============

    def test_active_exposure_overrides(self, auth_headers):
        """Test /risk/exposure-override/active returns created overrides"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/risk/exposure-override/active",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data, "Missing items"
        
        items = data.get("items", [])
        print(f"Active exposure overrides: count={len(items)}")
        for item in items[:5]:
            print(f"  - {item.get('scope')}: {item.get('override_type')}, expires={item.get('expires_at')}")

    # ============ Service Restart Action Test ============

    def test_service_restart_action_contract(self, auth_headers):
        """Test service restart returns proper contract"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/service/restart",
            headers=auth_headers,
            json={
                "service": "all",
                "reason": "P0 test: gate_fix:db_restart_then_gate_recheck",
                "confirmation_phrase": "RESTART SERVICE",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify action contract
        assert "status" in data, "Missing status"
        assert "trace_id" in data, "Missing trace_id"
        assert "message" in data, "Missing message"
        assert "state_snapshot" in data, "Missing state_snapshot"
        
        print(f"Service Restart: trace_id={data['trace_id']}, message={data['message']}")

    # ============ Override Active Endpoint Test ============

    def test_override_active_endpoint(self, auth_headers):
        """Test /runtime/override/active returns proper structure"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/override/active",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data, "Missing items"
        print(f"Runtime overrides active: count={len(data.get('items', []))}")

    # ============ Action Audit Endpoint Test ============

    def test_action_audit_endpoint(self, auth_headers):
        """Test /runtime/action-audit returns audit trail"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/action-audit",
            headers=auth_headers,
            params={"since_hours": 24, "limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data, "Missing items"
        
        items = data.get("items", [])
        print(f"Action audit: count={len(items)}")
        
        # Check that recent actions have trace_id in details
        for item in items[:5]:
            details = item.get("details", {})
            if "trace_id" in details:
                print(f"  - {item.get('action')}: trace_id={details.get('trace_id')}")


class TestP0ActionContractValidation:
    """Validate all critical action endpoints return proper contract"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip(f"Authentication failed: {response.status_code}")

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

    def _validate_action_contract(self, data, action_name):
        """Helper to validate action response contract"""
        required_fields = ["status", "trace_id", "message", "state_snapshot"]
        missing = [f for f in required_fields if f not in data]
        assert not missing, f"{action_name}: Missing fields {missing}"
        
        assert data["trace_id"] is not None, f"{action_name}: trace_id is None"
        assert data["trace_id"] != "-", f"{action_name}: trace_id is '-'"
        assert isinstance(data["state_snapshot"], dict), f"{action_name}: state_snapshot not dict"
        
        return True

    def test_ws_reconnect_contract(self, auth_headers):
        """Validate WS reconnect action contract"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/ws/reconnect",
            headers=auth_headers,
            json={
                "reason": "Contract validation test",
                "confirmation_phrase": "RECONNECT WS",
            },
        )
        assert response.status_code == 200
        assert self._validate_action_contract(response.json(), "ws_reconnect")

    def test_gate_recheck_contract(self, auth_headers):
        """Validate Gate recheck action contract"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/gate/recheck",
            headers=auth_headers,
            json={
                "reason": "Contract validation test",
                "confirmation_phrase": "RECHECK RELEASE GATE",
            },
        )
        assert response.status_code == 200
        assert self._validate_action_contract(response.json(), "gate_recheck")

    def test_exposure_override_contract(self, auth_headers):
        """Validate exposure override action contract"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/risk/exposure-override",
            headers=auth_headers,
            json={
                "override_type": "force_allow",
                "scope": "global",
                "ttl_minutes": 5,
                "reason": "Contract validation test",
                "confirmation_phrase": "APPLY EXPOSURE OVERRIDE",
            },
        )
        assert response.status_code == 200
        assert self._validate_action_contract(response.json(), "exposure_override")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
