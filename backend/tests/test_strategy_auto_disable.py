# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.governance.strategy_auto_disable import evaluate_strategy_auto_disable


def test_auto_disable_triggers_when_multiple_conditions_met():
    rows = [
        {
            "strategy": "breakout_v1",
            "strategy_health_score": 18,
            "strategy_pnl_rolling": -0.006,
            "drawdown_state": "LIMIT_BREACH",
        }
    ]
    result = evaluate_strategy_auto_disable(
        rows,
        decay_state={"breakout_v1": {"repeated_decay_count": 4}},
        lifecycle_registry={},
    )
    state = result["strategy_disable_state"][0]
    assert state["should_disable"] is True
    assert result["disable_events"][0]["event"] == "STRATEGY_DISABLED"


def test_auto_disable_keeps_disabled_locked():
    rows = [{"strategy": "trend_follow_v1", "strategy_health_score": 80, "strategy_pnl_rolling": 0.002, "drawdown_state": "NORMAL"}]
    result = evaluate_strategy_auto_disable(
        rows,
        decay_state={"trend_follow_v1": {"repeated_decay_count": 0}},
        lifecycle_registry={"trend_follow_v1": {"lifecycle_state": "DISABLED"}},
    )
    state = result["strategy_disable_state"][0]
    assert state["disable_state"] == "DISABLED"
    assert state["controlled_recovery_state"] == "OBSERVE_ONLY"
