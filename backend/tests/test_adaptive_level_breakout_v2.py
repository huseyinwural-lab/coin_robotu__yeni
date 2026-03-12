import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.legacy.adaptive_level_breakout_v2 import AdaptiveLevelBreakoutV2


def _state(side: str) -> dict:
    closes = [100 + i * 0.05 for i in range(120)]
    if side == "SHORT":
        closes = [100 - i * 0.05 for i in range(120)]
        closes[-1] = closes[-2] * 0.985
    else:
        closes[-1] = closes[-2] * 1.015
    highs = [close * 1.004 for close in closes]
    lows = [close * 0.996 for close in closes]
    volumes = [1000 + i * 5 for i in range(120)]
    volumes[-1] = volumes[-2] * 1.4
    return {
        "closes": closes,
        "highs": highs,
        "lows": lows,
        "volumes": volumes,
        "timeframe": "15m",
    }


def test_adaptive_level_breakout_v2_long_and_tags():
    strategy = AdaptiveLevelBreakoutV2()
    payload = strategy.generate_signal(_state("LONG"))
    assert payload["signal"] == "LONG"
    assert payload["context"]["cluster_sensitivity"] in {"HIGH", "MEDIUM"}
    assert payload["context"]["capital_sensitivity"] in {"HIGH", "MEDIUM"}


def test_adaptive_level_breakout_v2_short():
    strategy = AdaptiveLevelBreakoutV2()
    payload = strategy.generate_signal(_state("SHORT"))
    assert payload["signal"] == "SHORT"
