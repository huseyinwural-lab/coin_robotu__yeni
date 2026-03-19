# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.governance.strategy_throttle_engine import build_strategy_throttle_state


def test_throttle_engine_escalates_with_decay_event():
    health_rows = [{"strategy": "mean_reversion_v1", "strategy_health_score": 58}]
    decay_events = [{"strategy": "mean_reversion_v1", "severity": "HIGH"}]
    payload = build_strategy_throttle_state(health_rows, decay_events)
    row = payload["strategy_throttle_state"][0]
    assert row["throttle_level"] == "L3"
    assert row["max_position_ratio"] < 0.5


def test_throttle_engine_recovers_stepwise():
    health_rows = [{"strategy": "trend_follow_v1", "strategy_health_score": 78}]
    previous_state = {"trend_follow_v1": {"throttle_level": "L2"}}
    payload = build_strategy_throttle_state(health_rows, [], previous_state=previous_state)
    row = payload["strategy_throttle_state"][0]
    assert row["throttle_level"] == "L1"
