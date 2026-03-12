import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.legacy.momentum_volume_breakout_v3 import MomentumVolumeBreakoutV3


def _state(uptrend: bool = True) -> dict:
    closes = [100 + i * (0.2 if uptrend else -0.2) for i in range(40)]
    if uptrend:
        closes[-1] = closes[-2] * 1.02
    else:
        closes[-1] = closes[-2] * 0.98
    highs = [c * 1.003 for c in closes]
    lows = [c * 0.997 for c in closes]
    volumes = [1200 + i * 10 for i in range(40)]
    volumes[-1] = volumes[-2] * 1.8
    return {
        "closes": closes,
        "highs": highs,
        "lows": lows,
        "volumes": volumes,
        "atr": 0.006,
    }


def test_momentum_volume_breakout_v3_emits_long_signal():
    strategy = MomentumVolumeBreakoutV3()
    payload = strategy.generate_signal(_state(uptrend=True))
    assert payload["signal"] == "LONG"
    assert payload["confidence"] > 0
    assert payload["context"]["long_short_symmetric"] is True


def test_momentum_volume_breakout_v3_emits_short_signal():
    strategy = MomentumVolumeBreakoutV3()
    payload = strategy.generate_signal(_state(uptrend=False))
    assert payload["signal"] == "SHORT"
    assert payload["confidence"] > 0
