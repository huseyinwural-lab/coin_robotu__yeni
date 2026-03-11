from datetime import datetime, timezone

from services.pipeline.events import SignalDecision


def _confidence(delta_pct: float) -> float:
    return round(min(max(abs(delta_pct) * 200, 0.35), 0.95), 2)


def _default_signal(symbol: str, strategy_id: str, close: float) -> SignalDecision:
    return SignalDecision(
        signal="none",
        symbol=symbol,
        direction="none",
        confidence=0.0,
        strategy_id=strategy_id,
        reason_codes=["insufficient_data"],
        proposed_entry=close,
        proposed_stop=close,
        proposed_take_profit=close,
        timestamp=datetime.now(timezone.utc),
    )


def evaluate_strategy(
    *,
    strategy_type: str,
    symbol: str,
    primary_candles: list[dict],
    secondary_candles: list[dict],
    spread_bps: float,
    params: dict,
) -> SignalDecision:
    if len(primary_candles) < 8 or len(secondary_candles) < 4:
        close = float(primary_candles[-1]["close"]) if primary_candles else 0
        return _default_signal(symbol, strategy_type, close)

    closes = [float(candle["close"]) for candle in primary_candles[-12:]]
    highs = [float(candle["high"]) for candle in primary_candles[-20:]]
    lows = [float(candle["low"]) for candle in primary_candles[-20:]]
    close = closes[-1]
    avg_close = sum(closes[:-1]) / (len(closes) - 1)
    delta_pct = (close - avg_close) / avg_close if avg_close else 0
    trend_close = float(secondary_candles[-1]["close"])
    trend_prev = float(secondary_candles[-2]["close"])

    signal = "none"
    direction = "none"
    reason_codes: list[str] = []

    if strategy_type == "trend_following":
        if close > avg_close and trend_close > trend_prev:
            signal, direction = "long", "long"
            reason_codes = ["trend_up", "close_above_mean"]
        elif close < avg_close and trend_close < trend_prev:
            signal, direction = "short", "short"
            reason_codes = ["trend_down", "close_below_mean"]

    elif strategy_type == "mean_reversion":
        zscore = (close - avg_close) / avg_close if avg_close else 0
        threshold = float(params.get("zscore_threshold", 0.006))
        if zscore > threshold:
            signal, direction = "short", "short"
            reason_codes = ["overextension_up", "mean_reversion_setup"]
        elif zscore < -threshold:
            signal, direction = "long", "long"
            reason_codes = ["overextension_down", "mean_reversion_setup"]

    elif strategy_type == "breakout":
        recent_high = max(highs[:-1])
        recent_low = min(lows[:-1])
        if close > recent_high:
            signal, direction = "long", "long"
            reason_codes = ["breakout_high", "momentum"]
        elif close < recent_low:
            signal, direction = "short", "short"
            reason_codes = ["breakout_low", "momentum"]
        elif abs(delta_pct) > 0.0025:
            signal = "long" if delta_pct > 0 else "short"
            direction = signal
            reason_codes = ["breakout_momentum_proxy", "delta_trigger"]

    elif strategy_type == "volatility_expansion":
        avg_range = sum(float(c["high"]) - float(c["low"]) for c in primary_candles[-10:-1]) / 9
        current_range = float(primary_candles[-1]["high"]) - float(primary_candles[-1]["low"])
        if current_range > avg_range * 1.8 and spread_bps < 45:
            signal = "long" if close > float(primary_candles[-1]["open"]) else "short"
            direction = signal
            reason_codes = ["range_expansion", "volatility_spike"]

    atr_like = sum(float(c["high"]) - float(c["low"]) for c in primary_candles[-14:]) / 14
    stop_dist = atr_like * float(params.get("atr_stop_multiplier", 1.4))
    take_profit_dist = stop_dist * float(params.get("risk_reward_ratio", 2.0))

    if direction == "long":
        stop = round(close - stop_dist, 6)
        tp = round(close + take_profit_dist, 6)
    elif direction == "short":
        stop = round(close + stop_dist, 6)
        tp = round(close - take_profit_dist, 6)
    else:
        stop = close
        tp = close

    if signal == "none":
        reason_codes = ["no_trigger"]

    return SignalDecision(
        signal=signal,
        symbol=symbol,
        direction=direction,
        confidence=_confidence(delta_pct),
        strategy_id=strategy_type,
        reason_codes=reason_codes,
        proposed_entry=round(close, 6),
        proposed_stop=stop,
        proposed_take_profit=tp,
        timestamp=datetime.now(timezone.utc),
    )