import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.simulation.scaling_robustness_engine import compute_scaling_robustness_score


def test_scaling_robustness_engine_uses_configurable_weights():
    payload = compute_scaling_robustness_score(
        pnl_stability=70,
        slippage_impact=75,
        execution_quality=80,
        liquidity_stress=85,
        weights={
            "pnl_stability": 0.25,
            "slippage_impact": 0.25,
            "execution_quality": 0.25,
            "liquidity_stress": 0.25,
        },
    )
    assert 0 <= payload["scaling_robustness_score"] <= 100
    assert payload["weights"]["pnl_stability"] == 0.25
