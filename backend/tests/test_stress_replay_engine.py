import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.simulation.stress_replay_engine import run_stress_replay


def test_stress_replay_engine_is_deterministic():
    first = run_stress_replay({"volatility": 1.0, "liquidity": 1.0, "spread_bps": 10}, "flash_crash")
    second = run_stress_replay({"volatility": 1.0, "liquidity": 1.0, "spread_bps": 10}, "flash_crash")
    assert first == second
