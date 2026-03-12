import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategy.futures.futures_strategy_engine import FuturesStrategyEngine
from core.strategy.futures.futures_trend_follow_v1 import FuturesTrendFollowV1


def test_strategy_engine_rejects_with_adl_pressure_when_side_matches():
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


def test_strategy_engine_allow_path_returns_trace():
    engine = FuturesStrategyEngine({"futures_trend_follow_v1": FuturesTrendFollowV1(trend_threshold=0.001)})
    result = engine.evaluate_symbol(
        strategy_id="futures_trend_follow_v1",
        market_state={
            "symbol": "ETHUSDT",
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
            "avg_distance_to_liquidation": 40,
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
    assert "paper_decision_allow" in result["trace"]
