"""
Execution Safety Core P0 Tests - Local TestClient Version
Tests for /api/execution-readiness/* endpoints using FastAPI TestClient
Bypasses preview URL 502 issues by testing directly against the app.
"""

import os
import sys
import pytest

# Add backend to path
sys.path.insert(0, "/app/backend")

from fastapi.testclient import TestClient
from server import fastapi_app

# Test credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def client():
    """Create TestClient for FastAPI app"""
    return TestClient(fastapi_app)


@pytest.fixture(scope="module")
def admin_token(client):
    """Get admin authentication token"""
    response = client.post(
        "/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Admin login failed: {response.status_code} - {response.text[:200]}")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestExecutionReadinessGateEndpointLocal:
    """Tests for GET /api/execution-readiness/gate endpoint using TestClient"""

    def test_gate_endpoint_requires_auth(self, client):
        """Gate endpoint should require admin authentication"""
        response = client.get("/api/execution-readiness/gate")
        assert response.status_code in [401, 403], f"Expected auth error, got {response.status_code}"
        print(f"PASS: Gate endpoint requires auth (status={response.status_code})")

    def test_gate_endpoint_returns_gate_state(self, client, auth_headers):
        """Gate endpoint should return gate_state field"""
        response = client.get("/api/execution-readiness/gate", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        
        # Verify gate_state field exists and is valid
        assert "gate_state" in data, "Missing gate_state field"
        assert data["gate_state"] in ["READY", "DEGRADED", "BLOCKED"], f"Invalid gate_state: {data['gate_state']}"
        print(f"PASS: gate_state={data['gate_state']}")

    def test_gate_endpoint_returns_execution_allowed(self, client, auth_headers):
        """Gate endpoint should return execution_allowed boolean"""
        response = client.get("/api/execution-readiness/gate", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "execution_allowed" in data, "Missing execution_allowed field"
        assert isinstance(data["execution_allowed"], bool), "execution_allowed should be boolean"
        print(f"PASS: execution_allowed={data['execution_allowed']}")

    def test_gate_endpoint_returns_hard_blockers(self, client, auth_headers):
        """Gate endpoint should return hard_blockers list"""
        response = client.get("/api/execution-readiness/gate", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "hard_blockers" in data, "Missing hard_blockers field"
        assert isinstance(data["hard_blockers"], list), "hard_blockers should be list"
        print(f"PASS: hard_blockers count={len(data['hard_blockers'])}, codes={data['hard_blockers'][:5]}")

    def test_gate_endpoint_returns_hard_blockers_detail(self, client, auth_headers):
        """Gate endpoint should return hard_blockers_detail list"""
        response = client.get("/api/execution-readiness/gate", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "hard_blockers_detail" in data, "Missing hard_blockers_detail field"
        assert isinstance(data["hard_blockers_detail"], list), "hard_blockers_detail should be list"
        
        # Verify structure of detail items
        for item in data["hard_blockers_detail"][:3]:
            assert "step_key" in item, "Missing step_key in blocker detail"
            assert "reason_code" in item, "Missing reason_code in blocker detail"
            assert "message" in item, "Missing message in blocker detail"
        
        print(f"PASS: hard_blockers_detail count={len(data['hard_blockers_detail'])}")

    def test_gate_endpoint_returns_bybit_smoke(self, client, auth_headers):
        """Gate endpoint should return bybit_order_smoke result"""
        response = client.get("/api/execution-readiness/gate", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "bybit_order_smoke" in data, "Missing bybit_order_smoke field"
        smoke = data["bybit_order_smoke"]
        assert "status" in smoke, "Missing status in bybit_order_smoke"
        assert "reason_code" in smoke, "Missing reason_code in bybit_order_smoke"
        assert "checked_at" in smoke, "Missing checked_at in bybit_order_smoke"
        print(f"PASS: bybit_order_smoke status={smoke['status']}, reason_code={smoke['reason_code']}")

    def test_gate_endpoint_returns_artifact(self, client, auth_headers):
        """Gate endpoint should return artifact metadata"""
        response = client.get("/api/execution-readiness/gate", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "artifact" in data, "Missing artifact field"
        artifact = data["artifact"]
        assert "status" in artifact, "Missing status in artifact"
        assert artifact["status"] in ["LOCAL_ONLY", "S3_UPLOADED"], f"Invalid artifact status: {artifact['status']}"
        assert "local_path" in artifact, "Missing local_path in artifact"
        print(f"PASS: artifact status={artifact['status']}, local_path exists={bool(artifact.get('local_path'))}")

    def test_gate_endpoint_returns_readiness_fields(self, client, auth_headers):
        """Gate endpoint should return readiness_state and readiness_score"""
        response = client.get("/api/execution-readiness/gate", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "readiness_state" in data, "Missing readiness_state field"
        assert "readiness_score" in data, "Missing readiness_score field"
        assert "go_live_allowed" in data, "Missing go_live_allowed field"
        
        print(f"PASS: readiness_state={data['readiness_state']}, score={data['readiness_score']}, go_live_allowed={data['go_live_allowed']}")

    def test_gate_endpoint_force_refresh_parameter(self, client, auth_headers):
        """Gate endpoint should accept force_refresh parameter"""
        response = client.get("/api/execution-readiness/gate?force_refresh=true", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "checked_at" in data, "Missing checked_at field"
        print(f"PASS: force_refresh=true accepted, checked_at={data['checked_at']}")


class TestExecutionReadinessIntentsEndpointLocal:
    """Tests for GET /api/execution-readiness/intents endpoint using TestClient"""

    def test_intents_endpoint_requires_auth(self, client):
        """Intents endpoint should require admin authentication"""
        response = client.get("/api/execution-readiness/intents")
        assert response.status_code in [401, 403], f"Expected auth error, got {response.status_code}"
        print(f"PASS: Intents endpoint requires auth (status={response.status_code})")

    def test_intents_endpoint_returns_state_machine_snapshot(self, client, auth_headers):
        """Intents endpoint should return state machine snapshot"""
        response = client.get("/api/execution-readiness/intents", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        
        # Verify required fields
        assert "total" in data, "Missing total field"
        assert "stuck_count" in data, "Missing stuck_count field"
        assert "state_counts" in data, "Missing state_counts field"
        assert "timeouts" in data, "Missing timeouts field"
        assert "items" in data, "Missing items field"
        
        print(f"PASS: total={data['total']}, stuck_count={data['stuck_count']}")

    def test_intents_endpoint_state_counts_structure(self, client, auth_headers):
        """Intents endpoint state_counts should have all state keys"""
        response = client.get("/api/execution-readiness/intents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        expected_states = ["CREATED", "SUBMITTED", "ACKED", "FILLED", "FAILED", "CANCELED", "QUARANTINED"]
        state_counts = data.get("state_counts", {})
        
        for state in expected_states:
            assert state in state_counts, f"Missing state {state} in state_counts"
        
        print(f"PASS: state_counts={state_counts}")

    def test_intents_endpoint_timeouts_structure(self, client, auth_headers):
        """Intents endpoint timeouts should have CREATED/SUBMITTED/ACKED"""
        response = client.get("/api/execution-readiness/intents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        timeouts = data.get("timeouts", {})
        expected_timeout_states = ["CREATED", "SUBMITTED", "ACKED"]
        
        for state in expected_timeout_states:
            assert state in timeouts, f"Missing timeout for state {state}"
            assert isinstance(timeouts[state], int), f"Timeout for {state} should be int"
        
        print(f"PASS: timeouts={timeouts}")

    def test_intents_endpoint_limit_parameter(self, client, auth_headers):
        """Intents endpoint should respect limit parameter"""
        response = client.get("/api/execution-readiness/intents?limit=5", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        assert len(items) <= 5, f"Expected max 5 items, got {len(items)}"
        print(f"PASS: limit=5 returned {len(items)} items")

    def test_intents_endpoint_include_events_parameter(self, client, auth_headers):
        """Intents endpoint should accept include_events parameter"""
        response = client.get("/api/execution-readiness/intents?include_events=true&limit=5", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # If there are items, they should have events field when include_events=true
        items = data.get("items", [])
        if items:
            # Events field should be present when include_events=true
            first_item = items[0]
            assert "events" in first_item, "Missing events field when include_events=true"
        
        print(f"PASS: include_events=true accepted, items count={len(items)}")

    def test_intents_endpoint_auto_quarantine_stuck_parameter(self, client, auth_headers):
        """Intents endpoint should accept auto_quarantine_stuck parameter"""
        response = client.get("/api/execution-readiness/intents?auto_quarantine_stuck=false", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "stuck_count" in data, "Missing stuck_count field"
        print(f"PASS: auto_quarantine_stuck=false accepted, stuck_count={data['stuck_count']}")


class TestExecutionReadinessQuarantineEndpointLocal:
    """Tests for GET /api/execution-readiness/quarantine endpoint using TestClient"""

    def test_quarantine_endpoint_requires_auth(self, client):
        """Quarantine endpoint should require admin authentication"""
        response = client.get("/api/execution-readiness/quarantine")
        assert response.status_code in [401, 403], f"Expected auth error, got {response.status_code}"
        print(f"PASS: Quarantine endpoint requires auth (status={response.status_code})")

    def test_quarantine_endpoint_returns_snapshot(self, client, auth_headers):
        """Quarantine endpoint should return DLQ snapshot"""
        response = client.get("/api/execution-readiness/quarantine", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        
        # Verify required fields
        assert "total" in data, "Missing total field"
        assert "summary" in data, "Missing summary field"
        assert "queue_metrics" in data, "Missing queue_metrics field"
        assert "items" in data, "Missing items field"
        
        print(f"PASS: total={data['total']}, summary keys={list(data['summary'].keys())}")

    def test_quarantine_endpoint_queue_metrics_structure(self, client, auth_headers):
        """Quarantine endpoint queue_metrics should have expected fields"""
        response = client.get("/api/execution-readiness/quarantine", headers=auth_headers)
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

    def test_quarantine_endpoint_limit_parameter(self, client, auth_headers):
        """Quarantine endpoint should respect limit parameter"""
        response = client.get("/api/execution-readiness/quarantine?limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        assert len(items) <= 10, f"Expected max 10 items, got {len(items)}"
        print(f"PASS: limit=10 returned {len(items)} items")

    def test_quarantine_endpoint_items_structure(self, client, auth_headers):
        """Quarantine endpoint items should have expected fields"""
        response = client.get("/api/execution-readiness/quarantine", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        if items:
            first_item = items[0]
            expected_fields = ["id", "event_id", "entity_type", "event_type", "status", "retry_count"]
            for field in expected_fields:
                assert field in first_item, f"Missing {field} in quarantine item"
        
        print(f"PASS: items structure verified, count={len(items)}")


class TestExecutionReadinessQuarantineActionsLocal:
    """Tests for POST /api/execution-readiness/quarantine/{event_id}/{action} endpoint using TestClient"""

    def test_quarantine_action_requires_auth(self, client):
        """Quarantine action endpoint should require admin authentication"""
        response = client.post("/api/execution-readiness/quarantine/test-event-id/replay")
        assert response.status_code in [401, 403], f"Expected auth error, got {response.status_code}"
        print(f"PASS: Quarantine action requires auth (status={response.status_code})")

    def test_quarantine_action_invalid_event_returns_404(self, client, auth_headers):
        """Quarantine action with invalid event_id should return 404"""
        response = client.post(
            "/api/execution-readiness/quarantine/nonexistent-event-id-12345/replay",
            headers=auth_headers,
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert "quarantine_event_not_found" in str(data.get("detail", "")), "Expected quarantine_event_not_found detail"
        print("PASS: Invalid event_id returns 404 with correct detail")

    def test_quarantine_action_invalid_action_returns_400(self, client, auth_headers):
        """Quarantine action with invalid action should return 400"""
        response = client.post(
            "/api/execution-readiness/quarantine/test-event-id/invalid_action",
            headers=auth_headers,
        )
        # Should return 400 for invalid action or 404 if event not found first
        assert response.status_code in [400, 404], f"Expected 400 or 404, got {response.status_code}: {response.text[:200]}"
        print(f"PASS: Invalid action returns {response.status_code}")

    def test_quarantine_action_valid_actions_list(self, client, auth_headers):
        """Valid actions should be replay, dismiss, mark_failed"""
        valid_actions = ["replay", "dismiss", "mark_failed"]
        
        for action in valid_actions:
            response = client.post(
                f"/api/execution-readiness/quarantine/nonexistent-event-id/{action}",
                headers=auth_headers,
            )
            # Should return 404 (event not found) not 400 (invalid action)
            assert response.status_code == 404, f"Action {action} should be valid, got {response.status_code}"
        
        print(f"PASS: All valid actions ({valid_actions}) accepted")


class TestGateHardBlockerBehavior:
    """Tests for hard blocker behavior in gate endpoint"""

    def test_gate_blocked_when_testnet_disabled(self, client, auth_headers):
        """Gate should be BLOCKED when TESTNET_TRADING_ENABLED=false"""
        # Note: This test verifies the current environment state
        response = client.get("/api/execution-readiness/gate", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Check if TESTNET_TRADING_DISABLED is in hard_blockers
        hard_blockers = data.get("hard_blockers", [])
        testnet_enabled = os.environ.get("TESTNET_TRADING_ENABLED", "false").lower() in ["true", "1", "yes"]
        
        if not testnet_enabled:
            assert "TESTNET_TRADING_DISABLED" in hard_blockers, "Expected TESTNET_TRADING_DISABLED in hard_blockers"
            print("PASS: TESTNET_TRADING_DISABLED correctly in hard_blockers")
        else:
            print(f"PASS: TESTNET_TRADING_ENABLED=true, hard_blockers={hard_blockers}")

    def test_gate_execution_allowed_false_when_blocked(self, client, auth_headers):
        """execution_allowed should be False when gate_state is BLOCKED"""
        response = client.get("/api/execution-readiness/gate", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        gate_state = data.get("gate_state")
        execution_allowed = data.get("execution_allowed")
        hard_blockers = data.get("hard_blockers", [])
        
        if gate_state == "BLOCKED":
            assert execution_allowed is False, "execution_allowed should be False when BLOCKED"
            assert len(hard_blockers) > 0, "hard_blockers should not be empty when BLOCKED"
        
        print(f"PASS: gate_state={gate_state}, execution_allowed={execution_allowed}, blockers={len(hard_blockers)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
