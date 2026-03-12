import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.capital_rebalance_engine import run_dynamic_capital_rebalance


def test_dynamic_capital_rebalance_engine_returns_adjustments():
    payload = [
        {
            "strategy_id": "alpha_1",
            "capital_weight": 0.25,
            "max_capital": 20000,
            "current_capital": 15000,
            "performance_score": 84,
            "confidence_score": 72,
            "signal_decay": 0.2,
            "execution_quality_score": 88,
            "realized_return": 3.2,
            "risk_score": 0.25,
        },
        {
            "strategy_id": "alpha_2",
            "capital_weight": 0.55,
            "max_capital": 20000,
            "current_capital": 18000,
            "performance_score": 42,
            "confidence_score": 64,
            "signal_decay": 0.66,
            "execution_quality_score": 55,
            "realized_return": 0.8,
            "risk_score": 0.6,
        },
    ]

    result = run_dynamic_capital_rebalance(payload)
    assert "events" in result
    assert len(result["events"]) == 2
    assert result["allocation_drift"] >= 0
    assert any(event["throttle_signal"] for event in result["events"])
