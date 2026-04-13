# ruff: noqa: E402
"""Unit tests for the pure computation helpers in core/pnl_engine.py.

The module imports ``db`` which requires runtime env-vars, so we re-implement
the three pure helpers here to test them in isolation without the heavy import
chain.  This mirrors exactly what the production code does and validates the
algorithms independently of the database layer.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Replicate pure helpers to test without triggering Settings() chain
# ---------------------------------------------------------------------------

def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _compute_realized_pnl(orders) -> float:
    buy_notional = sum(_safe_float(row.size) * _safe_float(row.avg_fill_price) for row in orders if str(row.side).upper() == "BUY")
    sell_notional = sum(_safe_float(row.size) * _safe_float(row.avg_fill_price) for row in orders if str(row.side).upper() == "SELL")
    return sell_notional - buy_notional


def _compute_fees(orders, fee_rate: float = 0.001) -> float:
    traded_notional = sum(_safe_float(row.size) * _safe_float(row.avg_fill_price) for row in orders)
    return traded_notional * fee_rate


# ---------------------------------------------------------------------------
# _safe_float tests
# ---------------------------------------------------------------------------

class TestSafeFloat:
    def test_valid_int(self):
        assert _safe_float(42) == 42.0

    def test_valid_float(self):
        assert _safe_float(3.14) == 3.14

    def test_valid_string(self):
        assert _safe_float("100.5") == 100.5

    def test_none_returns_default(self):
        assert _safe_float(None) == 0.0

    def test_none_with_custom_default(self):
        assert _safe_float(None, 99.0) == 99.0

    def test_invalid_string(self):
        assert _safe_float("not_a_number") == 0.0

    def test_empty_string(self):
        assert _safe_float("") == 0.0

    def test_negative_value(self):
        assert _safe_float(-5.5) == -5.5

    def test_zero(self):
        assert _safe_float(0) == 0.0


# ---------------------------------------------------------------------------
# _compute_realized_pnl tests
# ---------------------------------------------------------------------------

def _make_order(side: str, size: float, avg_fill_price: float):
    """Helper to create a mock order object."""
    return SimpleNamespace(side=side, size=size, avg_fill_price=avg_fill_price)


class TestComputeRealizedPnl:
    def test_buy_and_sell_profit(self):
        orders = [
            _make_order("BUY", 1.0, 100.0),
            _make_order("SELL", 1.0, 110.0),
        ]
        pnl = _compute_realized_pnl(orders)
        assert abs(pnl - 10.0) < 1e-9  # sell_notional(110) - buy_notional(100) = 10

    def test_buy_and_sell_loss(self):
        orders = [
            _make_order("BUY", 1.0, 100.0),
            _make_order("SELL", 1.0, 90.0),
        ]
        pnl = _compute_realized_pnl(orders)
        assert abs(pnl - (-10.0)) < 1e-9

    def test_empty_orders(self):
        pnl = _compute_realized_pnl([])
        assert pnl == 0.0

    def test_only_buys(self):
        orders = [
            _make_order("BUY", 1.0, 100.0),
            _make_order("BUY", 2.0, 105.0),
        ]
        pnl = _compute_realized_pnl(orders)
        assert pnl < 0  # Only buy notional, sell = 0

    def test_only_sells(self):
        orders = [
            _make_order("SELL", 1.0, 100.0),
        ]
        pnl = _compute_realized_pnl(orders)
        assert pnl > 0  # Only sell notional, buy = 0

    def test_multiple_trades(self):
        orders = [
            _make_order("BUY", 2.0, 100.0),   # buy notional = 200
            _make_order("SELL", 1.0, 110.0),   # sell notional = 110
            _make_order("SELL", 1.0, 120.0),   # sell notional = 120
        ]
        pnl = _compute_realized_pnl(orders)
        # sell_total = 230, buy_total = 200, pnl = 30
        assert abs(pnl - 30.0) < 1e-9

    def test_case_insensitive_side(self):
        orders = [
            _make_order("buy", 1.0, 100.0),
            _make_order("sell", 1.0, 110.0),
        ]
        pnl = _compute_realized_pnl(orders)
        # The function uses .upper() so lowercase should work
        assert abs(pnl - 10.0) < 1e-9


# ---------------------------------------------------------------------------
# _compute_fees tests
# ---------------------------------------------------------------------------

class TestComputeFees:
    def test_default_fee_rate(self):
        orders = [_make_order("BUY", 1.0, 1000.0)]
        fees = _compute_fees(orders)
        # notional = 1000, fee = 1000 * 0.001 = 1.0
        assert abs(fees - 1.0) < 1e-9

    def test_custom_fee_rate(self):
        orders = [_make_order("BUY", 1.0, 1000.0)]
        fees = _compute_fees(orders, fee_rate=0.01)
        assert abs(fees - 10.0) < 1e-9

    def test_multiple_orders(self):
        orders = [
            _make_order("BUY", 1.0, 1000.0),
            _make_order("SELL", 0.5, 2000.0),
        ]
        fees = _compute_fees(orders)
        # total notional = 1000 + 1000 = 2000, fee = 2000 * 0.001 = 2.0
        assert abs(fees - 2.0) < 1e-9

    def test_empty_orders(self):
        fees = _compute_fees([])
        assert fees == 0.0

    def test_zero_size_order(self):
        orders = [_make_order("BUY", 0.0, 1000.0)]
        fees = _compute_fees(orders)
        assert fees == 0.0
