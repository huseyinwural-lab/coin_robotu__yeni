import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.futures_mean_reversion_v1 import FuturesMeanReversionV1


def test_mean_reversion_generates_short_signal_on_positive_deviation():
    strategy = FuturesMeanReversionV1()
    signal = strategy.generate_signal(
        {
            "latest_price": 102.5,
            "range_mean": 100.0,
            "atr": 0.01,
            "volatility_compression": 0.8,
            "range_persistence": 0.75,
            "funding_bias": {"funding_rate": 0.0, "bias_direction": "NEUTRAL"},
        }
    )
    assert signal["signal"] == "SHORT"
    assert signal["confidence"] > 0
    assert signal["context"]["reason"] == "MEAN_REVERSION_SETUP"


def test_mean_reversion_filters_when_setup_not_valid():
    strategy = FuturesMeanReversionV1()
    signal = strategy.generate_signal(
        {
            "latest_price": 100.2,
            "range_mean": 100.0,
            "atr": 0.02,
            "volatility_compression": 0.15,
            "range_persistence": 0.2,
            "funding_bias": {"funding_rate": 0.002, "bias_direction": "LONG_BIAS"},
        }
    )
    assert signal["signal"] == "NONE"
    assert signal["confidence"] == 0.0
    assert signal["context"]["reason"] == "MEAN_REVERSION_FILTERED"
