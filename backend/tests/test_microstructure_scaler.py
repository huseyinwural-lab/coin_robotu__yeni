import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.leverage.microstructure_scaler import MicrostructureScaler


def test_microstructure_scaler_reduces_on_shock_and_critical_depth():
    result = MicrostructureScaler().evaluate(
        microstructure_risk_score=0.85,
        execution_suitability={"severity": "HIGH", "max_allowed_size_ratio": 0.6},
        spread_state="SHOCK",
        depth_state="CRITICAL",
    )
    assert result["liquidity_adjusted_leverage"] < 0.6
    assert result["size_clamp_ratio"] <= 0.4


def test_microstructure_scaler_near_normal_conditions():
    result = MicrostructureScaler().evaluate(
        microstructure_risk_score=0.15,
        execution_suitability={"severity": "LOW", "max_allowed_size_ratio": 1.0},
        spread_state="NORMAL",
        depth_state="NORMAL",
    )
    assert result["liquidity_adjusted_leverage"] > 0.8
    assert result["size_clamp_ratio"] == 1.0
