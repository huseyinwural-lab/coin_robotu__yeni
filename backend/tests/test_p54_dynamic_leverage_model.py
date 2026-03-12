"""
Phase 5.4 Dynamic Leverage Model Test Suite
Test: Leverage modülleri deterministic çalışıyor mu, paper decision flow leverage içeriyor mu,
decision trace contract leverage alanlarını içeriyor mu, endpoints contract alanlarını dönüyor mu
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
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture(scope="module")
def admin_token():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL tanımlı değil")
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30,
        )
    except requests.RequestException as exc:
        pytest.skip(f"Auth endpoint erişilemedi: {exc}")
    if response.status_code != 200:
        pytest.skip(f"Admin login başarısız: {response.text}")
    return response.json()["access_token"]


# ============================================================================
# LEVERAGE MODULE DETERMINISM TESTS
# ============================================================================


class TestConfidenceScalerDeterministic:
    """confidence_scaler modülü deterministic çalışıyor mu"""

    def test_confidence_scaler_deterministic_low_confidence(self):
        from core.futures.leverage.confidence_scaler import ConfidenceScaler
        scaler = ConfidenceScaler()
        for _ in range(3):
            r1 = scaler.evaluate(0.35)
            r2 = scaler.evaluate(0.35)
            assert r1 == r2, "ConfidenceScaler not deterministic"
        assert r1["confidence_leverage_multiplier"] == 0.7

    def test_confidence_scaler_deterministic_mid_confidence(self):
        from core.futures.leverage.confidence_scaler import ConfidenceScaler
        scaler = ConfidenceScaler()
        r = scaler.evaluate(0.55)
        assert r["confidence_leverage_multiplier"] == 1.0

    def test_confidence_scaler_deterministic_high_confidence(self):
        from core.futures.leverage.confidence_scaler import ConfidenceScaler
        scaler = ConfidenceScaler()
        r = scaler.evaluate(0.88)
        assert r["confidence_leverage_multiplier"] == 1.2


class TestMicrostructureScalerDeterministic:
    """microstructure_scaler modülü deterministic çalışıyor mu"""

    def test_microstructure_scaler_deterministic(self):
        from core.futures.leverage.microstructure_scaler import MicrostructureScaler
        scaler = MicrostructureScaler()
        kwargs = {
            "microstructure_risk_score": 0.45,
            "execution_suitability": {"severity": "MEDIUM", "max_allowed_size_ratio": 0.8},
            "spread_state": "ELEVATED",
            "depth_state": "WARNING",
        }
        for _ in range(3):
            r1 = scaler.evaluate(**kwargs)
            r2 = scaler.evaluate(**kwargs)
            assert r1 == r2, "MicrostructureScaler not deterministic"

    def test_microstructure_scaler_shock_depth_critical(self):
        from core.futures.leverage.microstructure_scaler import MicrostructureScaler
        scaler = MicrostructureScaler()
        r = scaler.evaluate(
            microstructure_risk_score=0.9,
            execution_suitability={"severity": "BLOCKED", "max_allowed_size_ratio": 0.3},
            spread_state="SHOCK",
            depth_state="CRITICAL",
        )
        assert r["liquidity_adjusted_leverage"] < 0.4
        assert r["size_clamp_ratio"] <= 0.35


class TestLiquidationScalerDeterministic:
    """liquidation_scaler modülü deterministic çalışıyor mu"""

    def test_liquidation_scaler_deterministic(self):
        from core.futures.leverage.liquidation_scaler import LiquidationScaler
        scaler = LiquidationScaler()
        for _ in range(3):
            r1 = scaler.evaluate(10)
            r2 = scaler.evaluate(10)
            assert r1 == r2, "LiquidationScaler not deterministic"

    def test_liquidation_scaler_very_low_distance(self):
        from core.futures.leverage.liquidation_scaler import LiquidationScaler
        scaler = LiquidationScaler()
        r = scaler.evaluate(5)
        assert r["liquidation_adjustment"] == 0.45
        assert r["liquidation_size_clamp_ratio"] == 0.35

    def test_liquidation_scaler_safe_distance(self):
        from core.futures.leverage.liquidation_scaler import LiquidationScaler
        scaler = LiquidationScaler()
        r = scaler.evaluate(25)
        assert r["liquidation_adjustment"] == 1.0
        assert r["liquidation_size_clamp_ratio"] == 1.0


class TestFundingScalerDeterministic:
    """funding_scaler modülü deterministic çalışıyor mu"""

    def test_funding_scaler_deterministic(self):
        from core.futures.leverage.funding_scaler import FundingScaler
        scaler = FundingScaler()
        kwargs = {
            "side": "LONG",
            "funding_bias": {"bias_direction": "SHORT_BIAS", "funding_pressure_state": "MEDIUM"},
        }
        for _ in range(3):
            r1 = scaler.evaluate(**kwargs)
            r2 = scaler.evaluate(**kwargs)
            assert r1 == r2, "FundingScaler not deterministic"

    def test_funding_scaler_long_under_long_bias_pressure(self):
        from core.futures.leverage.funding_scaler import FundingScaler
        scaler = FundingScaler()
        r = scaler.evaluate(
            side="LONG",
            funding_bias={"bias_direction": "LONG_BIAS", "funding_pressure_state": "HIGH"},
        )
        assert r["funding_adjustment_factor"] == 0.7


class TestPortfolioLeverageGuardDeterministic:
    """portfolio_leverage_guard modülü deterministic çalışıyor mu"""

    def test_portfolio_guard_deterministic(self):
        from core.futures.leverage.portfolio_leverage_guard import PortfolioLeverageGuard
        guard = PortfolioLeverageGuard()
        for _ in range(3):
            r1 = guard.evaluate(portfolio_leverage=2.2, proposed_leverage=3.8)
            r2 = guard.evaluate(portfolio_leverage=2.2, proposed_leverage=3.8)
            assert r1 == r2, "PortfolioLeverageGuard not deterministic"

    def test_portfolio_guard_high_portfolio_leverage(self):
        from core.futures.leverage.portfolio_leverage_guard import PortfolioLeverageGuard
        guard = PortfolioLeverageGuard()
        r = guard.evaluate(portfolio_leverage=2.8, proposed_leverage=4.5)
        assert r["portfolio_adjustment_factor"] == 0.55


class TestLeverageEngineDeterministic:
    """leverage_engine modülü deterministic çalışıyor mu"""

    def test_leverage_engine_deterministic(self):
        from core.futures.leverage.leverage_engine import LeverageEngine
        engine = LeverageEngine()
        kwargs = {
            "symbol": "BTCUSDT",
            "strategy": "futures_trend_follow_v1",
            "side": "LONG",
            "base_leverage": 2.5,
            "confidence": 0.72,
            "microstructure_risk_score": 0.25,
            "execution_suitability": {"severity": "LOW", "max_allowed_size_ratio": 0.95},
            "spread_state": "NORMAL",
            "depth_state": "NORMAL",
            "distance_to_liquidation": 16,
            "funding_bias": {"bias_direction": "NEUTRAL", "funding_pressure_state": "LOW"},
            "portfolio_leverage": 1.3,
        }
        for _ in range(3):
            r1 = engine.evaluate(**kwargs)
            r2 = engine.evaluate(**kwargs)
            assert r1["decision"]["final_leverage"] == r2["decision"]["final_leverage"]
            assert r1["decision"]["position_size_ratio"] == r2["decision"]["position_size_ratio"]

    def test_leverage_engine_outputs_decision_trace_extension(self):
        from core.futures.leverage.leverage_engine import LeverageEngine
        engine = LeverageEngine()
        r = engine.evaluate(
            symbol="ETHUSDT",
            strategy="futures_trend_follow_v1",
            side="SHORT",
            base_leverage=3.0,
            confidence=0.65,
            microstructure_risk_score=0.3,
            execution_suitability={"severity": "LOW", "max_allowed_size_ratio": 1.0},
            spread_state="NORMAL",
            depth_state="NORMAL",
            distance_to_liquidation=18,
            funding_bias={"bias_direction": "LONG_BIAS", "funding_pressure_state": "LOW"},
            portfolio_leverage=1.5,
        )
        ext = r["decision_trace_extension"]
        assert "leverage_decision" in ext
        assert "confidence_multiplier" in ext
        assert "microstructure_multiplier" in ext
        assert "liquidation_multiplier" in ext
        assert "funding_multiplier" in ext
        assert "final_leverage" in ext
        assert "position_size_ratio" in ext


# ============================================================================
# DECISION TRACE CONTRACT WITH LEVERAGE FIELDS
# ============================================================================


class TestDecisionTraceContractLeverageFields:
    """decision trace contract leverage alanlarını içeriyor mu"""

    def test_decision_trace_model_has_leverage_fields(self):
        from core.futures.decision.decision_trace_model import FuturesDecisionTrace
        trace = FuturesDecisionTrace(
            trace_id="test-id",
            timestamp="2026-03-12T10:00:00Z",
            symbol="BTCUSDT",
            strategy="futures_trend_follow_v1",
            side="LONG",
            signal_confidence=0.82,
            regime="TRENDING",
            microstructure_result="PASS",
            risk_result="PASS",
            liquidation_result="PASS",
            adl_result="PASS",
            leverage_decision="dynamic",
            confidence_multiplier=1.2,
            microstructure_multiplier=0.92,
            liquidation_multiplier=0.85,
            funding_multiplier=1.0,
            final_leverage=2.8,
            position_size_ratio=0.75,
            final_decision="ALLOW",
            reason_code="ALLOW",
            decision_layer="GATE",
        )
        assert trace.leverage_decision == "dynamic"
        assert trace.confidence_multiplier == 1.2
        assert trace.microstructure_multiplier == 0.92
        assert trace.liquidation_multiplier == 0.85
        assert trace.funding_multiplier == 1.0
        assert trace.final_leverage == 2.8
        assert trace.position_size_ratio == 0.75

    def test_build_decision_trace_outputs_leverage_fields(self):
        from core.futures.decision.decision_trace_model import build_decision_trace
        trace = build_decision_trace(
            symbol="ETHUSDT",
            strategy="futures_trend_follow_v1",
            side="SHORT",
            signal_confidence=0.68,
            regime="VOLATILE",
            microstructure_result="PASS",
            risk_result="PASS",
            liquidation_result="PASS",
            adl_result="PASS",
            leverage_decision="dynamic",
            confidence_multiplier=1.0,
            microstructure_multiplier=0.78,
            liquidation_multiplier=0.65,
            funding_multiplier=1.08,
            final_leverage=1.9,
            position_size_ratio=0.45,
            final_decision="ALLOW",
            reason_code="ALLOW",
            decision_layer="GATE",
        )
        assert trace["leverage_decision"] == "dynamic"
        assert trace["confidence_multiplier"] == 1.0
        assert trace["microstructure_multiplier"] == 0.78
        assert trace["liquidation_multiplier"] == 0.65
        assert trace["funding_multiplier"] == 1.08
        assert trace["final_leverage"] == 1.9
        assert trace["position_size_ratio"] == 0.45


# ============================================================================
# PAPER DECISION FLOW WITH DYNAMIC LEVERAGE STEP
# ============================================================================


class TestPaperDecisionFlowWithDynamicLeverage:
    """Paper decision flow zinciri dynamic leverage adımını içeriyor mu"""

    def test_paper_decision_flow_trace_includes_dynamic_leverage_engine(self):
        from core.strategy.futures_paper_decision_flow import run_futures_paper_decision_flow
        from dataclasses import dataclass

        @dataclass
        class MockPosition:
            leverage: float = 2.0

        result = run_futures_paper_decision_flow(
            signal={"symbol": "BTCUSDT", "side": "LONG", "confidence": 0.78, "regime": "TRENDING"},
            position=MockPosition(),
            portfolio_state={
                "distance_to_liquidation": 22,
                "margin_usage": 0.25,
                "portfolio_leverage": 1.1,
            },
            policy_state={"policy_state": "SAFE", "policy_action": "ALLOW"},
            funding_bias={"bias_direction": "NEUTRAL", "funding_pressure_state": "LOW"},
            microstructure_result={
                "gate": {"gate_pass": True, "gate_reason": ""},
                "execution_suitability": {"execution_suitable": True, "max_allowed_size_ratio": 1.0},
                "aggregate": {"microstructure_risk_score": 0.12},
                "spread": {"spread_state": "NORMAL"},
                "thinning": {"thinning_state": "NORMAL"},
            },
            strategy_id="futures_trend_follow_v1",
        )
        assert "dynamic_leverage_engine" in result["trace"]
        assert "leverage_decision" in result
        assert "leverage_trace_extension" in result

    def test_paper_decision_flow_leverage_trace_extension_complete(self):
        from core.strategy.futures_paper_decision_flow import run_futures_paper_decision_flow
        from dataclasses import dataclass

        @dataclass
        class MockPosition:
            leverage: float = 3.0

        result = run_futures_paper_decision_flow(
            signal={"symbol": "ETHUSDT", "side": "SHORT", "confidence": 0.65, "regime": "VOLATILE"},
            position=MockPosition(),
            portfolio_state={
                "distance_to_liquidation": 14,
                "margin_usage": 0.4,
                "portfolio_leverage": 1.7,
            },
            policy_state={"policy_state": "SAFE", "policy_action": "ALLOW"},
            funding_bias={"bias_direction": "LONG_BIAS", "funding_pressure_state": "LOW"},
            microstructure_result={
                "gate": {"gate_pass": True},
                "execution_suitability": {"execution_suitable": True, "max_allowed_size_ratio": 0.9},
                "aggregate": {"microstructure_risk_score": 0.22},
                "spread": {"spread_state": "NORMAL"},
                "thinning": {"thinning_state": "NORMAL"},
            },
            strategy_id="futures_trend_follow_v1",
        )
        ext = result["leverage_trace_extension"]
        required_keys = [
            "leverage_decision",
            "confidence_multiplier",
            "microstructure_multiplier",
            "liquidation_multiplier",
            "funding_multiplier",
            "final_leverage",
            "position_size_ratio",
        ]
        for key in required_keys:
            assert key in ext, f"Missing key in leverage_trace_extension: {key}"

    def test_paper_decision_flow_decision_trace_model_has_leverage(self):
        from core.strategy.futures_paper_decision_flow import run_futures_paper_decision_flow
        from dataclasses import dataclass

        @dataclass
        class MockPosition:
            leverage: float = 2.5

        result = run_futures_paper_decision_flow(
            signal={"symbol": "BTCUSDT", "side": "LONG", "confidence": 0.82, "regime": "TRENDING"},
            position=MockPosition(),
            portfolio_state={
                "distance_to_liquidation": 18,
                "margin_usage": 0.3,
                "portfolio_leverage": 1.4,
            },
            policy_state={"policy_state": "SAFE", "policy_action": "ALLOW"},
            funding_bias={"bias_direction": "NEUTRAL", "funding_pressure_state": "LOW"},
            microstructure_result={
                "gate": {"gate_pass": True},
                "execution_suitability": {"execution_suitable": True, "max_allowed_size_ratio": 1.0},
                "aggregate": {"microstructure_risk_score": 0.1},
                "spread": {"spread_state": "NORMAL"},
                "thinning": {"thinning_state": "NORMAL"},
            },
            strategy_id="futures_trend_follow_v1",
        )
        trace_model = result.get("decision_trace_model", {})
        assert trace_model.get("leverage_decision") is not None
        assert trace_model.get("confidence_multiplier") is not None
        assert trace_model.get("microstructure_multiplier") is not None
        assert trace_model.get("liquidation_multiplier") is not None
        assert trace_model.get("funding_multiplier") is not None
        assert trace_model.get("final_leverage") is not None
        assert trace_model.get("position_size_ratio") is not None


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================


class TestLeverageStatusEndpoint:
    """GET /api/admin/futures/leverage/status endpoint contract alanlarını dönüyor mu"""

    def test_leverage_status_returns_200(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/leverage/status", headers=headers, timeout=25)
        assert response.status_code == 200

    def test_leverage_status_contract_fields(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        requests.post(f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle", headers=headers, timeout=30)
        response = requests.get(f"{BASE_URL}/api/admin/futures/leverage/status", headers=headers, timeout=25)
        assert response.status_code == 200
        payload = response.json()
        required_fields = [
            "symbol",
            "strategy",
            "confidence",
            "microstructure_quality",
            "liquidation_distance",
            "funding_bias",
            "final_leverage",
            "size_ratio",
            "leverage_distribution",
            "size_clamp_events",
            "confidence_vs_leverage",
            "liquidation_distance_vs_leverage",
        ]
        for field in required_fields:
            assert field in payload, f"Missing field in leverage/status: {field}"


class TestStrategyStatusRegressionWithLeverage:
    """GET /api/admin/futures/strategy/status regression - leverage fields"""

    def test_strategy_status_returns_200(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/strategy/status", headers=headers, timeout=25)
        assert response.status_code == 200

    def test_strategy_status_decision_trace_has_leverage_decision(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        requests.post(f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle", headers=headers, timeout=30)
        response = requests.get(f"{BASE_URL}/api/admin/futures/strategy/status", headers=headers, timeout=25)
        payload = response.json()
        if payload.get("decision_trace"):
            first_decision = payload["decision_trace"][0]
            # leverage_decision is in decision_trace_model when populated
            trace_model = first_decision.get("decision_trace_model", {})
            assert "leverage_decision" in trace_model, "leverage_decision not in decision_trace_model"
            assert "final_leverage" in trace_model, "final_leverage not in decision_trace_model"
            assert "position_size_ratio" in trace_model, "position_size_ratio not in decision_trace_model"


class TestDecisionDiagnosticsRegressionWithLeverage:
    """GET /api/admin/futures/decision-diagnostics regression - leverage fields"""

    def test_decision_diagnostics_returns_200(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/decision-diagnostics", headers=headers, timeout=25)
        assert response.status_code == 200

    def test_decision_diagnostics_has_leverage_fields(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/decision-diagnostics", headers=headers, timeout=25)
        payload = response.json()
        required_fields = [
            "leverage_distribution",
            "size_clamp_events",
            "confidence_vs_leverage",
            "liquidation_distance_vs_leverage",
        ]
        for field in required_fields:
            assert field in payload, f"Missing leverage field in decision-diagnostics: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
