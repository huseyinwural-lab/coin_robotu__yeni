# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.portfolio.strategy_exposure_tracker import StrategyExposureTracker


def test_strategy_exposure_tracker_computes_symbol_and_strategy_exposure():
    tracker = StrategyExposureTracker(max_symbol_exposure=8.0, max_strategy_exposure=8.0, max_cluster_exposure=12.0)
    payload = tracker.compute(
        [
            {
                "decision": "ALLOW",
                "symbol": "BTCUSDT",
                "strategy": "trend_follow_v1",
                "confidence": 0.8,
                "leverage_decision": {"final_leverage": 3.0, "position_size_ratio": 0.7},
            },
            {
                "decision": "ALLOW",
                "symbol": "ETHUSDT",
                "strategy": "breakout_v1",
                "confidence": 0.75,
                "leverage_decision": {"final_leverage": 2.5, "position_size_ratio": 0.6},
            },
        ]
    )
    assert payload["symbol_exposure"]["BTCUSDT"] > 0
    assert payload["strategy_exposure"]["trend_follow_v1"] > 0
    assert payload["cluster_exposure"]["MAJOR_CLUSTER"] > 0


def test_strategy_exposure_tracker_blocks_when_limits_exceeded():
    tracker = StrategyExposureTracker(max_symbol_exposure=1.8, max_strategy_exposure=5.0, max_cluster_exposure=5.0)
    adjusted, blocked, exposure = tracker.apply(
        [
            {
                "decision": "ALLOW",
                "symbol": "BTCUSDT",
                "strategy": "trend_follow_v1",
                "confidence": 0.85,
                "leverage_decision": {"final_leverage": 3.0, "position_size_ratio": 0.8},
            },
            {
                "decision": "ALLOW",
                "symbol": "BTCUSDT",
                "strategy": "breakout_v1",
                "confidence": 0.6,
                "leverage_decision": {"final_leverage": 2.0, "position_size_ratio": 0.7},
            },
        ]
    )
    assert len(blocked) >= 1
    assert blocked[0]["reason_code"] == "GATE_REJECT"
    assert blocked[0]["decision_layer"] == "PORTFOLIO"
    assert len([row for row in adjusted if row.get("decision") == "ALLOW"]) == 1
    assert exposure["blocked_total"] >= 1
