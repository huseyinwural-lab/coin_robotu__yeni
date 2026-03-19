# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.execution.futures_testnet_release_gate import FuturesTestnetReleaseGate


def test_release_gate_blocked_without_enablement():
    result = FuturesTestnetReleaseGate().evaluate(
        live_mode_enabled=False,
        release_gate_status="PASS",
        has_live_credentials=False,
    )
    assert result["status"] == "BLOCKED"
    assert result["order_path_open"] is False


def test_release_gate_pass_with_warnings_allowed():
    result = FuturesTestnetReleaseGate().evaluate(
        live_mode_enabled=True,
        release_gate_status="PASS_WITH_WARNINGS",
        has_live_credentials=False,
    )
    assert result["status"] == "PASS_WITH_WARNINGS"
    assert result["order_path_open"] is True
