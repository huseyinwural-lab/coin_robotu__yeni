from services.exchange_adapter.execution_adapter import ExchangeExecutionAdapter
from services.exchange_adapter.market_data_adapter import ExchangeMarketDataAdapter
from services.exchange_adapter_smoke_service import run_exchange_adapter_smoke


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_market_data_adapter_bybit_and_okx(monkeypatch):
    def fake_get(url, params=None, timeout=8):
        if "bybit" in url:
            return FakeResponse(
                {
                    "result": {
                        "list": [
                            {
                                "lastPrice": "100",
                                "bid1Price": "99",
                                "ask1Price": "101",
                            }
                        ]
                    }
                }
            )
        return FakeResponse({"data": [{"last": "100", "bidPx": "99", "askPx": "101"}]})

    monkeypatch.setattr("services.exchange_adapter.market_data_adapter.httpx.get", fake_get)

    adapter = ExchangeMarketDataAdapter()
    bybit = adapter.fetch_ticker(exchange="bybit", symbol="BTCUSDT")
    okx = adapter.fetch_ticker(exchange="okx", symbol="BTCUSDT")

    assert bybit["exchange"] == "bybit"
    assert okx["exchange"] == "okx"
    assert bybit["spread_bps"] > 0


def test_execution_adapter_mocked_without_credentials(monkeypatch):
    monkeypatch.delenv("BYBIT_API_KEY", raising=False)
    monkeypatch.delenv("BYBIT_API_SECRET", raising=False)
    adapter = ExchangeExecutionAdapter()

    result = adapter.submit_order(exchange="bybit", symbol="BTCUSDT", side="buy", price=100, qty=0.01, leverage=3)
    assert result["mocked"] is True
    assert result["status"] == "MOCKED"


def test_exchange_adapter_smoke_service_summary(monkeypatch):
    monkeypatch.setattr(
        "services.exchange_adapter.market_data_adapter.ExchangeMarketDataAdapter.fetch_ticker",
        lambda self, exchange, symbol: {
            "exchange": exchange,
            "symbol": symbol,
            "last_price": 100.0,
            "bid_price": 99.0,
            "ask_price": 101.0,
            "spread_bps": 200.0,
        },
    )
    payload = run_exchange_adapter_smoke(symbols=["BTCUSDT"])
    assert payload["summary"]["market_pass_count"] >= 2
