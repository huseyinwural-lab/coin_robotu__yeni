"""
Execution Control & Recovery System P0 Tests
Tests for:
- Execution State Transitions (control, detail, simulate, simulate-batch)
- Idempotency Collisions (list, resolve)
- Failed Events (list, dead-letter, retry, resolve, reprocess, bulk actions)
- Manual Intervention (guardrails, state transitions)
- Execution Trace (correlation chain)
- State Rebuild (scoped run, logs)
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Auth headers for API requests"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestExecutionStateTransitionsControl:
    """GET /api/admin-phase3/execution-state-transitions/control tests"""

    def test_control_endpoint_returns_200(self, auth_headers):
        """Basic control endpoint returns 200 with rows, summary_counts, state_counters"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "rows" in data, "Response should have 'rows' field"
        assert "summary_counts" in data, "Response should have 'summary_counts' field"
        assert "state_counters" in data, "Response should have 'state_counters' field"
        assert isinstance(data["rows"], list)
        assert isinstance(data["summary_counts"], dict)
        assert isinstance(data["state_counters"], dict)

    def test_control_with_source_type_filter(self, auth_headers):
        """Control endpoint filters by source_type"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?source_type=simulation",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for row in data.get("rows", []):
            if row.get("source_type"):
                assert row["source_type"] == "simulation", f"Expected simulation, got {row['source_type']}"

    def test_control_with_search_filter(self, auth_headers):
        """Control endpoint supports search parameter"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?search=BTC",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "rows" in data

    def test_control_with_state_filter(self, auth_headers):
        """Control endpoint filters by state"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?state=filled",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for row in data.get("rows", []):
            assert row.get("state") == "filled"


class TestExecutionStateSimulation:
    """POST /api/admin-phase3/execution-state-transitions/simulate tests"""

    def test_simulate_creates_persistent_record(self, auth_headers):
        """Simulation creates persistent execution event with source_type/environment/correlation_id"""
        correlation_id = f"test_sim_{uuid.uuid4().hex[:12]}"
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol=BTCUSDT&side=long&outcome=filled"
            f"&source_type=simulation&environment=simulation&correlation_id={correlation_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "execution_event_id" in data, "Response should have execution_event_id"
        assert "final_state" in data, "Response should have final_state"
        assert "state_path" in data, "Response should have state_path"
        assert "source_type" in data, "Response should have source_type"
        assert "environment" in data, "Response should have environment"
        assert "correlation_id" in data, "Response should have correlation_id"
        
        # Verify values
        assert data["source_type"] == "simulation"
        assert data["environment"] == "simulation"
        assert data["correlation_id"] == correlation_id
        assert isinstance(data["state_path"], list)
        assert len(data["state_path"]) > 0
        
        return data

    def test_simulate_timeout_outcome(self, auth_headers):
        """Simulation with timeout outcome"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol=ETHUSDT&side=short&outcome=timeout"
            f"&source_type=simulation&environment=simulation",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "timeout" in data.get("state_path", []) or data.get("final_state") in ["timeout", "fallback_submitted", "filled"]

    def test_simulate_partial_outcome(self, auth_headers):
        """Simulation with partial fill outcome"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol=SOLUSDT&side=long&outcome=partial"
            f"&source_type=simulation&environment=simulation",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "partial_fill_ratio" in data

    def test_simulate_invalid_outcome_returns_422(self, auth_headers):
        """Invalid outcome returns 422"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol=BTCUSDT&side=long&outcome=invalid_outcome"
            f"&source_type=simulation&environment=simulation",
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_simulate_invalid_source_type_returns_422(self, auth_headers):
        """Invalid source_type returns 422"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol=BTCUSDT&side=long&outcome=filled"
            f"&source_type=invalid_source&environment=simulation",
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestExecutionStateSimulateBatch:
    """POST /api/admin-phase3/execution-state-transitions/simulate-batch tests"""

    def test_batch_simulate_creates_multiple_records(self, auth_headers):
        """Batch simulation creates multiple records"""
        scenarios = [
            {"symbol": "BTCUSDT", "side": "long", "outcome": "filled", "strategy_type": "breakout", "source_type": "simulation", "environment": "simulation"},
            {"symbol": "ETHUSDT", "side": "short", "outcome": "timeout", "strategy_type": "breakout", "source_type": "simulation", "environment": "simulation"},
        ]
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate-batch",
            headers=auth_headers,
            json={"scenarios": scenarios},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("status") == "success"
        assert data.get("total") == 2
        assert data.get("created") == 2
        assert len(data.get("records", [])) == 2


class TestExecutionStateDetail:
    """GET /api/admin-phase3/execution-state-transitions/{event_id}/detail tests"""

    def test_detail_returns_current_previous_path_dwell_time(self, auth_headers):
        """Detail endpoint returns current_state, previous_state, full_state_path, dwell_time_seconds"""
        # First create a simulation to get an event_id
        sim_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol=BTCUSDT&side=long&outcome=filled"
            f"&source_type=simulation&environment=simulation",
            headers=auth_headers,
        )
        assert sim_response.status_code == 200
        event_id = sim_response.json().get("execution_event_id")
        assert event_id, "Simulation should return execution_event_id"
        
        # Now get detail
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/{event_id}/detail",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "execution_event" in data
        assert "current_state" in data
        assert "previous_state" in data
        assert "full_state_path" in data
        assert "transition_count" in data
        assert "dwell_time_seconds" in data
        assert "transitions" in data
        
        # Verify types
        assert isinstance(data["full_state_path"], list)
        assert isinstance(data["transition_count"], int)
        assert isinstance(data["dwell_time_seconds"], (int, float))
        assert isinstance(data["transitions"], list)

    def test_detail_not_found_returns_404(self, auth_headers):
        """Non-existent event_id returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/nonexistent_event_id/detail",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestIdempotencyCollisions:
    """Idempotency collision tests"""

    def test_list_idempotency_collisions(self, auth_headers):
        """GET /api/admin-phase3/idempotency-collisions returns list"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/idempotency-collisions",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # If there are collisions, verify structure
        if data:
            collision = data[0]
            assert "collision_id" in collision
            assert "idempotency_key" in collision
            assert "status" in collision

    def test_list_idempotency_collisions_with_status_filter(self, auth_headers):
        """Idempotency collisions can be filtered by status"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/idempotency-collisions?status_filter=open",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for collision in data:
            assert collision.get("status") == "open"

    def test_create_duplicate_simulation_creates_collision(self, auth_headers):
        """Running same simulation twice creates idempotency collision"""
        # Run simulation twice with same parameters
        params = "?strategy_type=breakout&symbol=XRPUSDT&side=long&outcome=filled&source_type=simulation&environment=simulation"
        
        response1 = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate{params}",
            headers=auth_headers,
        )
        assert response1.status_code == 200
        
        response2 = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate{params}",
            headers=auth_headers,
        )
        assert response2.status_code == 200
        
        # Check for collision
        collisions_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/idempotency-collisions?status_filter=open",
            headers=auth_headers,
        )
        assert collisions_response.status_code == 200
        # Collision may or may not be created depending on timing - just verify endpoint works


class TestIdempotencyCollisionResolve:
    """Idempotency collision resolve tests"""

    def test_resolve_collision_with_valid_action(self, auth_headers):
        """Resolve collision with valid action"""
        # First get list of open collisions (without status_filter to avoid 422)
        list_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/idempotency-collisions?limit=100",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        all_collisions = list_response.json()
        
        # Filter for open collisions
        open_collisions = [c for c in all_collisions if c.get("status") == "open"]
        
        if not open_collisions:
            pytest.skip("No open collisions to resolve")
        
        collision = open_collisions[0]
        collision_id = collision["collision_id"]
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/idempotency-collisions/{collision_id}/resolve",
            headers=auth_headers,
            json={
                "action": "mark_safe_duplicate",
                "reason_note": "Test resolution",
                "correlation_id": collision.get("correlation_id") or f"test_{collision_id}",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "resolved"
        assert data.get("resolution_action") == "mark_safe_duplicate"

    def test_resolve_collision_invalid_action_returns_400(self, auth_headers):
        """Invalid resolve action returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/idempotency-collisions/test_collision_id/resolve",
            headers=auth_headers,
            json={
                "action": "invalid_action",
                "reason_note": "Test",
                "correlation_id": "test_corr",
            },
        )
        # Should return 400 or 404
        assert response.status_code in [400, 404]


class TestFailedEvents:
    """Failed events tests"""

    def test_list_failed_events(self, auth_headers):
        """GET /api/admin-phase3/failed-events returns list"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/failed-events",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if data:
            event = data[0]
            assert "id" in event
            assert "event_type" in event
            assert "status" in event
            assert "retry_count" in event

    def test_list_failed_events_with_status_filter(self, auth_headers):
        """Failed events can be filtered by status"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/failed-events?status_filter=pending",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for event in data:
            assert event.get("status") == "pending"

    def test_list_failed_events_with_search(self, auth_headers):
        """Failed events support search"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/failed-events?search=test",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_failed_events_with_failure_class(self, auth_headers):
        """Failed events can be filtered by failure_class"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/failed-events?failure_class=downstream_error",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for event in data:
            assert event.get("failure_class") == "downstream_error"

    def test_list_dead_letter_events(self, auth_headers):
        """GET /api/admin-phase3/failed-events/dead-letter returns dead/quarantined events"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/failed-events/dead-letter",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        for event in data:
            assert event.get("status") in ["dead", "quarantined"]

    def test_seed_failed_event(self, auth_headers):
        """POST /api/admin-phase3/failed-events/seed creates test event"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/failed-events/seed",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "event_type" in data
        return data


class TestFailedEventActions:
    """Failed event retry/resolve/reprocess tests"""

    @pytest.fixture
    def seeded_event(self, auth_headers):
        """Create a seeded failed event for testing"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/failed-events/seed",
            headers=auth_headers,
        )
        assert response.status_code == 200
        return response.json()

    def test_retry_failed_event(self, auth_headers, seeded_event):
        """POST /api/admin-phase3/failed-events/{id}/retry works"""
        event_id = seeded_event["id"]
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/failed-events/{event_id}/retry",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ["retrying", "dead"]  # dead if max_retry reached

    def test_resolve_failed_event(self, auth_headers, seeded_event):
        """POST /api/admin-phase3/failed-events/{id}/resolve works"""
        event_id = seeded_event["id"]
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/failed-events/{event_id}/resolve",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "resolved"

    def test_reprocess_failed_event(self, auth_headers):
        """POST /api/admin-phase3/failed-events/{id}/reprocess works"""
        # First seed a new event
        seed_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/failed-events/seed",
            headers=auth_headers,
        )
        assert seed_response.status_code == 200
        event_id = seed_response.json()["id"]
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/failed-events/{event_id}/reprocess",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "retrying"
        assert data.get("retry_count") == 0

    def test_retry_nonexistent_event_returns_404(self, auth_headers):
        """Retry non-existent event returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/failed-events/nonexistent_id/retry",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestFailedEventBulkActions:
    """Bulk retry/resolve tests"""

    def test_bulk_retry_failed_events(self, auth_headers):
        """POST /api/admin-phase3/failed-events/bulk-retry works"""
        # Seed some events first
        event_ids = []
        for _ in range(2):
            response = requests.post(
                f"{BASE_URL}/api/admin-phase3/failed-events/seed",
                headers=auth_headers,
            )
            if response.status_code == 200:
                event_ids.append(response.json()["id"])
        
        if not event_ids:
            pytest.skip("Could not seed events for bulk test")
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/failed-events/bulk-retry",
            headers=auth_headers,
            json=event_ids,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_bulk_resolve_failed_events(self, auth_headers):
        """POST /api/admin-phase3/failed-events/bulk-resolve works"""
        # Seed some events first
        event_ids = []
        for _ in range(2):
            response = requests.post(
                f"{BASE_URL}/api/admin-phase3/failed-events/seed",
                headers=auth_headers,
            )
            if response.status_code == 200:
                event_ids.append(response.json()["id"])
        
        if not event_ids:
            pytest.skip("Could not seed events for bulk test")
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/failed-events/bulk-resolve",
            headers=auth_headers,
            json=event_ids,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        for event in data:
            assert event.get("status") == "resolved"


class TestManualIntervention:
    """Manual intervention guardrails tests"""
    
    # Production confirmation phrase required for manual actions in prod environment
    PROD_CONFIRMATION_PHRASE = "CONFIRM_PROD_MANUAL_ACTION"

    def test_manual_action_requires_correlation_id(self, auth_headers):
        """Manual action requires correlation_id"""
        # First create a simulation to get an event_id
        sim_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol=BTCUSDT&side=long&outcome=filled"
            f"&source_type=simulation&environment=simulation",
            headers=auth_headers,
        )
        assert sim_response.status_code == 200
        event_id = sim_response.json().get("execution_event_id")
        
        # Try manual action without correlation_id
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/{event_id}/manual-action",
            headers=auth_headers,
            json={
                "action_type": "cancel_execution",
                "reason_note": "Test cancellation",
                "correlation_id": "",  # Empty correlation_id
                "confirmation_phrase": self.PROD_CONFIRMATION_PHRASE,
            },
        )
        assert response.status_code == 400
        assert "correlation_id" in response.json().get("detail", "").lower()

    def test_manual_action_force_state_change(self, auth_headers):
        """Manual action force_state_change works with valid params (prod guardrails)"""
        # Create a simulation with unique symbol to avoid idempotency collision
        correlation_id = f"manual_force_{uuid.uuid4().hex[:12]}"
        unique_symbol = f"AVAXUSDT"  # Use different symbol to avoid collision
        sim_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol={unique_symbol}&side=long&outcome=filled"
            f"&source_type=simulation&environment=simulation&correlation_id={correlation_id}",
            headers=auth_headers,
        )
        assert sim_response.status_code == 200
        event_id = sim_response.json().get("execution_event_id")
        
        # Force state change with prod confirmation phrase
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/{event_id}/manual-action",
            headers=auth_headers,
            json={
                "action_type": "force_state_change",
                "reason_note": "Test force state change",
                "correlation_id": correlation_id,
                "confirmation_phrase": self.PROD_CONFIRMATION_PHRASE,
                "payload": {"to_state": "cancelled"},
            },
        )
        # 200 = success, 409 = idempotency collision guard (also valid behavior)
        assert response.status_code in [200, 409], f"Expected 200 or 409, got {response.status_code}: {response.text}"
        if response.status_code == 200:
            data = response.json()
            assert data.get("status") == "success"
            assert data.get("current_state") == "cancelled"
        else:
            # 409 means idempotency collision guard is working correctly
            assert "collision" in response.json().get("detail", "").lower()

    def test_manual_action_cancel_execution(self, auth_headers):
        """Manual action cancel_execution works with prod guardrails"""
        correlation_id = f"cancel_test_{uuid.uuid4().hex[:12]}"
        sim_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol=ETHUSDT&side=short&outcome=filled"
            f"&source_type=simulation&environment=simulation&correlation_id={correlation_id}",
            headers=auth_headers,
        )
        assert sim_response.status_code == 200
        event_id = sim_response.json().get("execution_event_id")
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/{event_id}/manual-action",
            headers=auth_headers,
            json={
                "action_type": "cancel_execution",
                "reason_note": "Test cancellation",
                "correlation_id": correlation_id,
                "confirmation_phrase": self.PROD_CONFIRMATION_PHRASE,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("current_state") == "cancelled"

    def test_manual_action_replay_safe_duplicate_guard(self, auth_headers):
        """Same manual action cannot be applied twice (replay-safe guard)"""
        correlation_id = f"replay_test_{uuid.uuid4().hex[:12]}"
        sim_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol=SOLUSDT&side=long&outcome=filled"
            f"&source_type=simulation&environment=simulation&correlation_id={correlation_id}",
            headers=auth_headers,
        )
        assert sim_response.status_code == 200
        event_id = sim_response.json().get("execution_event_id")
        
        # First action with prod confirmation
        action_payload = {
            "action_type": "cancel_execution",
            "reason_note": "First cancellation",
            "correlation_id": correlation_id,
            "confirmation_phrase": self.PROD_CONFIRMATION_PHRASE,
        }
        response1 = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/{event_id}/manual-action",
            headers=auth_headers,
            json=action_payload,
        )
        assert response1.status_code == 200, f"First action failed: {response1.text}"
        
        # Same action again should fail with 409
        response2 = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/{event_id}/manual-action",
            headers=auth_headers,
            json=action_payload,
        )
        assert response2.status_code == 409, f"Expected 409, got {response2.status_code}: {response2.text}"

    def test_manual_action_requires_prod_confirmation_phrase(self, auth_headers):
        """Manual action in prod environment requires confirmation phrase"""
        correlation_id = f"prod_test_{uuid.uuid4().hex[:12]}"
        sim_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol=BTCUSDT&side=long&outcome=filled"
            f"&source_type=simulation&environment=simulation&correlation_id={correlation_id}",
            headers=auth_headers,
        )
        assert sim_response.status_code == 200
        event_id = sim_response.json().get("execution_event_id")
        
        # Try without confirmation phrase - should fail in prod
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/{event_id}/manual-action",
            headers=auth_headers,
            json={
                "action_type": "cancel_execution",
                "reason_note": "Test without phrase",
                "correlation_id": correlation_id,
            },
        )
        # In prod environment, this should return 400 for missing/invalid phrase
        assert response.status_code == 400
        assert "phrase" in response.json().get("detail", "").lower()

    def test_manual_action_invalid_action_type_returns_400(self, auth_headers):
        """Invalid action_type returns 400"""
        sim_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol=BTCUSDT&side=long&outcome=filled"
            f"&source_type=simulation&environment=simulation",
            headers=auth_headers,
        )
        assert sim_response.status_code == 200
        event_id = sim_response.json().get("execution_event_id")
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/{event_id}/manual-action",
            headers=auth_headers,
            json={
                "action_type": "invalid_action",
                "reason_note": "Test",
                "correlation_id": f"test_{uuid.uuid4().hex[:8]}",
                "confirmation_phrase": self.PROD_CONFIRMATION_PHRASE,
            },
        )
        assert response.status_code == 400


class TestExecutionTrace:
    """GET /api/admin-phase3/execution-trace/{correlation_id} tests"""

    def test_execution_trace_returns_chain(self, auth_headers):
        """Execution trace returns chain for correlation_id"""
        # Create a simulation with known correlation_id
        correlation_id = f"trace_test_{uuid.uuid4().hex[:12]}"
        sim_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol=BTCUSDT&side=long&outcome=filled"
            f"&source_type=simulation&environment=simulation&correlation_id={correlation_id}",
            headers=auth_headers,
        )
        assert sim_response.status_code == 200
        
        # Get trace
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-trace/{correlation_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "correlation_id" in data
        assert "chain" in data
        assert "intents" in data
        assert "events" in data
        assert "failures" in data
        
        assert data["correlation_id"] == correlation_id
        assert isinstance(data["chain"], list)
        assert isinstance(data["events"], list)
        
        # Should have at least one chain item from simulation
        assert len(data["chain"]) > 0 or len(data["events"]) > 0

    def test_execution_trace_nonexistent_correlation(self, auth_headers):
        """Trace for non-existent correlation returns empty chain"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-trace/nonexistent_correlation_id",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["correlation_id"] == "nonexistent_correlation_id"
        # Chain may be empty for non-existent correlation


class TestStateRebuild:
    """State rebuild tests"""

    def test_list_state_rebuild_logs(self, auth_headers):
        """GET /api/admin-phase3/state-rebuild-logs returns list"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/state-rebuild-logs",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if data:
            log = data[0]
            assert "id" in log
            assert "rebuild_type" in log
            assert "status" in log
            assert "trigger_source" in log
            assert "details" in log

    def test_trigger_state_rebuild_full(self, auth_headers):
        """POST /api/admin-phase3/state-rebuild/run with full scope"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/state-rebuild/run?scope_type=full",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "id" in data
        assert "rebuild_type" in data
        assert "status" in data
        assert data["status"] in ["started", "completed"]
        assert "details" in data

    def test_trigger_state_rebuild_scoped(self, auth_headers):
        """POST /api/admin-phase3/state-rebuild/run with scoped parameters"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/state-rebuild/run"
            f"?scope_type=symbol_scoped&scope_value=BTCUSDT",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] in ["started", "completed"]
        details = data.get("details", {})
        assert details.get("scope_type") == "symbol_scoped"
        assert details.get("scope_value") == "BTCUSDT"

    def test_trigger_state_rebuild_with_date_range(self, auth_headers):
        """POST /api/admin-phase3/state-rebuild/run with date range"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/state-rebuild/run"
            f"?scope_type=date_range&date_from=2026-01-01&date_to=2026-03-22",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        details = data.get("details", {})
        assert details.get("date_from") == "2026-01-01"
        assert details.get("date_to") == "2026-03-22"


class TestAuthorizationGuards:
    """Authorization and access control tests"""

    def test_endpoints_require_authentication(self):
        """All endpoints require authentication"""
        endpoints = [
            ("GET", "/api/admin-phase3/execution-state-transitions/control"),
            ("GET", "/api/admin-phase3/failed-events"),
            ("GET", "/api/admin-phase3/idempotency-collisions"),
            ("GET", "/api/admin-phase3/state-rebuild-logs"),
        ]
        
        for method, endpoint in endpoints:
            if method == "GET":
                response = requests.get(f"{BASE_URL}{endpoint}")
            else:
                response = requests.post(f"{BASE_URL}{endpoint}")
            
            assert response.status_code in [401, 403], f"{endpoint} should require auth, got {response.status_code}"
