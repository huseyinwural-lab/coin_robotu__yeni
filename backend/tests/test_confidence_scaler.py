# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.leverage.confidence_scaler import ConfidenceScaler


def test_confidence_scaler_low_confidence_clamps_leverage():
    result = ConfidenceScaler().evaluate(0.25)
    assert result["confidence_leverage_multiplier"] == 0.7


def test_confidence_scaler_high_confidence_boosts_leverage():
    result = ConfidenceScaler().evaluate(0.82)
    assert result["confidence_leverage_multiplier"] == 1.2
