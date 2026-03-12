import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.strategy_conflict_engine import detect_conflicts_for_signal


def test_strategy_conflict_resolver_detects_and_resolves_conflict():
    active_signals = [
        {
            "strategy_id": "mean_reversion_v1",
            "symbol": "BTCUSDT",
            "signal_direction": "sell",
            "confidence_score": 0.82,
        },
        {
            "strategy_id": "breakout_v3",
            "symbol": "BTCUSDT",
            "signal_direction": "buy",
            "confidence_score": 0.68,
        },
    ]
    strategy_stats = {
        "mean_reversion_v1": {"state": "ACTIVE", "performance_score": 76, "signal_decay": 0.22},
        "breakout_v3": {"state": "ACTIVE", "performance_score": 58, "signal_decay": 0.35},
    }

    result = detect_conflicts_for_signal(
        active_signals=active_signals,
        strategy_id="breakout_v3",
        symbol="BTCUSDT",
        signal_direction="buy",
        confidence_score=0.68,
        strategy_stats=strategy_stats,
    )
    assert result["conflict_detected"] is True
    assert result["winning_strategy"] == "mean_reversion_v1"
    assert result["losing_strategy"] == "breakout_v3"
    assert result["conflict_count"] >= 1
