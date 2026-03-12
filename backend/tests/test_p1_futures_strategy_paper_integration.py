"""
P1: Futures Strategy Integration (Paper Mode) Tests
- Tests strategy contract, trend strategy signal generation
- Tests futures strategy engine chain: strategy -> microstructure guard -> risk engine -> liquidation gate -> ADL gate -> policy -> paper decision
- Tests paper executor synthetic lifecycle (paper_position_opened/closed, paper_pnl)
- Tests POST /api/admin/futures/strategy/run-paper-cycle endpoint
- Tests GET /api/admin/futures/strategy/status endpoint
- Regression tests for /api/admin/futures/risk/status and /api/admin/futures/liquidation-protection/status
"""
import os
import sys
from pathlib import Path

import pytest
import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://liquidation-guard.preview.emergentagent.com")

# Import core modules for unit tests
from core.strategy.futures.strategy_contract import FuturesStrategy, StrategySignal
from core.strategy.futures.futures_trend_follow_v1 import FuturesTrendFollowV1
from core.strategy.futures.futures_strategy_engine import FuturesStrategyEngine
from core.execution.futures_paper_executor import FuturesPaperExecutor


@pytest.fixture(scope="module")
def auth_token():
    """Authenticate and get admin token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@platform.dev", "password": "Admin12345!"},
        headers={"Content-Type": "application/json"},
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def admin_client(auth_token):
    """Session with admin auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
    })
    return session


# ========== Strategy Contract & Trend Strategy Unit Tests ==========

class TestStrategyContract:
    """Tests for StrategySignal dataclass and FuturesStrategy ABC contract"""

    def test_strategy_signal_dataclass_fields(self):
        """StrategySignal must have required fields"""
        signal = StrategySignal(
            symbol="BTCUSDT",
            side="LONG",
            confidence=0.75,
            regime="TRENDING",
            reason="TEST_REASON",
        )
        assert signal.symbol == "BTCUSDT"
        assert signal.side == "LONG"
        assert signal.confidence == 0.75
        assert signal.regime == "TRENDING"
        assert signal.reason == "TEST_REASON"

    def test_futures_strategy_abc_requires_generate_signal(self):
        """FuturesStrategy ABC must have generate_signal method"""
        assert hasattr(FuturesStrategy, "generate_signal")


class TestFuturesTrendFollowV1:
    """Tests for FuturesTrendFollowV1 strategy signal generation"""

    def test_long_signal_when_all_conditions_match(self):
        """LONG signal when trend direction LONG, regime TRENDING, funding aligned"""
        strategy = FuturesTrendFollowV1(trend_threshold=0.002)
        signal = strategy.generate_signal({
            "symbol": "BTCUSDT",
            "trend_strength": 0.005,
            "trend_direction": "LONG",
            "volatility_regime": "TRENDING",
            "spread_state": "NORMAL",
            "funding_alignment": True,
        })
        assert signal.side == "LONG"
        assert signal.confidence > 0.45
        assert signal.reason == "TREND_FUNDING_ALIGNED"

    def test_short_signal_when_short_conditions_match(self):
        """SHORT signal when trend direction SHORT, regime TRENDING, funding aligned"""
        strategy = FuturesTrendFollowV1(trend_threshold=0.002)
        signal = strategy.generate_signal({
            "symbol": "ETHUSDT",
            "trend_strength": 0.008,
            "trend_direction": "SHORT",
            "volatility_regime": "TRENDING",
            "spread_state": "NORMAL",
            "funding_alignment": True,
        })
        assert signal.side == "SHORT"
        assert signal.confidence > 0.45
        assert signal.reason == "TREND_FUNDING_ALIGNED"

    def test_none_signal_when_spread_shock(self):
        """NONE signal with SPREAD_SHOCK reason when spread_state is SHOCK"""
        strategy = FuturesTrendFollowV1()
        signal = strategy.generate_signal({
            "symbol": "BTCUSDT",
            "trend_strength": 0.01,
            "trend_direction": "LONG",
            "volatility_regime": "TRENDING",
            "spread_state": "SHOCK",
            "funding_alignment": True,
        })
        assert signal.side == "NONE"
        assert signal.reason == "SPREAD_SHOCK"

    def test_none_signal_when_regime_not_trending(self):
        """NONE signal when volatility_regime is not TRENDING"""
        strategy = FuturesTrendFollowV1()
        signal = strategy.generate_signal({
            "symbol": "BTCUSDT",
            "trend_strength": 0.01,
            "trend_direction": "LONG",
            "volatility_regime": "RANGING",
            "spread_state": "NORMAL",
            "funding_alignment": True,
        })
        assert signal.side == "NONE"
        assert signal.reason == "REGIME_NOT_TRENDING"

    def test_none_signal_when_trend_strength_below_threshold(self):
        """NONE signal when trend_strength is below threshold"""
        strategy = FuturesTrendFollowV1(trend_threshold=0.01)
        signal = strategy.generate_signal({
            "symbol": "BTCUSDT",
            "trend_strength": 0.005,  # Below 0.01 threshold
            "trend_direction": "LONG",
            "volatility_regime": "TRENDING",
            "spread_state": "NORMAL",
            "funding_alignment": True,
        })
        assert signal.side == "NONE"
        assert signal.reason == "TREND_STRENGTH_BELOW_THRESHOLD"

    def test_none_signal_when_funding_misaligned(self):
        """NONE signal when funding_alignment is False"""
        strategy = FuturesTrendFollowV1(trend_threshold=0.002)
        signal = strategy.generate_signal({
            "symbol": "BTCUSDT",
            "trend_strength": 0.01,
            "trend_direction": "LONG",
            "volatility_regime": "TRENDING",
            "spread_state": "NORMAL",
            "funding_alignment": False,
        })
        assert signal.side == "NONE"
        assert signal.reason == "FUNDING_BIAS_MISALIGNED"

    def test_confidence_clamped_to_max_1(self):
        """Confidence should be clamped to max 1.0"""
        strategy = FuturesTrendFollowV1(trend_threshold=0.001)
        signal = strategy.generate_signal({
            "symbol": "BTCUSDT",
            "trend_strength": 0.05,  # Very high strength
            "trend_direction": "LONG",
            "volatility_regime": "TRENDING",
            "spread_state": "NORMAL",
            "funding_alignment": True,
        })
        assert signal.confidence <= 1.0


# ========== Futures Strategy Engine Chain Tests ==========

class TestFuturesStrategyEngine:
    """Tests for strategy -> microstructure guard -> risk engine -> liquidation gate -> ADL gate -> policy -> paper decision chain"""

    def test_engine_allow_path_full_trace(self):
        """ALLOW decision includes full trace through all gates"""
        engine = FuturesStrategyEngine({"futures_trend_follow_v1": FuturesTrendFollowV1(trend_threshold=0.001)})
        result = engine.evaluate_symbol(
            strategy_id="futures_trend_follow_v1",
            market_state={
                "symbol": "BTCUSDT",
                "latest_price": 100,
                "trend_strength": 0.01,
                "trend_direction": "SHORT",
                "volatility_regime": "TRENDING",
                "spread_state": "NORMAL",
                "funding_alignment": True,
            },
            risk_snapshot={
                "portfolio_leverage": 1.0,
                "margin_usage": 20,
                "avg_distance_to_liquidation": 50,
                "cascade_status": "NONE",
                "policy_state": "SAFE",
                "policy_action": "ALLOW",
                "policy_leverage_cap": 3,
                "adl_state": {
                    "risk_level": "LOW",
                    "dominant_side": "NONE",
                    "portfolio_adl_risk": 0.1,
                },
            },
        )
        assert result["decision"] == "ALLOW"
        assert "paper_execution" in result["trace"]
        # Verify full chain in trace
        expected_trace = [
            "signal",
            "microstructure_guard",
            "risk_engine",
            "liquidation_protection",
            "adl_shield",
            "dynamic_leverage_engine",
            "policy_engine",
            "hard_gate",
            "attribution",
            "decision_trace",
            "paper_execution",
        ]
        assert result["trace"] == expected_trace

    def test_engine_rejects_with_strategy_none_signal(self):
        """REJECT when strategy generates NONE signal"""
        engine = FuturesStrategyEngine({"futures_trend_follow_v1": FuturesTrendFollowV1()})
        result = engine.evaluate_symbol(
            strategy_id="futures_trend_follow_v1",
            market_state={
                "symbol": "BTCUSDT",
                "latest_price": 100,
                "trend_strength": 0.001,  # Below threshold
                "trend_direction": "LONG",
                "volatility_regime": "TRENDING",
                "spread_state": "NORMAL",
                "funding_alignment": True,
            },
            risk_snapshot={
                "portfolio_leverage": 1.0,
                "margin_usage": 20,
                "avg_distance_to_liquidation": 50,
                "cascade_status": "NONE",
                "policy_state": "SAFE",
            },
        )
        assert result["decision"] == "REJECT"
        assert "decision_reject" in result["trace"]

    def test_engine_rejects_with_adl_pressure_same_side(self):
        """REJECT when ADL pressure is high on same side as trade"""
        engine = FuturesStrategyEngine({"futures_trend_follow_v1": FuturesTrendFollowV1(trend_threshold=0.001)})
        result = engine.evaluate_symbol(
            strategy_id="futures_trend_follow_v1",
            market_state={
                "symbol": "BTCUSDT",
                "latest_price": 100,
                "trend_strength": 0.01,
                "trend_direction": "LONG",
                "volatility_regime": "TRENDING",
                "spread_state": "NORMAL",
                "funding_alignment": True,
            },
            risk_snapshot={
                "portfolio_leverage": 1.0,
                "margin_usage": 30,
                "avg_distance_to_liquidation": 40,
                "cascade_status": "NONE",
                "policy_state": "SAFE",
                "policy_action": "ALLOW",
                "policy_leverage_cap": 3,
                "adl_state": {
                    "risk_level": "HIGH",
                    "dominant_side": "LONG",
                    "portfolio_adl_risk": 0.9,
                },
            },
        )
        assert result["decision"] == "REJECT"
        assert result["reason_code"].startswith("ADL_")

    def test_engine_rejects_with_policy_critical(self):
        """REJECT when policy_state is CRITICAL (via policy engine at end of chain)"""
        engine = FuturesStrategyEngine({"futures_trend_follow_v1": FuturesTrendFollowV1(trend_threshold=0.001)})
        result = engine.evaluate_symbol(
            strategy_id="futures_trend_follow_v1",
            market_state={
                "symbol": "BTCUSDT",
                "latest_price": 100,
                "trend_strength": 0.01,
                "trend_direction": "LONG",
                "volatility_regime": "TRENDING",
                "spread_state": "NORMAL",
                "funding_alignment": True,
            },
            risk_snapshot={
                "portfolio_leverage": 1.0,
                "margin_usage": 20,
                "avg_distance_to_liquidation": 50,
                "cascade_status": "NONE",
                "policy_state": "CRITICAL",
                "policy_action": "ALLOW",  # Allow to pass through liquidation gate
                "policy_leverage_cap": 3,
                "adl_state": {
                    "risk_level": "LOW",
                    "dominant_side": "NONE",
                    "portfolio_adl_risk": 0.1,
                },
            },
        )
        assert result["decision"] == "REJECT"
        assert result["reason_code"] == "POLICY_BLOCK"

    def test_engine_run_cycle_multiple_symbols(self):
        """run_cycle processes multiple market states"""
        engine = FuturesStrategyEngine({"futures_trend_follow_v1": FuturesTrendFollowV1(trend_threshold=0.001)})
        results = engine.run_cycle(
            strategy_id="futures_trend_follow_v1",
            market_states=[
                {"symbol": "BTCUSDT", "latest_price": 100, "trend_strength": 0.01, "trend_direction": "LONG", "volatility_regime": "TRENDING", "spread_state": "NORMAL", "funding_alignment": True},
                {"symbol": "ETHUSDT", "latest_price": 50, "trend_strength": 0.01, "trend_direction": "SHORT", "volatility_regime": "TRENDING", "spread_state": "NORMAL", "funding_alignment": True},
            ],
            risk_snapshot={
                "portfolio_leverage": 1.0,
                "margin_usage": 20,
                "avg_distance_to_liquidation": 50,
                "cascade_status": "NONE",
                "policy_state": "SAFE",
                "policy_action": "ALLOW",
                "policy_leverage_cap": 3,
                "adl_state": {"risk_level": "LOW", "dominant_side": "NONE", "portfolio_adl_risk": 0.1},
            },
        )
        assert len(results) == 2
        assert results[0]["symbol"] == "BTCUSDT"
        assert results[1]["symbol"] == "ETHUSDT"


# ========== Paper Executor Tests ==========

class TestFuturesPaperExecutor:
    """Tests for paper executor synthetic lifecycle (no real orders)"""

    def test_paper_executor_creates_full_lifecycle(self):
        """Paper executor creates paper_position_opened and paper_position_closed events"""
        executor = FuturesPaperExecutor()
        result = executor.simulate(
            strategy_signal={"side": "LONG", "confidence": 0.85},
            market_state={"latest_price": 100, "spread_bps": 15, "trend_strength": 0.005},
        )
        assert result["paper_position_opened"] is True
        assert result["paper_position_closed"] is True
        assert isinstance(result["paper_pnl"], float)
        assert "entry_price" in result
        assert "exit_price" in result
        assert "expected_slippage_bps" in result
        assert "exit_reason" in result
        assert "lifecycle" in result
        assert result["lifecycle"] == ["paper_position_opened", "paper_position_closed"]
        # Check events
        assert len(result["events"]) == 2
        assert result["events"][0]["event"] == "paper_position_opened"
        assert result["events"][1]["event"] == "paper_position_closed"

    def test_paper_executor_short_side(self):
        """Paper executor handles SHORT side"""
        executor = FuturesPaperExecutor()
        result = executor.simulate(
            strategy_signal={"side": "SHORT", "confidence": 0.75},
            market_state={"latest_price": 100, "spread_bps": 10, "trend_strength": 0.004},
        )
        assert result["paper_position_opened"] is True
        assert result["paper_position_closed"] is True
        assert isinstance(result["paper_pnl"], float)

    def test_paper_executor_no_action_for_none_signal(self):
        """Paper executor returns no-op for NONE signal"""
        executor = FuturesPaperExecutor()
        result = executor.simulate(
            strategy_signal={"side": "NONE", "confidence": 0.0},
            market_state={"latest_price": 100, "spread_bps": 10, "trend_strength": 0.001},
        )
        assert result["paper_position_opened"] is False
        assert result["paper_position_closed"] is False
        assert result["paper_pnl"] == 0.0
        assert result["reason"] == "NO_ACTION_SIGNAL"
        assert result["events"] == []


# ========== API Endpoint Tests ==========

class TestFuturesStrategyAPIEndpoints:
    """Tests for /api/admin/futures/strategy/* endpoints"""

    def test_post_run_paper_cycle_returns_200(self, admin_client):
        """POST /api/admin/futures/strategy/run-paper-cycle returns 200"""
        response = admin_client.post(f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields
        assert "strategy" in data
        assert data["strategy"] == "futures_trend_follow_v1"
        assert "generated_at" in data
        assert "metrics" in data
        assert "signal_feed" in data
        assert "decision_trace" in data
        assert "paper_pnl_series" in data
        assert "reject_reason_breakdown" in data
        assert "confidence_distribution" in data

    def test_post_run_paper_cycle_metrics_fields(self, admin_client):
        """run-paper-cycle metrics contain expected counters"""
        response = admin_client.post(f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle")
        assert response.status_code == 200
        
        metrics = response.json().get("metrics", {})
        assert "futures_strategy_signal_total" in metrics
        assert "futures_strategy_allowed_total" in metrics
        assert "futures_strategy_rejected_total" in metrics
        assert "futures_strategy_confidence" in metrics
        assert "futures_strategy_paper_pnl" in metrics

    def test_get_strategy_status_returns_200(self, admin_client):
        """GET /api/admin/futures/strategy/status returns 200 with all fields"""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify all required fields
        assert "signal_feed" in data
        assert "decision_trace" in data
        assert "paper_pnl_series" in data
        assert "reject_reason_breakdown" in data
        assert "confidence_distribution" in data
        assert "metrics" in data

    def test_get_strategy_status_signal_feed_structure(self, admin_client):
        """signal_feed contains symbol, side, confidence, regime, reason"""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy/status")
        assert response.status_code == 200
        
        signal_feed = response.json().get("signal_feed", [])
        if signal_feed:
            signal = signal_feed[0]
            assert "symbol" in signal
            assert "side" in signal
            assert "confidence" in signal
            assert "regime" in signal
            assert "reason" in signal

    def test_get_strategy_status_decision_trace_structure(self, admin_client):
        """decision_trace contains full trace with gates"""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy/status")
        assert response.status_code == 200
        
        decision_trace = response.json().get("decision_trace", [])
        if decision_trace:
            trace = decision_trace[0]
            assert "strategy_id" in trace
            assert "symbol" in trace
            assert "side" in trace
            assert "decision" in trace
            assert "reason_code" in trace
            assert "trace" in trace

    def test_get_strategy_status_confidence_distribution_buckets(self, admin_client):
        """confidence_distribution has expected buckets"""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy/status")
        assert response.status_code == 200
        
        confidence_dist = response.json().get("confidence_distribution", [])
        buckets = [item["bucket"] for item in confidence_dist]
        assert "0.00-0.49" in buckets
        assert "0.50-0.69" in buckets
        assert "0.70-0.84" in buckets
        assert "0.85-1.00" in buckets


# ========== Regression Tests ==========

class TestRegressionFuturesRiskEndpoints:
    """Regression tests for existing futures risk endpoints"""

    def test_futures_risk_status_still_works(self, admin_client):
        """GET /api/admin/futures/risk/status returns 200"""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/risk/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "portfolio_leverage" in data
        assert "margin_usage" in data
        assert "policy_state" in data
        assert "decision_trace" in data

    def test_liquidation_protection_status_still_works(self, admin_client):
        """GET /api/admin/futures/liquidation-protection/status returns 200"""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/liquidation-protection/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "policy_state" in data
        assert "critical_positions" in data
        assert "gate_rejections" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
