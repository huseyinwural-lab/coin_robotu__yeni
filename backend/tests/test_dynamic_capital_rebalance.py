import sys
from datetime import datetime, timezone
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
    assert "governance_summary" in result


def test_dynamic_capital_rebalance_applies_weight_and_capital_caps():
    payload = [
        {
            "strategy_id": "alpha_cap_1",
            "capital_weight": 0.05,
            "max_capital": 10000,
            "current_capital": 3000,
            "performance_score": 95,
            "confidence_score": 10,
            "signal_decay": 0.05,
            "execution_quality_score": 95,
            "realized_return": 5.5,
            "risk_score": 0.1,
        },
        {
            "strategy_id": "alpha_cap_2",
            "capital_weight": 0.95,
            "max_capital": 10000,
            "current_capital": 8500,
            "performance_score": 10,
            "confidence_score": 80,
            "signal_decay": 0.8,
            "execution_quality_score": 40,
            "realized_return": -1.2,
            "risk_score": 0.7,
        },
    ]

    result = run_dynamic_capital_rebalance(
        payload,
        governance={
            "cadence_window_minutes": 1,
            "max_weight_shift_per_cycle": 0.2,
            "max_capital_shift_pct": 0.05,
            "drift_threshold": 0.08,
        },
    )

    event = next(item for item in result["events"] if item["strategy_id"] == "alpha_cap_1")
    assert event["max_weight_shift_applied"] is True
    assert event["max_capital_shift_applied"] is True
    assert abs(event["capital_shift"]) <= 500


def test_dynamic_capital_rebalance_blocks_within_cadence_window():
    payload = [
        {
            "strategy_id": "alpha_cadence_1",
            "capital_weight": 0.5,
            "max_capital": 10000,
            "current_capital": 5000,
            "last_rebalanced_at": "2026-03-17T10:00:00+00:00",
            "performance_score": 90,
            "confidence_score": 10,
            "signal_decay": 0.1,
            "execution_quality_score": 90,
            "realized_return": 3.2,
            "risk_score": 0.2,
        }
    ]

    result = run_dynamic_capital_rebalance(
        payload,
        governance={
            "cadence_window_minutes": 30,
            "max_weight_shift_per_cycle": 0.2,
            "max_capital_shift_pct": 0.2,
            "drift_threshold": 0.08,
        },
        now_ts=datetime(2026, 3, 17, 10, 10, tzinfo=timezone.utc),
    )

    event = result["events"][0]
    assert event["cadence_window_blocked"] is True
    assert event["new_strategy_weight"] == event["old_strategy_weight"]
    assert result["governance_summary"]["cadence_blocked_strategies"] == 1
