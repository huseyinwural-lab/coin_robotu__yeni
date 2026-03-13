from datetime import datetime, timezone
from statistics import fmean, pstdev

from sqlalchemy.orm import Session

from models import CanonicalStrategyRegistry
from services.canonical_strategy_registry_service import enabled_production_strategies
from services.pipeline.cache_store import get_json, set_json, utc_now_iso
from services.pipeline.legacy.spot_strategy_service import calculate_indicator_snapshot, get_spot_tradable_universe


THRESHOLD = 5
REJECT_THRESHOLD = 2


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _ema(series: list[float], period: int) -> float:
    if not series:
        return 0.0
    alpha = 2 / (period + 1)
    value = series[0]
    for item in series[1:]:
        value = (item * alpha) + (value * (1 - alpha))
    return float(value)


def _rolling_std(series: list[float]) -> float:
    if len(series) < 2:
        return 0.0
    return float(pstdev(series))


def _direction_from_scores(long_score: int, short_score: int) -> tuple[str, list[str]]:
    notes: list[str] = []
    if long_score >= THRESHOLD and short_score < REJECT_THRESHOLD:
        return "long", notes
    if short_score >= THRESHOLD and long_score < REJECT_THRESHOLD:
        return "short", notes
    if long_score >= THRESHOLD and short_score >= THRESHOLD:
        notes.append("long_short_conflict")
    return "none", notes


def _apply_direction_mode(signal: str, row: CanonicalStrategyRegistry) -> str:
    mode = str(row.direction or "both").lower()
    if mode == "long" and signal == "short":
        return "none"
    if mode == "short" and signal == "long":
        return "none"
    return signal


def _regime_label(candles: list[dict], indicators: dict) -> str:
    close = indicators.get("close", 0.0)
    ema50 = indicators.get("ema50", 0.0)
    ema200 = indicators.get("ema200", 0.0)
    atr_pct = indicators.get("atr_pct", 0.0)
    rsi = indicators.get("rsi14", 50)

    if atr_pct >= 0.02:
        return "breakout"
    if ema50 > ema200 and close >= ema50 and rsi >= 48:
        return "trend"
    if ema50 < ema200 and close <= ema50 and rsi <= 52:
        return "trend"
    if 40 <= rsi <= 60 and abs(close - ema50) / max(ema50, 1e-9) <= 0.01:
        return "pullback"
    return "reversal"


def _evaluate_ichimoku(candles: list[dict]) -> tuple[str, int, int, list[str]]:
    if len(candles) < 60:
        return "none", 0, 0, ["insufficient_data"]

    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]
    closes = [_safe_float(c["close"]) for c in candles]
    close = closes[-1]

    tenkan = (max(highs[-9:]) + min(lows[-9:])) / 2
    kijun = (max(highs[-26:]) + min(lows[-26:])) / 2
    senkou_a = (tenkan + kijun) / 2
    senkou_b = (max(highs[-52:]) + min(lows[-52:])) / 2
    chikou_ok_long = close > closes[-26]
    chikou_ok_short = close < closes[-26]

    long_score = 0
    short_score = 0
    reasons: list[str] = []

    if tenkan > kijun:
        long_score += 3
        reasons.append("tenkan_above_kijun")
    else:
        short_score += 3

    cloud_top = max(senkou_a, senkou_b)
    cloud_bottom = min(senkou_a, senkou_b)
    if close > cloud_top:
        long_score += 3
        reasons.append("price_above_cloud")
    elif close < cloud_bottom:
        short_score += 3

    if senkou_a > senkou_b:
        long_score += 2
        reasons.append("senkou_a_above_senkou_b")
    else:
        short_score += 2

    if chikou_ok_long:
        long_score += 1
    if chikou_ok_short:
        short_score += 1

    signal, notes = _direction_from_scores(long_score, short_score)
    return signal, long_score, short_score, reasons + notes


def _evaluate_supertrend_flip(candles: list[dict]) -> tuple[str, int, int, list[str]]:
    if len(candles) < 120:
        return "none", 0, 0, ["insufficient_data"]
    indicators = calculate_indicator_snapshot(candles)
    prev_indicators = calculate_indicator_snapshot(candles[:-1])
    close = indicators.get("close", 0.0)
    prev_close = _safe_float(candles[-2].get("close"))
    atr = indicators.get("atr14", 0.0)
    ema = indicators.get("ema50", 0.0)
    prev_ema = prev_indicators.get("ema50", ema)

    long_score = 0
    short_score = 0
    reasons: list[str] = []

    if prev_close <= prev_ema and close > ema:
        long_score += 3
        reasons.append("supertrend_flip_long")
    if prev_close >= prev_ema and close < ema:
        short_score += 3

    if close > ema + (atr * 0.25):
        long_score += 2
    if close < ema - (atr * 0.25):
        short_score += 2

    atr_pct = indicators.get("atr_pct", 0.0)
    if atr_pct >= 0.008:
        if close >= ema:
            long_score += 1
        else:
            short_score += 1

    signal, notes = _direction_from_scores(long_score, short_score)
    return signal, long_score, short_score, reasons + notes


def _evaluate_bollinger_squeeze(candles: list[dict]) -> tuple[str, int, int, list[str]]:
    if len(candles) < 40:
        return "none", 0, 0, ["insufficient_data"]

    closes = [_safe_float(c["close"]) for c in candles]
    close = closes[-1]
    prev_close = closes[-2]
    window = closes[-20:]
    sma20 = fmean(window)
    std20 = _rolling_std(window)
    upper = sma20 + (2 * std20)
    lower = sma20 - (2 * std20)
    width_pct = ((upper - lower) / sma20) if sma20 else 0.0

    long_score = 0
    short_score = 0
    reasons: list[str] = []

    squeeze = width_pct <= 0.06
    if squeeze:
        long_score += 2
        short_score += 2
        reasons.append("squeeze_detected")

    if close > upper:
        long_score += 3
        reasons.append("upper_band_break")
    if close < lower:
        short_score += 3

    if close > prev_close:
        long_score += 1
    if close < prev_close:
        short_score += 1

    signal, notes = _direction_from_scores(long_score, short_score)
    return signal, long_score, short_score, reasons + notes


def _evaluate_macd_impulse(candles: list[dict]) -> tuple[str, int, int, list[str]]:
    if len(candles) < 60:
        return "none", 0, 0, ["insufficient_data"]

    closes = [_safe_float(c["close"]) for c in candles]
    ema12 = _ema(closes[-80:], 12)
    ema26 = _ema(closes[-120:], 26)
    macd_now = ema12 - ema26

    series = closes[-80:]
    macd_series: list[float] = []
    for i in range(30, len(series)):
        segment = series[: i + 1]
        macd_series.append(_ema(segment, 12) - _ema(segment, 26))
    signal_line = _ema(macd_series[-30:], 9) if macd_series else 0.0
    hist_now = macd_now - signal_line
    hist_prev = (macd_series[-2] - _ema(macd_series[-31:-1], 9)) if len(macd_series) > 2 else 0.0

    long_score = 0
    short_score = 0
    reasons: list[str] = []

    if macd_now > signal_line:
        long_score += 3
        reasons.append("macd_above_signal")
    if macd_now < signal_line:
        short_score += 3

    if hist_prev <= 0 < hist_now:
        long_score += 2
        reasons.append("histogram_flip_positive")
    if hist_prev >= 0 > hist_now:
        short_score += 2

    if abs(macd_now) <= max(abs(signal_line), 1e-9) * 1.4:
        if macd_now >= 0:
            long_score += 1
        else:
            short_score += 1

    signal, notes = _direction_from_scores(long_score, short_score)
    return signal, long_score, short_score, reasons + notes


def _evaluate_strategy(strategy_id: str, candles: list[dict]) -> tuple[str, int, int, list[str]]:
    if strategy_id == "ichimoku_trend_continuation":
        return _evaluate_ichimoku(candles)
    if strategy_id == "supertrend_flip":
        return _evaluate_supertrend_flip(candles)
    if strategy_id == "bollinger_squeeze_breakout":
        return _evaluate_bollinger_squeeze(candles)
    if strategy_id == "macd_impulse":
        return _evaluate_macd_impulse(candles)
    return "none", 0, 0, ["strategy_not_enabled_in_sprint1"]


def scan_canonical_universe_for_signals(db: Session, cache, *, max_symbols: int = 50) -> dict:
    universe = get_spot_tradable_universe(cache)
    symbols = [symbol.upper() for symbol in universe.get("symbols", [])][:max_symbols]
    strategies = enabled_production_strategies(db)

    rows: list[dict] = []
    for symbol in symbols:
        candles = get_json(cache, f"market_data_store:{symbol}:15m") or get_json(cache, f"market:candles:{symbol}:15m") or []
        if len(candles) < 60:
            continue

        indicators = calculate_indicator_snapshot(candles)
        symbol_regime = _regime_label(candles, indicators)

        for strategy in strategies:
            if strategy.market_regime not in {"any", symbol_regime}:
                continue

            signal, long_score, short_score, reason_codes = _evaluate_strategy(strategy.strategy_id, candles)
            signal = _apply_direction_mode(signal, strategy)

            if signal == "none":
                score = max(long_score, short_score)
            else:
                score = long_score if signal == "long" else short_score

            rows.append(
                {
                    "symbol": symbol,
                    "strategy_code": strategy.strategy_id,
                    "strategy_family": strategy.strategy_family,
                    "signal": signal,
                    "signal_score": float(score),
                    "signal_strength": round(float(score) / 10, 4),
                    "reason_codes": reason_codes,
                    "long_score": long_score,
                    "short_score": short_score,
                    "market_regime": symbol_regime,
                    "entry": indicators.get("close", 0.0),
                    "stop": indicators.get("close", 0.0) - indicators.get("atr14", 0.0),
                    "take_profit": indicators.get("close", 0.0) + (indicators.get("atr14", 0.0) * 1.8),
                }
            )

    rows.sort(key=lambda item: (item.get("signal") != "none", item.get("signal_score", 0.0)), reverse=True)
    executable = [item for item in rows if item.get("signal") in {"long", "short"}]
    payload = {
        "generated_at": utc_now_iso(),
        "symbol_count": len(symbols),
        "strategies_count": len(strategies),
        "executable_count": len(executable),
        "top_executable": executable[:25],
        "top_ranked": rows[:250],
        "score_model": {
            "threshold": THRESHOLD,
            "reject_threshold": REJECT_THRESHOLD,
            "strong_confirmation": 3,
            "medium_confirmation": 2,
            "weak_confirmation": 1,
            "contradiction": -2,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    set_json(cache, "canonical_strategy:last_scan", payload)
    return payload
