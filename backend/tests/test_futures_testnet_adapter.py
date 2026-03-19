# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.execution.futures_execution_contract import FuturesExecutionRequest
from core.execution.futures_testnet_adapter import FuturesTestnetAdapter


class _FakeAdapter:
    def _signed_post(self, *_args, **_kwargs):
        return {"orderId": 12345, "status": "NEW"}, 200

    def cancel_order(self, *_args, **_kwargs):
        return {"status": "CANCELED"}, 200

    def query_order(self, *_args, **_kwargs):
        return {"status": "FILLED"}, 200

    def _signed_get(self, *_args, **_kwargs):
        return [{"qty": "0.01", "price": "100.0"}], 200, {}


def _request():
    return FuturesExecutionRequest(
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=0.01,
        leverage=2,
        reduce_only=False,
        client_order_id="client-123456",
        decision_trace_id="trace-123456",
        strategy="futures_trend_follow_v1",
        reason_context={},
    )


def test_testnet_adapter_submit_market_order():
    adapter = FuturesTestnetAdapter(adapter=_FakeAdapter())
    result = adapter.submit_market_order("k", "s", _request())
    assert result["accepted"] is True
    assert result["order_id"] == 12345


def test_testnet_adapter_fill_status_summary():
    adapter = FuturesTestnetAdapter(adapter=_FakeAdapter())
    result = adapter.fill_status("k", "s", symbol="BTCUSDT", order_id=1)
    assert result["has_fill"] is True
    assert result["filled_qty"] == 0.01
