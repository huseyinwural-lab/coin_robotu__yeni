SYMBOL_MAPPINGS = {
    "binance": {
        "BTCUSDT": "BTCUSDT",
        "ETHUSDT": "ETHUSDT",
        "SOLUSDT": "SOLUSDT",
    },
    "bybit": {
        "BTCUSDT": "BTCUSDT",
        "ETHUSDT": "ETHUSDT",
        "SOLUSDT": "SOLUSDT",
    },
    "okx": {
        "BTCUSDT": "BTC-USDT",
        "ETHUSDT": "ETH-USDT",
        "SOLUSDT": "SOL-USDT",
    },
}


def normalize_symbol(symbol: str) -> str:
    return str(symbol or "").upper().replace("-", "").strip()


def to_exchange_symbol(exchange: str, symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    exchange_key = str(exchange or "").lower().strip()
    mapping = SYMBOL_MAPPINGS.get(exchange_key) or {}
    return mapping.get(normalized, normalized if exchange_key != "okx" else normalized.replace("USDT", "-USDT"))
