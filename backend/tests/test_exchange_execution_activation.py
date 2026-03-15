from services.exchange_adapter_smoke_service import run_exchange_adapter_smoke


def test_exchange_execution_validation_payload_contains_required_checks(monkeypatch):
    monkeypatch.setattr(
        "services.exchange_adapter.market_data_adapter.ExchangeMarketDataAdapter.fetch_ticker",
        lambda self, exchange, symbol: {
            "exchange": exchange,
            "symbol": symbol,
            "last_price": 100,
            "bid_price": 99,
            "ask_price": 101,
            "spread_bps": 200,
        },
    )
    monkeypatch.setattr(
        "services.exchange_adapter.market_data_adapter.ExchangeMarketDataAdapter.fetch_funding_rate",
        lambda self, exchange, symbol: {
            "exchange": exchange,
            "symbol": symbol,
            "funding_rate": 0.0001,
        },
    )

    payload = run_exchange_adapter_smoke(symbols=["BTCUSDT"])
    assert payload["summary"]["market_fail_count"] == 0
    assert payload["summary"]["precision_pass_count"] >= 2
    for row in payload["execution_adapter"]:
        assert "cancel" in row
        assert "precision_validation" in row
        assert "retry_behavior" in row
