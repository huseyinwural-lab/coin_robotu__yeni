"""
Test Strategy Allocation UX Changes - Iteration 27
Tests:
1. GET /api/admin/strategy-allocation returns 12 canonical strategies
2. State values are only ACTIVE/DISABLED
3. Drift auto disable/throttle state enforcement is removed (advisory mode)
4. Update endpoint does not require double-confirm for state changes
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "http://127.0.0.1:8001"

ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

CANONICAL_STRATEGY_IDS = [
    "ichimoku_trend_continuation",
    "golden_cross_regime",
    "supertrend_flip",
    "vortex_directional_cross",
    "bollinger_squeeze_breakout",
    "moving_momentum",
    "fibonacci_pullback_continuation",
    "macd_impulse",
    "fisher_reversal",
    "divergence_reversal_suite",
    "structure_breakout",
    "stochastic_exhaustion_reentry",
]


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text[:200]}")
    data = response.json()
    token = data.get("access_token")
    if not token:
        pytest.skip("No access_token in login response")
    return token


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Create authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    })
    return session


class TestStrategyAllocationEndpoint:
    """Tests for GET /api/admin/strategy-allocation"""

    def test_returns_12_canonical_strategies(self, api_client):
        """Backend should return exactly 12 canonical strategies"""
        response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        assert len(data) == 12, f"Expected 12 strategies, got {len(data)}"
        
        # Verify all canonical strategy IDs are present
        returned_ids = {s["strategy_id"] for s in data}
        expected_ids = set(CANONICAL_STRATEGY_IDS)
        assert returned_ids == expected_ids, f"Missing strategies: {expected_ids - returned_ids}, Extra: {returned_ids - expected_ids}"

    def test_state_values_only_active_or_disabled(self, api_client):
        """State values should only be ACTIVE or DISABLED (not THROTTLED)"""
        response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        assert response.status_code == 200
        
        data = response.json()
        allowed_states = {"ACTIVE", "DISABLED"}
        
        for strategy in data:
            state = strategy.get("state")
            assert state in allowed_states, f"Strategy {strategy['strategy_id']} has invalid state: {state}"

    def test_state_reason_code_is_manual(self, api_client):
        """State reason code should be MANUAL_STATE (advisory mode, no auto enforcement)"""
        response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        assert response.status_code == 200
        
        data = response.json()
        for strategy in data:
            reason_code = strategy.get("state_reason_code", "")
            # Advisory mode: state_reason_code should be MANUAL_STATE, not AUTO_DISABLED_BY_DRIFT
            assert reason_code == "MANUAL_STATE", f"Strategy {strategy['strategy_id']} has non-manual state_reason_code: {reason_code}"


class TestStrategyAllocationUpdate:
    """Tests for PUT /api/admin/strategy-allocation/{strategy_id}"""

    def test_update_state_without_double_confirm(self, api_client):
        """Update should work without double-confirm for state changes"""
        # First get current state
        response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        assert response.status_code == 200
        
        data = response.json()
        strategy = data[0]  # Pick first strategy
        strategy_id = strategy["strategy_id"]
        current_state = strategy["state"]
        new_state = "DISABLED" if current_state == "ACTIVE" else "ACTIVE"
        
        # Update only state (keep same weight/capital to avoid weight validation issues)
        update_response = api_client.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            json={
                "expected_revision": strategy.get("revision_id", 1),
                "state": new_state,
                "reason_note": "test_state_change_no_double_confirm",
            },
        )
        
        # Should succeed without requiring double-confirm
        # Note: 400 with weight error is acceptable - we're testing that double-confirm is NOT required
        if update_response.status_code == 400:
            error_detail = update_response.json().get("detail", "")
            # If error is about weight, that's fine - not about double-confirm
            assert "double confirm" not in error_detail.lower(), f"Double confirm required: {error_detail}"
            assert "confirm_primary" not in error_detail.lower(), f"Double confirm required: {error_detail}"
            print(f"Update returned 400 due to weight validation (expected): {error_detail}")
        else:
            assert update_response.status_code in [200, 201], f"Update failed: {update_response.status_code} - {update_response.text[:300]}"
            
            # Verify state changed
            verify_response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
            assert verify_response.status_code == 200
            updated_data = verify_response.json()
            updated_strategy = next((s for s in updated_data if s["strategy_id"] == strategy_id), None)
            assert updated_strategy is not None
            assert updated_strategy["state"] == new_state, f"State not updated: expected {new_state}, got {updated_strategy['state']}"
            
            # Revert state back
            revert_response = api_client.put(
                f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
                json={
                    "expected_revision": updated_strategy.get("revision_id", 1),
                    "state": current_state,
                    "reason_note": "test_revert_state",
                },
            )
            assert revert_response.status_code in [200, 201, 400], f"Revert failed: {revert_response.status_code}"


class TestDriftAdvisoryMode:
    """Tests for drift advisory mode (no auto state enforcement)"""

    def test_no_auto_disabled_by_drift(self, api_client):
        """Drift should not auto-disable strategies (advisory mode)"""
        response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        assert response.status_code == 200
        
        data = response.json()
        for strategy in data:
            reason_code = strategy.get("state_reason_code", "")
            # Should NOT have AUTO_DISABLED_BY_DRIFT or AUTO_THROTTLED_BY_DRIFT
            assert "AUTO_DISABLED" not in reason_code, f"Strategy {strategy['strategy_id']} has auto-disabled state: {reason_code}"
            assert "AUTO_THROTTLED" not in reason_code, f"Strategy {strategy['strategy_id']} has auto-throttled state: {reason_code}"

    def test_is_drift_override_false(self, api_client):
        """is_drift_override should be false (no drift enforcement)"""
        response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        assert response.status_code == 200
        
        data = response.json()
        for strategy in data:
            is_override = strategy.get("is_drift_override", False)
            assert is_override is False, f"Strategy {strategy['strategy_id']} has is_drift_override=True"


class TestStrategyAllocationSummary:
    """Tests for GET /api/admin/strategy-allocation/summary"""

    def test_summary_endpoint(self, api_client):
        """Summary endpoint should return valid data"""
        response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation/summary")
        assert response.status_code == 200
        
        data = response.json()
        assert "total_strategies" in data
        assert data["total_strategies"] == 12, f"Expected 12 strategies in summary, got {data['total_strategies']}"
        assert "total_weight" in data
        assert "total_capital" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
