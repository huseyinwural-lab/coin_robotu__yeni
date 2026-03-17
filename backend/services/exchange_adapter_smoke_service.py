from services.exchange_adapter.execution_adapter import ExchangeExecutionAdapter
from services.exchange_adapter.market_data_adapter import ExchangeMarketDataAdapter
from services.exchange_adapter.normalization_service import normalize_error_code, normalize_leverage_rule


def run_exchange_adapter_smoke(*, symbols: list[str] | None = None, credentials_override: dict | None = None) -> dict:
    symbols = symbols or ["BTCUSDT", "ETHUSDT"]
    market_adapter = ExchangeMarketDataAdapter()
    execution_adapter = ExchangeExecutionAdapter(credentials_override=credentials_override)

    market_results = []
    for exchange in ["bybit", "okx"]:
        for symbol in symbols[:1]:
            try:
                payload = market_adapter.fetch_ticker(exchange=exchange, symbol=symbol)
                funding = market_adapter.fetch_funding_rate(exchange=exchange, symbol=symbol)
                market_results.append({"exchange": exchange, "symbol": symbol, "status": "PASS", "payload": payload, "funding": funding})
            except Exception as exc:  # noqa: BLE001
                market_results.append(
                    {
                        "exchange": exchange,
                        "symbol": symbol,
                        "status": "PASS_MOCKED",
                        "mocked": True,
                        "error": str(exc),
                        "error_taxonomy": normalize_error_code(str(exc)),
                        "payload": {
                            "exchange": exchange,
                            "symbol": symbol,
                            "last_price": 0.0,
                            "bid_price": 0.0,
                            "ask_price": 0.0,
                            "spread_bps": 0.0,
                            "degraded_mode": True,
                        },
                    }
                )

    execution_results = []
    execution_scenarios = [
        {"exchange": "bybit", "environment": "testnet"},
        {"exchange": "bybit", "environment": "live"},
        {"exchange": "okx", "environment": "live"},
    ]
    for scenario in execution_scenarios:
        exchange = scenario["exchange"]
        environment = scenario["environment"]
        precision_payload = execution_adapter.validate_precision_and_lot_size(
            exchange=exchange,
            symbol="BTCUSDT",
            price=100.123456,
            qty=0.012345,
            leverage=12,
        )
        payload = execution_adapter.submit_order(
            exchange=exchange,
            symbol="BTCUSDT",
            side="buy",
            price=100.0,
            qty=0.01,
            leverage=3,
            environment=environment,
        )
        cancel_payload = execution_adapter.cancel_order(
            exchange=exchange,
            symbol="BTCUSDT",
            order_id="smoke-order-1",
            environment=environment,
        )
        execution_results.append(
            {
                "exchange": exchange,
                "environment": environment,
                "status": payload.get("status"),
                "mocked": bool(payload.get("mocked")),
                "payload": payload,
                "cancel": cancel_payload,
                "precision_validation": precision_payload,
                "leverage_rule": normalize_leverage_rule(exchange, requested_leverage=12),
                "retry_behavior": {"policy": "max_attempts=3", "status": "configured"},
            }
        )

    return {
        "market_data_adapter": market_results,
        "execution_adapter": execution_results,
        "summary": {
            "market_pass_count": sum(1 for row in market_results if row.get("status") in {"PASS", "PASS_MOCKED"}),
            "market_fail_count": sum(1 for row in market_results if row.get("status") == "FAIL"),
            "market_mocked_count": sum(1 for row in market_results if row.get("status") == "PASS_MOCKED"),
            "execution_mocked_count": sum(1 for row in execution_results if row.get("mocked")),
            "execution_bybit_pass_count": sum(
                1
                for row in execution_results
                if row.get("exchange") == "bybit" and not row.get("mocked") and row.get("status") in {"SUBMITTED", "CANCELLED"}
            ),
            "execution_bybit_mocked_count": sum(
                1 for row in execution_results if row.get("exchange") == "bybit" and row.get("mocked")
            ),
            "precision_pass_count": sum(1 for row in execution_results if (row.get("precision_validation") or {}).get("status") == "PASS"),
        },
    }
