# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.governance.strategy_health_monitor import build_strategy_health_snapshot


def test_strategy_health_monitor_builds_scores_with_components():
    history = [
        {
            "ts": "2026-03-12T01:00:00+00:00",
            "strategy_metrics": [
                {
                    "strategy": "mean_reversion_v1",
                    "paper_pnl": 0.001,
                    "execution_quality": 0.72,
                    "avg_confidence": 0.62,
                }
            ],
            "strategy_attribution": [{"strategy": "mean_reversion_v1", "win_rate": 0.58}],
        },
        {
            "ts": "2026-03-12T02:00:00+00:00",
            "strategy_metrics": [
                {
                    "strategy": "mean_reversion_v1",
                    "paper_pnl": 0.0005,
                    "execution_quality": 0.69,
                    "avg_confidence": 0.64,
                }
            ],
            "strategy_attribution": [{"strategy": "mean_reversion_v1", "win_rate": 0.61}],
        },
    ]
    payload = build_strategy_health_snapshot(
        history=history,
        strategy_metrics=[{"strategy": "mean_reversion_v1", "paper_pnl": 0.0004, "execution_quality": 0.7, "avg_confidence": 0.63}],
        strategy_attribution=[{"strategy": "mean_reversion_v1", "win_rate": 0.6}],
    )

    assert len(payload["strategies"]) == 1
    row = payload["strategies"][0]
    assert row["strategy"] == "mean_reversion_v1"
    assert 0 <= row["strategy_health_score"] <= 100
    assert "pnl_component" in row["health_components"]
    assert "execution_quality_component" in row["health_components"]


def test_strategy_health_monitor_controlled_degrade_for_low_observation():
    payload = build_strategy_health_snapshot(
        history=[],
        strategy_metrics=[{"strategy": "breakout_v1", "paper_pnl": 0.0, "execution_quality": 0.5, "avg_confidence": 0.5}],
        strategy_attribution=[],
        min_observation_threshold=3,
    )
    row = payload["strategies"][0]
    assert row["data_state"] == "CONTROLLED_DEGRADE"
    assert "insufficient_observation" in row["missing_components"]
