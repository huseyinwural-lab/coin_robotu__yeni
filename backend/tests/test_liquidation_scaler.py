import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.leverage.liquidation_scaler import LiquidationScaler


def test_liquidation_scaler_strict_on_very_low_distance():
    result = LiquidationScaler().evaluate(6.5)
    assert result["liquidation_adjustment"] == 0.45
    assert result["liquidation_size_clamp_ratio"] == 0.35


def test_liquidation_scaler_neutral_on_safe_distance():
    result = LiquidationScaler().evaluate(22)
    assert result["liquidation_adjustment"] == 1.0
    assert result["liquidation_size_clamp_ratio"] == 1.0
