from math import sqrt

from services.pipeline.cache_store import get_json


def _extract_close_returns(candles: list[dict], window: int = 200) -> list[float]:
    if len(candles) < 3:
        return []
    closes = [float(item["close"]) for item in candles[-window:]]
    returns: list[float] = []
    for index in range(1, len(closes)):
        prev = closes[index - 1]
        if prev == 0:
            continue
        returns.append((closes[index] - prev) / prev)
    return returns


def _pearson(x: list[float], y: list[float]) -> float:
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    x = x[-n:]
    y = y[-n:]

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    var_x = sum((value - mean_x) ** 2 for value in x)
    var_y = sum((value - mean_y) ** 2 for value in y)
    if var_x <= 0 or var_y <= 0:
        return 0.0
    return round(cov / sqrt(var_x * var_y), 4)


def pair_correlation(cache, symbol_a: str, symbol_b: str, window: int = 200) -> float:
    if symbol_a.upper() == symbol_b.upper():
        return 1.0
    candles_a = get_json(cache, f"market:candles:{symbol_a.upper()}:15m") or []
    candles_b = get_json(cache, f"market:candles:{symbol_b.upper()}:15m") or []
    returns_a = _extract_close_returns(candles_a, window)
    returns_b = _extract_close_returns(candles_b, window)
    return _pearson(returns_a, returns_b)


def build_correlation_matrix(cache, symbols: list[str], window: int = 200) -> dict:
    normalized_symbols = sorted({symbol.upper() for symbol in symbols if symbol})
    matrix = {}
    for base_symbol in normalized_symbols:
        matrix[base_symbol] = {}
        for compare_symbol in normalized_symbols:
            matrix[base_symbol][compare_symbol] = pair_correlation(cache, base_symbol, compare_symbol, window)
    return {
        "window": window,
        "symbols": normalized_symbols,
        "matrix": matrix,
    }
