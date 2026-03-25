from datetime import datetime, timezone


def _ema(values: list[float], period: int) -> list[float]:
    if period <= 0 or len(values) < period:
        return []
    multiplier = 2 / (period + 1)
    seed = sum(values[:period]) / period
    ema_values = [seed]
    for value in values[period:]:
        ema_values.append((value - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains = []
    losses = []
    for idx in range(1, period + 1):
        change = values[-idx] - values[-idx - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def generate_strategy_signal(
    *,
    symbol: str,
    closes: list[float],
    strategy_name: str = "ema_rsi",
    ema_fast_period: int = 9,
    ema_slow_period: int = 21,
    rsi_period: int = 14,
    min_confidence: float = 0.55,
) -> dict | None:
    if len(closes) < max(ema_slow_period + 2, rsi_period + 2):
        return None

    fast = _ema(closes, ema_fast_period)
    slow = _ema(closes, ema_slow_period)
    if len(fast) < 2 or len(slow) < 2:
        return None

    current_fast, previous_fast = fast[-1], fast[-2]
    current_slow, previous_slow = slow[-1], slow[-2]
    rsi_value = _rsi(closes, rsi_period)
    if rsi_value is None:
        return None

    crossed_up = previous_fast <= previous_slow and current_fast > current_slow
    crossed_down = previous_fast >= previous_slow and current_fast < current_slow

    side = None
    if crossed_up and rsi_value < 70:
        side = "BUY"
    elif crossed_down and rsi_value > 30:
        side = "SELL"

    if side is None:
        return None

    ema_gap = abs(current_fast - current_slow)
    confidence = min(0.99, 0.5 + min(0.35, ema_gap / max(abs(current_slow), 1e-9)))
    if confidence < min_confidence:
        return None

    return {
        "symbol": str(symbol).upper(),
        "side": side,
        "size": 1.0,
        "confidence": round(confidence, 6),
        "strategy_name": strategy_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
