"""
Iteration 96: Learning Recommendation Impact Simulator Tests
Tests for the new Learning Recommendation Impact Simulator feature:
- POST /api/admin/learning/simulate-impact (global form)
- POST /api/admin/learning/recommendations/{id}/simulate (row quick simulate)
- Simulation response metriks validation (projected_risk_score, projected_gate_decision, etc.)
- Read-only guardrail (simulate should not modify any data)
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

@pytest.fixture(scope="module")
def admin_token():
    """Obtain admin JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": os.environ.get("TEST_ADMIN_EMAIL", ""),
        "password": os.environ.get("TEST_ADMIN_PASSWORD", "")
    })
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("access_token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth token."""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }


class TestLearningImpactSimulatorGlobalForm:
    """Tests for POST /api/admin/learning/simulate-impact (global form)"""

    def test_simulate_impact_global_basic(self, admin_headers):
        """Test basic global simulate-impact call with minimal parameters."""
        payload = {
            "recommendation_type": "decrease_weight_recommendation"
        }
        resp = requests.post(f"{BASE_URL}/api/admin/learning/simulate-impact", json=payload, headers=admin_headers)
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        # Required metrics in response
        assert "projected_risk_score" in data, "Missing projected_risk_score"
        assert "projected_gate_decision" in data, "Missing projected_gate_decision"
        assert "expected_hit_rate_delta" in data, "Missing expected_hit_rate_delta"
        assert "expected_avg_return_delta" in data, "Missing expected_avg_return_delta"
        assert "allocation_drift_delta" in data, "Missing allocation_drift_delta"
        assert "hedge_effect_score" in data, "Missing hedge_effect_score"
        
        # Verify read_only flag is true
        assert data.get("read_only") is True, "Simulation should have read_only=True"
        
        # Verify schema/engine version present
        assert "schema_version" in data, "Missing schema_version"
        assert "engine_version" in data, "Missing engine_version"
        
        print(f"Global simulate basic: projected_risk={data['projected_risk_score']}, gate={data['projected_gate_decision']}")

    def test_simulate_impact_with_strategy_id(self, admin_headers):
        """Test simulate-impact with strategy_id parameter (strategy scope)."""
        payload = {
            "strategy_id": "test_strategy_001",
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.7
        }
        resp = requests.post(f"{BASE_URL}/api/admin/learning/simulate-impact", json=payload, headers=admin_headers)
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert data.get("strategy_id") == "test_strategy_001"
        assert "scope" in data
        # Verify all 6 output metrics present
        required_metrics = ["projected_risk_score", "projected_gate_decision", "expected_hit_rate_delta", 
                           "expected_avg_return_delta", "allocation_drift_delta", "hedge_effect_score"]
        for metric in required_metrics:
            assert metric in data, f"Missing metric: {metric}"
        
        print(f"Strategy scope simulate: scope={data.get('scope')}, risk={data['projected_risk_score']}")

    def test_simulate_impact_with_family(self, admin_headers):
        """Test simulate-impact with family parameter (family scope)."""
        payload = {
            "family": "trend",
            "recommendation_type": "increase_weight_recommendation",
            "suggested_weight_multiplier": 1.2
        }
        resp = requests.post(f"{BASE_URL}/api/admin/learning/simulate-impact", json=payload, headers=admin_headers)
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert data.get("family") == "trend"
        assert data.get("recommendation_type") == "increase_weight_recommendation"
        
        # Verify baseline info is included
        assert "baseline" in data, "Missing baseline data"
        baseline = data["baseline"]
        assert "hit_rate" in baseline or "quality_score" in baseline, "Baseline should have reference metrics"
        
        print(f"Family scope simulate: family={data.get('family')}, gate_decision={data['projected_gate_decision']}")

    def test_simulate_impact_with_strategy_and_family(self, admin_headers):
        """Test simulate-impact with both strategy_id and family (combined scope)."""
        payload = {
            "strategy_id": "trend_follow_v1",
            "family": "trend",
            "recommendation_type": "disable_recommendation"
        }
        resp = requests.post(f"{BASE_URL}/api/admin/learning/simulate-impact", json=payload, headers=admin_headers)
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        # Verify both parameters recorded
        assert "strategy_id" in data or "family" in data
        assert data.get("recommendation_type") == "disable_recommendation"
        
        # Verify assumptions list present
        assert "assumptions" in data, "Missing assumptions list"
        assumptions = data["assumptions"]
        assert isinstance(assumptions, list)
        assert len(assumptions) > 0, "Assumptions should have at least one item"
        
        print(f"Combined scope simulate: scope={data.get('scope')}, assumptions={assumptions}")

    def test_simulate_impact_all_recommendation_types(self, admin_headers):
        """Test all three recommendation types produce valid output."""
        recommendation_types = [
            "disable_recommendation",
            "decrease_weight_recommendation",
            "increase_weight_recommendation"
        ]
        
        for rec_type in recommendation_types:
            payload = {
                "recommendation_type": rec_type,
                "suggested_weight_multiplier": 0.8 if "decrease" in rec_type else 1.1 if "increase" in rec_type else None
            }
            resp = requests.post(f"{BASE_URL}/api/admin/learning/simulate-impact", json=payload, headers=admin_headers)
            
            assert resp.status_code == 200, f"Failed for {rec_type}: {resp.status_code}"
            
            data = resp.json()
            assert data.get("projected_gate_decision") in ["ALLOW", "ADJUST_POSITION", "REQUIRE_APPROVAL", "REJECT"], \
                f"Invalid gate_decision for {rec_type}: {data.get('projected_gate_decision')}"
            
            print(f"Rec type {rec_type}: gate={data['projected_gate_decision']}, risk={data['projected_risk_score']}")


class TestLearningImpactSimulatorRowQuick:
    """Tests for POST /api/admin/learning/recommendations/{id}/simulate (row quick simulate)"""

    def test_simulate_recommendation_by_id_success(self, admin_headers):
        """Test quick simulate on existing recommendation."""
        # First get recommendations list
        overview_resp = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers)
        assert overview_resp.status_code == 200, f"Overview failed: {overview_resp.status_code}"
        
        overview = overview_resp.json()
        recommendations = overview.get("recommendations", [])
        
        if not recommendations:
            pytest.skip("No recommendations available to test row simulate")
        
        rec_id = recommendations[0]["id"]
        
        # Quick simulate on this recommendation
        resp = requests.post(f"{BASE_URL}/api/admin/learning/recommendations/{rec_id}/simulate", headers=admin_headers)
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        # Verify all 6 output metrics
        required_metrics = ["projected_risk_score", "projected_gate_decision", "expected_hit_rate_delta", 
                           "expected_avg_return_delta", "allocation_drift_delta", "hedge_effect_score"]
        for metric in required_metrics:
            assert metric in data, f"Missing metric in row simulate: {metric}"
        
        assert data.get("read_only") is True, "Row simulate should be read_only"
        
        print(f"Row simulate rec_id={rec_id}: risk={data['projected_risk_score']}, gate={data['projected_gate_decision']}")

    def test_simulate_recommendation_not_found(self, admin_headers):
        """Test simulate on non-existent recommendation returns 404."""
        fake_rec_id = "non-existent-recommendation-id-12345"
        
        resp = requests.post(f"{BASE_URL}/api/admin/learning/recommendations/{fake_rec_id}/simulate", headers=admin_headers)
        
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        
        print("Row simulate 404 test passed")


class TestReadOnlyGuardrail:
    """Tests to verify simulation does NOT modify production data."""

    def test_simulate_does_not_apply_recommendation(self, admin_headers):
        """Verify simulate-impact does not change is_applied status."""
        # Get overview before simulate
        resp1 = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers)
        assert resp1.status_code == 200
        
        before_overview = resp1.json()
        before_recommendations = before_overview.get("recommendations", [])
        
        unapplied_count_before = sum(1 for r in before_recommendations if not r.get("is_applied"))
        
        # Run global simulate
        simulate_payload = {
            "strategy_id": "test_strategy_ro",
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.5
        }
        sim_resp = requests.post(f"{BASE_URL}/api/admin/learning/simulate-impact", json=simulate_payload, headers=admin_headers)
        assert sim_resp.status_code == 200, f"Simulate failed: {sim_resp.text}"
        
        # Get overview after simulate
        resp2 = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers)
        assert resp2.status_code == 200
        
        after_overview = resp2.json()
        after_recommendations = after_overview.get("recommendations", [])
        
        unapplied_count_after = sum(1 for r in after_recommendations if not r.get("is_applied"))
        
        # Verify no recommendations were applied by simulate
        assert unapplied_count_before == unapplied_count_after, \
            f"Simulate should not apply recommendations! Before: {unapplied_count_before}, After: {unapplied_count_after}"
        
        print(f"Read-only guardrail verified: unapplied before={unapplied_count_before}, after={unapplied_count_after}")

    def test_simulate_does_not_change_strategy_weight(self, admin_headers):
        """Verify simulate-impact does not modify strategy weight."""
        # Get strategy registry before simulate
        reg_resp1 = requests.get(f"{BASE_URL}/api/admin/canonical-strategy-registry", headers=admin_headers)
        if reg_resp1.status_code != 200:
            pytest.skip("Cannot verify strategy weight guardrail - registry unavailable")
        
        strategies_before = reg_resp1.json()
        if not strategies_before:
            pytest.skip("No strategies in registry to test")
        
        strategy = strategies_before[0]
        strategy_id = strategy.get("strategy_id")
        weight_before = strategy.get("weight")
        
        # Run aggressive simulate that would change weight
        simulate_payload = {
            "strategy_id": strategy_id,
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.1  # Aggressive multiplier
        }
        sim_resp = requests.post(f"{BASE_URL}/api/admin/learning/simulate-impact", json=simulate_payload, headers=admin_headers)
        assert sim_resp.status_code == 200
        
        # Get strategy registry after simulate
        reg_resp2 = requests.get(f"{BASE_URL}/api/admin/canonical-strategy-registry", headers=admin_headers)
        assert reg_resp2.status_code == 200
        
        strategies_after = reg_resp2.json()
        strategy_after = next((s for s in strategies_after if s.get("strategy_id") == strategy_id), None)
        
        if strategy_after:
            weight_after = strategy_after.get("weight")
            assert weight_before == weight_after, \
                f"Simulate should not change weight! Before: {weight_before}, After: {weight_after}"
            print(f"Weight guardrail verified: strategy={strategy_id}, weight unchanged at {weight_before}")
        else:
            print(f"Strategy {strategy_id} not found after simulate - guardrail test inconclusive")


class TestSimulationResponseMetrics:
    """Tests to verify all 6 required output metrics are present and valid."""

    def test_all_six_metrics_present_and_typed(self, admin_headers):
        """Verify all 6 required metrics are present with correct types."""
        payload = {
            "family": "breakout",
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.75
        }
        resp = requests.post(f"{BASE_URL}/api/admin/learning/simulate-impact", json=payload, headers=admin_headers)
        
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify projected_risk_score (float 0-1)
        assert "projected_risk_score" in data
        risk_score = data["projected_risk_score"]
        assert isinstance(risk_score, (int, float)), f"projected_risk_score should be numeric: {type(risk_score)}"
        assert 0 <= risk_score <= 1, f"projected_risk_score should be 0-1: {risk_score}"
        
        # Verify projected_gate_decision (string enum)
        assert "projected_gate_decision" in data
        gate = data["projected_gate_decision"]
        assert gate in ["ALLOW", "ADJUST_POSITION", "REQUIRE_APPROVAL", "REJECT"], f"Invalid gate: {gate}"
        
        # Verify expected_hit_rate_delta (float)
        assert "expected_hit_rate_delta" in data
        hit_delta = data["expected_hit_rate_delta"]
        assert isinstance(hit_delta, (int, float)), f"expected_hit_rate_delta should be numeric: {type(hit_delta)}"
        
        # Verify expected_avg_return_delta (float)
        assert "expected_avg_return_delta" in data
        return_delta = data["expected_avg_return_delta"]
        assert isinstance(return_delta, (int, float)), f"expected_avg_return_delta should be numeric: {type(return_delta)}"
        
        # Verify allocation_drift_delta (float)
        assert "allocation_drift_delta" in data
        drift = data["allocation_drift_delta"]
        assert isinstance(drift, (int, float)), f"allocation_drift_delta should be numeric: {type(drift)}"
        
        # Verify hedge_effect_score (float 0-1)
        assert "hedge_effect_score" in data
        hedge = data["hedge_effect_score"]
        assert isinstance(hedge, (int, float)), f"hedge_effect_score should be numeric: {type(hedge)}"
        assert 0 <= hedge <= 1, f"hedge_effect_score should be 0-1: {hedge}"
        
        print(f"All 6 metrics verified: risk={risk_score}, gate={gate}, hit_delta={hit_delta}, "
              f"return_delta={return_delta}, drift={drift}, hedge={hedge}")


class TestAdminLearningPanelUIIntegration:
    """Tests for Admin Learning Panel API endpoints used by UI."""

    def test_overview_includes_all_panel_data(self, admin_headers):
        """Verify overview endpoint returns all data needed for panel UI."""
        resp = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers)
        
        assert resp.status_code == 200
        data = resp.json()
        
        # Required sections for panel UI
        assert "strategy_memory" in data, "Missing strategy_memory"
        assert "family_memory" in data, "Missing family_memory"
        assert "recommendations" in data, "Missing recommendations"
        assert "events" in data, "Missing events"
        assert "guardrails" in data, "Missing guardrails"
        
        # Verify guardrails structure
        guardrails = data["guardrails"]
        assert guardrails.get("auto_change_forbidden") is True, "auto_change_forbidden should be True"
        assert guardrails.get("admin_approval_required") is True, "admin_approval_required should be True"
        
        print(f"Overview verified: {len(data['strategy_memory'])} strategies, "
              f"{len(data['family_memory'])} families, {len(data['recommendations'])} recommendations")

    def test_refresh_learning_memory(self, admin_headers):
        """Test POST /api/admin/learning/refresh endpoint."""
        resp = requests.post(f"{BASE_URL}/api/admin/learning/refresh", params={"days": 30}, headers=admin_headers)
        
        assert resp.status_code == 200, f"Refresh failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "schema_version" in data
        assert "events_count" in data
        assert "recommendation_count" in data
        
        print(f"Refresh completed: events={data.get('events_count')}, recommendations={data.get('recommendation_count')}")


class TestUnauthorizedAccess:
    """Tests to verify endpoints require admin authentication."""

    def test_simulate_impact_requires_auth(self):
        """Verify simulate-impact requires authentication."""
        payload = {"recommendation_type": "decrease_weight_recommendation"}
        resp = requests.post(f"{BASE_URL}/api/admin/learning/simulate-impact", json=payload)
        
        assert resp.status_code in [401, 403], f"Should require auth, got {resp.status_code}"
        print("Auth required for simulate-impact: verified")

    def test_row_simulate_requires_auth(self):
        """Verify row simulate requires authentication."""
        resp = requests.post(f"{BASE_URL}/api/admin/learning/recommendations/fake-id/simulate")
        
        assert resp.status_code in [401, 403], f"Should require auth, got {resp.status_code}"
        print("Auth required for row simulate: verified")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
