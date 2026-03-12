import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.portfolio.strategy_interaction_guard import StrategyInteractionGuard


def test_interaction_guard_blocks_conflicting_long_short_for_same_symbol():
    guard = StrategyInteractionGuard(max_same_side_per_symbol=2)
    decisions, blocked = guard.apply(
        [
            {"symbol": "BTCUSDT", "strategy": "trend_follow_v1", "decision": "ALLOW", "side": "LONG", "confidence": 0.61},
            {"symbol": "BTCUSDT", "strategy": "breakout_v1", "decision": "ALLOW", "side": "SHORT", "confidence": 0.84},
        ]
    )
    assert len(blocked) == 1
    assert blocked[0]["reasons"][-1] == "STRATEGY_INTERACTION_CONFLICT"
    assert len([row for row in decisions if row.get("decision") == "ALLOW"]) == 1


def test_interaction_guard_limits_same_side_stacking():
    guard = StrategyInteractionGuard(max_same_side_per_symbol=2)
    decisions, blocked = guard.apply(
        [
            {"symbol": "ETHUSDT", "strategy": "trend_follow_v1", "decision": "ALLOW", "side": "LONG", "confidence": 0.8},
            {"symbol": "ETHUSDT", "strategy": "mean_reversion_v1", "decision": "ALLOW", "side": "LONG", "confidence": 0.7},
            {"symbol": "ETHUSDT", "strategy": "breakout_v1", "decision": "ALLOW", "side": "LONG", "confidence": 0.6},
        ]
    )
    assert len([row for row in decisions if row.get("decision") == "ALLOW"]) == 2
    assert len(blocked) == 1
    assert blocked[0]["reasons"][-1] == "STRATEGY_INTERACTION_STACKED"
