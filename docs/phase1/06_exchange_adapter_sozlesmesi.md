# Exchange Adapter Sözleşmesi

## Interface
`ExchangeAdapter`

### healthcheck() -> dict
- exchange
- connection
- mode
- last_ping

### execute_mock_order(symbol, side, quantity) -> AdapterExecutionResult

## AdapterExecutionResult
- exchange_order_id
- status
- symbol
- side
- quantity
- mock_price
- mode

## Faz Durumu
- Phase-1: BinanceMockAdapter
- Phase-2: Binance gerçek execution + Bybit/OKX adapterleri
