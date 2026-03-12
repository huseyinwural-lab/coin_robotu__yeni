import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.live.order_reconciliation_engine import reconcile_order_state


def test_order_reconciliation_engine_detects_missing_and_mismatch():
    payload = reconcile_order_state(
        engine_orders=[
            {"order_id": "1", "symbol": "BTCUSDT", "side": "BUY", "price": 100, "quantity": 1, "status": "FILLED"},
            {"order_id": "2", "symbol": "ETHUSDT", "side": "BUY", "price": 80, "quantity": 2, "status": "FILLED"},
        ],
        exchange_orders=[
            {"order_id": "1", "symbol": "BTCUSDT", "side": "BUY", "price": 101, "quantity": 1, "status": "FILLED"},
        ],
    )
    assert payload["order_reconciliation_state"] == "ERROR"
    assert payload["event"]["event"] == "ORDER_RECONCILIATION_ERROR"
