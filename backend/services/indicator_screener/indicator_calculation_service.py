from statistics import fmean


class IndicatorCalculationError(ValueError):
    pass


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _ema(series: list[float], period: int) -> float:
    if len(series) < period:
        raise IndicatorCalculationError(f"EMA{period} için yetersiz candle verisi")
    alpha = 2 / (period + 1)
    seed = fmean(series[:period])
    ema_value = seed
    for price in series[period:]:
        ema_value = (price * alpha) + (ema_value * (1 - alpha))
    return float(ema_value)


def _sma(series: list[float], period: int) -> float:
    if len(series) < period:
        raise IndicatorCalculationError(f"SMA{period} için yetersiz candle verisi")
    return float(fmean(series[-period:]))


def _rsi(series: list[float], period: int) -> float:
    if len(series) < period + 1:
        raise IndicatorCalculationError(f"RSI({period}) için yetersiz candle verisi")
    gains: list[float] = []
    losses: list[float] = []
    for idx in range(-period, 0):
        delta = series[idx] - series[idx - 1]
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))
    avg_gain = fmean(gains) if gains else 0.0
    avg_loss = fmean(losses) if losses else 0.0
    if avg_loss <= 1e-12:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _fibonacci_levels(candles: list[dict], lookback: int = 100) -> dict[str, float]:
    if len(candles) < 20:
        raise IndicatorCalculationError("Fibonacci için yetersiz candle verisi")

    sample = candles[-lookback:] if len(candles) >= lookback else candles
    highs = [_safe_float(item.get("high")) for item in sample]
    lows = [_safe_float(item.get("low")) for item in sample]
    swing_high = max(highs) if highs else 0.0
    swing_low = min(lows) if lows else 0.0
    price_range = max(swing_high - swing_low, 1e-9)

    return {
        "fibo_100": float(swing_high),
        "fibo_78_6": float(swing_low + (price_range * 0.786)),
        "fibo_127_2": float(swing_high + (price_range * 0.272)),
        "fibo_161_8": float(swing_high + (price_range * 0.618)),
    }


def calculate_indicator_values(candles: list[dict]) -> dict[str, float]:
    if len(candles) < 60:
        raise IndicatorCalculationError("İndikatör hesaplaması için en az 60 kapalı candle gerekli")

    closes = [_safe_float(candle.get("close")) for candle in candles]
    last_candle = candles[-1]
    fib = _fibonacci_levels(candles)

    return {
        "open": _safe_float(last_candle.get("open")),
        "high": _safe_float(last_candle.get("high")),
        "low": _safe_float(last_candle.get("low")),
        "close": _safe_float(last_candle.get("close")),
        "volume": _safe_float(last_candle.get("volume")),
        "rsi14": _rsi(closes, 14),
        "rsi7": _rsi(closes, 7),
        "ema20": _ema(closes, 20),
        "ema50": _ema(closes, 50),
        "sma20": _sma(closes, 20),
        "sma50": _sma(closes, 50),
        "fibo_161_8": fib["fibo_161_8"],
        "fibo_127_2": fib["fibo_127_2"],
        "fibo_100": fib["fibo_100"],
        "fibo_78_6": fib["fibo_78_6"],
    }
