import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.execution.futures_execution_contract import FuturesExecutionRequest
from core.execution.futures_reduce_only_guard import FuturesReduceOnlyGuard


def _request(side: str):
    return FuturesExecutionRequest(
        symbol="BTCUSDT",
        side=side,
        order_type="MARKET",
        quantity=0.01,
        leverage=2,
        reduce_only=True,
        client_order_id="client-123456",
        decision_trace_id="trace-123456",
        strategy="futures_trend_follow_v1",
        reason_context={},
    )


def test_reduce_only_guard_blocks_exposure_increase_long():
    result = FuturesReduceOnlyGuard().evaluate(_request("BUY"), {"quantity": 0.5, "side": "LONG"})
    assert result["pass"] is False
    assert result["reason_code"] == "REDUCE_ONLY_WOULD_INCREASE_LONG"


def test_reduce_only_guard_allows_reduction():
    result = FuturesReduceOnlyGuard().evaluate(_request("SELL"), {"quantity": 0.5, "side": "LONG"})
    assert result["pass"] is True
