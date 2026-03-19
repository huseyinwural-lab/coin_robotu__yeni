# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.governance.strategy_lifecycle_registry import (
    apply_lifecycle_transitions,
    enforce_strategy_lifecycle_on_decisions,
)


def test_lifecycle_transitions_follow_registry_rules():
    payload = apply_lifecycle_transitions(
        strategy_ids=["trend_follow_v1"],
        existing_registry={"trend_follow_v1": {"strategy": "trend_follow_v1", "lifecycle_state": "ACTIVE", "transition_history": []}},
        throttle_by_strategy={"trend_follow_v1": {"throttle_level": "L2"}},
        disable_by_strategy={"trend_follow_v1": {"should_disable": False}},
    )
    row = payload["registry"]["trend_follow_v1"]
    assert row["lifecycle_state"] == "THROTTLED"
    assert len(payload["transitions"]) == 1


def test_disabled_strategy_hard_block_enforced():
    decisions = [
        {
            "symbol": "BTCUSDT",
            "strategy": "breakout_v1",
            "decision": "ALLOW",
            "reasons": [],
            "confidence": 0.8,
            "leverage_decision": {"position_size_ratio": 0.9, "final_leverage": 3},
        }
    ]
    adjusted, summary = enforce_strategy_lifecycle_on_decisions(
        decisions,
        lifecycle_registry={"breakout_v1": {"lifecycle_state": "DISABLED"}},
        throttle_by_strategy={},
    )
    assert adjusted[0]["decision"] == "REJECT"
    assert "STRATEGY_DISABLED_HARD_BLOCK" in adjusted[0]["reasons"]
    assert summary["disabled_blocked_total"] == 1
