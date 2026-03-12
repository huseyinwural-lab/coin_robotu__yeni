import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.leverage.leverage_engine import LeverageEngine


def test_leverage_engine_outputs_deterministic_decision_contract():
    engine = LeverageEngine()
    result = engine.evaluate(
        symbol="BTCUSDT",
        strategy="futures_trend_follow_v1",
        side="LONG",
        base_leverage=3.0,
        confidence=0.78,
        microstructure_risk_score=0.25,
        execution_suitability={"severity": "LOW", "max_allowed_size_ratio": 1.0},
        spread_state="NORMAL",
        depth_state="NORMAL",
        distance_to_liquidation=18,
        funding_bias={"bias_direction": "NEUTRAL", "funding_pressure_state": "LOW"},
        portfolio_leverage=1.4,
    )
    decision = result["decision"]
    assert 1.0 <= decision["final_leverage"] <= 5.0
    assert 0.0 <= decision["position_size_ratio"] <= 1.0
    assert "confidence_multiplier" in result["decision_trace_extension"]


def test_leverage_engine_clamps_under_bad_conditions():
    engine = LeverageEngine()
    result = engine.evaluate(
        symbol="ETHUSDT",
        strategy="futures_trend_follow_v1",
        side="LONG",
        base_leverage=5.0,
        confidence=0.32,
        microstructure_risk_score=0.92,
        execution_suitability={"severity": "BLOCKED", "max_allowed_size_ratio": 0.2},
        spread_state="SHOCK",
        depth_state="CRITICAL",
        distance_to_liquidation=6,
        funding_bias={"bias_direction": "LONG_BIAS", "funding_pressure_state": "HIGH"},
        portfolio_leverage=2.7,
    )
    decision = result["decision"]
    assert decision["final_leverage"] <= 2.0
    assert decision["position_size_ratio"] <= 0.35
