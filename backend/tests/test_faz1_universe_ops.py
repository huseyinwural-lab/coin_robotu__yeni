"""
Faz-1 Universe Operations Test Suite
Tests for: Scanner Control, Rollout Orchestrator, Risk/Exposure, Slow Strategy/Symbol endpoints
All endpoints require double-confirm standard: reason + phrase mandatory
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://audit-closure-dash.preview.emergentagent.com"

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "quote.user@platform.local"
USER_PASSWORD = "QuoteUser123!"


class TestAuth:
    """Authentication helper tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get super admin token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip(f"Admin auth failed: {response.status_code} - {response.text}")
    
    @pytest.fixture(scope="class")
    def user_token(self):
        """Get regular user token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip(f"User auth failed: {response.status_code} - {response.text}")
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def user_headers(self, user_token):
        return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


class TestScannerControl(TestAuth):
    """Scanner Control endpoints: start, stop, trigger"""
    
    def test_scanner_state_get(self, admin_headers):
        """GET /api/admin/universe-monitor/scanner/state - should return scanner runtime state"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/state",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "runtime" in data, "Response should contain 'runtime' field"
        assert "whitelist" in data, "Response should contain 'whitelist' field"
        assert "blacklist" in data, "Response should contain 'blacklist' field"
        print(f"Scanner state: running={data.get('runtime', {}).get('running')}")
    
    def test_scanner_start_requires_phrase(self, admin_headers):
        """POST /api/admin/universe-monitor/scanner/start - requires correct phrase"""
        # Test with wrong phrase
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/start",
            headers=admin_headers,
            json={"reason": "Testing scanner start", "confirmation_phrase": "WRONG PHRASE"}
        )
        assert response.status_code == 400, f"Expected 400 for wrong phrase, got {response.status_code}"
        
    def test_scanner_start_success(self, admin_headers):
        """POST /api/admin/universe-monitor/scanner/start - with correct phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/start",
            headers=admin_headers,
            json={"reason": "Testing scanner start for Faz-1", "confirmation_phrase": "START SCANNER"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Verify contract: status=success + trace_id + message + state_snapshot
        assert data.get("status") == "success", "Response should have status=success"
        assert "trace_id" in data, "Response should contain trace_id"
        assert "message" in data, "Response should contain message"
        assert "state_snapshot" in data, "Response should contain state_snapshot"
        print(f"Scanner start: trace_id={data.get('trace_id')}, message={data.get('message')}")
    
    def test_scanner_stop_success(self, admin_headers):
        """POST /api/admin/universe-monitor/scanner/stop - with correct phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/stop",
            headers=admin_headers,
            json={"reason": "Testing scanner stop for Faz-1", "confirmation_phrase": "STOP SCANNER"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data
        print(f"Scanner stop: trace_id={data.get('trace_id')}")
    
    def test_scanner_trigger_returns_queue_id(self, admin_headers):
        """POST /api/admin/universe-monitor/scanner/trigger - should return queue_id/request_id + queued status"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/trigger",
            headers=admin_headers,
            json={"reason": "Manual scan trigger test for Faz-1", "confirmation_phrase": "TRIGGER MANUAL SCAN"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        assert "queue_id" in data, "Response should contain queue_id for manual scan"
        # Verify state_snapshot contains queued status
        state = data.get("state_snapshot", {})
        manual_trigger = state.get("manual_trigger", {})
        assert manual_trigger.get("status") == "queued", "Manual trigger should have status=queued"
        print(f"Scanner trigger: queue_id={data.get('queue_id')}, status={manual_trigger.get('status')}")


class TestScannerSymbolManagement(TestAuth):
    """Scanner symbol management: whitelist/blacklist update, bulk toggle, filter config"""
    
    def test_scanner_symbol_lists_get(self, admin_headers):
        """GET /api/admin/universe-monitor/scanner/symbol-lists"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/symbol-lists",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "whitelist" in data
        assert "blacklist" in data
        print(f"Symbol lists: whitelist={len(data.get('whitelist', []))}, blacklist={len(data.get('blacklist', []))}")
    
    def test_whitelist_update(self, admin_headers):
        """POST /api/admin/universe-monitor/scanner/symbol-lists/whitelist"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/symbol-lists/whitelist",
            headers=admin_headers,
            json={
                "action": "add",
                "symbols": ["TESTUSDT", "TESTBTC"],
                "reason": "Testing whitelist update for Faz-1",
                "confirmation_phrase": "UPDATE SYMBOL LIST"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        assert "state_snapshot" in data
        print(f"Whitelist update: trace_id={data.get('trace_id')}")
    
    def test_blacklist_update(self, admin_headers):
        """POST /api/admin/universe-monitor/scanner/symbol-lists/blacklist"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/symbol-lists/blacklist",
            headers=admin_headers,
            json={
                "action": "add",
                "symbols": ["SCAMUSDT"],
                "reason": "Testing blacklist update for Faz-1",
                "confirmation_phrase": "UPDATE SYMBOL LIST"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        print(f"Blacklist update: trace_id={data.get('trace_id')}")
    
    def test_bulk_symbol_toggle(self, admin_headers):
        """POST /api/admin/universe-monitor/universe/symbols/bulk-toggle"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/universe/symbols/bulk-toggle",
            headers=admin_headers,
            json={
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "enabled": True,
                "reason": "Testing bulk toggle for Faz-1",
                "confirmation_phrase": "BULK UPDATE SYMBOLS"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        assert "state_snapshot" in data
        print(f"Bulk toggle: trace_id={data.get('trace_id')}")
    
    def test_filter_config_get(self, admin_headers):
        """GET /api/admin/universe-monitor/universe/filter-config"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/universe/filter-config",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "min_liquidity_usd" in data
        assert "min_volume_24h_usd" in data
        assert "max_spread_bps" in data
        print(f"Filter config: min_liquidity={data.get('min_liquidity_usd')}, min_volume={data.get('min_volume_24h_usd')}")
    
    def test_filter_config_update(self, admin_headers):
        """PUT /api/admin/universe-monitor/universe/filter-config"""
        response = requests.put(
            f"{BASE_URL}/api/admin/universe-monitor/universe/filter-config",
            headers=admin_headers,
            json={
                "min_liquidity_usd": 1000000,
                "min_volume_24h_usd": 5000000,
                "max_spread_bps": 40,
                "reason": "Testing filter config update for Faz-1",
                "confirmation_phrase": "UPDATE FILTER CONFIG"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        print(f"Filter config update: trace_id={data.get('trace_id')}")


class TestRolloutOrchestrator(TestAuth):
    """Rollout orchestrator endpoints: promote, demote, rollback, status"""
    
    def test_rollout_status(self, admin_headers):
        """GET /api/admin/universe-monitor/rollout/status - should contain required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/rollout/status",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Verify required fields per spec
        assert "current_stage" in data, "Response should contain current_stage"
        assert "previous_stage" in data, "Response should contain previous_stage"
        assert "pending_approvers" in data, "Response should contain pending_approvers"
        assert "approval_policy" in data, "Response should contain approval_policy"
        assert "rollback_available" in data, "Response should contain rollback_available"
        print(f"Rollout status: current={data.get('current_stage')}, previous={data.get('previous_stage')}, policy={data.get('approval_policy')}")
    
    def test_rollout_promote(self, admin_headers):
        """POST /api/admin/universe-monitor/rollout/promote"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/rollout/promote",
            headers=admin_headers,
            json={
                "reason": "Testing rollout promote for Faz-1",
                "confirmation_phrase": "PROMOTE ROLLOUT"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data
        # Verify state_snapshot contains rollout info with changed_by and change_reason
        rollout = data.get("state_snapshot", {}).get("rollout", {})
        assert "changed_by" in rollout or "recommendation_payload" in rollout, "Rollout should track changed_by"
        print(f"Rollout promote: trace_id={data.get('trace_id')}")
    
    def test_rollout_demote(self, admin_headers):
        """POST /api/admin/universe-monitor/rollout/demote"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/rollout/demote",
            headers=admin_headers,
            json={
                "reason": "Testing rollout demote for Faz-1",
                "confirmation_phrase": "DEMOTE ROLLOUT"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        print(f"Rollout demote: trace_id={data.get('trace_id')}")
    
    def test_rollout_rollback(self, admin_headers):
        """POST /api/admin/universe-monitor/rollout/rollback"""
        # First promote to create a previous_stage
        requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/rollout/promote",
            headers=admin_headers,
            json={"reason": "Setup for rollback test", "confirmation_phrase": "PROMOTE ROLLOUT"}
        )
        
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/rollout/rollback",
            headers=admin_headers,
            json={
                "reason": "Testing rollout rollback for Faz-1",
                "confirmation_phrase": "ROLLBACK ROLLOUT"
            }
        )
        # May return 400 if no previous_stage available
        if response.status_code == 400:
            data = response.json()
            assert "rollback_not_available" in str(data), "Should indicate rollback not available"
            print("Rollback not available (no previous stage)")
        else:
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert data.get("status") == "success"
            assert "trace_id" in data
            print(f"Rollout rollback: trace_id={data.get('trace_id')}")


class TestRiskExposure(TestAuth):
    """Risk/Exposure endpoints: exposure-limit, exposure-clusters, exposure-override"""
    
    def test_exposure_clusters_get(self, admin_headers):
        """GET /api/admin/universe-monitor/risk/exposure-clusters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/risk/exposure-clusters",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "cluster_exposure" in data or "portfolio_exposure" in data
        print(f"Exposure clusters: portfolio={data.get('portfolio_exposure')}")
    
    def test_exposure_limit_update(self, admin_headers):
        """PUT /api/admin/universe-monitor/risk/exposure-limit"""
        response = requests.put(
            f"{BASE_URL}/api/admin/universe-monitor/risk/exposure-limit",
            headers=admin_headers,
            json={
                "max_total_exposure_pct": 50,
                "max_symbol_exposure_pct": 25,
                "max_cluster_exposure_pct": 35,
                "force": True,
                "reason": "Testing exposure limit update for Faz-1",
                "confirmation_phrase": "UPDATE EXPOSURE LIMIT"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        assert "state_snapshot" in data
        print(f"Exposure limit update: trace_id={data.get('trace_id')}")
    
    def test_exposure_override_create(self, admin_headers):
        """POST /api/admin/universe-monitor/risk/exposure-override"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/risk/exposure-override",
            headers=admin_headers,
            json={
                "override_type": "force_allow",
                "scope": "global",
                "ttl_minutes": 30,
                "reason": "Testing exposure override for Faz-1",
                "confirmation_phrase": "APPLY EXPOSURE OVERRIDE"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        assert "state_snapshot" in data
        # Verify TTL visibility in state_snapshot
        override = data.get("state_snapshot", {}).get("override", {})
        assert "expires_at" in override, "Override should have expires_at for TTL visibility"
        print(f"Exposure override: trace_id={data.get('trace_id')}, expires_at={override.get('expires_at')}")
    
    def test_exposure_override_active_get(self, admin_headers):
        """GET /api/admin/universe-monitor/risk/exposure-override/active - TTL visibility"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/risk/exposure-override/active",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        # If there are active overrides, verify TTL fields
        for item in data.get("items", []):
            assert "ttl_remaining_seconds" in item or "expires_at" in item, "Active override should show TTL"
        print(f"Active overrides: count={len(data.get('items', []))}")


class TestSlowControl(TestAuth):
    """Slow control endpoints: strategy disable, throttle, symbol pause"""
    
    def test_slow_controls_status(self, admin_headers):
        """GET /api/admin/universe-monitor/slow-controls/status"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/slow-controls/status",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "disabled_strategies" in data
        assert "throttled_strategies" in data
        assert "paused_symbols" in data
        print(f"Slow controls: disabled={len(data.get('disabled_strategies', []))}, throttled={len(data.get('throttled_strategies', {}))}, paused={len(data.get('paused_symbols', []))}")
    
    def test_strategy_disable(self, admin_headers):
        """POST /api/admin/universe-monitor/strategy/{id}/disable"""
        strategy_id = "test_strategy_v1"
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/strategy/{strategy_id}/disable",
            headers=admin_headers,
            json={
                "reason": "Testing strategy disable for Faz-1",
                "confirmation_phrase": "DISABLE STRATEGY"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        assert "state_snapshot" in data
        print(f"Strategy disable: trace_id={data.get('trace_id')}")
    
    def test_strategy_throttle(self, admin_headers):
        """POST /api/admin/universe-monitor/strategy/{id}/throttle"""
        strategy_id = "test_strategy_v1"
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/strategy/{strategy_id}/throttle",
            headers=admin_headers,
            json={
                "throttle_profile": "soft",
                "reason": "Testing strategy throttle for Faz-1",
                "confirmation_phrase": "THROTTLE STRATEGY"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        assert "state_snapshot" in data
        print(f"Strategy throttle: trace_id={data.get('trace_id')}")
    
    def test_symbol_pause(self, admin_headers):
        """POST /api/admin/universe-monitor/symbol/{symbol}/pause"""
        symbol = "TESTUSDT"
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/symbol/{symbol}/pause",
            headers=admin_headers,
            json={
                "pause": True,
                "reason": "Testing symbol pause for Faz-1",
                "confirmation_phrase": "PAUSE SYMBOL"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        assert "state_snapshot" in data
        print(f"Symbol pause: trace_id={data.get('trace_id')}")


class TestDoubleConfirmContract(TestAuth):
    """Verify double-confirm standard: reason + phrase mandatory for all critical actions"""
    
    def test_missing_reason_rejected(self, admin_headers):
        """Actions without reason should be rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/start",
            headers=admin_headers,
            json={"confirmation_phrase": "START SCANNER"}  # Missing reason
        )
        assert response.status_code == 422, f"Expected 422 for missing reason, got {response.status_code}"
    
    def test_short_reason_rejected(self, admin_headers):
        """Actions with too short reason should be rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/start",
            headers=admin_headers,
            json={"reason": "abc", "confirmation_phrase": "START SCANNER"}  # Reason too short
        )
        assert response.status_code == 422, f"Expected 422 for short reason, got {response.status_code}"
    
    def test_missing_phrase_rejected(self, admin_headers):
        """Actions without confirmation phrase should be rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/start",
            headers=admin_headers,
            json={"reason": "Testing without phrase"}  # Missing phrase
        )
        assert response.status_code == 422, f"Expected 422 for missing phrase, got {response.status_code}"
    
    def test_wrong_phrase_rejected(self, admin_headers):
        """Actions with wrong phrase should be rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/start",
            headers=admin_headers,
            json={"reason": "Testing with wrong phrase", "confirmation_phrase": "WRONG PHRASE"}
        )
        assert response.status_code == 400, f"Expected 400 for wrong phrase, got {response.status_code}"


class TestActionResponseContract(TestAuth):
    """Verify critical action response contract: status=success + trace_id + message + state_snapshot"""
    
    def test_scanner_start_contract(self, admin_headers):
        """Scanner start should return full contract"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/scanner/start",
            headers=admin_headers,
            json={"reason": "Contract test for scanner start", "confirmation_phrase": "START SCANNER"}
        )
        assert response.status_code == 200
        data = response.json()
        self._verify_action_contract(data)
    
    def test_rollout_promote_contract(self, admin_headers):
        """Rollout promote should return full contract"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/rollout/promote",
            headers=admin_headers,
            json={"reason": "Contract test for rollout promote", "confirmation_phrase": "PROMOTE ROLLOUT"}
        )
        assert response.status_code == 200
        data = response.json()
        self._verify_action_contract(data)
    
    def test_exposure_limit_contract(self, admin_headers):
        """Exposure limit update should return full contract"""
        response = requests.put(
            f"{BASE_URL}/api/admin/universe-monitor/risk/exposure-limit",
            headers=admin_headers,
            json={
                "max_total_exposure_pct": 50,
                "max_symbol_exposure_pct": 25,
                "max_cluster_exposure_pct": 35,
                "force": True,
                "reason": "Contract test for exposure limit",
                "confirmation_phrase": "UPDATE EXPOSURE LIMIT"
            }
        )
        assert response.status_code == 200
        data = response.json()
        self._verify_action_contract(data)
    
    def test_strategy_disable_contract(self, admin_headers):
        """Strategy disable should return full contract"""
        response = requests.post(
            f"{BASE_URL}/api/admin/universe-monitor/strategy/contract_test_v1/disable",
            headers=admin_headers,
            json={"reason": "Contract test for strategy disable", "confirmation_phrase": "DISABLE STRATEGY"}
        )
        assert response.status_code == 200
        data = response.json()
        self._verify_action_contract(data)
    
    def _verify_action_contract(self, data):
        """Helper to verify action response contract"""
        assert data.get("status") == "success", f"Expected status=success, got {data.get('status')}"
        assert "trace_id" in data, "Response must contain trace_id"
        assert data.get("trace_id"), "trace_id must not be empty"
        assert "message" in data, "Response must contain message"
        assert "state_snapshot" in data, "Response must contain state_snapshot"
        assert isinstance(data.get("state_snapshot"), dict), "state_snapshot must be a dict"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
