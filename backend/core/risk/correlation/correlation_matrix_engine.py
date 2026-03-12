import json
from math import sqrt


DEFAULT_TIMEFRAME = "15m"
DEFAULT_WINDOW = 96
DEFAULT_CACHE_TTL_SECONDS = 60


def _normalize_symbol(symbol: str) -> str:
    normalized = str(symbol or "").upper().strip()
    if not normalized:
        return ""
    if normalized.endswith("USDT"):
        return normalized
    return f"{normalized}USDT"


def _symbol_label(symbol: str) -> str:
    normalized = _normalize_symbol(symbol)
    return normalized[:-4] if normalized.endswith("USDT") else normalized


def _safe_json(raw):
    if not raw:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)
    except Exception:
        return None


def _close_returns(candles: list[dict], window: int) -> list[float]:
    closes = [float(item.get("close", 0.0)) for item in candles[-window:] if float(item.get("close", 0.0)) > 0]
    if len(closes) < 4:
        return []
    output: list[float] = []
    for index in range(1, len(closes)):
        prev = closes[index - 1]
        if prev <= 0:
            continue
        output.append((closes[index] - prev) / prev)
    return output


def _pearson(x: list[float], y: list[float]) -> float:
    n = min(len(x), len(y))
    if n < 4:
        return 0.0
    x = x[-n:]
    y = y[-n:]

    mean_x = sum(x) / n
    mean_y = sum(y) / n
    covariance = sum((x[idx] - mean_x) * (y[idx] - mean_y) for idx in range(n))
    variance_x = sum((value - mean_x) ** 2 for value in x)
    variance_y = sum((value - mean_y) ** 2 for value in y)
    if variance_x <= 0 or variance_y <= 0:
        return 0.0
    return round(covariance / sqrt(variance_x * variance_y), 4)


def build_correlation_matrix(
    cache,
    symbols: list[str],
    *,
    timeframe: str = DEFAULT_TIMEFRAME,
    window: int = DEFAULT_WINDOW,
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    refresh: bool = False,
) -> dict:
    normalized = sorted({_normalize_symbol(symbol) for symbol in symbols if _normalize_symbol(symbol)})
    labels = [_symbol_label(symbol) for symbol in normalized]

    cache_key = f"futures:correlation:matrix:{timeframe}:{window}:{'-'.join(labels)}"
    if cache and not refresh:
        cached = _safe_json(cache.get(cache_key))
        if isinstance(cached, dict):
            return cached

    returns_map: dict[str, list[float]] = {}
    for symbol in normalized:
        candles = _safe_json(cache.get(f"market:candles:{symbol}:{timeframe}")) if cache else []
        candles = candles if isinstance(candles, list) else []
        returns_map[_symbol_label(symbol)] = _close_returns(candles, window)

    matrix: dict[str, dict[str, float]] = {}
    for base in labels:
        matrix[base] = {}
        for compare in labels:
            if base == compare:
                matrix[base][compare] = 1.0
                continue
            matrix[base][compare] = _pearson(returns_map.get(base, []), returns_map.get(compare, []))

    payload = {
        "timeframe": timeframe,
        "window": int(window),
        "symbols": labels,
        "correlation_matrix": matrix,
    }
    if cache:
        cache.set(cache_key, json.dumps(payload))
        if hasattr(cache, "expire"):
            cache.expire(cache_key, int(cache_ttl_seconds))
    return payload
