# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.correlation.cluster_exposure_calculator import calculate_cluster_exposure


def test_cluster_exposure_calculation_aggregates_positions():
    payload = calculate_cluster_exposure(
        clusters=[{"cluster_id": "CLUSTER_1", "symbols": ["BTC", "ETH"]}],
        positions=[
            {"symbol": "BTCUSDT", "side": "LONG", "position_notional": 1200, "leverage": 3},
            {"symbol": "ETHUSDT", "side": "LONG", "position_notional": 800, "leverage": 2},
        ],
        portfolio_equity=10000,
    )
    row = payload["cluster_exposures"][0]
    assert row["cluster_exposure"] == 0.2
    assert row["cluster_direction"] == "LONG"
    assert row["cluster_position_count"] == 2
