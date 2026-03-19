# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.microstructure.microstructure_gate import MicrostructureGate


def test_microstructure_gate_rejects_on_shock_and_anomaly():
    gate = MicrostructureGate()
    result = gate.evaluate(
        spread_result={"spread_state": "SHOCK"},
        thinning_result={"thinning_state": "NORMAL"},
        vacuum_result={"vacuum_state": "LOW"},
        quote_result={"quote_stability_state": "STABLE"},
        slippage_result={"slippage_state": "ANOMALY"},
        aggregate_result={"risk_level": "WARNING", "microstructure_risk_score": 0.5},
        stale_data=False,
    )
    assert result["gate_pass"] is False
    assert result["gate_reason"].startswith("MICROSTRUCTURE_")


def test_microstructure_gate_passes_when_safe():
    gate = MicrostructureGate()
    result = gate.evaluate(
        spread_result={"spread_state": "NORMAL"},
        thinning_result={"thinning_state": "NORMAL"},
        vacuum_result={"vacuum_state": "LOW"},
        quote_result={"quote_stability_state": "STABLE"},
        slippage_result={"slippage_state": "NORMAL"},
        aggregate_result={"risk_level": "SAFE", "microstructure_risk_score": 0.1},
        stale_data=False,
    )
    assert result["gate_pass"] is True
    assert result["gate_reason"] == "PASS"
