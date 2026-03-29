# Learning Adaptive Engine & Lifecycle Routes API Tests
# Tests: rolling_windows, decay_score, regime_drift_flag, drift_confidence, actionability_flag, adaptive_summary
# Tests: actionable_state, recommendation_score, decision_candidate, auto_apply_eligible, scope_reason, cross_strategy_correlation
# Tests: simulate-impact portfolio-style inputs (strategy_ids, symbol_cluster, scenario)
# Tests: baseline_metrics/projected_metrics/delta_metrics/sample_coverage/portfolio_impact/interaction_effects/risk_aware_view
# Tests: lifecycle routes: simulate, approve, apply, rollback, reject, version-history, post-change-monitoring

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Authenticate as admin and return token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token returned from login")
    return token


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Return headers with admin auth token"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestLearningOverviewAdaptiveFields:
    """Test admin learning overview exposes adaptive fields"""

    def test_overview_returns_200(self, admin_headers):
        """GET /api/admin/learning/overview returns 200"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_overview_has_schema_version(self, admin_headers):
        """Overview response has schema_version"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        assert "schema_version" in data, "Missing schema_version"
        assert data["schema_version"] == "learning.v1"

    def test_overview_has_engine_version(self, admin_headers):
        """Overview response has engine_version"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        assert "engine_version" in data, "Missing engine_version"

    def test_overview_has_guardrails(self, admin_headers):
        """Overview response has guardrails with admin_approval_required"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        assert "guardrails" in data, "Missing guardrails"
        guardrails = data["guardrails"]
        assert guardrails.get("admin_approval_required") is True

    def test_overview_has_strategy_memory(self, admin_headers):
        """Overview response has strategy_memory list"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        assert "strategy_memory" in data, "Missing strategy_memory"
        assert isinstance(data["strategy_memory"], list)

    def test_overview_has_family_memory(self, admin_headers):
        """Overview response has family_memory list"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        assert "family_memory" in data, "Missing family_memory"
        assert isinstance(data["family_memory"], list)

    def test_overview_has_recommendations(self, admin_headers):
        """Overview response has recommendations list"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        assert "recommendations" in data, "Missing recommendations"
        assert isinstance(data["recommendations"], list)

    def test_overview_has_events(self, admin_headers):
        """Overview response has events list"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        assert "events" in data, "Missing events"
        assert isinstance(data["events"], list)

    def test_overview_has_adaptive_summary(self, admin_headers):
        """Overview response has adaptive_summary with affected_strategies"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        assert "adaptive_summary" in data, "Missing adaptive_summary"
        assert "affected_strategies" in data["adaptive_summary"], "Missing affected_strategies in adaptive_summary"

    def test_strategy_memory_has_rolling_windows(self, admin_headers):
        """Strategy memory items have rolling_windows field"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        strategy_memory = data.get("strategy_memory", [])
        if strategy_memory:
            first_item = strategy_memory[0]
            assert "rolling_windows" in first_item, "Missing rolling_windows in strategy_memory item"

    def test_strategy_memory_has_decay_score(self, admin_headers):
        """Strategy memory items have decay_score field"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        strategy_memory = data.get("strategy_memory", [])
        if strategy_memory:
            first_item = strategy_memory[0]
            assert "decay_score" in first_item, "Missing decay_score in strategy_memory item"

    def test_strategy_memory_has_regime_drift_flag(self, admin_headers):
        """Strategy memory items have regime_drift_flag field"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        strategy_memory = data.get("strategy_memory", [])
        if strategy_memory:
            first_item = strategy_memory[0]
            assert "regime_drift_flag" in first_item, "Missing regime_drift_flag in strategy_memory item"

    def test_strategy_memory_has_drift_confidence(self, admin_headers):
        """Strategy memory items have drift_confidence field"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        strategy_memory = data.get("strategy_memory", [])
        if strategy_memory:
            first_item = strategy_memory[0]
            assert "drift_confidence" in first_item, "Missing drift_confidence in strategy_memory item"

    def test_strategy_memory_has_actionability_flag(self, admin_headers):
        """Strategy memory items have actionability_flag field"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        strategy_memory = data.get("strategy_memory", [])
        if strategy_memory:
            first_item = strategy_memory[0]
            assert "actionability_flag" in first_item, "Missing actionability_flag in strategy_memory item"


class TestRecommendationPayloadFields:
    """Test recommendation payload exposes required fields"""

    def test_recommendation_has_actionable_state(self, admin_headers):
        """Recommendations have actionable_state field"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        recommendations = data.get("recommendations", [])
        if recommendations:
            first_rec = recommendations[0]
            assert "actionable_state" in first_rec, "Missing actionable_state in recommendation"
            assert first_rec["actionable_state"] in ["actionable", "monitor_only", "ignore"]

    def test_recommendation_has_recommendation_score(self, admin_headers):
        """Recommendations have recommendation_score field"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        recommendations = data.get("recommendations", [])
        if recommendations:
            first_rec = recommendations[0]
            assert "recommendation_score" in first_rec, "Missing recommendation_score in recommendation"
            assert isinstance(first_rec["recommendation_score"], (int, float))

    def test_recommendation_has_decision_candidate(self, admin_headers):
        """Recommendations have decision_candidate field"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        recommendations = data.get("recommendations", [])
        if recommendations:
            first_rec = recommendations[0]
            assert "decision_candidate" in first_rec, "Missing decision_candidate in recommendation"
            assert isinstance(first_rec["decision_candidate"], bool)

    def test_recommendation_has_auto_apply_eligible(self, admin_headers):
        """Recommendations have auto_apply_eligible field"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        recommendations = data.get("recommendations", [])
        if recommendations:
            first_rec = recommendations[0]
            assert "auto_apply_eligible" in first_rec, "Missing auto_apply_eligible in recommendation"
            assert isinstance(first_rec["auto_apply_eligible"], bool)

    def test_recommendation_has_scope_reason(self, admin_headers):
        """Recommendations have scope_reason field"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        recommendations = data.get("recommendations", [])
        if recommendations:
            first_rec = recommendations[0]
            assert "scope_reason" in first_rec, "Missing scope_reason in recommendation"

    def test_recommendation_has_cross_strategy_correlation(self, admin_headers):
        """Recommendations have cross_strategy_correlation field"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        data = response.json()
        recommendations = data.get("recommendations", [])
        if recommendations:
            first_rec = recommendations[0]
            assert "cross_strategy_correlation" in first_rec, "Missing cross_strategy_correlation in recommendation"


class TestSimulateImpactPortfolioStyle:
    """Test admin simulate-impact accepts portfolio-style inputs"""

    def test_simulate_impact_returns_200(self, admin_headers):
        """POST /api/admin/learning/simulate-impact returns 200"""
        payload = {
            "strategy_id": None,
            "strategy_ids": [],
            "family": None,
            "symbol_cluster": [],
            "scenario": "base",
            "recommendation_type": "decrease_weight_recommendation",
            "suggested_weight_multiplier": 0.8,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/simulate-impact",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_simulate_impact_with_strategy_ids(self, admin_headers):
        """Simulate-impact accepts strategy_ids list"""
        payload = {
            "strategy_ids": ["TEST_STRATEGY_1", "TEST_STRATEGY_2"],
            "scenario": "base",
            "recommendation_type": "decrease_weight_recommendation",
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/simulate-impact",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert "strategy_ids" in data

    def test_simulate_impact_with_symbol_cluster(self, admin_headers):
        """Simulate-impact accepts symbol_cluster list"""
        payload = {
            "symbol_cluster": ["BTCUSDT", "ETHUSDT"],
            "scenario": "base",
            "recommendation_type": "decrease_weight_recommendation",
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/simulate-impact",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert "symbol_cluster" in data

    def test_simulate_impact_with_scenario(self, admin_headers):
        """Simulate-impact accepts scenario parameter"""
        for scenario in ["base", "stressed", "high_volatility", "low_liquidity"]:
            payload = {
                "scenario": scenario,
                "recommendation_type": "decrease_weight_recommendation",
            }
            response = requests.post(
                f"{BASE_URL}/api/admin/learning/simulate-impact",
                headers=admin_headers,
                json=payload,
                timeout=30,
            )
            assert response.status_code == 200, f"Failed for scenario {scenario}"
            data = response.json()
            assert data.get("scenario") == scenario

    def test_simulate_impact_has_baseline_metrics(self, admin_headers):
        """Simulate-impact response has baseline_metrics"""
        payload = {"recommendation_type": "decrease_weight_recommendation"}
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/simulate-impact",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        data = response.json()
        assert "baseline_metrics" in data, "Missing baseline_metrics"
        baseline = data["baseline_metrics"]
        assert "hit_rate" in baseline
        assert "avg_return" in baseline
        assert "drawdown" in baseline
        assert "risk_score" in baseline

    def test_simulate_impact_has_projected_metrics(self, admin_headers):
        """Simulate-impact response has projected_metrics"""
        payload = {"recommendation_type": "decrease_weight_recommendation"}
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/simulate-impact",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        data = response.json()
        assert "projected_metrics" in data, "Missing projected_metrics"
        projected = data["projected_metrics"]
        assert "hit_rate" in projected
        assert "avg_return" in projected
        assert "drawdown" in projected
        assert "risk_score" in projected

    def test_simulate_impact_has_delta_metrics(self, admin_headers):
        """Simulate-impact response has delta_metrics"""
        payload = {"recommendation_type": "decrease_weight_recommendation"}
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/simulate-impact",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        data = response.json()
        assert "delta_metrics" in data, "Missing delta_metrics"
        delta = data["delta_metrics"]
        assert "hit_rate_delta" in delta
        assert "avg_return_delta" in delta
        assert "drawdown_delta" in delta
        assert "risk_delta" in delta

    def test_simulate_impact_has_sample_coverage(self, admin_headers):
        """Simulate-impact response has sample_coverage"""
        payload = {"recommendation_type": "decrease_weight_recommendation"}
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/simulate-impact",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        data = response.json()
        assert "sample_coverage" in data, "Missing sample_coverage"
        coverage = data["sample_coverage"]
        assert "sample_size" in coverage
        assert "trade_linked" in coverage
        assert "coverage_ratio" in coverage
        assert "reliability_score" in coverage

    def test_simulate_impact_has_portfolio_impact(self, admin_headers):
        """Simulate-impact response has portfolio_impact"""
        payload = {"recommendation_type": "decrease_weight_recommendation"}
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/simulate-impact",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        data = response.json()
        assert "portfolio_impact" in data, "Missing portfolio_impact"
        portfolio = data["portfolio_impact"]
        assert "net_pnl_delta" in portfolio
        assert "drawdown_delta" in portfolio
        assert "capital_usage_delta" in portfolio
        assert "exposure_delta" in portfolio
        assert "concentration_delta" in portfolio

    def test_simulate_impact_has_interaction_effects(self, admin_headers):
        """Simulate-impact response has interaction_effects"""
        payload = {"recommendation_type": "decrease_weight_recommendation"}
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/simulate-impact",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        data = response.json()
        assert "interaction_effects" in data, "Missing interaction_effects"
        effects = data["interaction_effects"]
        assert "correlation_impact" in effects
        assert "conflict_detection" in effects
        assert "capital_contention" in effects
        assert "strategy_count" in effects

    def test_simulate_impact_has_risk_aware_view(self, admin_headers):
        """Simulate-impact response has risk_aware_view"""
        payload = {"recommendation_type": "decrease_weight_recommendation"}
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/simulate-impact",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        data = response.json()
        assert "risk_aware_view" in data, "Missing risk_aware_view"
        risk_view = data["risk_aware_view"]
        assert "tail_impact" in risk_view
        assert "cluster_impact" in risk_view
        assert "capital_impact" in risk_view
        assert "actionability_flag" in risk_view


class TestLearningLifecycleRoutes:
    """Test learning recommendation lifecycle routes"""

    def test_events_endpoint_returns_200(self, admin_headers):
        """GET /api/admin/learning/events returns 200"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/events", headers=admin_headers, timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        assert "schema_version" in data

    def test_refresh_endpoint_returns_200(self, admin_headers):
        """POST /api/admin/learning/refresh returns 200"""
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/refresh?days=30",
            headers=admin_headers,
            timeout=60,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "schema_version" in data
        assert "engine_version" in data

    def test_simulate_recommendation_returns_200_or_404(self, admin_headers):
        """POST /api/admin/learning/recommendations/{id}/simulate returns 200 or 404"""
        # First get a recommendation ID from overview
        overview_response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        recommendations = overview_response.json().get("recommendations", [])
        if not recommendations:
            pytest.skip("No recommendations available to test simulate")
        
        rec_id = recommendations[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/recommendations/{rec_id}/simulate",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}"

    def test_approve_recommendation_returns_200_or_404(self, admin_headers):
        """POST /api/admin/learning/recommendations/{id}/approve returns 200 or 404"""
        overview_response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        recommendations = overview_response.json().get("recommendations", [])
        if not recommendations:
            pytest.skip("No recommendations available to test approve")
        
        rec_id = recommendations[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/recommendations/{rec_id}/approve",
            headers=admin_headers,
            json={"reason": "test approval reason"},
            timeout=30,
        )
        assert response.status_code in [200, 400, 404], f"Expected 200/400/404, got {response.status_code}"

    def test_reject_recommendation_returns_200_or_404(self, admin_headers):
        """POST /api/admin/learning/recommendations/{id}/reject returns 200 or 404"""
        overview_response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        recommendations = overview_response.json().get("recommendations", [])
        if not recommendations:
            pytest.skip("No recommendations available to test reject")
        
        rec_id = recommendations[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/recommendations/{rec_id}/reject",
            headers=admin_headers,
            json={"reason": "test rejection reason"},
            timeout=30,
        )
        assert response.status_code in [200, 400, 404], f"Expected 200/400/404, got {response.status_code}"

    def test_version_history_returns_200_or_404(self, admin_headers):
        """GET /api/admin/learning/recommendations/{id}/version-history returns 200 or 404"""
        overview_response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        recommendations = overview_response.json().get("recommendations", [])
        if not recommendations:
            pytest.skip("No recommendations available to test version-history")
        
        rec_id = recommendations[0]["id"]
        response = requests.get(
            f"{BASE_URL}/api/admin/learning/recommendations/{rec_id}/version-history",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert "items" in data

    def test_post_change_monitoring_returns_200_or_404(self, admin_headers):
        """GET /api/admin/learning/recommendations/{id}/post-change-monitoring returns 200 or 404"""
        overview_response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        recommendations = overview_response.json().get("recommendations", [])
        if not recommendations:
            pytest.skip("No recommendations available to test post-change-monitoring")
        
        rec_id = recommendations[0]["id"]
        response = requests.get(
            f"{BASE_URL}/api/admin/learning/recommendations/{rec_id}/post-change-monitoring",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert "windows" in data

    def test_apply_recommendation_returns_200_or_error(self, admin_headers):
        """POST /api/admin/learning/recommendations/{id}/apply returns 200 or error"""
        overview_response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        recommendations = overview_response.json().get("recommendations", [])
        if not recommendations:
            pytest.skip("No recommendations available to test apply")
        
        rec_id = recommendations[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/recommendations/{rec_id}/apply",
            headers=admin_headers,
            json={"reason": "test apply reason"},
            timeout=30,
        )
        # Apply may fail if recommendation is not in approvable state
        assert response.status_code in [200, 400, 404], f"Expected 200/400/404, got {response.status_code}"

    def test_rollback_recommendation_returns_200_or_error(self, admin_headers):
        """POST /api/admin/learning/recommendations/{id}/rollback returns 200 or error"""
        overview_response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        recommendations = overview_response.json().get("recommendations", [])
        if not recommendations:
            pytest.skip("No recommendations available to test rollback")
        
        rec_id = recommendations[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/recommendations/{rec_id}/rollback",
            headers=admin_headers,
            json={"reason": "test rollback reason"},
            timeout=30,
        )
        # Rollback may fail if recommendation is not in rollbackable state
        assert response.status_code in [200, 400, 404], f"Expected 200/400/404, got {response.status_code}"


class TestNoRegressions:
    """Test no regressions in learning backend route contracts"""

    def test_overview_contract_stable(self, admin_headers):
        """Overview response contract is stable"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/overview", headers=admin_headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        required_keys = ["schema_version", "engine_version", "generated_at", "guardrails", "strategy_memory", "family_memory", "recommendations", "events", "adaptive_summary"]
        for key in required_keys:
            assert key in data, f"Missing required key: {key}"

    def test_simulate_impact_contract_stable(self, admin_headers):
        """Simulate-impact response contract is stable"""
        payload = {"recommendation_type": "decrease_weight_recommendation"}
        response = requests.post(
            f"{BASE_URL}/api/admin/learning/simulate-impact",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        required_keys = [
            "schema_version", "engine_version", "simulated_at", "scope", "recommendation_type",
            "read_only", "projected_risk_score", "projected_gate_decision",
            "expected_hit_rate_delta", "expected_avg_return_delta", "allocation_drift_delta",
            "hedge_effect_score", "baseline_metrics", "projected_metrics", "delta_metrics",
            "sample_coverage", "portfolio_impact", "interaction_effects", "risk_aware_view"
        ]
        for key in required_keys:
            assert key in data, f"Missing required key: {key}"

    def test_events_contract_stable(self, admin_headers):
        """Events response contract is stable"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/events", headers=admin_headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "schema_version" in data
        assert "engine_version" in data
        assert "generated_at" in data

    def test_user_suggestions_endpoint_exists(self, admin_headers):
        """GET /api/admin/learning/user-suggestions returns 200"""
        response = requests.get(f"{BASE_URL}/api/admin/learning/user-suggestions", headers=admin_headers, timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
