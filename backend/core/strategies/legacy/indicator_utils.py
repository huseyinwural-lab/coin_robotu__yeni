import math


def clip(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def rolling_mean(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    window = values[-max(1, period) :]
    return sum(window) / len(window)


def rolling_std(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    window = values[-max(1, period) :]
    mean = rolling_mean(window, len(window))
    variance = sum((item - mean) ** 2 for item in window) / len(window)
    return math.sqrt(max(variance, 0.0))


def momentum_pct(closes: list[float], lookback: int) -> float:
    if len(closes) <= lookback:
        return 0.0
    base = closes[-lookback - 1]
    if base <= 0:
        return 0.0
    return (closes[-1] - base) / base


def zscore(value: float, sample: list[float]) -> float:
    if not sample:
        return 0.0
    mean = sum(sample) / len(sample)
    variance = sum((x - mean) ** 2 for x in sample) / len(sample)
    std = math.sqrt(max(variance, 0.0))
    if std <= 1e-12:
        return 0.0
    return (value - mean) / std


def rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) <= period:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for idx in range(-period, 0):
        diff = closes[idx] - closes[idx - 1]
        gains.append(max(diff, 0.0))
        losses.append(abs(min(diff, 0.0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss <= 1e-12:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def stochastic_k(closes: list[float], highs: list[float], lows: list[float], period: int = 14) -> float:
    if len(closes) < period or len(highs) < period or len(lows) < period:
        return 50.0
    highest = max(highs[-period:])
    lowest = min(lows[-period:])
    if highest <= lowest:
        return 50.0
    return ((closes[-1] - lowest) / (highest - lowest)) * 100.0


def cci(closes: list[float], highs: list[float], lows: list[float], period: int = 14) -> float:
    if len(closes) < period or len(highs) < period or len(lows) < period:
        return 0.0
    typical_prices = [
        (high_value + low_value + close_value) / 3.0
        for high_value, low_value, close_value in zip(highs[-period:], lows[-period:], closes[-period:])
    ]
    tp_mean = sum(typical_prices) / period
    mean_dev = sum(abs(tp - tp_mean) for tp in typical_prices) / period
    if mean_dev <= 1e-12:
        return 0.0
    return (typical_prices[-1] - tp_mean) / (0.015 * mean_dev)


def williams_r(closes: list[float], highs: list[float], lows: list[float], period: int = 14) -> float:
    if len(closes) < period or len(highs) < period or len(lows) < period:
        return -50.0
    highest = max(highs[-period:])
    lowest = min(lows[-period:])
    if highest <= lowest:
        return -50.0
    return -100.0 * ((highest - closes[-1]) / (highest - lowest))


def normalize_01(value: float, min_value: float, max_value: float) -> float:
    if max_value <= min_value:
        return 0.5
    return clip((value - min_value) / (max_value - min_value), 0.0, 1.0)
