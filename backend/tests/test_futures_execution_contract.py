# ruff: noqa: E402
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.execution.futures_execution_contract import FuturesExecutionRequest


def test_execution_contract_valid_payload():
    payload = FuturesExecutionRequest(
        symbol="btcusdt",
        side="BUY",
        order_type="MARKET",
        quantity=0.01,
        leverage=3,
        reduce_only=False,
        client_order_id="client-123456",
        decision_trace_id="trace-123456",
        strategy="futures_trend_follow_v1",
        reason_context={"layer": "GATE"},
    )
    assert payload.symbol == "BTCUSDT"


def test_execution_contract_rejects_non_usdt_symbol():
    with pytest.raises(Exception):
        FuturesExecutionRequest(
            symbol="BTCUSD",
            side="BUY",
            order_type="MARKET",
            quantity=0.01,
            leverage=3,
            reduce_only=False,
            client_order_id="client-123456",
            decision_trace_id="trace-123456",
            strategy="futures_trend_follow_v1",
            reason_context={},
        )
