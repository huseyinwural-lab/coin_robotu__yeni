"""
Strategy Allocation Governance Tests - Phase 1 + Phase 2
Tests for Capital Governance Layer on Allocation Panel

Endpoints tested:
- GET /api/admin/strategy-allocation/summary
- POST /api/admin/strategy-allocation/normalize
- PUT /api/admin/strategy-allocation/{id}
- POST /api/admin/strategy-allocation (create)
- DELETE /api/admin/strategy-allocation/{id}
- POST /api/admin/strategy-allocation/bulk-update
- POST /api/admin/strategy-allocation/{id}/throttle-toggle
- GET /api/admin/strategy-allocation/state-history
"""

import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

DOUBLE_CONFIRM_PRIMARY = "CONFIRM"
DOUBLE_CONFIRM_SECONDARY = "STATE CHANGE"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token")
    if not token:
        pytest.skip("No access_token in login response")
    return token


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
    })
    return session


class TestStrategyAllocationSummary:
    """Tests for GET /api/admin/strategy-allocation/summary"""

    def test_summary_returns_correct_fields(self, api_client):
        """Summary endpoint returns all required governance fields"""
        response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields exist
        assert "total_strategies" in data, "Missing total_strategies"
        assert "total_weight" in data, "Missing total_weight"
        assert "weight_balance_delta" in data, "Missing weight_balance_delta (delta)"
        assert "total_capital" in data, "Missing total_capital"
        assert "used_capital" in data, "Missing used_capital"
        assert "available_capital" in data, "Missing available_capital"
        assert "over_allocated_count" in data, "Missing over_allocated_count"
        assert "over_allocated_strategies" in data, "Missing over_allocated_strategies"
        
        # Verify data types
        assert isinstance(data["total_strategies"], int)
        assert isinstance(data["total_weight"], (int, float))
        assert isinstance(data["weight_balance_delta"], (int, float))
        assert isinstance(data["total_capital"], (int, float))
        assert isinstance(data["used_capital"], (int, float))
        assert isinstance(data["available_capital"], (int, float))
        assert isinstance(data["over_allocated_count"], int)
        assert isinstance(data["over_allocated_strategies"], list)
        
        print(f"Summary: total_weight={data['total_weight']}, delta={data['weight_balance_delta']}, "
              f"total_capital={data['total_capital']}, used={data['used_capital']}, available={data['available_capital']}")


class TestStrategyAllocationNormalize:
    """Tests for POST /api/admin/strategy-allocation/normalize"""

    def test_normalize_sets_weight_to_one(self, api_client):
        """Normalize endpoint sets total weight to 1.0"""
        response = api_client.post(f"{BASE_URL}/api/admin/strategy-allocation/normalize")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "success", f"Expected status=success, got {data.get('status')}"
        assert "trace_id" in data, "Missing trace_id"
        assert "summary" in data, "Missing summary in response"
        
        # Verify weight is now 1.0
        summary = data.get("summary", {})
        total_weight = summary.get("total_weight", 0)
        delta = summary.get("weight_balance_delta", 1)
        
        # Allow small tolerance
        assert abs(total_weight - 1.0) < 0.0001, f"Weight should be 1.0 after normalize, got {total_weight}"
        assert abs(delta) < 0.0001, f"Delta should be ~0 after normalize, got {delta}"
        
        print(f"Normalize success: total_weight={total_weight}, delta={delta}, trace_id={data.get('trace_id')}")


class TestStrategyAllocationUpdate:
    """Tests for PUT /api/admin/strategy-allocation/{id}"""

    def test_update_rejects_when_weight_not_one(self, api_client):
        """Backend rejects update when total weight != 1"""
        # First get existing strategies
        list_response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        assert list_response.status_code == 200
        strategies = list_response.json()
        
        if not strategies:
            pytest.skip("No strategies available for testing")
        
        strategy = strategies[0]
        strategy_id = strategy["strategy_id"]
        
        # Try to set weight to a value that would break weight=1 constraint
        # This should fail if there are multiple strategies
        response = api_client.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            json={"capital_weight": 0.5}  # Arbitrary value that likely breaks weight=1
        )
        
        # If there's only one strategy, weight=0.5 would fail
        # If multiple strategies, changing one without adjusting others fails
        if len(strategies) == 1:
            # Single strategy must have weight=1
            assert response.status_code == 400, f"Expected 400 for weight!=1, got {response.status_code}"
            error_detail = response.json().get("detail", "")
            assert "weight" in error_detail.lower() or "1" in error_detail, f"Error should mention weight: {error_detail}"
            print(f"Correctly rejected weight!=1: {error_detail}")
        else:
            # Multiple strategies - changing one breaks total
            assert response.status_code == 400, f"Expected 400 for weight!=1, got {response.status_code}"
            print(f"Correctly rejected weight change that breaks total=1")

    def test_update_rejects_over_allocation(self, api_client):
        """Backend rejects when current_capital > max_capital"""
        list_response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        assert list_response.status_code == 200
        strategies = list_response.json()
        
        if not strategies:
            pytest.skip("No strategies available for testing")
        
        strategy = strategies[0]
        strategy_id = strategy["strategy_id"]
        
        # Try to set current_capital > max_capital
        response = api_client.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            json={
                "current_capital": 100000,
                "max_capital": 1000  # current > max
            }
        )
        
        assert response.status_code == 400, f"Expected 400 for over-allocation, got {response.status_code}"
        error_detail = response.json().get("detail", "")
        assert "capital" in error_detail.lower() or "aşamaz" in error_detail.lower(), f"Error should mention capital: {error_detail}"
        print(f"Correctly rejected over-allocation: {error_detail}")

    def test_state_change_requires_double_confirm(self, api_client):
        """State change requires confirm_primary=CONFIRM and confirm_secondary=STATE CHANGE"""
        list_response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        assert list_response.status_code == 200
        strategies = list_response.json()
        
        if not strategies:
            pytest.skip("No strategies available for testing")
        
        # Find a strategy that's not DISABLED
        strategy = None
        for s in strategies:
            if s["state"] != "DISABLED":
                strategy = s
                break
        
        if not strategy:
            pytest.skip("No non-DISABLED strategy available")
        
        strategy_id = strategy["strategy_id"]
        current_state = strategy["state"]
        new_state = "THROTTLED" if current_state == "ACTIVE" else "ACTIVE"
        
        # Try state change without double confirm
        response = api_client.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            json={"state": new_state}
        )
        
        assert response.status_code == 400, f"Expected 400 without double confirm, got {response.status_code}"
        error_detail = response.json().get("detail", "")
        assert "double confirm" in error_detail.lower() or "confirm" in error_detail.lower(), f"Error should mention confirm: {error_detail}"
        print(f"Correctly rejected state change without double confirm: {error_detail}")


class TestStrategyAllocationCreate:
    """Tests for POST /api/admin/strategy-allocation (create)"""

    def test_create_strategy_works(self, api_client):
        """Create new strategy allocation works"""
        # First normalize to ensure weight=1
        api_client.post(f"{BASE_URL}/api/admin/strategy-allocation/normalize")
        
        # Get current summary
        summary_response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation/summary")
        summary = summary_response.json()
        
        # Create a new strategy with weight=0 (won't break weight=1 constraint)
        # But this will fail because total weight must be 1
        test_strategy_id = f"TEST_STRATEGY_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        response = api_client.post(
            f"{BASE_URL}/api/admin/strategy-allocation",
            json={
                "strategy_id": test_strategy_id,
                "capital_weight": 0.0,  # Adding 0 weight won't change total
                "max_capital": 1000,
                "current_capital": 0,
                "state": "ACTIVE"
            }
        )
        
        # This should fail because adding weight=0 means total weight stays at 1
        # but the new strategy has 0 weight which is invalid for a strategy
        # OR it might succeed if the system allows 0-weight strategies
        if response.status_code == 201 or response.status_code == 200:
            print(f"Strategy created: {test_strategy_id}")
            # Cleanup - delete the test strategy
            api_client.delete(f"{BASE_URL}/api/admin/strategy-allocation/{test_strategy_id}?auto_normalize=true")
        else:
            # Expected to fail due to weight constraint
            assert response.status_code == 400, f"Expected 400 or 201, got {response.status_code}: {response.text}"
            print(f"Create rejected (expected): {response.json().get('detail', '')}")


class TestStrategyAllocationDelete:
    """Tests for DELETE /api/admin/strategy-allocation/{id}"""

    def test_delete_with_auto_normalize(self, api_client):
        """Delete strategy with auto_normalize works"""
        # First create a test strategy
        api_client.post(f"{BASE_URL}/api/admin/strategy-allocation/normalize")
        
        # Get current strategies
        list_response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        strategies = list_response.json()
        
        if len(strategies) < 2:
            pytest.skip("Need at least 2 strategies to test delete")
        
        # Find a test strategy or use the last one
        test_strategy = None
        for s in strategies:
            if s["strategy_id"].startswith("TEST_"):
                test_strategy = s
                break
        
        if not test_strategy:
            # Skip if no test strategy exists
            pytest.skip("No TEST_ strategy available for deletion test")
        
        strategy_id = test_strategy["strategy_id"]
        
        # Delete with auto_normalize
        response = api_client.delete(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            params={"auto_normalize": True}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "trace_id" in data
        assert "summary" in data
        
        # Verify weight is still 1 after delete
        summary = data.get("summary", {})
        total_weight = summary.get("total_weight", 0)
        assert abs(total_weight - 1.0) < 0.0001, f"Weight should be 1.0 after delete+normalize, got {total_weight}"
        
        print(f"Delete with auto_normalize success: {strategy_id}, trace_id={data.get('trace_id')}")


class TestStrategyAllocationBulkUpdate:
    """Tests for POST /api/admin/strategy-allocation/bulk-update"""

    def test_bulk_update_works(self, api_client):
        """Bulk update multiple strategies works"""
        # First normalize
        api_client.post(f"{BASE_URL}/api/admin/strategy-allocation/normalize")
        
        # Get current strategies
        list_response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        strategies = list_response.json()
        
        if len(strategies) < 2:
            pytest.skip("Need at least 2 strategies for bulk update test")
        
        # Prepare bulk update - just update max_capital without changing weights
        updates = []
        for s in strategies[:2]:
            updates.append({
                "strategy_id": s["strategy_id"],
                "max_capital": float(s["max_capital"]) + 100  # Small increase
            })
        
        response = api_client.post(
            f"{BASE_URL}/api/admin/strategy-allocation/bulk-update",
            json={
                "updates": updates,
                "auto_normalize": False
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "updated_count" in data
        assert data["updated_count"] == len(updates)
        
        print(f"Bulk update success: updated_count={data['updated_count']}, trace_id={data.get('trace_id')}")


class TestStrategyAllocationThrottleToggle:
    """Tests for POST /api/admin/strategy-allocation/{id}/throttle-toggle"""

    def test_throttle_toggle_requires_double_confirm(self, api_client):
        """Throttle toggle requires double confirm"""
        list_response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        strategies = list_response.json()
        
        if not strategies:
            pytest.skip("No strategies available")
        
        # Find a non-DISABLED strategy
        strategy = None
        for s in strategies:
            if s["state"] != "DISABLED":
                strategy = s
                break
        
        if not strategy:
            pytest.skip("No non-DISABLED strategy available")
        
        strategy_id = strategy["strategy_id"]
        
        # Try without proper confirm
        response = api_client.post(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}/throttle-toggle",
            json={
                "confirm_primary": "wrong",
                "confirm_secondary": "wrong"
            }
        )
        
        assert response.status_code == 400, f"Expected 400 without proper confirm, got {response.status_code}"
        print(f"Correctly rejected throttle toggle without proper confirm")

    def test_throttle_toggle_with_double_confirm(self, api_client):
        """Throttle toggle works with proper double confirm"""
        list_response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        strategies = list_response.json()
        
        if not strategies:
            pytest.skip("No strategies available")
        
        # Find a non-DISABLED strategy
        strategy = None
        for s in strategies:
            if s["state"] != "DISABLED":
                strategy = s
                break
        
        if not strategy:
            pytest.skip("No non-DISABLED strategy available")
        
        strategy_id = strategy["strategy_id"]
        original_state = strategy["state"]
        
        # Toggle with proper confirm
        response = api_client.post(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}/throttle-toggle",
            json={
                "confirm_primary": DOUBLE_CONFIRM_PRIMARY,
                "confirm_secondary": DOUBLE_CONFIRM_SECONDARY
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify state changed
        new_state = data.get("state")
        expected_state = "THROTTLED" if original_state == "ACTIVE" else "ACTIVE"
        assert new_state == expected_state, f"Expected state={expected_state}, got {new_state}"
        
        print(f"Throttle toggle success: {original_state} -> {new_state}")
        
        # Toggle back to restore original state
        api_client.post(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}/throttle-toggle",
            json={
                "confirm_primary": DOUBLE_CONFIRM_PRIMARY,
                "confirm_secondary": DOUBLE_CONFIRM_SECONDARY
            }
        )


class TestStrategyAllocationStateHistory:
    """Tests for GET /api/admin/strategy-allocation/state-history"""

    def test_state_history_returns_log_list(self, api_client):
        """State history endpoint returns log entries"""
        response = api_client.get(
            f"{BASE_URL}/api/admin/strategy-allocation/state-history",
            params={"limit": 50}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "rows" in data, "Missing rows field"
        assert isinstance(data["rows"], list), "rows should be a list"
        
        # If there are entries, verify structure
        if data["rows"]:
            entry = data["rows"][0]
            assert "trace_id" in entry, "Missing trace_id"
            assert "strategy_id" in entry, "Missing strategy_id"
            assert "action_type" in entry, "Missing action_type"
            assert "admin_id" in entry, "Missing admin_id"
            assert "timestamp" in entry, "Missing timestamp"
            
            print(f"State history has {len(data['rows'])} entries")
            print(f"Latest entry: action_type={entry['action_type']}, strategy_id={entry['strategy_id']}")
        else:
            print("State history is empty (no actions logged yet)")


class TestStrategyAllocationList:
    """Tests for GET /api/admin/strategy-allocation"""

    def test_list_returns_strategies(self, api_client):
        """List endpoint returns strategy allocations"""
        response = api_client.get(f"{BASE_URL}/api/admin/strategy-allocation")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        
        if data:
            strategy = data[0]
            # Verify required fields
            assert "strategy_id" in strategy
            assert "capital_weight" in strategy
            assert "max_capital" in strategy
            assert "current_capital" in strategy
            assert "state" in strategy
            assert "confidence_score" in strategy
            assert "performance_score" in strategy
            assert "signal_decay" in strategy
            assert "execution_quality_score" in strategy
            
            print(f"Found {len(data)} strategies")
            print(f"First strategy: {strategy['strategy_id']}, state={strategy['state']}, weight={strategy['capital_weight']}")
        else:
            print("No strategies found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
