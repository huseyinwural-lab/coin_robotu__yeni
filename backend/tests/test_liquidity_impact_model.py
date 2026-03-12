import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.simulation.liquidity_impact_model import estimate_liquidity_impact


def test_liquidity_impact_model_returns_impact_score():
    payload = estimate_liquidity_impact(order_size=200000, market_depth=1000000, spread_width_bps=15, liquidity_tier="LOW")
    assert payload["impact_ratio"] > 0
    assert payload["impact_score"] > 0
