import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.microstructure.spread_shock_detector import SpreadShockDetector


def test_spread_shock_detector_detects_shock_state():
    detector = SpreadShockDetector()
    result = detector.evaluate({"spread_bps": 30}, baseline_spread_bps=10)
    assert result["spread_state"] == "SHOCK"
    assert result["shock_ratio"] >= 2.5


def test_spread_shock_detector_detects_normal_state():
    detector = SpreadShockDetector()
    result = detector.evaluate({"spread_bps": 8}, baseline_spread_bps=10)
    assert result["spread_state"] == "NORMAL"
