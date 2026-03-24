from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.commercial_ops_p0_service import _build_spot_inventory, _extract_assets, _normalize_market_types, _spot_unrealized_usd


@dataclass
class _TradeRow:
    market_type: str
    symbol: str
    side: str
    executed_qty: float
    executed_price: float
    trade_time: datetime


class _FakeClient:
    def __init__(self, prices: dict[str, float]):
        self.prices = prices

    def get_spot_price(self, symbol: str) -> float:
        return float(self.prices.get(symbol, 0.0))


def test_normalize_market_types_deduplicates():
    assert _normalize_market_types(["spot", "SPOT", "futures", "unknown"]) == ["spot", "futures"]


def test_extract_assets_for_stable_quotes():
    assert _extract_assets("BTCUSDT") == ("BTC", "USDT")
    assert _extract_assets("ETHBUSD") == ("ETH", "BUSD")


def test_spot_inventory_and_unrealized_calculation():
    rows = [
        _TradeRow(
            market_type="spot",
            symbol="BTCUSDT",
            side="BUY",
            executed_qty=1.0,
            executed_price=100.0,
            trade_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        _TradeRow(
            market_type="spot",
            symbol="BTCUSDT",
            side="SELL",
            executed_qty=0.4,
            executed_price=120.0,
            trade_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
    ]
    inventory = _build_spot_inventory(rows)
    assert round(inventory["BTCUSDT"]["qty"], 8) == 0.6

    unrealized_total, detail = _spot_unrealized_usd(_FakeClient({"BTCUSDT": 150.0}), rows)
    assert "BTCUSDT" in detail
    assert unrealized_total > 0
