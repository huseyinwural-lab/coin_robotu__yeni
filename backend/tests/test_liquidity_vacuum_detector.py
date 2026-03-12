import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.microstructure.liquidity_vacuum_detector import LiquidityVacuumDetector


def test_liquidity_vacuum_detector_high_vacuum():
    detector = LiquidityVacuumDetector()
    result = detector.evaluate(
        {"top_of_book_size": 0.2, "depth_imbalance": 0.55, "liquidity_gap_score": 85},
        {"thinning_state": "CRITICAL"},
    )
    assert result["vacuum_state"] == "HIGH"
    assert result["vacuum_score"] >= 0.75


def test_liquidity_vacuum_detector_low_vacuum():
    detector = LiquidityVacuumDetector()
    result = detector.evaluate(
        {"top_of_book_size": 20, "depth_imbalance": 0.05, "liquidity_gap_score": 5},
        {"thinning_state": "NORMAL"},
    )
    assert result["vacuum_state"] == "LOW"
