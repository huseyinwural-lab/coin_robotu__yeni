# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.microstructure.quote_stability_detector import QuoteStabilityDetector


def test_quote_stability_detector_chaotic_state():
    detector = QuoteStabilityDetector()
    result = detector.evaluate({"quote_update_rate": 12, "price_jump_score": 90, "spread_bps": 30})
    assert result["quote_stability_state"] == "CHAOTIC"


def test_quote_stability_detector_stable_state():
    detector = QuoteStabilityDetector()
    result = detector.evaluate({"quote_update_rate": 1.5, "price_jump_score": 8, "spread_bps": 5})
    assert result["quote_stability_state"] == "STABLE"
