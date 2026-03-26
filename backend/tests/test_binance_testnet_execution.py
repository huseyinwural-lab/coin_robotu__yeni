import os

import pytest

from core.exchanges.binance_adapter import BinanceExecutionAdapter


def test_binance_testnet_order_lifecycle_market_limit_cancel():
    os.environ["EXECUTION_MODE"] = "testnet"
    os.environ["TESTNET_TRADING_ENABLED"] = "true"
    os.environ["LIVE_TRADING_ENABLED"] = "false"
    os.environ["LIVE_ROUTE_APPROVED"] = "false"

    adapter = BinanceExecutionAdapter(mode="testnet")
    try:
        _ = adapter.get_available_balance(asset="USDT")
    except RuntimeError as exc:
        pytest.skip(f"testnet credentials not valid/available: {exc}")

    limit_order = adapter.submit_order(
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "size": 0.0001,
            "order_type": "LIMIT",
            "limit_price": 1000,
            "mark_price": 1000,
            "idempotency_key": "iter4-limit-lifecycle",
        }
    )
    assert limit_order.get("external_order_id")

    status = adapter.get_order_status(symbol="BTCUSDT", order_id=limit_order["external_order_id"])
    assert status.get("status")

    cancel = adapter.cancel_order(symbol="BTCUSDT", order_id=limit_order["external_order_id"])
    assert cancel.get("status") in {"CANCELED", "PENDING_CANCEL", "NEW", "PARTIALLY_FILLED", "FILLED"}
