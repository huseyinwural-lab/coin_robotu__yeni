# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.simulation.slippage_simulator import simulate_expected_slippage


def test_slippage_simulator_estimates_slippage():
    payload = simulate_expected_slippage(
        order_size=120000,
        volatility_regime="HIGH",
        spread_bps=18,
        liquidity_score=0.6,
        impact_score=42,
    )
    assert payload["expected_slippage_bps"] > 0
