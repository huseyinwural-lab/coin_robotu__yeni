import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.legacy.volatility_breakout_v2 import VolatilityBreakoutV2


def _market_state(direction: str) -> dict:
    base = [100 + (i * 0.02) for i in range(30)]
    if direction == "LONG":
        base[-2] = 101.5
        base[-1] = 102.2
    else:
        base[-2] = 98.5
        base[-1] = 97.8

    highs = [close * 1.004 for close in base]
    lows = [close * 0.996 for close in base]
    opens = [base[i - 1] if i > 0 else base[0] for i in range(len(base))]
    return {
        "closes": base,
        "highs": highs,
        "lows": lows,
        "opens": opens,
        "spread_bps": 8,
        "atr": 0.009,
        "volatility_regime": "VOLATILE",
    }


def test_volatility_breakout_v2_long_confirmation():
    strategy = VolatilityBreakoutV2()
    payload = strategy.generate_signal(_market_state("LONG"))
    assert payload["signal"] == "LONG"
    assert payload["context"]["liquidity_ok"] is True


def test_volatility_breakout_v2_short_confirmation():
    strategy = VolatilityBreakoutV2()
    payload = strategy.generate_signal(_market_state("SHORT"))
    assert payload["signal"] == "SHORT"
