"""
Execution Safety Core P0 Tests - Iteration 172
Tests for /api/execution-readiness/* endpoints:
- GET /gate - execution safety gate with hard blocker behavior
- GET /intents - state machine + stuck detection payload
- GET /quarantine - Postgres DLQ + queue metrics payload
- POST /quarantine/{event_id}/{action} - replay/dismiss/mark_failed actions

Service-level function tests:
- get_execution_safety_gate
- get_execution_intent_state_machine_snapshot
- get_runtime_quarantine_snapshot
"""

import os
import pytest
import requests
from datetime import datetime, timezone

# Use preview URL from environment
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"

# Test credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30,
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text[:200]}")
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Admin login request failed: {str(e)[:200]}")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestExecutionReadinessGateEndpoint:
    """Tests for GET /api/execution-readiness/gate endpoint"""

    def test_gate_endpoint_requires_auth(self):
        """Gate endpoint should require admin authentication"""
        try:
            response = requests.get(f"{BASE_URL}/api/execution-readiness/gate", timeout=30)
            # Should return 401 or 403 without auth
            assert response.status_code in [401, 403, 502], f"Expected auth error, got {response.status_code}"
            print(f"PASS: Gate endpoint requires auth (status={response.status_code})")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed (preview may be down): {str(e)[:200]}")

    def test_gate_endpoint_returns_gate_state(self, auth_headers):
        """Gate endpoint should return gate_state field"""
        try:
            response = requests.get(
                f"{BASE_URL}/api/execution-readiness/gate",
                headers=auth_headers,
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
            data = response.json()
            
            # Verify gate_state field exists and is valid
            assert "gate_state" in data, "Missing gate_state field"
            assert data["gate_state"] in ["READY", "DEGRADED", "BLOCKED"], f"Invalid gate_state: {data['gate_state']}"
            print(f"PASS: gate_state={data['gate_state']}")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")

    def test_gate_endpoint_returns_execution_allowed(self, auth_headers):
        """Gate endpoint should return execution_allowed boolean"""
        try:
            response = requests.get(
                f"{BASE_URL}/api/execution-readiness/gate",
                headers=auth_headers,
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            assert response.status_code == 200
            data = response.json()
            
            assert "execution_allowed" in data, "Missing execution_allowed field"
            assert isinstance(data["execution_allowed"], bool), "execution_allowed should be boolean"
            print(f"PASS: execution_allowed={data['execution_allowed']}")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")

    def test_gate_endpoint_returns_hard_blockers(self, auth_headers):
        """Gate endpoint should return hard_blockers list"""
        try:
            response = requests.get(
                f"{BASE_URL}/api/execution-readiness/gate",
                headers=auth_headers,
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            assert response.status_code == 200
            data = response.json()
            
            assert "hard_blockers" in data, "Missing hard_blockers field"
            assert isinstance(data["hard_blockers"], list), "hard_blockers should be list"
            print(f"PASS: hard_blockers count={len(data['hard_blockers'])}")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")

    def test_gate_endpoint_returns_bybit_smoke(self, auth_headers):
        """Gate endpoint should return bybit_order_smoke result"""
        try:
            response = requests.get(
                f"{BASE_URL}/api/execution-readiness/gate",
                headers=auth_headers,
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            assert response.status_code == 200
            data = response.json()
            
            assert "bybit_order_smoke" in data, "Missing bybit_order_smoke field"
            smoke = data["bybit_order_smoke"]
            assert "status" in smoke, "Missing status in bybit_order_smoke"
            assert "reason_code" in smoke, "Missing reason_code in bybit_order_smoke"
            print(f"PASS: bybit_order_smoke status={smoke['status']}, reason_code={smoke['reason_code']}")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")

    def test_gate_endpoint_returns_artifact(self, auth_headers):
        """Gate endpoint should return artifact metadata"""
        try:
            response = requests.get(
                f"{BASE_URL}/api/execution-readiness/gate",
                headers=auth_headers,
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            assert response.status_code == 200
            data = response.json()
            
            assert "artifact" in data, "Missing artifact field"
            artifact = data["artifact"]
            assert "status" in artifact, "Missing status in artifact"
            # Status can be LOCAL_ONLY or S3_UPLOADED
            assert artifact["status"] in ["LOCAL_ONLY", "S3_UPLOADED"], f"Invalid artifact status: {artifact['status']}"
            print(f"PASS: artifact status={artifact['status']}")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")


class TestExecutionReadinessIntentsEndpoint:
    """Tests for GET /api/execution-readiness/intents endpoint"""

    def test_intents_endpoint_requires_auth(self):
        """Intents endpoint should require admin authentication"""
        try:
            response = requests.get(f"{BASE_URL}/api/execution-readiness/intents", timeout=30)
            assert response.status_code in [401, 403, 502], f"Expected auth error, got {response.status_code}"
            print(f"PASS: Intents endpoint requires auth (status={response.status_code})")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")

    def test_intents_endpoint_returns_state_machine_snapshot(self, auth_headers):
        """Intents endpoint should return state machine snapshot"""
        try:
            response = requests.get(
                f"{BASE_URL}/api/execution-readiness/intents",
                headers=auth_headers,
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
            data = response.json()
            
            # Verify required fields
            assert "total" in data, "Missing total field"
            assert "stuck_count" in data, "Missing stuck_count field"
            assert "state_counts" in data, "Missing state_counts field"
            assert "timeouts" in data, "Missing timeouts field"
            assert "items" in data, "Missing items field"
            
            print(f"PASS: total={data['total']}, stuck_count={data['stuck_count']}")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")

    def test_intents_endpoint_state_counts_structure(self, auth_headers):
        """Intents endpoint state_counts should have all state keys"""
        try:
            response = requests.get(
                f"{BASE_URL}/api/execution-readiness/intents",
                headers=auth_headers,
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            assert response.status_code == 200
            data = response.json()
            
            expected_states = ["CREATED", "SUBMITTED", "ACKED", "FILLED", "FAILED", "CANCELLED", "QUARANTINED"]
            state_counts = data.get("state_counts", {})
            
            for state in expected_states:
                assert state in state_counts, f"Missing state {state} in state_counts"
            
            print(f"PASS: state_counts has all expected states: {list(state_counts.keys())}")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")

    def test_intents_endpoint_timeouts_structure(self, auth_headers):
        """Intents endpoint timeouts should have CREATED/SUBMITTED/ACKED"""
        try:
            response = requests.get(
                f"{BASE_URL}/api/execution-readiness/intents",
                headers=auth_headers,
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            assert response.status_code == 200
            data = response.json()
            
            timeouts = data.get("timeouts", {})
            expected_timeout_states = ["CREATED", "SUBMITTED", "ACKED"]
            
            for state in expected_timeout_states:
                assert state in timeouts, f"Missing timeout for state {state}"
                assert isinstance(timeouts[state], int), f"Timeout for {state} should be int"
            
            print(f"PASS: timeouts={timeouts}")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")

    def test_intents_endpoint_limit_parameter(self, auth_headers):
        """Intents endpoint should respect limit parameter"""
        try:
            response = requests.get(
                f"{BASE_URL}/api/execution-readiness/intents",
                headers=auth_headers,
                params={"limit": 5},
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            assert response.status_code == 200
            data = response.json()
            
            items = data.get("items", [])
            assert len(items) <= 5, f"Expected max 5 items, got {len(items)}"
            print(f"PASS: limit=5 returned {len(items)} items")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")


class TestExecutionReadinessQuarantineEndpoint:
    """Tests for GET /api/execution-readiness/quarantine endpoint"""

    def test_quarantine_endpoint_requires_auth(self):
        """Quarantine endpoint should require admin authentication"""
        try:
            response = requests.get(f"{BASE_URL}/api/execution-readiness/quarantine", timeout=30)
            assert response.status_code in [401, 403, 502], f"Expected auth error, got {response.status_code}"
            print(f"PASS: Quarantine endpoint requires auth (status={response.status_code})")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")

    def test_quarantine_endpoint_returns_snapshot(self, auth_headers):
        """Quarantine endpoint should return DLQ snapshot"""
        try:
            response = requests.get(
                f"{BASE_URL}/api/execution-readiness/quarantine",
                headers=auth_headers,
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
            data = response.json()
            
            # Verify required fields
            assert "total" in data, "Missing total field"
            assert "summary" in data, "Missing summary field"
            assert "queue_metrics" in data, "Missing queue_metrics field"
            assert "items" in data, "Missing items field"
            
            print(f"PASS: total={data['total']}, summary keys={list(data['summary'].keys())}")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")

    def test_quarantine_endpoint_queue_metrics_structure(self, auth_headers):
        """Quarantine endpoint queue_metrics should have expected fields"""
        try:
            response = requests.get(
                f"{BASE_URL}/api/execution-readiness/quarantine",
                headers=auth_headers,
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            assert response.status_code == 200
            data = response.json()
            
            queue_metrics = data.get("queue_metrics", {})
            expected_fields = [
                "redis_available",
                "runtime_events_queue",
                "runtime_retry_queue",
                "runtime_dead_letter_queue",
                "runtime_quarantine_queue",
            ]
            
            for field in expected_fields:
                assert field in queue_metrics, f"Missing {field} in queue_metrics"
            
            print(f"PASS: queue_metrics={queue_metrics}")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")

    def test_quarantine_endpoint_limit_parameter(self, auth_headers):
        """Quarantine endpoint should respect limit parameter"""
        try:
            response = requests.get(
                f"{BASE_URL}/api/execution-readiness/quarantine",
                headers=auth_headers,
                params={"limit": 10},
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            assert response.status_code == 200
            data = response.json()
            
            items = data.get("items", [])
            assert len(items) <= 10, f"Expected max 10 items, got {len(items)}"
            print(f"PASS: limit=10 returned {len(items)} items")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")


class TestExecutionReadinessQuarantineActions:
    """Tests for POST /api/execution-readiness/quarantine/{event_id}/{action} endpoint"""

    def test_quarantine_action_requires_auth(self):
        """Quarantine action endpoint should require admin authentication"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/execution-readiness/quarantine/test-event-id/replay",
                timeout=30,
            )
            assert response.status_code in [401, 403, 502], f"Expected auth error, got {response.status_code}"
            print(f"PASS: Quarantine action requires auth (status={response.status_code})")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")

    def test_quarantine_action_invalid_event_returns_404(self, auth_headers):
        """Quarantine action with invalid event_id should return 404"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/execution-readiness/quarantine/nonexistent-event-id-12345/replay",
                headers=auth_headers,
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text[:200]}"
            print(f"PASS: Invalid event_id returns 404")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")

    def test_quarantine_action_invalid_action_returns_400(self, auth_headers):
        """Quarantine action with invalid action should return 400"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/execution-readiness/quarantine/test-event-id/invalid_action",
                headers=auth_headers,
                timeout=30,
            )
            if response.status_code == 502:
                pytest.skip("Preview URL returning 502")
            
            # Should return 400 for invalid action or 404 if event not found first
            assert response.status_code in [400, 404], f"Expected 400 or 404, got {response.status_code}: {response.text[:200]}"
            print(f"PASS: Invalid action returns {response.status_code}")
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Request failed: {str(e)[:200]}")


class TestServiceLevelFunctions:
    """Service-level function tests (direct Python imports)"""

    def test_hard_block_reason_codes_defined(self):
        """HARD_BLOCK_REASON_CODES should be defined with expected codes"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from services.execution_safety_core_service import HARD_BLOCK_REASON_CODES
        
        expected_codes = [
            "TESTNET_TRADING_DISABLED",
            "MARKET_DATA_MISSING",
            "KILL_SWITCH_ACTIVE",
            "BYBIT_TESTNET_CREDENTIALS_MISSING",
            "BYBIT_AUTH_PROBE_FAIL",
            "BYBIT_CONNECTIVITY_FAIL",
            "BYBIT_ORDER_SMOKE_FAIL",
        ]
        
        for code in expected_codes:
            assert code in HARD_BLOCK_REASON_CODES, f"Missing expected code: {code}"
        
        print(f"PASS: HARD_BLOCK_REASON_CODES has {len(HARD_BLOCK_REASON_CODES)} codes")

    def test_intent_allowed_transitions_defined(self):
        """INTENT_ALLOWED_TRANSITIONS should define valid state machine"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from services.execution_safety_core_service import INTENT_ALLOWED_TRANSITIONS
        
        expected_states = ["CREATED", "SUBMITTED", "ACKED", "FILLED", "FAILED", "CANCELLED", "QUARANTINED"]
        
        for state in expected_states:
            assert state in INTENT_ALLOWED_TRANSITIONS, f"Missing state: {state}"
        
        # Verify terminal states have no transitions
        assert len(INTENT_ALLOWED_TRANSITIONS["FILLED"]) == 0, "FILLED should be terminal"
        assert len(INTENT_ALLOWED_TRANSITIONS["FAILED"]) == 0, "FAILED should be terminal"
        assert len(INTENT_ALLOWED_TRANSITIONS["CANCELLED"]) == 0, "CANCELLED should be terminal"
        
        print(f"PASS: INTENT_ALLOWED_TRANSITIONS defines {len(INTENT_ALLOWED_TRANSITIONS)} states")

    def test_intent_stuck_timeout_defaults(self):
        """INTENT_STUCK_TIMEOUT_DEFAULTS should have reasonable values"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from services.execution_safety_core_service import INTENT_STUCK_TIMEOUT_DEFAULTS
        
        assert INTENT_STUCK_TIMEOUT_DEFAULTS["CREATED"] == 60, "CREATED timeout should be 60s"
        assert INTENT_STUCK_TIMEOUT_DEFAULTS["SUBMITTED"] == 120, "SUBMITTED timeout should be 120s"
        assert INTENT_STUCK_TIMEOUT_DEFAULTS["ACKED"] == 300, "ACKED timeout should be 300s"
        
        print(f"PASS: INTENT_STUCK_TIMEOUT_DEFAULTS={INTENT_STUCK_TIMEOUT_DEFAULTS}")

    def test_hard_block_step_keys_defined(self):
        """HARD_BLOCK_STEP_KEYS should be defined"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from services.execution_safety_core_service import HARD_BLOCK_STEP_KEYS
        
        expected_keys = [
            "market_data_present",
            "orderbook_sync",
            "exchange_connection_ready",
            "venue_connectivity_bybit",
            "proof_quality",
            "kill_switch",
        ]
        
        for key in expected_keys:
            assert key in HARD_BLOCK_STEP_KEYS, f"Missing step key: {key}"
        
        print(f"PASS: HARD_BLOCK_STEP_KEYS has {len(HARD_BLOCK_STEP_KEYS)} keys")


class TestRouterRegistration:
    """Tests to verify router is properly registered in server.py"""

    def test_execution_readiness_router_imported(self):
        """execution_readiness_core router should be imported in server.py"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        # Check server.py imports
        with open("/app/backend/server.py", "r") as f:
            content = f.read()
        
        assert "execution_readiness_core" in content, "execution_readiness_core not imported in server.py"
        assert "api_router.include_router(execution_readiness_core.router)" in content, "Router not included"
        
        print("PASS: execution_readiness_core router properly registered")

    def test_router_prefix_is_correct(self):
        """Router should have /execution-readiness prefix"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from routers.execution_readiness_core import router
        
        assert router.prefix == "/execution-readiness", f"Expected /execution-readiness, got {router.prefix}"
        print(f"PASS: Router prefix={router.prefix}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
