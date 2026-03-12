import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.decision.reason_codes import ReasonCode


def test_reason_code_taxonomy_is_single_and_complete():
    expected = {
        "SIGNAL_WEAK",
        "MICROSTRUCTURE_SPREAD_SHOCK",
        "MICROSTRUCTURE_DEPTH_COLLAPSE",
        "MICROSTRUCTURE_SLIPPAGE_ANOMALY",
        "RISK_LEVERAGE_LIMIT",
        "RISK_MARGIN_USAGE",
        "LIQUIDATION_DISTANCE_TOO_LOW",
        "CASCADE_DETECTED",
        "ADL_PRESSURE_LONG",
        "ADL_PRESSURE_SHORT",
        "POLICY_BLOCK",
        "GATE_REJECT",
        "ALLOW",
    }
    current = {item.value for item in ReasonCode}
    assert expected == current
    assert len(current) == len(ReasonCode)
