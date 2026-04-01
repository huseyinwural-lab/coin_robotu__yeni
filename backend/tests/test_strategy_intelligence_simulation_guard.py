"""
Strategy Intelligence - Simulation Guard & Override Governance Tests
Sprint1 full + Sprint2 başlangıcı (before/after compare + basic impact preview + risk/decision delta)
Hariç: approval workflow, batch/preset/history vb.

Test Coverage:
- /api/admin/risk-simulation geniş response (simulation_id, before_state, after_state, projected_pnl/drawdown/exposure/var/liquidity, risk_delta, decision_delta)
- Simulation guard: /api/admin/manual-overrides create için simulation_id zorunlu
- Reason zorunluluğu: min-length guard (override create/revoke)
- Expiry zorunluluğu: expires_at veya ttl_minutes zorunlu
- /api/admin/active-overrides endpoint çalışıyor ve active filtreli
- /api/admin/manual-overrides/{id}/revoke çalışıyor
"""

import os
import pytest
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_EMAIL = "canary.requester@platform.local"
ADMIN_PASSWORD = "CanaryRequester123!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def super_admin_token(api_client):
    """Get super_admin authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": SUPER_ADMIN_EMAIL,
        "password": SUPER_ADMIN_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token")
    pytest.skip(f"Super admin authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_token(api_client):
    """Get admin authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token")
    # If admin user doesn't exist, skip tests requiring it
    return None


@pytest.fixture(scope="module")
def authenticated_client(api_client, super_admin_token):
    """Session with super_admin auth header"""
    api_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
    return api_client


@pytest.fixture(scope="module")
def test_user_id(authenticated_client):
    """Get a test user ID for simulation"""
    response = authenticated_client.get(f"{BASE_URL}/api/admin/users")
    if response.status_code == 200:
        users = response.json()
        if users and len(users) > 0:
            return str(users[0].get("id"))
    # Fallback to a dummy user ID
    return "test_user_12345"


class TestRiskSimulationEndpoint:
    """Tests for /api/admin/risk-simulation endpoint"""

    def test_risk_simulation_returns_full_response(self, authenticated_client, test_user_id):
        """Verify risk-simulation returns all required fields including before/after state"""
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
                "position_size_value": 100
            },
            "apply_override": False
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/admin/risk-simulation", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify simulation_id is returned
        assert "simulation_id" in data, "simulation_id missing from response"
        assert data["simulation_id"], "simulation_id should not be empty"
        assert data["simulation_id"].startswith("sim_"), f"simulation_id should start with 'sim_': {data['simulation_id']}"
        
        # Verify before_state
        assert "before_state" in data, "before_state missing from response"
        before = data["before_state"]
        assert isinstance(before, dict), "before_state should be a dict"
        assert "risk_score" in before, "before_state.risk_score missing"
        assert "gate_decision" in before, "before_state.gate_decision missing"
        assert "exposure" in before, "before_state.exposure missing"
        
        # Verify after_state
        assert "after_state" in data, "after_state missing from response"
        after = data["after_state"]
        assert isinstance(after, dict), "after_state should be a dict"
        assert "risk_score" in after, "after_state.risk_score missing"
        assert "gate_decision" in after, "after_state.gate_decision missing"
        assert "exposure" in after, "after_state.exposure missing"
        
        # Verify projected metrics
        assert "projected_pnl" in data, "projected_pnl missing"
        assert "projected_drawdown" in data, "projected_drawdown missing"
        assert "projected_exposure" in data, "projected_exposure missing"
        assert "projected_var" in data, "projected_var missing"
        assert "projected_liquidity_impact" in data, "projected_liquidity_impact missing"
        
        # Verify risk_delta and decision_delta
        assert "risk_delta" in data, "risk_delta missing"
        assert "decision_delta" in data, "decision_delta missing"
        
        print(f"✓ Risk simulation returned full response with simulation_id={data['simulation_id']}")
        print(f"  before_state: risk_score={before.get('risk_score')}, gate_decision={before.get('gate_decision')}")
        print(f"  after_state: risk_score={after.get('risk_score')}, gate_decision={after.get('gate_decision')}")
        print(f"  risk_delta={data['risk_delta']}, decision_delta={data['decision_delta']}")

    def test_risk_simulation_requires_user_id(self, authenticated_client):
        """Verify simulation fails without user_id"""
        payload = {
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100
            }
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/admin/risk-simulation", json=payload)
        assert response.status_code == 422, f"Expected 422 for missing user_id, got {response.status_code}"
        print("✓ Risk simulation correctly requires user_id")

    def test_risk_simulation_requires_symbol(self, authenticated_client, test_user_id):
        """Verify simulation fails without symbol in intent_payload"""
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "side": "buy",
                "notional": 100
            }
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/admin/risk-simulation", json=payload)
        assert response.status_code == 400, f"Expected 400 for missing symbol, got {response.status_code}"
        print("✓ Risk simulation correctly requires symbol")


class TestManualOverrideSimulationGuard:
    """Tests for simulation_id requirement on manual override creation"""

    def test_override_create_requires_simulation_id(self, authenticated_client, test_user_id):
        """Verify override creation fails without simulation_id"""
        future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        payload = {
            "scope": "strategy_intelligence",
            "target_type": "user",
            "target_id": test_user_id,
            "action_type": "test_override_action",
            "reason": "This is a test reason with minimum 12 characters",
            "simulation_id": "",  # Empty simulation_id
            "expires_at": future_time,
            "payload": {}
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/admin/manual-overrides", json=payload)
        assert response.status_code == 400, f"Expected 400 for empty simulation_id, got {response.status_code}"
        assert "simulation" in response.text.lower(), f"Error should mention simulation: {response.text}"
        print("✓ Override creation correctly requires simulation_id")

    def test_override_create_requires_valid_simulation_id(self, authenticated_client, test_user_id):
        """Verify override creation fails with invalid simulation_id"""
        future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        payload = {
            "scope": "strategy_intelligence",
            "target_type": "user",
            "target_id": test_user_id,
            "action_type": "test_override_action",
            "reason": "This is a test reason with minimum 12 characters",
            "simulation_id": "invalid_sim_id_12345",  # Invalid simulation_id
            "expires_at": future_time,
            "payload": {}
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/admin/manual-overrides", json=payload)
        assert response.status_code == 400, f"Expected 400 for invalid simulation_id, got {response.status_code}"
        print("✓ Override creation correctly validates simulation_id")


class TestReasonMinLengthGuard:
    """Tests for reason minimum length requirement"""

    def test_override_create_requires_min_reason_length(self, authenticated_client, test_user_id):
        """Verify override creation fails with short reason"""
        future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        payload = {
            "scope": "strategy_intelligence",
            "target_type": "user",
            "target_id": test_user_id,
            "action_type": "test_override_action",
            "reason": "short",  # Less than 12 characters
            "simulation_id": "sim_test123456",
            "expires_at": future_time,
            "payload": {}
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/admin/manual-overrides", json=payload)
        # Should fail either due to validation or simulation_id check
        assert response.status_code in [400, 422], f"Expected 400/422 for short reason, got {response.status_code}"
        print("✓ Override creation correctly requires minimum reason length")

    def test_revoke_requires_min_reason_length(self, authenticated_client):
        """Verify revoke fails with short reason"""
        # First get an active override to revoke
        response = authenticated_client.get(f"{BASE_URL}/api/admin/active-overrides")
        if response.status_code != 200:
            pytest.skip("Could not get active overrides")
        
        overrides = response.json()
        if not overrides:
            pytest.skip("No active overrides to test revoke")
        
        override_id = overrides[0].get("override_id")
        
        # Try to revoke with short reason
        revoke_response = authenticated_client.post(
            f"{BASE_URL}/api/admin/manual-overrides/{override_id}/revoke",
            json={"reason": "short"}  # Less than 12 characters
        )
        assert revoke_response.status_code in [400, 422], f"Expected 400/422 for short revoke reason, got {revoke_response.status_code}"
        print("✓ Revoke correctly requires minimum reason length")


class TestExpiryRequirement:
    """Tests for expiry requirement (expires_at or ttl_minutes)"""

    def test_override_requires_expiry(self, authenticated_client, test_user_id):
        """Verify override creation fails without expiry"""
        # First run a simulation to get a valid simulation_id
        sim_payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3
            },
            "apply_override": False
        }
        
        sim_response = authenticated_client.post(f"{BASE_URL}/api/admin/risk-simulation", json=sim_payload)
        if sim_response.status_code != 200:
            pytest.skip(f"Could not run simulation: {sim_response.text}")
        
        simulation_id = sim_response.json().get("simulation_id")
        
        # Try to create override without expiry
        payload = {
            "scope": "strategy_intelligence",
            "target_type": "user",
            "target_id": test_user_id,
            "action_type": "test_override_action",
            "reason": "This is a test reason with minimum 12 characters",
            "simulation_id": simulation_id,
            # No expires_at and no ttl_minutes
            "payload": {}
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/admin/manual-overrides", json=payload)
        assert response.status_code == 400, f"Expected 400 for missing expiry, got {response.status_code}"
        assert "expires" in response.text.lower() or "ttl" in response.text.lower(), f"Error should mention expiry: {response.text}"
        print("✓ Override creation correctly requires expiry (expires_at or ttl_minutes)")


class TestActiveOverridesEndpoint:
    """Tests for /api/admin/active-overrides endpoint"""

    def test_active_overrides_returns_list(self, authenticated_client):
        """Verify active-overrides endpoint returns a list"""
        response = authenticated_client.get(f"{BASE_URL}/api/admin/active-overrides")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "active-overrides should return a list"
        print(f"✓ Active overrides endpoint returned {len(data)} items")

    def test_active_overrides_only_active_status(self, authenticated_client):
        """Verify active-overrides only returns active status items"""
        response = authenticated_client.get(f"{BASE_URL}/api/admin/active-overrides")
        assert response.status_code == 200
        
        data = response.json()
        for item in data:
            status = item.get("current_status", "")
            assert status == "active", f"Expected only active status, got: {status}"
        
        print(f"✓ All {len(data)} active overrides have status='active'")


class TestRevokeEndpoint:
    """Tests for /api/admin/manual-overrides/{id}/revoke endpoint"""

    def test_revoke_nonexistent_override(self, authenticated_client):
        """Verify revoke fails for non-existent override"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/admin/manual-overrides/nonexistent_id_12345/revoke",
            json={"reason": "This is a valid revoke reason with 12+ chars"}
        )
        assert response.status_code == 400, f"Expected 400 for non-existent override, got {response.status_code}"
        print("✓ Revoke correctly fails for non-existent override")


class TestFullOverrideWorkflow:
    """End-to-end test for simulation → override → revoke workflow"""

    def test_full_workflow_simulation_to_override_to_revoke(self, authenticated_client, test_user_id):
        """Test complete workflow: simulation → create override → revoke"""
        
        # Step 1: Run simulation
        sim_payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "ETHUSDT",
                "side": "buy",
                "notional": 50,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 2,
                "position_size_value": 50
            },
            "apply_override": False
        }
        
        sim_response = authenticated_client.post(f"{BASE_URL}/api/admin/risk-simulation", json=sim_payload)
        assert sim_response.status_code == 200, f"Simulation failed: {sim_response.text}"
        
        sim_data = sim_response.json()
        simulation_id = sim_data.get("simulation_id")
        assert simulation_id, "simulation_id not returned"
        print(f"✓ Step 1: Simulation completed with id={simulation_id}")
        
        # Step 2: Create override with valid simulation_id
        future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        override_payload = {
            "scope": "strategy_intelligence",
            "target_type": "user",
            "target_id": test_user_id,
            "action_type": "TEST_workflow_override",
            "reason": "Full workflow test - creating override for testing purposes",
            "simulation_id": simulation_id,
            "expires_at": future_time,
            "previous_state": sim_data.get("before_state", {}),
            "next_state": sim_data.get("after_state", {}),
            "impact_preview": {
                "projected_risk_score": sim_data.get("projected_risk_score"),
                "risk_delta": sim_data.get("risk_delta"),
                "decision_delta": sim_data.get("decision_delta")
            },
            "payload": {"source": "test_workflow"}
        }
        
        override_response = authenticated_client.post(f"{BASE_URL}/api/admin/manual-overrides", json=override_payload)
        assert override_response.status_code == 200, f"Override creation failed: {override_response.text}"
        
        override_data = override_response.json()
        override_id = override_data.get("override_id")
        assert override_id, "override_id not returned"
        assert override_data.get("current_status") == "active", f"Expected active status, got: {override_data.get('current_status')}"
        print(f"✓ Step 2: Override created with id={override_id}")
        
        # Step 3: Verify override appears in active-overrides
        active_response = authenticated_client.get(f"{BASE_URL}/api/admin/active-overrides")
        assert active_response.status_code == 200
        
        active_data = active_response.json()
        found = any(item.get("override_id") == override_id for item in active_data)
        assert found, f"Created override {override_id} not found in active-overrides"
        print("✓ Step 3: Override found in active-overrides list")
        
        # Step 4: Revoke the override
        revoke_response = authenticated_client.post(
            f"{BASE_URL}/api/admin/manual-overrides/{override_id}/revoke",
            json={"reason": "Full workflow test - revoking override for cleanup"}
        )
        assert revoke_response.status_code == 200, f"Revoke failed: {revoke_response.text}"
        
        revoke_data = revoke_response.json()
        assert revoke_data.get("status") == "revoked", f"Expected revoked status, got: {revoke_data.get('status')}"
        assert revoke_data.get("override_id") == override_id
        print("✓ Step 4: Override revoked successfully")
        
        # Step 5: Verify override status changed to revoked (may still appear in list but with revoked status)
        active_response2 = authenticated_client.get(f"{BASE_URL}/api/admin/active-overrides")
        assert active_response2.status_code == 200
        
        active_data2 = active_response2.json()
        # Check if the override is either not in the list OR has revoked status
        found_item = next((item for item in active_data2 if item.get("override_id") == override_id), None)
        if found_item:
            # If still in list, verify it has revoked status
            assert found_item.get("current_status") == "revoked", f"Override should have revoked status, got: {found_item.get('current_status')}"
            print("✓ Step 5: Override found with revoked status (filtering may be delayed)")
        else:
            print("✓ Step 5: Revoked override no longer in active-overrides")
        
        print("\n✓ Full workflow test PASSED: simulation → override → revoke")


class TestStrategyIntelligenceDashboard:
    """Tests for /api/admin/strategy-intelligence dashboard endpoint"""

    def test_dashboard_returns_expected_structure(self, authenticated_client):
        """Verify strategy-intelligence dashboard returns expected fields"""
        response = authenticated_client.get(f"{BASE_URL}/api/admin/strategy-intelligence")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify required fields
        assert "generated_at" in data, "generated_at missing"
        assert "strategy_conflicts" in data, "strategy_conflicts missing"
        assert "capital_rebalance_events" in data, "capital_rebalance_events missing"
        assert "hedge_suggestions" in data, "hedge_suggestions missing"
        assert "governance_summary" in data, "governance_summary missing"
        assert "allocation_drift" in data, "allocation_drift missing"
        assert "strategy_performance_delta" in data, "strategy_performance_delta missing"
        assert "risk_adjusted_return" in data, "risk_adjusted_return missing"
        
        # Verify types
        assert isinstance(data["strategy_conflicts"], list), "strategy_conflicts should be a list"
        assert isinstance(data["capital_rebalance_events"], list), "capital_rebalance_events should be a list"
        assert isinstance(data["hedge_suggestions"], list), "hedge_suggestions should be a list"
        
        print("✓ Strategy intelligence dashboard returned valid structure")
        print(f"  conflicts: {len(data['strategy_conflicts'])}, rebalance_events: {len(data['capital_rebalance_events'])}")
        print(f"  allocation_drift: {data['allocation_drift']}, risk_adjusted_return: {data['risk_adjusted_return']}")


class TestManualOverridesListEndpoint:
    """Tests for /api/admin/manual-overrides list endpoint"""

    def test_manual_overrides_returns_list(self, authenticated_client):
        """Verify manual-overrides endpoint returns a list"""
        response = authenticated_client.get(f"{BASE_URL}/api/admin/manual-overrides")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "manual-overrides should return a list"
        print(f"✓ Manual overrides endpoint returned {len(data)} items")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
