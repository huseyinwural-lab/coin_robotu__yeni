# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.execution.futures_execution_reconciler import FuturesExecutionReconciler


def test_reconciler_maps_partial_fill_state():
    result = FuturesExecutionReconciler().reconcile(submitted=True, exchange_status="NEW", executed_qty=0.2)
    assert result["state"] == "partially_filled"


def test_reconciler_unknown_when_not_submitted():
    result = FuturesExecutionReconciler().reconcile(submitted=False, exchange_status="", executed_qty=0)
    assert result["state"] == "unknown_needs_reconcile"
