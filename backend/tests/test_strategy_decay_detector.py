import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.governance.strategy_decay_detector import detect_strategy_decay


def test_decay_detector_requires_persistence_before_event():
    health_rows = [
        {
            "strategy": "trend_follow_v1",
            "strategy_pnl_rolling": -0.002,
            "strategy_win_rate_rolling": 0.3,
            "strategy_confidence_vs_result": 0.62,
            "strategy_execution_quality": 0.4,
            "observation_count": 9,
        }
    ]

    first = detect_strategy_decay(health_rows, previous_state={})
    assert first["event_count"] == 0

    second = detect_strategy_decay(health_rows, previous_state=first["decay_state"])
    assert second["event_count"] == 1
    event = second["strategy_decay_events"][0]
    assert event["event"] == "STRATEGY_DECAY_DETECTED"
    assert event["decay_type"] == "MULTI_TRIGGER"


def test_decay_detector_tracks_repeated_decay_count():
    health_rows = [
        {
            "strategy": "breakout_v1",
            "strategy_pnl_rolling": -0.002,
            "strategy_win_rate_rolling": 0.31,
            "strategy_confidence_vs_result": 0.6,
            "strategy_execution_quality": 0.38,
            "observation_count": 8,
        }
    ]
    state = {}
    for _ in range(4):
        result = detect_strategy_decay(health_rows, previous_state=state)
        state = result["decay_state"]

    assert state["breakout_v1"]["repeated_decay_count"] >= 3
