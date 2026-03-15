from services.exchange_adapter.execution_adapter import ExchangeExecutionAdapter
from services.exchange_adapter.market_data_adapter import ExchangeMarketDataAdapter


def run_exchange_adapter_smoke(*, symbols: list[str] | None = None) -> dict:
    symbols = symbols or ["BTCUSDT", "ETHUSDT"]
    market_adapter = ExchangeMarketDataAdapter()
    execution_adapter = ExchangeExecutionAdapter()

    market_results = []
    for exchange in ["bybit", "okx"]:
        for symbol in symbols[:1]:
            try:
                payload = market_adapter.fetch_ticker(exchange=exchange, symbol=symbol)
                market_results.append({"exchange": exchange, "symbol": symbol, "status": "PASS", "payload": payload})
            except Exception as exc:  # noqa: BLE001
                market_results.append({"exchange": exchange, "symbol": symbol, "status": "FAIL", "error": str(exc)})

    execution_results = []
    for exchange in ["bybit", "okx"]:
        payload = execution_adapter.submit_order(
            exchange=exchange,
            symbol="BTCUSDT",
            side="buy",
            price=100.0,
            qty=0.01,
            leverage=3,
        )
        execution_results.append({"exchange": exchange, "status": payload.get("status"), "mocked": bool(payload.get("mocked")), "payload": payload})

    return {
        "market_data_adapter": market_results,
        "execution_adapter": execution_results,
        "summary": {
            "market_pass_count": sum(1 for row in market_results if row.get("status") == "PASS"),
            "market_fail_count": sum(1 for row in market_results if row.get("status") == "FAIL"),
            "execution_mocked_count": sum(1 for row in execution_results if row.get("mocked")),
        },
    }
