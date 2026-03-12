import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.microstructure.orderbook_thinning_detector import OrderbookThinningDetector


def test_orderbook_thinning_detector_critical_state():
    detector = OrderbookThinningDetector()
    result = detector.evaluate(
        {"bid_depth_top_n": 20, "ask_depth_top_n": 15},
        baseline_depth={"bid_depth_top_n": 100, "ask_depth_top_n": 100},
    )
    assert result["thinning_state"] == "CRITICAL"
    assert result["dominant_thin_side"] in {"BID", "ASK", "NONE"}


def test_orderbook_thinning_detector_normal_state():
    detector = OrderbookThinningDetector()
    result = detector.evaluate(
        {"bid_depth_top_n": 95, "ask_depth_top_n": 98},
        baseline_depth={"bid_depth_top_n": 100, "ask_depth_top_n": 100},
    )
    assert result["thinning_state"] == "NORMAL"
