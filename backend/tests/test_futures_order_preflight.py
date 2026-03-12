import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.execution.futures_execution_contract import FuturesExecutionRequest
from core.execution.futures_order_preflight import FuturesOrderPreflight


def _request(reduce_only: bool = False):
    return FuturesExecutionRequest(
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=0.01,
        leverage=3,
        reduce_only=reduce_only,
        client_order_id="client-123456",
        decision_trace_id="trace-123456",
        strategy="futures_trend_follow_v1",
        reason_context={},
    )


def test_preflight_blocks_when_release_gate_blocked():
    result = FuturesOrderPreflight().evaluate(
        request=_request(),
        context={
            "active_symbols": ["BTCUSDT"],
            "max_trade_leverage": 5,
            "margin_available": 1000,
            "margin_required": 10,
            "testnet_mode_enabled": True,
            "release_gate_status": "BLOCKED",
            "environment": "testnet",
        },
    )
    assert result["preflight_pass"] is False
    assert result["reason_code"] == "RELEASE_GATE_BLOCKED"


def test_preflight_blocks_reduce_only_inconsistency():
    result = FuturesOrderPreflight().evaluate(
        request=_request(reduce_only=True),
        context={
            "active_symbols": ["BTCUSDT"],
            "max_trade_leverage": 5,
            "current_position_qty": 0,
            "current_position_side": "NONE",
            "margin_available": 1000,
            "margin_required": 10,
            "testnet_mode_enabled": True,
            "release_gate_status": "PASS",
            "environment": "testnet",
        },
    )
    assert result["preflight_pass"] is False
    assert result["reason_code"] == "REDUCE_ONLY_INCONSISTENT"
