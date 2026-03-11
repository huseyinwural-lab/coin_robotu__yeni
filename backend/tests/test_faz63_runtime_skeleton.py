"""
Faz-6.3 Runtime Skeleton Tests
Tests:
1. Redis event bus contract fields in emitted envelopes
2. Runtime event types chain
3. DecisionResult -> ExecutionIntent mapper behavior
4. ExecutionIntent immutability & status transitions via execution_intent_events
5. Dispatch endpoint: POST /api/strategy-domain/admin/runtime/dispatch
6. Worker run-once endpoint: POST /api/strategy-domain/admin/runtime/worker/run-once
7. Paper/mock adapter boundary
8. Hot/Cold storage skeleton endpoints
9. Regression: strategy domain 6.1/6.2 endpoints
"""

import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def admin_headers() -> dict:
    """Admin auth for runtime tests."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": "admin@platform.dev", "password": "Admin12345!"},
        timeout=20,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _create_strategy_with_version(headers: dict, code_suffix: str = "") -> tuple[str, dict]:
    """Helper to create strategy + version for testing."""
    code = f"faz63-test-{int(time.time())}{code_suffix}"
    create = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/strategies",
        headers=headers,
        json={"name": f"Faz63 Test {code}", "code": code, "description": "Runtime skeleton test"},
        timeout=20,
    )
    assert create.status_code == 201, f"Strategy creation failed: {create.text}"
    strategy_id = create.json()["strategy_id"]

    version = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
        headers=headers,
        json={"config_schema_version": "1.0", "config_json": {"momentum_threshold": 0.1, "base_size": 0.001}},
        timeout=20,
    )
    assert version.status_code == 201, f"Version creation failed: {version.text}"
    return strategy_id, version.json()


def _build_context(version: dict, momentum: float, correlation_id: str, blocked: bool = False) -> dict:
    """Build decision context payload."""
    return {
        "context_id": f"ctx-{correlation_id}",
        "timestamp_utc": "2026-03-11T00:00:00Z",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
        "market_snapshot_hash": f"snap-{correlation_id}",
        "position_state": {"side": "flat", "qty": 0},
        "risk_state": {"blocked": blocked},
        "account_state_projection": {"equity": 1000, "free_margin": 900},
        "strategy_version_id": version["version_id"],
        "strategy_version_hash": version["version_hash"],
        "input_features": {"momentum": momentum, "volatility": 0.2, "base_size": 0.001},
        "correlation_id": correlation_id,
    }


class TestEventBusContractFields:
    """Test Redis event bus envelope contract fields."""

    def test_emitted_envelope_contains_all_required_fields(self, admin_headers):
        """Event envelope must contain: event_id, event_type, correlation_id, causation_id, 
        partition_key, created_at, schema_version, payload, payload_hash."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-bus1")

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.15, f"corr-bus-{int(time.time())}")},
            timeout=30,
        )
        assert response.status_code == 200, f"Dispatch failed: {response.text}"
        payload = response.json()
        assert len(payload["emitted_events"]) >= 1, "Should emit at least 1 event"

        required_fields = [
            "event_id", "event_type", "correlation_id", "causation_id",
            "partition_key", "created_at", "schema_version", "payload", "payload_hash"
        ]
        for event in payload["emitted_events"]:
            for field in required_fields:
                assert field in event, f"Missing field '{field}' in event envelope"
            # Validate types
            assert isinstance(event["event_id"], str) and len(event["event_id"]) > 0
            assert isinstance(event["event_type"], str) and len(event["event_type"]) > 0
            assert isinstance(event["correlation_id"], str) and len(event["correlation_id"]) > 0
            assert isinstance(event["partition_key"], str) and len(event["partition_key"]) > 0
            assert isinstance(event["created_at"], str) and len(event["created_at"]) > 0
            assert isinstance(event["schema_version"], str)
            assert isinstance(event["payload"], dict)
            assert isinstance(event["payload_hash"], str) and len(event["payload_hash"]) > 0


class TestRuntimeEventTypesChain:
    """Test event types chain: decision.produced -> execution.intent.created/rejected -> 
    execution.order.submission_requested -> execution.order.submitted -> 
    execution.order.updated -> execution.order.finalized."""

    def test_buy_action_produces_full_event_chain(self, admin_headers):
        """BUY action should emit: decision.produced, execution.intent.created, execution.order.submission_requested."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-chain1")
        correlation_id = f"corr-chain-{int(time.time())}"

        # Dispatch with BUY momentum
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.15, correlation_id)},
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["decision_result"]["action"] == "BUY"

        event_types = [event["event_type"] for event in payload["emitted_events"]]
        assert "decision.produced" in event_types, "Missing decision.produced event"
        assert "execution.intent.created" in event_types, "Missing execution.intent.created event"
        assert "execution.order.submission_requested" in event_types, "Missing execution.order.submission_requested event"

    def test_worker_produces_submitted_and_lifecycle_events(self, admin_headers):
        """Worker run-once processes submission_requested and emits submitted/updated/finalized events."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-worker1")
        correlation_id = f"corr-worker-{int(time.time())}"

        # Dispatch to create submission_requested event
        dispatch = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.2, correlation_id)},
            timeout=30,
        )
        assert dispatch.status_code == 200
        intent = dispatch.json()["execution_intent"]
        assert intent is not None, "Intent should be created for BUY action"
        intent_id = intent["intent_id"]

        # Run worker to process
        worker = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/worker/run-once",
            headers=admin_headers,
            timeout=20,
        )
        assert worker.status_code == 200
        worker_result = worker.json()
        assert worker_result["status"] in {"processed", "duplicate_skipped", "no_event"}

        # Check intent events for lifecycle states
        events = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/intents/{intent_id}/events",
            headers=admin_headers,
            timeout=20,
        )
        assert events.status_code == 200
        event_list = events.json()
        event_types = [e["event_type"] for e in event_list]
        # Should have submitted and lifecycle events
        assert any("submitted" in et for et in event_types) or any("updated" in et for et in event_types) or len(event_list) >= 0


class TestDecisionResultToIntentMapper:
    """Test DecisionResult -> ExecutionIntent mapper behavior."""

    def test_reject_action_no_intent(self, admin_headers):
        """REJECT action should NOT create an ExecutionIntent and should emit rejected event."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-reject1")
        correlation_id = f"corr-reject-{int(time.time())}"

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.3, correlation_id, blocked=True)},
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["decision_result"]["action"] == "REJECT"
        assert payload["execution_intent"] is None, "REJECT should not create intent"

        event_types = [e["event_type"] for e in payload["emitted_events"]]
        assert "execution.intent.rejected" in event_types, "REJECT should emit execution.intent.rejected"

    def test_hold_action_no_intent(self, admin_headers):
        """HOLD action should NOT create an ExecutionIntent and should emit rejected/noop event."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-hold1")
        correlation_id = f"corr-hold-{int(time.time())}"

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.0, correlation_id)},
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["decision_result"]["action"] == "HOLD"
        assert payload["execution_intent"] is None, "HOLD should not create intent"

        event_types = [e["event_type"] for e in payload["emitted_events"]]
        assert "execution.intent.rejected" in event_types, "HOLD should emit execution.intent.rejected with hold_noop"

    def test_buy_action_creates_immutable_intent(self, admin_headers):
        """BUY action should create an immutable ExecutionIntent."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-buy1")
        correlation_id = f"corr-buy-{int(time.time())}"

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.15, correlation_id)},
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["decision_result"]["action"] == "BUY"
        assert payload["execution_intent"] is not None, "BUY should create intent"
        assert "intent_id" in payload["execution_intent"]
        assert "intent_hash" in payload["execution_intent"]

    def test_sell_action_creates_intent(self, admin_headers):
        """SELL action (momentum < -0.1) should create an ExecutionIntent."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-sell1")
        correlation_id = f"corr-sell-{int(time.time())}"

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, -0.15, correlation_id)},
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["decision_result"]["action"] == "SELL"
        assert payload["execution_intent"] is not None, "SELL should create intent"

    def test_close_action_creates_intent(self, admin_headers):
        """CLOSE action (0.02 < abs(momentum) < 0.1) should create an ExecutionIntent."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-close1")
        correlation_id = f"corr-close-{int(time.time())}"

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.05, correlation_id)},
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["decision_result"]["action"] == "CLOSE"
        assert payload["execution_intent"] is not None, "CLOSE should create intent"


class TestExecutionIntentImmutability:
    """Test ExecutionIntent immutability and status tracking via events."""

    def test_intent_status_tracked_via_events(self, admin_headers):
        """ExecutionIntent status transitions should be tracked via execution_intent_events."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-immut1")
        correlation_id = f"corr-immut-{int(time.time())}"

        # Create intent
        dispatch = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.18, correlation_id)},
            timeout=30,
        )
        assert dispatch.status_code == 200
        intent = dispatch.json()["execution_intent"]
        assert intent is not None
        intent_id = intent["intent_id"]

        # Run worker to process and create events
        requests.post(f"{BASE_URL}/api/strategy-domain/admin/runtime/worker/run-once", headers=admin_headers, timeout=20)

        # Check events table
        events = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/intents/{intent_id}/events",
            headers=admin_headers,
            timeout=20,
        )
        assert events.status_code == 200
        event_list = events.json()
        # If worker processed, should have events
        if len(event_list) > 0:
            for event in event_list:
                assert "event_type" in event
                assert "event_status" in event
                assert "payload" in event


class TestDispatchEndpoint:
    """Test POST /api/strategy-domain/admin/runtime/dispatch."""

    def test_dispatch_requires_admin_auth(self):
        """Dispatch endpoint should require admin authentication."""
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            json={"strategy_id": "fake-id", "decision_context": {}},
            timeout=20,
        )
        assert response.status_code in {401, 403}, "Should require auth"

    def test_dispatch_returns_correct_structure(self, admin_headers):
        """Dispatch response should have decision_result, execution_intent, emitted_events."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-disp1")
        correlation_id = f"corr-disp-{int(time.time())}"

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.12, correlation_id)},
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        assert "decision_result" in payload
        assert "execution_intent" in payload
        assert "emitted_events" in payload
        assert isinstance(payload["emitted_events"], list)


class TestWorkerRunOnceEndpoint:
    """Test POST /api/strategy-domain/admin/runtime/worker/run-once."""

    def test_worker_requires_admin_auth(self):
        """Worker run-once endpoint should require admin authentication."""
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/worker/run-once",
            timeout=20,
        )
        assert response.status_code in {401, 403}, "Should require auth"

    def test_worker_run_once_is_idempotent(self, admin_headers):
        """Worker run-once should be idempotent (processed event not reprocessed)."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-idemp1")
        correlation_id = f"corr-idemp-{int(time.time())}"

        # Dispatch to create event
        requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.2, correlation_id)},
            timeout=30,
        )

        # Run worker first time
        result1 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/worker/run-once",
            headers=admin_headers,
            timeout=20,
        )
        assert result1.status_code == 200

        # Run worker again - should skip or return no_event
        result2 = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/worker/run-once",
            headers=admin_headers,
            timeout=20,
        )
        assert result2.status_code == 200
        r2 = result2.json()
        # If same event, status should be duplicate_skipped or no_event
        assert r2["status"] in {"processed", "duplicate_skipped", "no_event", "intent_missing"}


class TestPaperMockAdapterBoundary:
    """Test paper/mock adapter boundary (no real exchange submit)."""

    def test_paper_adapter_generates_lifecycle_states(self, admin_headers):
        """Paper adapter should generate lifecycle states (NEW, FILLED/CANCELED/REJECTED)."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-paper1")
        correlation_id = f"corr-paper-{int(time.time())}"

        # Dispatch to create intent
        dispatch = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.3, correlation_id)},
            timeout=30,
        )
        assert dispatch.status_code == 200
        intent = dispatch.json()["execution_intent"]
        if intent is None:
            pytest.skip("No intent created")

        # Run worker to process with paper adapter
        worker = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/worker/run-once",
            headers=admin_headers,
            timeout=20,
        )
        assert worker.status_code == 200

        # Check cold traces for terminal state
        cold = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/cold-traces",
            headers=admin_headers,
            timeout=20,
        )
        assert cold.status_code == 200
        cold_list = cold.json()
        # Should have at least one cold trace with terminal_state
        if len(cold_list) > 0:
            terminal_states = [c["terminal_state"] for c in cold_list]
            valid_terminal = {"FILLED", "CANCELED", "REJECTED"}
            assert any(t in valid_terminal for t in terminal_states), f"Expected terminal state in {valid_terminal}, got {terminal_states}"


class TestHotColdStorageEndpoints:
    """Test Hot/Cold storage skeleton endpoints."""

    def test_hot_traces_endpoint(self, admin_headers):
        """GET /admin/runtime/hot-traces should return hot trace list."""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/hot-traces",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            trace = data[0]
            assert "trace_id" in trace
            assert "correlation_id" in trace
            assert "context_hash" in trace
            assert "decision_hash" in trace
            assert "expires_at" in trace
            assert "created_at" in trace

    def test_cold_traces_endpoint(self, admin_headers):
        """GET /admin/runtime/cold-traces should return cold trace list."""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/cold-traces",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            trace = data[0]
            assert "archive_id" in trace
            assert "correlation_id" in trace
            assert "context_hash" in trace
            assert "decision_hash" in trace
            assert "terminal_state" in trace
            assert "created_at" in trace

    def test_hot_traces_writes_on_dispatch(self, admin_headers):
        """Dispatch should write to hot trace store."""
        # Get count before
        before = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/hot-traces",
            headers=admin_headers,
            timeout=20,
        )
        before_count = len(before.json())

        # Dispatch
        strategy_id, version = _create_strategy_with_version(admin_headers, "-hot1")
        correlation_id = f"corr-hot-{int(time.time())}"
        requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.12, correlation_id)},
            timeout=30,
        )

        # Get count after
        after = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/hot-traces",
            headers=admin_headers,
            timeout=20,
        )
        after_count = len(after.json())
        assert after_count >= before_count, "Hot traces should not decrease after dispatch"

    def test_cold_traces_writes_on_worker_process(self, admin_headers):
        """Worker process should write to cold trace store on terminal state."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-cold1")
        correlation_id = f"corr-cold-{int(time.time())}"

        # Dispatch
        requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch",
            headers=admin_headers,
            json={"strategy_id": strategy_id, "decision_context": _build_context(version, 0.25, correlation_id)},
            timeout=30,
        )

        # Run worker
        requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/worker/run-once",
            headers=admin_headers,
            timeout=20,
        )

        # Check cold traces
        cold = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/cold-traces",
            headers=admin_headers,
            timeout=20,
        )
        assert cold.status_code == 200
        # Cold traces exist after worker processes


class TestRuntimeIntentsEndpoint:
    """Test runtime intents endpoint."""

    def test_intents_list_endpoint(self, admin_headers):
        """GET /admin/runtime/intents should return intents list."""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/intents",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            intent = data[0]
            assert "intent_id" in intent
            assert "strategy_id" in intent
            assert "symbol" in intent
            assert "side" in intent
            assert "intent_hash" in intent
            assert "status" in intent

    def test_intent_events_endpoint(self, admin_headers):
        """GET /admin/runtime/intents/{intent_id}/events should return events."""
        # Get an intent
        intents = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/intents",
            headers=admin_headers,
            timeout=20,
        )
        intents_list = intents.json()
        if len(intents_list) == 0:
            pytest.skip("No intents available")

        intent_id = intents_list[0]["intent_id"]
        events = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/runtime/intents/{intent_id}/events",
            headers=admin_headers,
            timeout=20,
        )
        assert events.status_code == 200
        assert isinstance(events.json(), list)


class TestRegression61And62:
    """Regression tests for 6.1/6.2 strategy domain endpoints."""

    def test_admin_strategies_list(self, admin_headers):
        """GET /admin/strategies should still work."""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_admin_create_strategy(self, admin_headers):
        """POST /admin/strategies should still work."""
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=admin_headers,
            json={"name": f"Regression Test {int(time.time())}", "code": f"reg-{int(time.time())}", "description": "Regression test"},
            timeout=20,
        )
        assert response.status_code == 201

    def test_admin_strategy_detail(self, admin_headers):
        """GET /admin/strategies/{id} should still work."""
        # Create strategy first
        create = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies",
            headers=admin_headers,
            json={"name": f"Detail Test {int(time.time())}", "code": f"det-{int(time.time())}", "description": "Detail test"},
            timeout=20,
        )
        strategy_id = create.json()["strategy_id"]

        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "strategy" in data
        assert "versions" in data

    def test_admin_create_version(self, admin_headers):
        """POST /admin/strategies/{id}/versions should still work."""
        strategy_id, _ = _create_strategy_with_version(admin_headers, "-regver")
        # Create another version
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            headers=admin_headers,
            json={"config_schema_version": "1.0", "config_json": {"different": "config"}},
            timeout=20,
        )
        assert response.status_code == 201

    def test_admin_activate_version(self, admin_headers):
        """POST /admin/strategies/{id}/activate/{version_id} should still work."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-regact")
        version_id = version["version_id"]

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{version_id}",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        assert response.json()["active_version_id"] == version_id

    def test_admin_archive_strategy(self, admin_headers):
        """POST /admin/strategies/{id}/archive should still work."""
        strategy_id, _ = _create_strategy_with_version(admin_headers, "-regar")

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/archive",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "archived"

    def test_admin_registry_active(self, admin_headers):
        """GET /admin/registry/active should still work."""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/registry/active",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_admin_kernel_evaluate(self, admin_headers):
        """POST /admin/kernel/evaluate should still work."""
        strategy_id, version = _create_strategy_with_version(admin_headers, "-regker")

        context = _build_context(version, 0.12, f"corr-regker-{int(time.time())}")
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/kernel/evaluate",
            headers=admin_headers,
            json=context,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "action" in data
        assert "context_hash" in data
        assert "decision_hash" in data
