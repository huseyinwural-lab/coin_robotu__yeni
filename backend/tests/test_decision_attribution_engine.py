# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.decision.decision_attribution_engine import DecisionAttributionEngine


def test_attribution_microstructure_priority_is_deterministic():
    result = DecisionAttributionEngine().evaluate(
        signal_valid=True,
        microstructure_pass=False,
        microstructure_reason="MICROSTRUCTURE_SPREAD_SHOCK",
        risk_pass=False,
        risk_reason="margin_usage_limit",
        liquidation_pass=False,
        liquidation_reason="LIQUIDATION_DISTANCE_TOO_LOW",
        adl_pass=False,
        adl_reason="ADL_PRESSURE_LONG",
        adl_pressure_side="LONG",
        policy_pass=False,
        gate_pass=False,
    )
    assert result == {
        "decision": "REJECT",
        "reason_code": "MICROSTRUCTURE_SPREAD_SHOCK",
        "decision_layer": "MICROSTRUCTURE",
    }


def test_attribution_policy_block_when_previous_layers_pass():
    result = DecisionAttributionEngine().evaluate(
        signal_valid=True,
        microstructure_pass=True,
        microstructure_reason="",
        risk_pass=True,
        risk_reason="",
        liquidation_pass=True,
        liquidation_reason="",
        adl_pass=True,
        adl_reason="",
        adl_pressure_side="NONE",
        policy_pass=False,
        gate_pass=False,
    )
    assert result["decision"] == "REJECT"
    assert result["reason_code"] == "POLICY_BLOCK"
    assert result["decision_layer"] == "POLICY"


def test_attribution_allow_when_all_layers_pass():
    result = DecisionAttributionEngine().evaluate(
        signal_valid=True,
        microstructure_pass=True,
        microstructure_reason="",
        risk_pass=True,
        risk_reason="",
        liquidation_pass=True,
        liquidation_reason="",
        adl_pass=True,
        adl_reason="",
        adl_pressure_side="NONE",
        policy_pass=True,
        gate_pass=True,
    )
    assert result == {
        "decision": "ALLOW",
        "reason_code": "ALLOW",
        "decision_layer": "GATE",
    }
