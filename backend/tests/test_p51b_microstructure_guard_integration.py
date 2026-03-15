"""
Phase 5.1B Market Microstructure Guard Integration Tests
Test coverage:
- All 6 detector modules contract behavior
- Risk aggregation + gate + execution suitability deterministic flow
- GET /api/admin/futures/microstructure/status endpoint contract
- Strategy paper cycle microstructure guard integration
- Regression for risk-monitor endpoints
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

# ==================== UNIT TESTS FOR DETECTOR MODULES ====================

from core.futures.microstructure.spread_shock_detector import SpreadShockDetector
from core.futures.microstructure.orderbook_thinning_detector import OrderbookThinningDetector
from core.futures.microstructure.liquidity_vacuum_detector import LiquidityVacuumDetector
from core.futures.microstructure.quote_stability_detector import QuoteStabilityDetector
from core.futures.microstructure.slippage_anomaly_estimator import SlippageAnomalyEstimator
from core.futures.microstructure.liquidity_disappearance_heuristic import LiquidityDisappearanceHeuristic
from core.futures.microstructure.microstructure_risk_aggregator import MicrostructureRiskAggregator
from core.futures.microstructure.microstructure_gate import MicrostructureGate
from core.futures.microstructure.execution_suitability_evaluator import ExecutionSuitabilityEvaluator


class TestSpreadShockDetector:
    """Spread shock detector contract tests"""

    def test_shock_state_when_ratio_exceeds_threshold(self):
        detector = SpreadShockDetector()
        result = detector.evaluate({"spread_bps": 30}, baseline_spread_bps=10)
        assert result["spread_state"] == "SHOCK"
        assert result["shock_ratio"] >= 2.5
        assert "spread_bps" in result
        assert "baseline_spread_bps" in result

    def test_elevated_state_when_moderate_spread(self):
        detector = SpreadShockDetector()
        result = detector.evaluate({"spread_bps": 18}, baseline_spread_bps=10)
        assert result["spread_state"] == "ELEVATED"
        assert 1.5 <= result["shock_ratio"] < 2.5

    def test_normal_state_when_spread_stable(self):
        detector = SpreadShockDetector()
        result = detector.evaluate({"spread_bps": 8}, baseline_spread_bps=10)
        assert result["spread_state"] == "NORMAL"
        assert result["shock_ratio"] < 1.5


class TestOrderbookThinningDetector:
    """Orderbook thinning detector contract tests"""

    def test_critical_thinning_when_large_drop(self):
        detector = OrderbookThinningDetector()
        result = detector.evaluate(
            {"bid_depth_top_n": 20, "ask_depth_top_n": 15},
            baseline_depth={"bid_depth_top_n": 100, "ask_depth_top_n": 100},
        )
        assert result["thinning_state"] == "CRITICAL"
        assert result["bid_depth_change"] <= -0.6 or result["ask_depth_change"] <= -0.6
        assert result["dominant_thin_side"] in {"BID", "ASK", "NONE"}

    def test_warning_thinning_when_moderate_drop(self):
        detector = OrderbookThinningDetector()
        result = detector.evaluate(
            {"bid_depth_top_n": 55, "ask_depth_top_n": 60},
            baseline_depth={"bid_depth_top_n": 100, "ask_depth_top_n": 100},
        )
        assert result["thinning_state"] == "WARNING"

    def test_normal_thinning_when_stable(self):
        detector = OrderbookThinningDetector()
        result = detector.evaluate(
            {"bid_depth_top_n": 95, "ask_depth_top_n": 98},
            baseline_depth={"bid_depth_top_n": 100, "ask_depth_top_n": 100},
        )
        assert result["thinning_state"] == "NORMAL"


class TestLiquidityVacuumDetector:
    """Liquidity vacuum detector contract tests"""

    def test_high_vacuum_on_poor_conditions(self):
        detector = LiquidityVacuumDetector()
        result = detector.evaluate(
            {"top_of_book_size": 0.2, "depth_imbalance": 0.55, "liquidity_gap_score": 85},
            {"thinning_state": "CRITICAL"},
        )
        assert result["vacuum_state"] == "HIGH"
        assert result["vacuum_score"] >= 0.75
        assert "expected_slippage_risk" in result

    def test_medium_vacuum_on_moderate_conditions(self):
        detector = LiquidityVacuumDetector()
        result = detector.evaluate(
            {"top_of_book_size": 1, "depth_imbalance": 0.35, "liquidity_gap_score": 40},
            {"thinning_state": "WARNING"},
        )
        assert result["vacuum_state"] == "MEDIUM"
        assert 0.45 <= result["vacuum_score"] < 0.75

    def test_low_vacuum_on_good_conditions(self):
        detector = LiquidityVacuumDetector()
        result = detector.evaluate(
            {"top_of_book_size": 20, "depth_imbalance": 0.05, "liquidity_gap_score": 5},
            {"thinning_state": "NORMAL"},
        )
        assert result["vacuum_state"] == "LOW"


class TestQuoteStabilityDetector:
    """Quote stability detector contract tests"""

    def test_chaotic_state_on_high_rate(self):
        detector = QuoteStabilityDetector()
        result = detector.evaluate({"quote_update_rate": 12, "price_jump_score": 90, "spread_bps": 30})
        assert result["quote_stability_state"] == "CHAOTIC"
        assert "mid_price_flicker_score" in result

    def test_unstable_state_on_moderate_conditions(self):
        detector = QuoteStabilityDetector()
        result = detector.evaluate({"quote_update_rate": 6, "price_jump_score": 30, "spread_bps": 15})
        assert result["quote_stability_state"] in {"UNSTABLE", "CHAOTIC"}

    def test_stable_state_on_calm_market(self):
        detector = QuoteStabilityDetector()
        result = detector.evaluate({"quote_update_rate": 1.5, "price_jump_score": 8, "spread_bps": 5})
        assert result["quote_stability_state"] == "STABLE"


class TestSlippageAnomalyEstimator:
    """Slippage anomaly estimator contract tests"""

    def test_anomaly_state_on_high_slippage(self):
        estimator = SlippageAnomalyEstimator()
        result = estimator.evaluate(
            {"spread_bps": 40},
            {"spread_bps": 40, "shock_ratio": 3.0},
            {"vacuum_score": 0.9},
        )
        assert result["slippage_state"] == "ANOMALY"
        assert result["anomaly_score"] >= 0.75
        assert "expected_slippage_bps" in result

    def test_elevated_state_on_moderate_slippage(self):
        estimator = SlippageAnomalyEstimator()
        result = estimator.evaluate(
            {"spread_bps": 15},
            {"spread_bps": 15, "shock_ratio": 1.8},
            {"vacuum_score": 0.5},
        )
        assert result["slippage_state"] in {"ELEVATED", "NORMAL"}

    def test_normal_state_on_low_slippage(self):
        estimator = SlippageAnomalyEstimator()
        result = estimator.evaluate(
            {"spread_bps": 5},
            {"spread_bps": 5, "shock_ratio": 1.1},
            {"vacuum_score": 0.1},
        )
        assert result["slippage_state"] == "NORMAL"


class TestLiquidityDisappearanceHeuristic:
    """Liquidity disappearance heuristic contract tests"""

    def test_strong_disappearance_signal(self):
        heuristic = LiquidityDisappearanceHeuristic()
        result = heuristic.evaluate(
            {"liquidity_gap_score": 80, "quote_update_rate": 15},
            {"thinning_state": "CRITICAL", "dominant_thin_side": "BID"},
            {"quote_update_rate": 15},
        )
        assert result["heuristic_state"] == "STRONG"
        assert result["liquidity_disappearance_score"] >= 0.75
        assert result["affected_side"] in {"LONG", "SHORT", "NONE"}

    def test_suspected_disappearance_signal(self):
        heuristic = LiquidityDisappearanceHeuristic()
        result = heuristic.evaluate(
            {"liquidity_gap_score": 45, "quote_update_rate": 7},
            {"thinning_state": "WARNING", "dominant_thin_side": "ASK"},
            {"quote_update_rate": 7},
        )
        assert result["heuristic_state"] in {"SUSPECTED", "STRONG"}

    def test_no_disappearance_signal(self):
        heuristic = LiquidityDisappearanceHeuristic()
        result = heuristic.evaluate(
            {"liquidity_gap_score": 10, "quote_update_rate": 3},
            {"thinning_state": "NORMAL", "dominant_thin_side": "NONE"},
            {"quote_update_rate": 3},
        )
        assert result["heuristic_state"] == "NONE"


class TestMicrostructureRiskAggregator:
    """Risk aggregator deterministic behavior tests"""

    def test_aggregator_blocked_on_severe_conditions(self):
        aggregator = MicrostructureRiskAggregator()
        result = aggregator.aggregate(
            snapshot={"stale_data": False},
            spread_result={"spread_state": "SHOCK"},
            thinning_result={"thinning_state": "CRITICAL"},
            vacuum_result={"vacuum_score": 0.95},
            quote_result={"quote_stability_state": "CHAOTIC"},
            slippage_result={"anomaly_score": 0.9},
            disappearance_result={"liquidity_disappearance_score": 0.8, "affected_side": "LONG"},
        )
        assert result["risk_level"] in {"CRITICAL", "BLOCKED"}
        assert result["side_risk"] == "LONG"
        assert "factor_scores" in result
        assert "dominant_factor" in result

    def test_aggregator_blocked_on_stale_data(self):
        aggregator = MicrostructureRiskAggregator()
        result = aggregator.aggregate(
            snapshot={"stale_data": True},
            spread_result={"spread_state": "NORMAL"},
            thinning_result={"thinning_state": "NORMAL"},
            vacuum_result={"vacuum_score": 0.1},
            quote_result={"quote_stability_state": "STABLE"},
            slippage_result={"anomaly_score": 0.1},
            disappearance_result={"liquidity_disappearance_score": 0.1, "affected_side": "NONE"},
        )
        assert result["risk_level"] == "BLOCKED"

    def test_aggregator_safe_on_normal_conditions(self):
        aggregator = MicrostructureRiskAggregator()
        result = aggregator.aggregate(
            snapshot={"stale_data": False},
            spread_result={"spread_state": "NORMAL"},
            thinning_result={"thinning_state": "NORMAL"},
            vacuum_result={"vacuum_score": 0.1},
            quote_result={"quote_stability_state": "STABLE"},
            slippage_result={"anomaly_score": 0.1},
            disappearance_result={"liquidity_disappearance_score": 0.1, "affected_side": "NONE"},
        )
        assert result["risk_level"] == "SAFE"


class TestMicrostructureGate:
    """Microstructure gate deterministic tests"""

    def test_gate_rejects_on_spread_shock(self):
        gate = MicrostructureGate()
        result = gate.evaluate(
            spread_result={"spread_state": "SHOCK"},
            thinning_result={"thinning_state": "NORMAL"},
            vacuum_result={"vacuum_state": "LOW"},
            quote_result={"quote_stability_state": "STABLE"},
            slippage_result={"slippage_state": "NORMAL"},
            aggregate_result={"risk_level": "WARNING", "microstructure_risk_score": 0.5},
            stale_data=False,
        )
        assert result["gate_pass"] is False
        assert "MICROSTRUCTURE_SPREAD_SHOCK" in result["all_reasons"]

    def test_gate_rejects_on_slippage_anomaly(self):
        gate = MicrostructureGate()
        result = gate.evaluate(
            spread_result={"spread_state": "NORMAL"},
            thinning_result={"thinning_state": "NORMAL"},
            vacuum_result={"vacuum_state": "LOW"},
            quote_result={"quote_stability_state": "STABLE"},
            slippage_result={"slippage_state": "ANOMALY"},
            aggregate_result={"risk_level": "SAFE", "microstructure_risk_score": 0.1},
            stale_data=False,
        )
        assert result["gate_pass"] is False
        assert "MICROSTRUCTURE_SLIPPAGE_ANOMALY" in result["all_reasons"]

    def test_gate_rejects_on_stale_data(self):
        gate = MicrostructureGate()
        result = gate.evaluate(
            spread_result={"spread_state": "NORMAL"},
            thinning_result={"thinning_state": "NORMAL"},
            vacuum_result={"vacuum_state": "LOW"},
            quote_result={"quote_stability_state": "STABLE"},
            slippage_result={"slippage_state": "NORMAL"},
            aggregate_result={"risk_level": "SAFE", "microstructure_risk_score": 0.1},
            stale_data=True,
        )
        assert result["gate_pass"] is False
        assert "MICROSTRUCTURE_STALE_DATA" in result["all_reasons"]

    def test_gate_passes_when_safe(self):
        gate = MicrostructureGate()
        result = gate.evaluate(
            spread_result={"spread_state": "NORMAL"},
            thinning_result={"thinning_state": "NORMAL"},
            vacuum_result={"vacuum_state": "LOW"},
            quote_result={"quote_stability_state": "STABLE"},
            slippage_result={"slippage_state": "NORMAL"},
            aggregate_result={"risk_level": "SAFE", "microstructure_risk_score": 0.1},
            stale_data=False,
        )
        assert result["gate_pass"] is True
        assert result["gate_reason"] == "PASS"


class TestExecutionSuitabilityEvaluator:
    """Execution suitability evaluator contract tests"""

    def test_blocked_when_gate_fails(self):
        evaluator = ExecutionSuitabilityEvaluator()
        result = evaluator.evaluate(
            aggregate_result={"risk_level": "WARNING", "side_risk": "LONG", "microstructure_risk_score": 0.5},
            gate_result={"gate_pass": False},
        )
        assert result["execution_suitable"] is False
        assert result["severity"] == "BLOCKED"
        assert result["max_allowed_size_ratio"] == 0.0
        assert result["leverage_cap_override"] == 1

    def test_high_severity_on_critical_level(self):
        evaluator = ExecutionSuitabilityEvaluator()
        result = evaluator.evaluate(
            aggregate_result={"risk_level": "CRITICAL", "side_risk": "SHORT", "microstructure_risk_score": 0.7},
            gate_result={"gate_pass": True},
        )
        assert result["execution_suitable"] is True
        assert result["severity"] == "HIGH"
        assert result["max_allowed_size_ratio"] == 0.35
        assert result["leverage_cap_override"] == 2

    def test_medium_severity_on_warning_level(self):
        evaluator = ExecutionSuitabilityEvaluator()
        result = evaluator.evaluate(
            aggregate_result={"risk_level": "WARNING", "side_risk": "NONE", "microstructure_risk_score": 0.5},
            gate_result={"gate_pass": True},
        )
        assert result["execution_suitable"] is True
        assert result["severity"] == "MEDIUM"
        assert result["max_allowed_size_ratio"] == 0.65
        assert result["leverage_cap_override"] == 3

    def test_low_severity_on_safe_level(self):
        evaluator = ExecutionSuitabilityEvaluator()
        result = evaluator.evaluate(
            aggregate_result={"risk_level": "SAFE", "side_risk": "NONE", "microstructure_risk_score": 0.1},
            gate_result={"gate_pass": True},
        )
        assert result["execution_suitable"] is True
        assert result["severity"] == "LOW"
        assert result["max_allowed_size_ratio"] >= 0.7
        assert result["leverage_cap_override"] == 5


# ==================== API INTEGRATION TESTS ====================

@pytest.fixture(scope="module")
def admin_token():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not defined")
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
    except requests.RequestException as exc:
        pytest.skip(f"Auth endpoint unavailable: {exc}")
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.text}")
    return response.json()["access_token"]


class TestMicrostructureStatusEndpoint:
    """GET /api/admin/futures/microstructure/status endpoint contract tests"""

    def test_endpoint_returns_200(self, admin_token):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert response.status_code == 200

    def test_response_contains_portfolio_state(self, admin_token):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        data = response.json()
        assert "portfolio_microstructure_state" in data
        assert data["portfolio_microstructure_state"] in {"SAFE", "WARNING", "CRITICAL", "BLOCKED"}

    def test_response_contains_risk_score(self, admin_token):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        data = response.json()
        assert "portfolio_microstructure_risk_score" in data
        assert isinstance(data["portfolio_microstructure_risk_score"], (int, float))

    def test_response_contains_symbols_at_risk(self, admin_token):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        data = response.json()
        assert "symbols_at_risk" in data
        assert isinstance(data["symbols_at_risk"], list)

    def test_response_contains_gate_rejections(self, admin_token):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        data = response.json()
        assert "gate_rejections" in data
        assert isinstance(data["gate_rejections"], list)

    def test_response_contains_execution_suitability(self, admin_token):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        data = response.json()
        assert "execution_suitability" in data
        suitability = data["execution_suitability"]
        assert "execution_suitable" in suitability
        assert "severity" in suitability
        assert "max_allowed_size_ratio" in suitability
        assert "leverage_cap_override" in suitability

    def test_response_contains_symbols_array(self, admin_token):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        data = response.json()
        assert "symbols" in data
        assert isinstance(data["symbols"], list)


class TestStrategyMicrostructureIntegration:
    """Strategy paper cycle microstructure guard integration tests"""

    def test_run_paper_cycle_returns_microstructure_data(self, admin_token):
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert "microstructure" in data
        microstructure = data["microstructure"]
        assert "portfolio_microstructure_state" in microstructure
        assert "gate_rejections" in microstructure
        assert "execution_suitability" in microstructure

    def test_strategy_status_returns_decision_trace(self, admin_token):
        # First run a cycle to populate cache
        requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "decision_trace" in data
        if data["decision_trace"]:
            trace = data["decision_trace"][0]
            assert "trace" in trace
            # When strategy produces a signal (not NONE), it goes through microstructure_guard
            # When signal is NONE, trace is just ['strategy_signal', 'decision_reject']
            # When signal passes through full decision flow, trace includes microstructure_guard
            allowed_traces = [t for t in data["decision_trace"] if t.get("decision") == "ALLOW"]
            if allowed_traces:
                assert "microstructure_guard" in allowed_traces[0]["trace"]
            else:
                # All signals rejected - check that trace exists
                assert len(trace["trace"]) > 0


class TestRegressionRiskMonitor:
    """Regression tests for risk-monitor endpoints"""

    def test_risk_status_still_works(self, admin_token):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/risk/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert response.status_code == 200

    def test_liquidation_protection_status_still_works(self, admin_token):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/liquidation-protection/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert response.status_code == 200
