# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.simulation.capital_scaling_simulator import run_capital_scaling_simulation


def test_capital_scaling_simulator_replays_levels():
    payload = run_capital_scaling_simulation(
        trades=[{"order_size": 10000, "expected_pnl": 120, "volatility_regime": "NORMAL"}],
        capital_levels=[1_000_000, 10_000_000, 100_000_000],
        market_depth=5_000_000,
        spread_bps=12,
        liquidity_tier="MEDIUM",
    )
    assert len(payload["scaling_performance_report"]) == 3
