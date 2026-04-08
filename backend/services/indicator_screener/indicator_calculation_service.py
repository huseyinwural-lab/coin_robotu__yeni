from statistics import fmean, pstdev


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


def _bollinger(series: list[float], period: int, std_factor: float = 2.0) -> dict[str, float]:
    if len(series) < period:
        raise IndicatorCalculationError(f"BOLL({period}) için yetersiz candle verisi")
    window = series[-period:]
    mid = fmean(window)
    std = pstdev(window)
    return {
        "mid": float(mid),
        "upper": float(mid + (std * std_factor)),
        "lower": float(mid - (std * std_factor)),
    }


def _apply_live_price_overlay(candles: list[dict], live_price: float | None) -> list[dict]:
    if not candles:
        return candles
    if live_price is None:
        return candles
    try:
        live = float(live_price)
    except (TypeError, ValueError):
        return candles
    if live <= 0:
        return candles

    patched = [dict(item) for item in candles]
    last = dict(patched[-1])
    last_high = _safe_float(last.get("high"), live)
    last_low = _safe_float(last.get("low"), live)
    last["close"] = live
    last["high"] = max(last_high, live)
    last["low"] = min(last_low, live)
    patched[-1] = last
    return patched


def calculate_indicator_values(candles: list[dict], live_price: float | None = None) -> dict[str, float]:
    if len(candles) < 60:
        raise IndicatorCalculationError("İndikatör hesaplaması için en az 60 kapalı candle gerekli")

    effective_candles = _apply_live_price_overlay(candles, live_price)
    closes = [_safe_float(candle.get("close")) for candle in effective_candles]
    last_candle = effective_candles[-1]
    fib = _fibonacci_levels(effective_candles)
    boll20 = _bollinger(closes, 20)

    return {
        "open": _safe_float(last_candle.get("open")),
        "high": _safe_float(last_candle.get("high")),
        "low": _safe_float(last_candle.get("low")),
        "close": _safe_float(last_candle.get("close")),
        "volume": _safe_float(last_candle.get("volume")),
        "rsi14": _rsi(closes, 14),
        "rsi7": _rsi(closes, 7),
        "ema21": _ema(closes, 21),
        "ema20": _ema(closes, 20),
        "ema50": _ema(closes, 50),
        "sma20": _sma(closes, 20),
        "sma50": _sma(closes, 50),
        "boll_upper20": boll20["upper"],
        "boll_mid20": boll20["mid"],
        "boll_lower20": boll20["lower"],
        "fibo_161_8": fib["fibo_161_8"],
        "fibo_127_2": fib["fibo_127_2"],
        "fibo_100": fib["fibo_100"],
        "fibo_78_6": fib["fibo_78_6"],
    }


def calculate_query_indicator_values(candles: list[dict], required_fields: set[str] | None = None, live_price: float | None = None) -> dict[str, float]:
    effective_candles = _apply_live_price_overlay(candles, live_price)
    values = calculate_indicator_values(effective_candles)
    if not required_fields:
        return values

    closes = [_safe_float(candle.get("close")) for candle in effective_candles]
    for field in {str(item or "").strip().lower() for item in required_fields}:
        if not field or field in values:
            continue
        if field.startswith("rsi") and field[3:].isdigit():
            period = int(field[3:])
            if period < 2:
                raise IndicatorCalculationError("RSI periyodu 2 veya büyük olmalı")
            values[field] = _rsi(closes, period)
            continue
        if field.startswith("ema") and field[3:].isdigit():
            period = int(field[3:])
            if period < 2:
                raise IndicatorCalculationError("EMA periyodu 2 veya büyük olmalı")
            values[field] = _ema(closes, period)
            continue
        if field.startswith("sma") and field[3:].isdigit():
            period = int(field[3:])
            if period < 2:
                raise IndicatorCalculationError("MA periyodu 2 veya büyük olmalı")
            values[field] = _sma(closes, period)
            continue
        if field.startswith("boll_upper") and field[10:].isdigit():
            period = int(field[10:])
            if period < 2:
                raise IndicatorCalculationError("BOLL periyodu 2 veya büyük olmalı")
            values[field] = _bollinger(closes, period)["upper"]
            continue
        if field.startswith("boll_mid") and field[8:].isdigit():
            period = int(field[8:])
            if period < 2:
                raise IndicatorCalculationError("BOLL periyodu 2 veya büyük olmalı")
            values[field] = _bollinger(closes, period)["mid"]
            continue
        if field.startswith("boll_lower") and field[10:].isdigit():
            period = int(field[10:])
            if period < 2:
                raise IndicatorCalculationError("BOLL periyodu 2 veya büyük olmalı")
            values[field] = _bollinger(closes, period)["lower"]
            continue
    return values
