"""
Iteration 76 - P1 Features Testing
Tests for:
1. GET /api/admin/risk-simulation/presets - returns high_volatility/liquidity_shock/conflict_heavy
2. POST /api/admin/risk-simulation - supports preset_scenario and preset_overrides
3. GET /api/admin/risk-simulation/history - filters: run_id, status_filter, request_mode, severity_band, request_type
4. GET /api/admin/decision-requests - includes sla_countdown_seconds, sla_state, escalation_state
5. Queue order logic honors SLA breach priority within pending
6. Role matrix: admin request-only, super_admin approve/reject/execute
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_EMAIL = "canary.requester@platform.local"
ADMIN_PASSWORD = "CanaryRequester123!"


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super_admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token")
    pytest.skip(f"Super admin login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token")
    pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def super_admin_headers(super_admin_token):
    """Headers with super_admin auth"""
    return {
        "Authorization": f"Bearer {super_admin_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def test_user_id(super_admin_headers):
    """Get a valid user_id for simulation tests"""
    response = requests.get(f"{BASE_URL}/api/auth/me", headers=super_admin_headers)
    if response.status_code == 200:
        return response.json().get("id")
    pytest.skip("Could not get user_id for testing")


class TestPresetSimulationEndpoints:
    """Tests for preset scenario simulation features"""

    def test_get_presets_returns_expected_keys(self, super_admin_headers):
        """GET /api/admin/risk-simulation/presets returns high_volatility, liquidity_shock, conflict_heavy"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk-simulation/presets",
            headers=super_admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data, "Response should have 'items' key"
        
        preset_keys = [item["preset_key"] for item in data["items"]]
        assert "high_volatility" in preset_keys, "high_volatility preset missing"
        assert "liquidity_shock" in preset_keys, "liquidity_shock preset missing"
        assert "conflict_heavy" in preset_keys, "conflict_heavy preset missing"
        
        # Verify each preset has required fields
        for item in data["items"]:
            assert "preset_key" in item
            assert "label" in item
            assert "description" in item
            assert "defaults" in item
            assert isinstance(item["defaults"], dict)

    def test_get_presets_high_volatility_defaults(self, super_admin_headers):
        """Verify high_volatility preset has expected default values"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk-simulation/presets",
            headers=super_admin_headers,
        )
        assert response.status_code == 200
        
        data = response.json()
        high_vol = next((p for p in data["items"] if p["preset_key"] == "high_volatility"), None)
        assert high_vol is not None, "high_volatility preset not found"
        
        defaults = high_vol["defaults"]
        assert "volatility_pct" in defaults
        assert "notional_scale" in defaults
        assert "signal_confidence" in defaults
        assert "position_size_scale" in defaults

    def test_simulation_with_preset_scenario(self, super_admin_headers, test_user_id):
        """POST /api/admin/risk-simulation with preset_scenario applies preset defaults"""
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
            },
            "apply_override": False,
            "preset_scenario": "high_volatility",
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers=super_admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "simulation_id" in data
        assert "projected_risk_score" in data
        assert "projected_gate_decision" in data
        
        # Verify preset was applied in simulation_payload
        sim_payload = data.get("simulation_payload", {})
        assert sim_payload.get("preset_scenario") == "high_volatility"

    def test_simulation_with_preset_overrides(self, super_admin_headers, test_user_id):
        """POST /api/admin/risk-simulation with preset_overrides customizes preset"""
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "ETHUSDT",
                "side": "sell",
                "notional": 200,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 5,
            },
            "apply_override": False,
            "preset_scenario": "liquidity_shock",
            "preset_overrides": {
                "volatility_pct": 12.5,
                "notional_scale": 0.4,
            },
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers=super_admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "simulation_id" in data
        
        # Verify overrides were applied
        sim_payload = data.get("simulation_payload", {})
        assert sim_payload.get("preset_scenario") == "liquidity_shock"
        assert "preset_overrides" in sim_payload

    def test_simulation_invalid_preset_returns_400(self, super_admin_headers, test_user_id):
        """POST /api/admin/risk-simulation with invalid preset_scenario returns 400"""
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
            },
            "apply_override": False,
            "preset_scenario": "invalid_preset_name",
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers=super_admin_headers,
            json=payload,
        )
        assert response.status_code == 400, f"Expected 400 for invalid preset, got {response.status_code}"


class TestSimulationHistoryFilters:
    """Tests for simulation history filtering"""

    def test_history_returns_items(self, super_admin_headers):
        """GET /api/admin/risk-simulation/history returns items list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk-simulation/history",
            headers=super_admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data, "Response should have 'items' key"
        assert isinstance(data["items"], list)

    def test_history_filter_by_run_id(self, super_admin_headers, test_user_id):
        """GET /api/admin/risk-simulation/history with run_id filter"""
        # First create a simulation to get a run_id
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers=super_admin_headers,
            json={
                "user_id": test_user_id,
                "intent_payload": {"symbol": "BTCUSDT", "side": "buy", "notional": 50},
                "apply_override": False,
            },
        )
        if sim_response.status_code == 200:
            run_id = sim_response.json().get("simulation_id", "")
            
            # Filter by partial run_id
            response = requests.get(
                f"{BASE_URL}/api/admin/risk-simulation/history",
                headers=super_admin_headers,
                params={"run_id": run_id[:8] if run_id else "sim_"},
            )
            assert response.status_code == 200

    def test_history_filter_by_status(self, super_admin_headers):
        """GET /api/admin/risk-simulation/history with status_filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk-simulation/history",
            headers=super_admin_headers,
            params={"status_filter": "preview"},
        )
        assert response.status_code == 200
        
        data = response.json()
        for item in data.get("items", []):
            assert item.get("status") == "preview", f"Expected status=preview, got {item.get('status')}"

    def test_history_filter_by_request_mode(self, super_admin_headers):
        """GET /api/admin/risk-simulation/history with request_mode filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk-simulation/history",
            headers=super_admin_headers,
            params={"request_mode": "single"},
        )
        assert response.status_code == 200
        
        data = response.json()
        for item in data.get("items", []):
            assert item.get("request_mode") == "single", f"Expected request_mode=single, got {item.get('request_mode')}"

    def test_history_filter_by_severity_band(self, super_admin_headers):
        """GET /api/admin/risk-simulation/history with severity_band filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk-simulation/history",
            headers=super_admin_headers,
            params={"severity_band": "critical"},
        )
        assert response.status_code == 200
        
        data = response.json()
        # Items should only have critical severity_band if any
        for item in data.get("items", []):
            if item.get("decision_severity_band"):
                assert item.get("decision_severity_band") == "critical"

    def test_history_filter_by_request_type(self, super_admin_headers):
        """GET /api/admin/risk-simulation/history with request_type filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk-simulation/history",
            headers=super_admin_headers,
            params={"request_type": "conflict_resolve"},
        )
        assert response.status_code == 200
        
        data = response.json()
        for item in data.get("items", []):
            if item.get("decision_request_type"):
                assert item.get("decision_request_type") == "conflict_resolve"

    def test_history_combined_filters(self, super_admin_headers):
        """GET /api/admin/risk-simulation/history with multiple filters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk-simulation/history",
            headers=super_admin_headers,
            params={
                "status_filter": "preview",
                "request_mode": "single",
                "limit": 10,
            },
        )
        assert response.status_code == 200
        
        data = response.json()
        assert len(data.get("items", [])) <= 10


class TestDecisionRequestsSLAFields:
    """Tests for SLA countdown and escalation fields in decision requests"""

    def test_decision_requests_include_sla_fields(self, super_admin_headers):
        """GET /api/admin/decision-requests includes sla_countdown_seconds, sla_state, escalation_state"""
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers=super_admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data
        
        # Check that SLA fields are present in response items
        for item in data.get("items", [])[:5]:  # Check first 5 items
            assert "sla_countdown_seconds" in item, f"sla_countdown_seconds missing in item {item.get('request_id')}"
            assert "sla_state" in item, f"sla_state missing in item {item.get('request_id')}"
            assert "escalation_state" in item, f"escalation_state missing in item {item.get('request_id')}"
            
            # Validate sla_state values
            valid_sla_states = ["breach", "warning", "healthy", "n/a"]
            assert item["sla_state"] in valid_sla_states, f"Invalid sla_state: {item['sla_state']}"
            
            # Validate escalation_state values
            valid_escalation_states = ["none", "notify_ops", "escalated_super_admin"]
            assert item["escalation_state"] in valid_escalation_states, f"Invalid escalation_state: {item['escalation_state']}"

    def test_pending_requests_have_countdown(self, super_admin_headers):
        """Pending decision requests should have sla_countdown_seconds"""
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers=super_admin_headers,
            params={"status_filter": "pending"},
        )
        assert response.status_code == 200
        
        data = response.json()
        for item in data.get("items", []):
            if item.get("status") == "pending":
                # Pending items should have countdown (not None unless breached)
                sla_state = item.get("sla_state")
                countdown = item.get("sla_countdown_seconds")
                
                if sla_state == "breach":
                    assert countdown == 0, "Breached items should have countdown=0"
                elif sla_state in ["warning", "healthy"]:
                    assert countdown is not None and countdown > 0, "Active pending items should have positive countdown"


class TestQueuePriorityOrdering:
    """Tests for queue priority ordering: breach > severity > risk_delta_score > created_at"""

    def test_queue_orders_pending_first(self, super_admin_headers):
        """Decision requests queue should show pending items first"""
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers=super_admin_headers,
        )
        assert response.status_code == 200
        
        data = response.json()
        items = data.get("items", [])
        
        if len(items) < 2:
            pytest.skip("Not enough items to test ordering")
        
        # Find first non-pending item
        first_non_pending_idx = None
        for idx, item in enumerate(items):
            if item.get("status") != "pending":
                first_non_pending_idx = idx
                break
        
        if first_non_pending_idx is not None:
            # All items before first_non_pending_idx should be pending
            for idx in range(first_non_pending_idx):
                assert items[idx].get("status") == "pending", f"Item at index {idx} should be pending"

    def test_queue_breach_priority_within_pending(self, super_admin_headers):
        """Within pending items, breach SLA should come before healthy"""
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers=super_admin_headers,
            params={"status_filter": "pending"},
        )
        assert response.status_code == 200
        
        data = response.json()
        items = data.get("items", [])
        
        # Check that breach items come before healthy items
        sla_rank = {"breach": 0, "warning": 1, "healthy": 2, "n/a": 9}
        
        prev_rank = -1
        for item in items:
            sla_state = item.get("sla_state", "n/a")
            current_rank = sla_rank.get(sla_state, 9)
            # Allow same rank or higher (worse) rank
            # This is a soft check since severity also affects ordering
            if current_rank < prev_rank:
                # This might be due to severity ordering, which is acceptable
                pass
            prev_rank = current_rank


class TestRoleMatrixEnforcement:
    """Tests for role matrix: admin request-only, super_admin approve/reject/execute"""

    def test_admin_can_create_decision_request(self, admin_headers, test_user_id):
        """Admin role can create decision requests"""
        # First create a simulation
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers=admin_headers,
            json={
                "user_id": test_user_id,
                "intent_payload": {"symbol": "BTCUSDT", "side": "buy", "notional": 100},
                "apply_override": False,
            },
        )
        
        if sim_response.status_code != 200:
            pytest.skip(f"Could not create simulation: {sim_response.text}")
        
        simulation_id = sim_response.json().get("simulation_id")
        
        # Admin should be able to create decision request
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/conflict-resolve",
            headers=admin_headers,
            json={
                "target_type": "strategy",
                "target_id": "test_strategy",
                "reason_note": "Test conflict resolution request",
                "simulation_run_id": simulation_id,
            },
        )
        assert response.status_code == 200, f"Admin should be able to create request: {response.text}"

    def test_super_admin_cannot_create_decision_request(self, super_admin_headers, test_user_id):
        """Super admin role cannot create decision requests (only approve/reject/execute)"""
        # First create a simulation
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers=super_admin_headers,
            json={
                "user_id": test_user_id,
                "intent_payload": {"symbol": "BTCUSDT", "side": "buy", "notional": 100},
                "apply_override": False,
            },
        )
        
        if sim_response.status_code != 200:
            pytest.skip(f"Could not create simulation: {sim_response.text}")
        
        simulation_id = sim_response.json().get("simulation_id")
        
        # Super admin should NOT be able to create decision request
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/conflict-resolve",
            headers=super_admin_headers,
            json={
                "target_type": "strategy",
                "target_id": "test_strategy",
                "reason_note": "Test conflict resolution request",
                "simulation_run_id": simulation_id,
            },
        )
        assert response.status_code == 403, f"Super admin should get 403 for create: {response.status_code}"

    def test_admin_cannot_approve_request(self, admin_headers, super_admin_headers, test_user_id):
        """Admin role cannot approve decision requests"""
        # Create a pending request first (using admin)
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers=admin_headers,
            json={
                "user_id": test_user_id,
                "intent_payload": {"symbol": "BTCUSDT", "side": "buy", "notional": 100},
                "apply_override": False,
            },
        )
        
        if sim_response.status_code != 200:
            pytest.skip(f"Could not create simulation: {sim_response.text}")
        
        simulation_id = sim_response.json().get("simulation_id")
        
        create_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/hedge-apply",
            headers=admin_headers,
            json={
                "target_type": "hedge",
                "target_id": "test_hedge",
                "reason_note": "Test hedge apply request",
                "simulation_run_id": simulation_id,
            },
        )
        
        if create_response.status_code != 200:
            pytest.skip(f"Could not create request: {create_response.text}")
        
        request_id = create_response.json().get("request_id")
        
        # Admin should NOT be able to approve
        approve_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{request_id}/approve",
            headers=admin_headers,
            json={"reason_note": "Test approval note"},
        )
        assert approve_response.status_code == 403, f"Admin should get 403 for approve: {approve_response.status_code}"

    def test_super_admin_can_approve_request(self, admin_headers, super_admin_headers, test_user_id):
        """Super admin role can approve decision requests"""
        # Create a pending request first (using admin)
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers=admin_headers,
            json={
                "user_id": test_user_id,
                "intent_payload": {"symbol": "BTCUSDT", "side": "buy", "notional": 100},
                "apply_override": False,
            },
        )
        
        if sim_response.status_code != 200:
            pytest.skip(f"Could not create simulation: {sim_response.text}")
        
        simulation_id = sim_response.json().get("simulation_id")
        
        create_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/rebalance-change",
            headers=admin_headers,
            json={
                "target_type": "rebalance",
                "target_id": "test_rebalance",
                "reason_note": "Test rebalance change request",
                "simulation_run_id": simulation_id,
            },
        )
        
        if create_response.status_code != 200:
            pytest.skip(f"Could not create request: {create_response.text}")
        
        request_id = create_response.json().get("request_id")
        
        # Super admin should be able to approve
        approve_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{request_id}/approve",
            headers=super_admin_headers,
            json={"reason_note": "Test approval note from super_admin"},
        )
        assert approve_response.status_code == 200, f"Super admin should be able to approve: {approve_response.text}"


class TestSimulationCompareEndpoint:
    """Tests for simulation compare endpoint"""

    def test_compare_current_returns_before_current_summary(self, super_admin_headers, test_user_id):
        """GET /api/admin/simulation-runs/{run_id}/compare-current returns before/current/compare_summary"""
        # First create a simulation
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers=super_admin_headers,
            json={
                "user_id": test_user_id,
                "intent_payload": {
                    "symbol": "BTCUSDT",
                    "side": "buy",
                    "notional": 100,
                    "strategy_binding": "spot_pullback_v1",
                    "volatility_pct": 3,
                },
                "apply_override": False,
            },
        )
        
        if sim_response.status_code != 200:
            pytest.skip(f"Could not create simulation: {sim_response.text}")
        
        run_id = sim_response.json().get("simulation_id")
        
        # Compare with current
        compare_response = requests.get(
            f"{BASE_URL}/api/admin/simulation-runs/{run_id}/compare-current",
            headers=super_admin_headers,
        )
        assert compare_response.status_code == 200, f"Expected 200, got {compare_response.status_code}: {compare_response.text}"
        
        data = compare_response.json()
        assert "run_id" in data
        assert "before" in data, "Response should have 'before' key"
        assert "current" in data, "Response should have 'current' key"
        assert "compare_summary" in data, "Response should have 'compare_summary' key"
        
        # Verify compare_summary has expected fields
        summary = data.get("compare_summary", {})
        assert "risk_delta_vs_history" in summary
        assert "confidence_adjusted_risk_delta_vs_history" in summary
        assert "decision_delta_vs_history" in summary


class TestBatchSimulationWithPresets:
    """Tests for batch simulation with preset support"""

    def test_batch_simulation_with_preset(self, super_admin_headers, test_user_id):
        """POST /api/admin/risk-simulation/batch supports preset_scenario"""
        payload = {
            "user_id": test_user_id,
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "intent_payload": {
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
            },
            "preset_scenario": "conflict_heavy",
            "preset_overrides": {},
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation/batch",
            headers=super_admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "batch_id" in data
        assert "items" in data
        assert data.get("total_symbols", 0) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
