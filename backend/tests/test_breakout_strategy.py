# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.futures_breakout_v1 import FuturesBreakoutV1


def test_breakout_generates_long_signal_when_confirmed():
    strategy = FuturesBreakoutV1()
    signal = strategy.generate_signal(
        {
            "latest_price": 105.0,
            "range_high": 103.0,
            "range_low": 96.0,
            "atr": 0.03,
            "atr_baseline": 0.02,
            "volatility_compression": 0.8,
            "volume_spike_ratio": 1.45,
            "microstructure_suitable": True,
        }
    )
    assert signal["signal"] == "LONG"
    assert signal["confidence"] > 0
    assert signal["context"]["reason"] == "BREAKOUT_CONFIRMED"


def test_breakout_filters_without_volume_confirmation():
    strategy = FuturesBreakoutV1()
    signal = strategy.generate_signal(
        {
            "latest_price": 105.0,
            "range_high": 103.0,
            "range_low": 96.0,
            "atr": 0.03,
            "atr_baseline": 0.02,
            "volatility_compression": 0.8,
            "volume_spike_ratio": 1.01,
            "microstructure_suitable": True,
        }
    )
    assert signal["signal"] == "NONE"
    assert signal["confidence"] == 0.0
    assert signal["context"]["reason"] == "BREAKOUT_FILTERED"
