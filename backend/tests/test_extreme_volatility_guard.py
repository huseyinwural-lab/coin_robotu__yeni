import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.tail_risk.extreme_volatility_guard import detect_extreme_volatility


def test_extreme_volatility_guard_detects_spike():
    payload = detect_extreme_volatility({"atr_ratio": 2.4, "price_delta_pct": 3.1, "volatility_percentile": 0.95})
    assert payload["active"] is True
    assert payload["event"]["event"] == "EXTREME_VOLATILITY_ALERT"
