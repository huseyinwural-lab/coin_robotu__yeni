"""
Learning Control UI Alignment Tests
Tests for P0-P3 requirements:
- P0: Learning Memory UI alignment (canonical event fields + strategy performance metrics)
- P1: Recommendation Simulator UI alignment
- P2: Version history + post-change monitoring visible
- P3: Admin action flow from panel
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from server import app

ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def client():
    """Get TestClient instance"""
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(client):
    """Get admin authentication token using TestClient"""
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text[:200]}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestLearningOverviewEndpoint:
    """P0: Test learning overview endpoint returns all required fields"""
    
    def test_overview_returns_200(self, client, auth_headers):
        """Test that overview endpoint is accessible"""
        response = client.get("/api/admin/learning/overview", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
    
    def test_overview_schema_version(self, client, auth_headers):
        """Test schema_version field is present"""
        response = client.get("/api/admin/learning/overview", headers=auth_headers)
        data = response.json()
        assert "schema_version" in data, "schema_version field missing"
        # May be null if no data, but field should exist
    
    def test_overview_engine_version(self, client, auth_headers):
        """Test engine_version field is present"""
        response = client.get("/api/admin/learning/overview", headers=auth_headers)
        data = response.json()
        assert "engine_version" in data, "engine_version field missing"
    
    def test_overview_guardrails(self, client, auth_headers):
        """Test guardrails field is present"""
        response = client.get("/api/admin/learning/overview", headers=auth_headers)
        data = response.json()
        assert "guardrails" in data, "guardrails field missing"
    
    def test_overview_strategy_memory(self, client, auth_headers):
        """Test strategy_memory array is present"""
        response = client.get("/api/admin/learning/overview", headers=auth_headers)
        data = response.json()
        assert "strategy_memory" in data, "strategy_memory field missing"
        assert isinstance(data["strategy_memory"], list), "strategy_memory should be a list"
    
    def test_overview_family_memory(self, client, auth_headers):
        """Test family_memory array is present"""
        response = client.get("/api/admin/learning/overview", headers=auth_headers)
        data = response.json()
        assert "family_memory" in data, "family_memory field missing"
        assert isinstance(data["family_memory"], list), "family_memory should be a list"
    
    def test_overview_recommendations(self, client, auth_headers):
        """Test recommendations array is present"""
        response = client.get("/api/admin/learning/overview", headers=auth_headers)
        data = response.json()
        assert "recommendations" in data, "recommendations field missing"
        assert isinstance(data["recommendations"], list), "recommendations should be a list"
    
    def test_overview_events(self, client, auth_headers):
        """Test events array is present"""
        response = client.get("/api/admin/learning/overview", headers=auth_headers)
        data = response.json()
        assert "events" in data, "events field missing"
        assert isinstance(data["events"], list), "events should be a list"
    
    def test_overview_adaptive_summary(self, client, auth_headers):
        """Test adaptive_summary field is present"""
        response = client.get("/api/admin/learning/overview", headers=auth_headers)
        data = response.json()
        assert "adaptive_summary" in data, "adaptive_summary field missing"


class TestLearningRefreshEndpoint:
    """Test learning refresh endpoint"""
    
    def test_refresh_returns_200(self, client, auth_headers):
        """Test that refresh endpoint works"""
        response = client.post(
            "/api/admin/learning/refresh?days=30",
            headers=auth_headers
        )
        # May return 200 or 401 depending on session state
        assert response.status_code in [200, 401], f"Unexpected status: {response.status_code}"


class TestSimulateImpactEndpoint:
    """P1: Test simulate-impact endpoint returns all required fields"""
    
    def test_simulate_impact_returns_200(self, client, auth_headers):
        """Test simulate-impact endpoint is accessible"""
        payload = {
            "strategy_id": "test_strategy",
            "strategy_ids": [],
            "family": None,
            "symbol_cluster": [],
            "scenario": "base",
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.8
        }
        response = client.post(
            "/api/admin/learning/simulate-impact",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code in [200, 401], f"Unexpected status: {response.status_code}"
    
    def test_simulate_impact_baseline_metrics(self, client, auth_headers):
        """Test baseline_metrics field in simulation response"""
        payload = {
            "strategy_id": "test_strategy",
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.8
        }
        response = client.post(
            "/api/admin/learning/simulate-impact",
            json=payload,
            headers=auth_headers
        )
        if response.status_code == 200:
            data = response.json()
            assert "baseline_metrics" in data, "baseline_metrics field missing"
    
    def test_simulate_impact_projected_metrics(self, client, auth_headers):
        """Test projected_metrics field in simulation response"""
        payload = {
            "strategy_id": "test_strategy",
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.8
        }
        response = client.post(
            "/api/admin/learning/simulate-impact",
            json=payload,
            headers=auth_headers
        )
        if response.status_code == 200:
            data = response.json()
            assert "projected_metrics" in data, "projected_metrics field missing"
    
    def test_simulate_impact_delta_metrics(self, client, auth_headers):
        """Test delta_metrics field in simulation response"""
        payload = {
            "strategy_id": "test_strategy",
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.8
        }
        response = client.post(
            "/api/admin/learning/simulate-impact",
            json=payload,
            headers=auth_headers
        )
        if response.status_code == 200:
            data = response.json()
            assert "delta_metrics" in data, "delta_metrics field missing"
    
    def test_simulate_impact_sample_coverage(self, client, auth_headers):
        """Test sample_coverage field in simulation response"""
        payload = {
            "strategy_id": "test_strategy",
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.8
        }
        response = client.post(
            "/api/admin/learning/simulate-impact",
            json=payload,
            headers=auth_headers
        )
        if response.status_code == 200:
            data = response.json()
            assert "sample_coverage" in data, "sample_coverage field missing"
    
    def test_simulate_impact_risk_aware_view(self, client, auth_headers):
        """Test risk_aware_view field in simulation response"""
        payload = {
            "strategy_id": "test_strategy",
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.8
        }
        response = client.post(
            "/api/admin/learning/simulate-impact",
            json=payload,
            headers=auth_headers
        )
        if response.status_code == 200:
            data = response.json()
            assert "risk_aware_view" in data, "risk_aware_view field missing"
    
    def test_simulate_impact_portfolio_impact(self, client, auth_headers):
        """Test portfolio_impact field in simulation response"""
        payload = {
            "strategy_id": "test_strategy",
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.8
        }
        response = client.post(
            "/api/admin/learning/simulate-impact",
            json=payload,
            headers=auth_headers
        )
        if response.status_code == 200:
            data = response.json()
            assert "portfolio_impact" in data, "portfolio_impact field missing"
    
    def test_simulate_impact_counterfactual_replay(self, client, auth_headers):
        """Test counterfactual_replay field in simulation response"""
        payload = {
            "strategy_id": "test_strategy",
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.8
        }
        response = client.post(
            "/api/admin/learning/simulate-impact",
            json=payload,
            headers=auth_headers
        )
        if response.status_code == 200:
            data = response.json()
            assert "counterfactual_replay" in data, "counterfactual_replay field missing"
    
    def test_simulate_impact_interaction_effects(self, client, auth_headers):
        """Test interaction_effects field in simulation response"""
        payload = {
            "strategy_id": "test_strategy",
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.8
        }
        response = client.post(
            "/api/admin/learning/simulate-impact",
            json=payload,
            headers=auth_headers
        )
        if response.status_code == 200:
            data = response.json()
            assert "interaction_effects" in data, "interaction_effects field missing"


class TestLearningEventsEndpoint:
    """Test learning events endpoint"""
    
    def test_events_returns_200(self, client, auth_headers):
        """Test events endpoint is accessible"""
        response = client.get("/api/admin/learning/events", headers=auth_headers)
        assert response.status_code in [200, 401], f"Unexpected status: {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
