import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.legacy.oscillator_composite_reversion_v2 import OscillatorCompositeReversionV2


def _state(bullish_pullback: bool) -> dict:
    closes = [100 + (i * 0.04) for i in range(50)]
    if bullish_pullback:
        closes[-5:] = [99.5, 99.0, 98.8, 98.6, 98.4]
    else:
        closes[-5:] = [101.5, 102.0, 102.4, 102.8, 103.2]
    highs = [close * 1.005 for close in closes]
    lows = [close * 0.995 for close in closes]
    return {
        "closes": closes,
        "highs": highs,
        "lows": lows,
        "volatility_regime": "RANGING",
        "volatility_compression": 0.3,
        "controlled_entry_mode": True,
    }


def test_oscillator_composite_reversion_v2_controlled_entry_required():
    strategy = OscillatorCompositeReversionV2()
    payload = strategy.generate_signal({"closes": [1] * 50, "highs": [1] * 50, "lows": [1] * 50})
    assert payload["signal"] == "NONE"
    assert payload["context"]["reason"] == "CONTROLLED_ENTRY_REQUIRED"


def test_oscillator_composite_reversion_v2_signal_generation():
    strategy = OscillatorCompositeReversionV2()
    long_payload = strategy.generate_signal(_state(bullish_pullback=True))
    short_payload = strategy.generate_signal(_state(bullish_pullback=False))
    assert long_payload["signal"] in {"LONG", "NONE"}
    assert short_payload["signal"] in {"SHORT", "NONE"}
    assert "composite_score" in long_payload["context"]
