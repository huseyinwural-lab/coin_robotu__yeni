"""
Phase 5.8A Capital Scaling Validation Comprehensive Tests
- Capital scaling simulator (1M/10M/100M)
- Liquidity impact model
- Slippage simulator
- Stress replay engine (high_volatility, low_liquidity, flash_crash, liquidation_cascade)
- Scaling robustness engine (config-driven weights)
- Scaling governance adapter
- Endpoints: /scaling-validation, /scaling-report
- Regression: live-readiness, tail-risk, capital, cluster, strategy endpoints
"""
import os
import sys
from pathlib import Path

import pytest
import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


@pytest.fixture(scope="module")
def admin_headers():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL tanımlı değil")
    login_response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if login_response.status_code != 200:
        pytest.skip(f"Admin login başarısız: {login_response.text}")
    token = login_response.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# === Capital Scaling Simulator Unit Tests ===
class TestCapitalScalingSimulator:
    """Capital scaling simulator (1M/10M/100M) deterministic replay tests"""
    
    def test_simulator_returns_three_capital_levels(self):
        from core.simulation.capital_scaling_simulator import run_capital_scaling_simulation
        
        trades = [
            {"order_size": 10000, "expected_pnl": 100.0, "volatility_regime": "NORMAL"},
            {"order_size": 8000, "expected_pnl": 80.0, "volatility_regime": "HIGH"},
        ]
        result = run_capital_scaling_simulation(
            trades=trades,
            capital_levels=[1_000_000.0, 10_000_000.0, 100_000_000.0],
            market_depth=4_500_000.0,
            spread_bps=12.0,
            liquidity_tier="MEDIUM",
        )
        
        assert "capital_levels" in result
        assert result["capital_levels"] == [1_000_000.0, 10_000_000.0, 100_000_000.0]
        assert "scaling_performance_report" in result
        assert len(result["scaling_performance_report"]) == 3
    
    def test_simulator_report_contains_required_metrics(self):
        from core.simulation.capital_scaling_simulator import run_capital_scaling_simulation
        
        trades = [{"order_size": 10000, "expected_pnl": 100.0, "volatility_regime": "NORMAL"}]
        result = run_capital_scaling_simulation(
            trades=trades,
            capital_levels=[1_000_000.0, 10_000_000.0],
            market_depth=4_500_000.0,
            spread_bps=12.0,
            liquidity_tier="MEDIUM",
        )
        
        for row in result["scaling_performance_report"]:
            assert "capital_level" in row
            assert "pnl" in row
            assert "slippage" in row
            assert "execution_quality" in row
            assert "liquidity_stress" in row
    
    def test_simulator_deterministic_output(self):
        from core.simulation.capital_scaling_simulator import run_capital_scaling_simulation
        
        trades = [{"order_size": 10000, "expected_pnl": 100.0, "volatility_regime": "NORMAL"}]
        params = dict(
            trades=trades,
            capital_levels=[1_000_000.0, 10_000_000.0, 100_000_000.0],
            market_depth=4_500_000.0,
            spread_bps=12.0,
            liquidity_tier="MEDIUM",
        )
        
        result1 = run_capital_scaling_simulation(**params)
        result2 = run_capital_scaling_simulation(**params)
        
        # Deterministic: same input -> same output
        assert result1["scaling_performance_report"] == result2["scaling_performance_report"]


# === Liquidity Impact Model Unit Tests ===
class TestLiquidityImpactModel:
    """Liquidity impact model output tests"""
    
    def test_impact_model_returns_required_fields(self):
        from core.simulation.liquidity_impact_model import estimate_liquidity_impact
        
        result = estimate_liquidity_impact(
            order_size=50000.0,
            market_depth=1_000_000.0,
            spread_width_bps=10.0,
            liquidity_tier="MEDIUM",
        )
        
        assert "impact_ratio" in result
        assert "impact_score" in result
        assert "liquidity_tier" in result
    
    def test_impact_increases_with_order_size(self):
        from core.simulation.liquidity_impact_model import estimate_liquidity_impact
        
        small_order = estimate_liquidity_impact(
            order_size=10000.0,
            market_depth=1_000_000.0,
            spread_width_bps=10.0,
            liquidity_tier="MEDIUM",
        )
        large_order = estimate_liquidity_impact(
            order_size=100000.0,
            market_depth=1_000_000.0,
            spread_width_bps=10.0,
            liquidity_tier="MEDIUM",
        )
        
        assert large_order["impact_ratio"] > small_order["impact_ratio"]
    
    def test_liquidity_tier_affects_impact(self):
        from core.simulation.liquidity_impact_model import estimate_liquidity_impact
        
        params = dict(order_size=50000.0, market_depth=1_000_000.0, spread_width_bps=10.0)
        
        high_liq = estimate_liquidity_impact(**params, liquidity_tier="HIGH")
        low_liq = estimate_liquidity_impact(**params, liquidity_tier="LOW")
        
        # LOW liquidity tier should have higher impact
        assert low_liq["impact_ratio"] > high_liq["impact_ratio"]


# === Slippage Simulator Unit Tests ===
class TestSlippageSimulator:
    """Slippage simulator output tests"""
    
    def test_slippage_returns_required_fields(self):
        from core.simulation.slippage_simulator import simulate_expected_slippage
        
        result = simulate_expected_slippage(
            order_size=10000.0,
            volatility_regime="NORMAL",
            spread_bps=12.0,
            liquidity_score=0.8,
            impact_score=25.0,
        )
        
        assert "expected_slippage_bps" in result
        assert "volatility_regime" in result
    
    def test_volatility_regime_affects_slippage(self):
        from core.simulation.slippage_simulator import simulate_expected_slippage
        
        params = dict(order_size=10000.0, spread_bps=12.0, liquidity_score=0.8, impact_score=25.0)
        
        normal = simulate_expected_slippage(**params, volatility_regime="NORMAL")
        extreme = simulate_expected_slippage(**params, volatility_regime="EXTREME")
        
        # EXTREME volatility should increase slippage
        assert extreme["expected_slippage_bps"] > normal["expected_slippage_bps"]


# === Stress Replay Engine Unit Tests ===
class TestStressReplayEngine:
    """Stress replay scenarios deterministic tests"""
    
    def test_all_four_scenarios_available(self):
        from core.simulation.stress_replay_engine import SCENARIO_MULTIPLIERS
        
        scenarios = ["high_volatility", "low_liquidity", "flash_crash", "liquidation_cascade"]
        for scenario in scenarios:
            assert scenario in SCENARIO_MULTIPLIERS
    
    def test_stress_replay_high_volatility(self):
        from core.simulation.stress_replay_engine import run_stress_replay
        
        base_metrics = {"volatility": 1.0, "liquidity": 1.0, "spread_bps": 12.0}
        result = run_stress_replay(base_metrics, "high_volatility")
        
        assert result["scenario"] == "high_volatility"
        assert result["volatility_multiplier"] == 1.6
        assert result["liquidity_multiplier"] == 0.75
        assert result["spread_multiplier"] == 1.4
        assert result["replayed_metrics"]["volatility"] == 1.6
    
    def test_stress_replay_low_liquidity(self):
        from core.simulation.stress_replay_engine import run_stress_replay
        
        base_metrics = {"volatility": 1.0, "liquidity": 1.0, "spread_bps": 12.0}
        result = run_stress_replay(base_metrics, "low_liquidity")
        
        assert result["scenario"] == "low_liquidity"
        assert result["liquidity_multiplier"] == 0.55
    
    def test_stress_replay_flash_crash(self):
        from core.simulation.stress_replay_engine import run_stress_replay
        
        base_metrics = {"volatility": 1.0, "liquidity": 1.0, "spread_bps": 12.0}
        result = run_stress_replay(base_metrics, "flash_crash")
        
        assert result["scenario"] == "flash_crash"
        assert result["volatility_multiplier"] == 2.2
        assert result["liquidity_multiplier"] == 0.4
    
    def test_stress_replay_liquidation_cascade(self):
        from core.simulation.stress_replay_engine import run_stress_replay
        
        base_metrics = {"volatility": 1.0, "liquidity": 1.0, "spread_bps": 12.0}
        result = run_stress_replay(base_metrics, "liquidation_cascade")
        
        assert result["scenario"] == "liquidation_cascade"
        assert result["volatility_multiplier"] == 1.9
    
    def test_stress_replay_deterministic(self):
        from core.simulation.stress_replay_engine import run_stress_replay
        
        base_metrics = {"volatility": 1.0, "liquidity": 1.0, "spread_bps": 12.0}
        
        result1 = run_stress_replay(base_metrics, "flash_crash")
        result2 = run_stress_replay(base_metrics, "flash_crash")
        
        assert result1 == result2


# === Scaling Robustness Engine Unit Tests ===
class TestScalingRobustnessEngine:
    """Robustness score state transitions and config-driven weights tests"""
    
    def test_robustness_engine_uses_configurable_weights(self):
        from core.simulation.scaling_robustness_engine import compute_scaling_robustness_score
        
        weights = {
            "pnl_stability": 0.3,
            "slippage_impact": 0.2,
            "execution_quality": 0.3,
            "liquidity_stress": 0.2,
        }
        result = compute_scaling_robustness_score(
            pnl_stability=80,
            slippage_impact=75,
            execution_quality=85,
            liquidity_stress=70,
            weights=weights,
        )
        
        assert result["weights"] == weights
        assert "scaling_robustness_score" in result
        assert "robustness_state" in result
        assert "components" in result
    
    def test_robustness_state_scalable(self):
        from core.simulation.scaling_robustness_engine import compute_scaling_robustness_score
        
        weights = {"pnl_stability": 0.25, "slippage_impact": 0.25, "execution_quality": 0.25, "liquidity_stress": 0.25}
        result = compute_scaling_robustness_score(
            pnl_stability=90,
            slippage_impact=85,
            execution_quality=88,
            liquidity_stress=85,
            weights=weights,
        )
        
        assert result["scaling_robustness_score"] >= 80
        assert result["robustness_state"] == "scalable"
    
    def test_robustness_state_caution(self):
        from core.simulation.scaling_robustness_engine import compute_scaling_robustness_score
        
        weights = {"pnl_stability": 0.25, "slippage_impact": 0.25, "execution_quality": 0.25, "liquidity_stress": 0.25}
        result = compute_scaling_robustness_score(
            pnl_stability=70,
            slippage_impact=72,
            execution_quality=75,
            liquidity_stress=68,
            weights=weights,
        )
        
        assert 60 <= result["scaling_robustness_score"] < 80
        assert result["robustness_state"] == "caution"
    
    def test_robustness_state_unstable(self):
        from core.simulation.scaling_robustness_engine import compute_scaling_robustness_score
        
        weights = {"pnl_stability": 0.25, "slippage_impact": 0.25, "execution_quality": 0.25, "liquidity_stress": 0.25}
        result = compute_scaling_robustness_score(
            pnl_stability=50,
            slippage_impact=45,
            execution_quality=55,
            liquidity_stress=40,
            weights=weights,
        )
        
        assert result["scaling_robustness_score"] < 60
        assert result["robustness_state"] == "unstable"


# === Scaling Governance Adapter Unit Tests ===
class TestScalingGovernanceAdapter:
    """Scaling governance adapter outputs tests"""
    
    def test_governance_adapter_scalable_state(self):
        from core.simulation.scaling_governance_adapter import build_scaling_governance_actions
        
        result = build_scaling_governance_actions({
            "scaling_robustness_score": 85.0,
            "robustness_state": "scalable",
        })
        
        assert result["capital_cap_recommendation"] == 1.0
        assert result["risk_downshift"] is False
        assert result["strategy_disable"] is False
    
    def test_governance_adapter_caution_state(self):
        from core.simulation.scaling_governance_adapter import build_scaling_governance_actions
        
        result = build_scaling_governance_actions({
            "scaling_robustness_score": 72.0,
            "robustness_state": "caution",
        })
        
        assert result["capital_cap_recommendation"] == 0.8
        assert result["risk_downshift"] is True
        assert result["strategy_disable"] is False
    
    def test_governance_adapter_unstable_state_no_disable(self):
        from core.simulation.scaling_governance_adapter import build_scaling_governance_actions
        
        result = build_scaling_governance_actions({
            "scaling_robustness_score": 50.0,
            "robustness_state": "unstable",
        })
        
        assert result["capital_cap_recommendation"] == 0.55
        assert result["risk_downshift"] is True
        assert result["strategy_disable"] is False
    
    def test_governance_adapter_unstable_state_with_disable(self):
        from core.simulation.scaling_governance_adapter import build_scaling_governance_actions
        
        result = build_scaling_governance_actions({
            "scaling_robustness_score": 40.0,
            "robustness_state": "unstable",
        })
        
        assert result["capital_cap_recommendation"] == 0.55
        assert result["risk_downshift"] is True
        assert result["strategy_disable"] is True


# === Endpoint Contract Tests ===
class TestScalingValidationEndpoint:
    """GET /api/admin/futures/scaling-validation endpoint contract tests"""
    
    def test_scaling_validation_returns_200(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/scaling-validation",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
    
    def test_scaling_validation_contract_full(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/scaling-validation",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        payload = response.json()
        
        # Required top-level fields
        required_fields = [
            "generated_at",
            "scaling_performance_report",
            "scaling_robustness_score",
            "robustness_state",
            "robustness_components",
            "robustness_weights",
            "scaling_governance_actions",
            "stress_replay_dashboard",
        ]
        for field in required_fields:
            assert field in payload, f"Missing field: {field}"
    
    def test_scaling_validation_performance_report_has_capital_levels(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/scaling-validation",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        
        report = payload.get("scaling_performance_report", [])
        assert len(report) == 3  # 1M, 10M, 100M
        
        capital_levels = [row.get("capital_level") for row in report]
        assert 1_000_000.0 in capital_levels
        assert 10_000_000.0 in capital_levels
        assert 100_000_000.0 in capital_levels
    
    def test_scaling_validation_report_metrics(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/scaling-validation",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        
        for row in payload.get("scaling_performance_report", []):
            assert "pnl" in row
            assert "slippage" in row
            assert "execution_quality" in row
            assert "liquidity_stress" in row
    
    def test_scaling_validation_includes_robustness_weights(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/scaling-validation",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        
        weights = payload.get("robustness_weights", {})
        assert "pnl_stability" in weights
        assert "slippage_impact" in weights
        assert "execution_quality" in weights
        assert "liquidity_stress" in weights
    
    def test_scaling_validation_stress_replay_dashboard(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/scaling-validation",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        
        stress_dashboard = payload.get("stress_replay_dashboard", [])
        assert len(stress_dashboard) == 4
        
        scenarios = [row.get("scenario") for row in stress_dashboard]
        assert "high_volatility" in scenarios
        assert "low_liquidity" in scenarios
        assert "flash_crash" in scenarios
        assert "liquidation_cascade" in scenarios
    
    def test_scaling_validation_governance_actions(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/scaling-validation",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        
        actions = payload.get("scaling_governance_actions", {})
        assert "capital_cap_recommendation" in actions
        assert "risk_downshift" in actions
        assert "strategy_disable" in actions


class TestScalingReportEndpoint:
    """GET /api/admin/futures/scaling-report endpoint contract tests"""
    
    def test_scaling_report_returns_200(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/scaling-report",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
    
    def test_scaling_report_contract(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/scaling-report",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        
        required_fields = [
            "generated_at",
            "scaling_performance_report",
            "scaling_robustness_score",
            "robustness_state",
            "stress_replay_dashboard",
        ]
        for field in required_fields:
            assert field in payload, f"Missing field: {field}"


# === Regression Tests ===
class TestRegressionEndpoints:
    """Regression: ensure existing endpoints still work"""
    
    def test_live_readiness_endpoint_not_broken(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/live-readiness",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
    
    def test_tail_risk_endpoint_not_broken(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/tail-risk",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
    
    def test_capital_drift_endpoint_not_broken(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/capital-drift",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
    
    def test_cluster_risk_endpoint_not_broken(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/cluster-risk",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
    
    def test_strategy_governance_endpoint_not_broken(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
    
    def test_strategy_performance_endpoint_not_broken(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-performance",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
    
    def test_capital_budget_endpoint_not_broken(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/capital-budget",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
    
    def test_capital_usage_endpoint_not_broken(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/capital-usage",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
