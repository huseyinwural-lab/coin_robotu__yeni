import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.leverage.funding_scaler import FundingScaler


def test_funding_scaler_reduces_long_under_long_bias_pressure():
    result = FundingScaler().evaluate(
        side="LONG",
        funding_bias={"bias_direction": "LONG_BIAS", "funding_pressure_state": "HIGH"},
    )
    assert result["funding_adjustment_factor"] == 0.7


def test_funding_scaler_boosts_when_bias_is_opposite():
    result = FundingScaler().evaluate(
        side="LONG",
        funding_bias={"bias_direction": "SHORT_BIAS", "funding_pressure_state": "LOW"},
    )
    assert result["funding_adjustment_factor"] == 1.08
