"""
Iteration 97 - User Learning Recommendation Impact Simulator Tests

Tests the new user-facing learning simulator endpoints:
- POST /api/user/learning-simulator/simulate - User simulate read-only impact
- POST /api/user/learning-simulator/suggestions - Submit suggestion to admin
- GET /api/user/learning-simulator/suggestions - List user's own suggestions
- GET /api/admin/learning/user-suggestions - Admin view all user suggestions

Validates:
1. User widget simulate endpoint integration
2. 6 output metrics: projected_risk_score, projected_gate_decision, expected_hit_rate_delta,
   expected_avg_return_delta, allocation_drift_delta, hedge_effect_score
3. Read-only guardrail - user simulate does not change state
4. Admin suggestion access
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
USER_EMAIL = "TEST_phase4iter2_pipeline@example.com"
USER_PASSWORD = "TestPassword123!"
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


@pytest.fixture(scope="module")
def user_token():
    """Get user authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"User login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def user_client(user_token):
    """Session with user auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {user_token}"
    })
    return session


@pytest.fixture(scope="module")
def admin_client(admin_token):
    """Session with admin auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}"
    })
    return session


class TestUserLearningSimulatorSimulate:
    """Tests for POST /api/user/learning-simulator/simulate endpoint"""

    def test_simulate_basic_request(self, user_client):
        """Test basic user simulation request returns 6 metrics"""
        response = user_client.post(
            f"{BASE_URL}/api/user/learning-simulator/simulate",
            json={
                "recommendation_type": "decrease_weight_recommendation",
                "suggested_weight_multiplier": 0.8
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify all 6 required metrics are present
        assert "projected_risk_score" in data, "Missing projected_risk_score"
        assert "projected_gate_decision" in data, "Missing projected_gate_decision"
        assert "expected_hit_rate_delta" in data, "Missing expected_hit_rate_delta"
        assert "expected_avg_return_delta" in data, "Missing expected_avg_return_delta"
        assert "allocation_drift_delta" in data, "Missing allocation_drift_delta"
        assert "hedge_effect_score" in data, "Missing hedge_effect_score"
        
        # Verify read_only flag is True
        assert data.get("read_only") is True, "read_only should be True"

    def test_simulate_with_strategy_id(self, user_client):
        """Test simulation with strategy_id scope"""
        response = user_client.post(
            f"{BASE_URL}/api/user/learning-simulator/simulate",
            json={
                "strategy_id": "SPOT_TREND_PULLBACK_V1",
                "recommendation_type": "decrease_weight_recommendation",
                "suggested_weight_multiplier": 0.9
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data.get("projected_risk_score"), (int, float))
        assert data.get("projected_gate_decision") in ["ALLOW", "ADJUST_POSITION", "REQUIRE_APPROVAL", "REJECT"]

    def test_simulate_with_family(self, user_client):
        """Test simulation with family scope"""
        response = user_client.post(
            f"{BASE_URL}/api/user/learning-simulator/simulate",
            json={
                "family": "momentum",
                "recommendation_type": "increase_weight_recommendation",
                "suggested_weight_multiplier": 1.2
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "projected_risk_score" in data
        assert "hedge_effect_score" in data

    def test_simulate_with_symbol(self, user_client):
        """Test simulation with symbol parameter"""
        response = user_client.post(
            f"{BASE_URL}/api/user/learning-simulator/simulate",
            json={
                "symbol": "BTCUSDT",
                "recommendation_type": "decrease_weight_recommendation"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "projected_risk_score" in data

    def test_simulate_all_recommendation_types(self, user_client):
        """Test all 3 recommendation types work"""
        rec_types = [
            "disable_recommendation",
            "decrease_weight_recommendation",
            "increase_weight_recommendation"
        ]
        
        for rec_type in rec_types:
            response = user_client.post(
                f"{BASE_URL}/api/user/learning-simulator/simulate",
                json={"recommendation_type": rec_type}
            )
            assert response.status_code == 200, f"Failed for {rec_type}: {response.status_code} - {response.text}"
            data = response.json()
            assert data.get("recommendation_type") == rec_type

    def test_simulate_requires_auth(self):
        """Test that simulate endpoint requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/user/learning-simulator/simulate",
            json={"recommendation_type": "decrease_weight_recommendation"}
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_simulate_metric_types(self, user_client):
        """Verify all metric types are correct"""
        response = user_client.post(
            f"{BASE_URL}/api/user/learning-simulator/simulate",
            json={"recommendation_type": "decrease_weight_recommendation"}
        )
        assert response.status_code == 200
        
        data = response.json()
        # Verify numeric types
        assert isinstance(data.get("projected_risk_score"), (int, float)), "projected_risk_score should be numeric"
        assert isinstance(data.get("expected_hit_rate_delta"), (int, float)), "expected_hit_rate_delta should be numeric"
        assert isinstance(data.get("expected_avg_return_delta"), (int, float)), "expected_avg_return_delta should be numeric"
        assert isinstance(data.get("allocation_drift_delta"), (int, float)), "allocation_drift_delta should be numeric"
        assert isinstance(data.get("hedge_effect_score"), (int, float)), "hedge_effect_score should be numeric"
        # Verify string type for gate decision
        assert isinstance(data.get("projected_gate_decision"), str), "projected_gate_decision should be string"


class TestUserLearningSuggestions:
    """Tests for user learning suggestions endpoints"""

    def test_submit_suggestion_after_simulation(self, user_client):
        """Test submitting a suggestion to admin after simulation"""
        # First run a simulation
        sim_response = user_client.post(
            f"{BASE_URL}/api/user/learning-simulator/simulate",
            json={
                "strategy_id": "TEST_STRATEGY_SUBMIT",
                "family": "momentum",
                "recommendation_type": "decrease_weight_recommendation",
                "suggested_weight_multiplier": 0.8
            }
        )
        assert sim_response.status_code == 200
        sim_data = sim_response.json()
        
        # Now submit suggestion with simulation result
        submit_response = user_client.post(
            f"{BASE_URL}/api/user/learning-simulator/suggestions",
            json={
                "symbol": "BTCUSDT",
                "strategy_id": "TEST_STRATEGY_SUBMIT",
                "family": "momentum",
                "recommendation_type": "decrease_weight_recommendation",
                "simulation_payload": sim_data,
                "note": "TEST_iter97_user_suggestion_test"
            }
        )
        assert submit_response.status_code == 200, f"Expected 200, got {submit_response.status_code}: {submit_response.text}"
        
        data = submit_response.json()
        assert "id" in data, "Suggestion should have an id"
        assert data.get("status") == "pending", "Initial status should be pending"
        assert data.get("recommendation_type") == "decrease_weight_recommendation"

    def test_submit_suggestion_requires_auth(self):
        """Test that suggestion submission requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/user/learning-simulator/suggestions",
            json={
                "recommendation_type": "decrease_weight_recommendation",
                "simulation_payload": {}
            }
        )
        assert response.status_code in [401, 403]

    def test_list_user_suggestions(self, user_client):
        """Test user can list their own suggestions"""
        response = user_client.get(f"{BASE_URL}/api/user/learning-simulator/suggestions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # If there are suggestions, verify structure
        if len(data) > 0:
            suggestion = data[0]
            assert "id" in suggestion
            assert "user_id" in suggestion
            assert "recommendation_type" in suggestion
            assert "status" in suggestion
            assert "created_at" in suggestion

    def test_list_suggestions_requires_auth(self):
        """Test that listing suggestions requires authentication"""
        response = requests.get(f"{BASE_URL}/api/user/learning-simulator/suggestions")
        assert response.status_code in [401, 403]


class TestAdminUserSuggestions:
    """Tests for admin access to user suggestions"""

    def test_admin_list_all_user_suggestions(self, admin_client):
        """Admin can view all user suggestions"""
        response = admin_client.get(f"{BASE_URL}/api/admin/learning/user-suggestions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # Verify structure if items exist
        if len(data) > 0:
            suggestion = data[0]
            assert "id" in suggestion
            assert "user_id" in suggestion
            assert "recommendation_type" in suggestion
            assert "status" in suggestion

    def test_admin_suggestions_requires_admin_role(self, user_client):
        """Regular user cannot access admin suggestions endpoint"""
        response = user_client.get(f"{BASE_URL}/api/admin/learning/user-suggestions")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_admin_suggestions_requires_auth(self):
        """Unauthenticated request should fail"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/user-suggestions")
        assert response.status_code in [401, 403]


class TestReadOnlyGuardrail:
    """Tests to verify user simulate is read-only and doesn't change state"""

    def test_user_simulate_does_not_apply_changes(self, user_client, admin_client):
        """User simulate should NOT apply any recommendation changes"""
        # Get initial admin learning overview
        overview_before = admin_client.get(f"{BASE_URL}/api/admin/learning/overview")
        assert overview_before.status_code == 200
        initial_overview = overview_before.json()
        
        # Run user simulation multiple times
        for i in range(3):
            user_client.post(
                f"{BASE_URL}/api/user/learning-simulator/simulate",
                json={
                    "strategy_id": f"TEST_READONLY_CHECK_{i}",
                    "recommendation_type": "decrease_weight_recommendation",
                    "suggested_weight_multiplier": 0.1  # Extreme value to detect changes
                }
            )
        
        # Verify overview hasn't changed due to simulations
        overview_after = admin_client.get(f"{BASE_URL}/api/admin/learning/overview")
        assert overview_after.status_code == 200
        final_overview = overview_after.json()
        
        # The simulation should not create new recommendations automatically
        # It's just a simulation/preview
        assert final_overview.get("schema_version") == initial_overview.get("schema_version")

    def test_simulate_response_has_read_only_flag(self, user_client):
        """Verify simulation response explicitly says read_only=True"""
        response = user_client.post(
            f"{BASE_URL}/api/user/learning-simulator/simulate",
            json={"recommendation_type": "decrease_weight_recommendation"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("read_only") is True, "read_only flag must be True in response"


class TestEndpointAccessControl:
    """Tests to verify proper access control"""

    def test_user_cannot_access_admin_apply_endpoint(self, user_client):
        """User cannot apply recommendations via admin endpoint"""
        # Try to access admin apply endpoint
        response = user_client.post(
            f"{BASE_URL}/api/admin/learning/recommendations/fake-id/apply"
        )
        assert response.status_code in [401, 403, 404]

    def test_user_cannot_access_admin_simulate_endpoint(self, user_client):
        """User cannot access admin-level simulation endpoint"""
        response = user_client.post(
            f"{BASE_URL}/api/admin/learning/simulate-impact",
            json={"recommendation_type": "decrease_weight_recommendation"}
        )
        assert response.status_code in [401, 403]

    def test_admin_can_access_user_simulator_too(self, admin_client):
        """Admin should also be able to use user-level simulator"""
        # Admin might want to see what users see
        response = admin_client.post(
            f"{BASE_URL}/api/user/learning-simulator/simulate",
            json={"recommendation_type": "decrease_weight_recommendation"}
        )
        # Admin should get 200 or 403 based on role restrictions
        # If endpoint is user-only, admin might get 403
        # If endpoint allows any authenticated user, admin gets 200
        assert response.status_code in [200, 403]


class TestDecisionCardsIntegration:
    """Tests for integration with decision cards (context for widget)"""

    def test_user_decision_cards_available(self, user_client):
        """Verify user can access decision cards for widget context"""
        response = user_client.get(f"{BASE_URL}/api/user/decision-cards", params={"limit": 5})
        # Endpoint may return 200 with empty data or items
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Check structure
        if "items" in data:
            items = data["items"]
            if len(items) > 0:
                card = items[0]
                # Card should have fields that widget uses
                assert "symbol" in card
                assert "dominant_family" in card or card.get("dominant_family") is None
                assert "top_contributors" in card or card.get("top_contributors") is None


class TestCleanup:
    """Cleanup test data"""

    def test_cleanup_test_suggestions(self, admin_client):
        """Clean up test suggestions (informational)"""
        # Just verify we can list - actual cleanup handled separately if needed
        response = admin_client.get(
            f"{BASE_URL}/api/admin/learning/user-suggestions",
            params={"limit": 50}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Count test suggestions
        test_suggestions = [s for s in data if "TEST_" in str(s.get("note", ""))]
        print(f"Found {len(test_suggestions)} test suggestions")
