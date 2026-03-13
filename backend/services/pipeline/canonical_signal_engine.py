from datetime import datetime, timezone
from statistics import fmean, pstdev

from sqlalchemy.orm import Session

from models import CanonicalStrategyRegistry
from services.canonical_strategy_registry_service import GLOBAL_RISK_POLICY, enabled_production_strategies
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


def _rsi(series: list[float], period: int = 14) -> float:
    if len(series) <= period:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for prev, current in zip(series[-(period + 1) : -1], series[-period:]):
        diff = current - prev
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _stochastic(candles: list[dict], period: int = 14) -> float:
    if len(candles) < period:
        return 50.0
    highs = [_safe_float(c["high"]) for c in candles[-period:]]
    lows = [_safe_float(c["low"]) for c in candles[-period:]]
    close = _safe_float(candles[-1]["close"])
    low_min = min(lows)
    high_max = max(highs)
    if high_max == low_min:
        return 50.0
    return ((close - low_min) / (high_max - low_min)) * 100


def _macd_values(closes: list[float]) -> tuple[float, float, float, float]:
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_now = ema12 - ema26

    macd_series: list[float] = []
    for i in range(30, len(closes)):
        segment = closes[: i + 1]
        macd_series.append(_ema(segment, 12) - _ema(segment, 26))

    signal_line = _ema(macd_series[-30:], 9) if macd_series else 0.0
    hist_now = macd_now - signal_line
    hist_prev = (macd_series[-2] - _ema(macd_series[-31:-1], 9)) if len(macd_series) > 2 else 0.0
    return macd_now, signal_line, hist_now, hist_prev


def _vortex_values(candles: list[dict], period: int = 14) -> tuple[float, float, float, float]:
    if len(candles) < period + 2:
        return 0.0, 0.0, 0.0, 0.0

    def calc(window: list[dict]) -> tuple[float, float]:
        tr_sum = 0.0
        vm_plus_sum = 0.0
        vm_minus_sum = 0.0
        for idx in range(1, len(window)):
            prev = window[idx - 1]
            curr = window[idx]
            high = _safe_float(curr["high"])
            low = _safe_float(curr["low"])
            prev_close = _safe_float(prev["close"])
            prev_high = _safe_float(prev["high"])
            prev_low = _safe_float(prev["low"])
            tr_sum += max(high - low, abs(high - prev_close), abs(low - prev_close))
            vm_plus_sum += abs(high - prev_low)
            vm_minus_sum += abs(low - prev_high)
        if tr_sum <= 0:
            return 0.0, 0.0
        return vm_plus_sum / tr_sum, vm_minus_sum / tr_sum

    now_plus, now_minus = calc(candles[-(period + 1) :])
    prev_plus, prev_minus = calc(candles[-(period + 2) : -1])
    return now_plus, now_minus, prev_plus, prev_minus


def _fisher_values(candles: list[dict], length: int = 10) -> tuple[float, float]:
    if len(candles) < length + 3:
        return 0.0, 0.0
    med = [(_safe_float(c["high"]) + _safe_float(c["low"])) / 2 for c in candles]

    def fisher_at(index: int) -> float:
        window = med[index - length + 1 : index + 1]
        highest = max(window)
        lowest = min(window)
        if highest == lowest:
            value = 0.0
        else:
            value = 0.66 * ((med[index] - lowest) / (highest - lowest) - 0.5)
        value = max(min(value, 0.999), -0.999)
        return 0.5 * ((1 + value) / max(1 - value, 1e-9))

    current = fisher_at(len(med) - 1)
    previous = fisher_at(len(med) - 2)
    return current, previous


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


def _evaluate_ichimoku(candles: list[dict]) -> tuple[int, int, list[str]]:
    if len(candles) < 60:
        return 0, 0, ["insufficient_data"]
    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]
    closes = [_safe_float(c["close"]) for c in candles]
    close = closes[-1]

    tenkan = (max(highs[-9:]) + min(lows[-9:])) / 2
    kijun = (max(highs[-26:]) + min(lows[-26:])) / 2
    senkou_a = (tenkan + kijun) / 2
    senkou_b = (max(highs[-52:]) + min(lows[-52:])) / 2

    long_score = 0
    short_score = 0
    reasons = []
    if tenkan > kijun:
        long_score += 3
        reasons.append("tenkan_cross_up")
    if tenkan < kijun:
        short_score += 3

    if close > max(senkou_a, senkou_b):
        long_score += 3
    if close < min(senkou_a, senkou_b):
        short_score += 3

    if senkou_a > senkou_b:
        long_score += 2
    if senkou_a < senkou_b:
        short_score += 2

    if close > closes[-26]:
        long_score += 1
    if close < closes[-26]:
        short_score += 1

    return long_score, short_score, reasons


def _evaluate_golden_cross(candles: list[dict], indicators: dict) -> tuple[int, int, list[str]]:
    if len(candles) < 220:
        return 0, 0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    close = closes[-1]
    ma50 = indicators.get("ema50", 0.0)
    ma200 = indicators.get("ema200", 0.0)
    prev_ma50 = _ema(closes[:-1], 50)
    slope = ma50 - prev_ma50
    long_score = 0
    short_score = 0
    if ma50 > ma200 and close > ma50 and slope > 0:
        long_score += 2
    if ma50 < ma200 and close < ma50 and slope < 0:
        short_score += 2
    return long_score, short_score, []


def _evaluate_supertrend(candles: list[dict], indicators: dict) -> tuple[int, int, list[str]]:
    if len(candles) < 120:
        return 0, 0, ["insufficient_data"]
    prev_indicators = calculate_indicator_snapshot(candles[:-1])
    close = indicators.get("close", 0.0)
    prev_close = _safe_float(candles[-2]["close"])
    ema = indicators.get("ema50", 0.0)
    prev_ema = prev_indicators.get("ema50", ema)
    atr = indicators.get("atr14", 0.0)
    atr_pct = indicators.get("atr_pct", 0.0)

    long_score = 0
    short_score = 0
    if prev_close <= prev_ema and close > ema:
        long_score += 2
    if prev_close >= prev_ema and close < ema:
        short_score += 2
    if atr_pct <= 0.004:
        return 0, 0, ["sideways_atr_band"]
    if close > ema + (atr * 0.2):
        long_score += 1
    if close < ema - (atr * 0.2):
        short_score += 1
    return long_score, short_score, []


def _evaluate_vortex(candles: list[dict]) -> tuple[int, int, list[str]]:
    now_plus, now_minus, prev_plus, prev_minus = _vortex_values(candles)
    long_score = 0
    short_score = 0
    if prev_plus <= prev_minus and now_plus > now_minus:
        long_score += 2
    if prev_minus <= prev_plus and now_minus > now_plus:
        short_score += 2
    if abs(now_plus - now_minus) <= 0.02:
        return 0, 0, ["vortex_converging"]
    return long_score, short_score, []


def _evaluate_bollinger(candles: list[dict]) -> tuple[int, int, list[str]]:
    if len(candles) < 40:
        return 0, 0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    close = closes[-1]
    prev_close = closes[-2]
    window = closes[-20:]
    sma20 = fmean(window)
    std20 = _rolling_std(window)
    upper = sma20 + (2 * std20)
    lower = sma20 - (2 * std20)
    width_pct = ((upper - lower) / sma20) if sma20 else 0.0
    squeeze = width_pct <= 0.06

    long_score = 0
    short_score = 0
    if squeeze and close > upper and close > prev_close:
        long_score += 3
    if squeeze and close < lower and close < prev_close:
        short_score += 3
    return long_score, short_score, []


def _evaluate_moving_momentum(candles: list[dict], indicators: dict) -> tuple[int, int, list[str]]:
    if len(candles) < 170:
        return 0, 0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    ma20 = _ema(closes, 20)
    ma150 = _ema(closes, 150)
    macd_now, signal_line, _, _ = _macd_values(closes[-180:])
    stoch = _stochastic(candles)

    long_score = 0
    short_score = 0
    if ma20 > ma150 and macd_now > signal_line and stoch > 20 and stoch < 50:
        long_score += 2
    if ma20 < ma150 and macd_now < signal_line and stoch < 80 and stoch > 50:
        short_score += 2
    if abs(ma20 - ma150) / max(ma150, 1e-9) < 0.002:
        return 0, 0, ["ma_slope_flat"]
    return long_score, short_score, []


def _evaluate_fibonacci_pullback(candles: list[dict], indicators: dict) -> tuple[int, int, list[str]]:
    if len(candles) < 120:
        return 0, 0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]
    close = closes[-1]
    prev_close = closes[-2]
    ma200 = indicators.get("ema200", _ema(closes, 200))

    long_score = 0
    short_score = 0

    swing_low = min(lows[-80:])
    swing_high = max(highs[-80:])
    span = max(swing_high - swing_low, 1e-9)
    fib38 = swing_high - (span * 0.382)
    fib61 = swing_high - (span * 0.618)
    in_zone_long = fib61 <= close <= fib38

    short_fib38 = swing_low + (span * 0.382)
    short_fib61 = swing_low + (span * 0.618)
    in_zone_short = short_fib38 <= close <= short_fib61

    if close > ma200 and in_zone_long and close > prev_close:
        long_score += 2
    if close < ma200 and in_zone_short and close < prev_close:
        short_score += 2
    return long_score, short_score, []


def _evaluate_macd_impulse(candles: list[dict]) -> tuple[int, int, list[str]]:
    if len(candles) < 80:
        return 0, 0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    macd_now, signal_line, hist_now, hist_prev = _macd_values(closes)

    recent_high = max(closes[-8:-1])
    recent_low = min(closes[-8:-1])
    close = closes[-1]

    long_score = 0
    short_score = 0
    if macd_now > signal_line and hist_now > 0 and close > recent_high:
        long_score += 2
    if macd_now < signal_line and hist_now < 0 and close < recent_low:
        short_score += 2
    if hist_prev > 0 >= hist_now:
        short_score += 1
    if hist_prev < 0 <= hist_now:
        long_score += 1
    return long_score, short_score, []


def _evaluate_fisher_reversal(candles: list[dict]) -> tuple[int, int, list[str]]:
    current, previous = _fisher_values(candles)
    long_score = 0
    short_score = 0
    if current > previous and current < -1.0:
        long_score += 1
    if current < previous and current > 1.0:
        short_score += 1
    if abs(current - previous) < 0.03:
        return 0, 0, ["fisher_flat"]
    return long_score, short_score, []


def _evaluate_divergence(candles: list[dict]) -> tuple[int, int, list[str]]:
    if len(candles) < 50:
        return 0, 0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    rsi_now = _rsi(closes[-30:])
    rsi_prev = _rsi(closes[-36:-6])
    long_score = 0
    short_score = 0
    if closes[-1] < closes[-6] and rsi_now > rsi_prev:
        long_score += 1
    if closes[-1] > closes[-6] and rsi_now < rsi_prev:
        short_score += 1
    return long_score, short_score, []


def _evaluate_structure_breakout(candles: list[dict]) -> tuple[int, int, list[str]]:
    if len(candles) < 60:
        return 0, 0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    close = closes[-1]
    recent_high = max(closes[-25:-1])
    recent_low = min(closes[-25:-1])
    long_score = 2 if close > recent_high else 0
    short_score = 2 if close < recent_low else 0
    if abs(close - recent_high) / max(recent_high, 1e-9) < 0.001 or abs(close - recent_low) / max(recent_low, 1e-9) < 0.001:
        return 0, 0, ["false_breakout_risk"]
    return long_score, short_score, []


def _evaluate_stochastic_exhaustion(candles: list[dict]) -> tuple[int, int, list[str]]:
    if len(candles) < 30:
        return 0, 0, ["insufficient_data"]
    stoch = _stochastic(candles)
    high_prev = _safe_float(candles[-2]["high"])
    low_prev = _safe_float(candles[-2]["low"])
    close = _safe_float(candles[-1]["close"])
    long_score = 1 if stoch < 20 and close > high_prev else 0
    short_score = 1 if stoch > 80 and close < low_prev else 0
    return long_score, short_score, []


def _evaluate_strategy(strategy_id: str, candles: list[dict], indicators: dict) -> tuple[int, int, list[str]]:
    if strategy_id == "ichimoku_trend_continuation":
        return _evaluate_ichimoku(candles)
    if strategy_id == "golden_cross_regime":
        return _evaluate_golden_cross(candles, indicators)
    if strategy_id == "supertrend_flip":
        return _evaluate_supertrend(candles, indicators)
    if strategy_id == "vortex_directional_cross":
        return _evaluate_vortex(candles)
    if strategy_id == "bollinger_squeeze_breakout":
        return _evaluate_bollinger(candles)
    if strategy_id == "moving_momentum":
        return _evaluate_moving_momentum(candles, indicators)
    if strategy_id == "fibonacci_pullback_continuation":
        return _evaluate_fibonacci_pullback(candles, indicators)
    if strategy_id == "macd_impulse":
        return _evaluate_macd_impulse(candles)
    if strategy_id == "fisher_reversal":
        return _evaluate_fisher_reversal(candles)
    if strategy_id == "divergence_reversal_suite":
        return _evaluate_divergence(candles)
    if strategy_id == "structure_breakout":
        return _evaluate_structure_breakout(candles)
    if strategy_id == "stochastic_exhaustion_reentry":
        return _evaluate_stochastic_exhaustion(candles)
    return 0, 0, ["strategy_not_implemented"]


def _apply_direction_mode(long_score: float, short_score: float, strategy: CanonicalStrategyRegistry) -> tuple[float, float]:
    mode = str(strategy.direction or "both").lower()
    if mode == "long":
        return long_score, 0.0
    if mode == "short":
        return 0.0, short_score
    return long_score, short_score


def _direction_from_scores(long_score: float, short_score: float) -> str:
    if long_score >= THRESHOLD and short_score < REJECT_THRESHOLD:
        return "long"
    if short_score >= THRESHOLD and long_score < REJECT_THRESHOLD:
        return "short"
    return "none"


def _resolve_levels(direction: str, entry: float, atr: float, top_source: CanonicalStrategyRegistry) -> tuple[float, float]:
    stop_cfg = top_source.stop_loss or {}
    tp_cfg = top_source.take_profit or {}
    atr_mult = _safe_float(stop_cfg.get("multiplier"), 1.5)
    rr = _safe_float(tp_cfg.get("ratio"), 2.0)

    if direction == "long":
        stop = entry - (atr * atr_mult)
        target = entry + max((entry - stop) * rr, atr)
        return stop, target
    stop = entry + (atr * atr_mult)
    target = entry - max((stop - entry) * rr, atr)
    return stop, target


def scan_canonical_universe_for_signals(db: Session, cache, *, max_symbols: int = 50) -> dict:
    universe = get_spot_tradable_universe(cache)
    symbols = [symbol.upper() for symbol in universe.get("symbols", [])][:max_symbols]
    strategies = enabled_production_strategies(db)

    rows: list[dict] = []
    for symbol in symbols:
        candles = get_json(cache, f"market_data_store:{symbol}:15m") or get_json(cache, f"market:candles:{symbol}:15m") or []
        if len(candles) < 80:
            continue

        indicators = calculate_indicator_snapshot(candles)
        symbol_regime = _regime_label(candles, indicators)

        aggregate_long = 0.0
        aggregate_short = 0.0
        source_rows: list[dict] = []

        for strategy in strategies:
            if strategy.market_regime not in {"any", symbol_regime}:
                continue

            long_raw, short_raw, reasons = _evaluate_strategy(strategy.strategy_id, candles, indicators)
            weighted_long = float(long_raw) * float(strategy.weight or 1)
            weighted_short = float(short_raw) * float(strategy.weight or 1)
            weighted_long, weighted_short = _apply_direction_mode(weighted_long, weighted_short, strategy)

            aggregate_long += weighted_long
            aggregate_short += weighted_short
            source_rows.append(
                {
                    "strategy_id": strategy.strategy_id,
                    "long_score": round(weighted_long, 4),
                    "short_score": round(weighted_short, 4),
                    "reasons": reasons,
                }
            )

        direction = _direction_from_scores(aggregate_long, aggregate_short)
        direction_score = aggregate_long if direction == "long" else aggregate_short if direction == "short" else max(aggregate_long, aggregate_short)
        top_source = max(
            source_rows,
            key=lambda item: item.get("long_score", 0) if direction == "long" else item.get("short_score", 0),
            default=None,
        )

        top_source_id = top_source.get("strategy_id") if top_source else "master_signal_engine"
        top_source_row = next((s for s in strategies if s.strategy_id == top_source_id), None)
        entry = indicators.get("close", 0.0)
        atr = indicators.get("atr14", 0.0)
        stop, target = _resolve_levels(direction, entry, atr, top_source_row) if top_source_row else (entry - atr, entry + atr)

        reason_codes = [
            f"source:{item['strategy_id']}:L{item['long_score']}:S{item['short_score']}"
            for item in sorted(source_rows, key=lambda x: (x.get("long_score", 0) + x.get("short_score", 0)), reverse=True)[:5]
        ]
        if direction == "none" and aggregate_long >= THRESHOLD and aggregate_short >= THRESHOLD:
            reason_codes.append("long_short_conflict")

        rows.append(
            {
                "symbol": symbol,
                "strategy_code": top_source_id,
                "signal": direction,
                "signal_score": round(float(direction_score), 4),
                "signal_strength": round(float(direction_score) / 12, 4),
                "reason_codes": reason_codes,
                "source_strategies": source_rows,
                "long_score": round(float(aggregate_long), 4),
                "short_score": round(float(aggregate_short), 4),
                "market_regime": symbol_regime,
                "entry": entry,
                "stop": stop,
                "take_profit": target,
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
            "global_risk": GLOBAL_RISK_POLICY,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    set_json(cache, "canonical_strategy:last_scan", payload)
    return payload
