import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategy.futures.futures_trend_follow_v1 import FuturesTrendFollowV1


def test_trend_follow_generates_long_signal_when_all_conditions_match():
    strategy = FuturesTrendFollowV1(trend_threshold=0.002)
    signal = strategy.generate_signal(
        {
            "symbol": "BTCUSDT",
            "trend_strength": 0.0045,
            "trend_direction": "LONG",
            "volatility_regime": "TRENDING",
            "spread_state": "NORMAL",
            "funding_alignment": True,
        }
    )
    assert signal.side == "LONG"
    assert signal.confidence > 0
    assert signal.reason == "TREND_FUNDING_ALIGNED"


def test_trend_follow_rejects_when_spread_shock():
    strategy = FuturesTrendFollowV1()
    signal = strategy.generate_signal(
        {
            "symbol": "ETHUSDT",
            "trend_strength": 0.01,
            "trend_direction": "SHORT",
            "volatility_regime": "TRENDING",
            "spread_state": "SHOCK",
            "funding_alignment": True,
        }
    )
    assert signal.side == "NONE"
    assert signal.reason == "SPREAD_SHOCK"
