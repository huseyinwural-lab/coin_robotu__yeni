from datetime import datetime, timezone
from time import perf_counter
from statistics import fmean, pstdev

from sqlalchemy.orm import Session

from models import CanonicalStrategyRegistry
from services.canonical_strategy_registry_service import GLOBAL_RISK_POLICY, enabled_production_strategies
from services.pipeline.cache_store import get_json, set_json, utc_now_iso
from services.pipeline.legacy.spot_strategy_service import calculate_indicator_snapshot
from services.pipeline.universe_engine import build_effective_universe
from services.strategy_family_gate_service import list_strategy_family_gates, strategy_family_gate_payload


THRESHOLD = 5
REJECT_THRESHOLD = 2
ENGINE_VERSION = "canonical-engine.v3"
SCHEMA_VERSION = "decision-card.v1"
STRATEGY_FAMILY_REGIME = {
    "trend": "trend",
    "breakout": "breakout",
    "pullback": "pullback",
    "reversal": "reversal",
}
FAMILY_ALIAS = {
    "momentum": "trend",
}


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


def _resolve_raw_signal(long_score: float, short_score: float) -> str:
    if long_score > short_score and long_score > 0:
        return "long"
    if short_score > long_score and short_score > 0:
        return "short"
    return "none"


def _normalized_family(family: str) -> str:
    candidate = str(family or "").strip().lower()
    return FAMILY_ALIAS.get(candidate, candidate)


def _eval_ichimoku(candles: list[dict]) -> tuple[float, float, list[str]]:
    if len(candles) < 60:
        return 0.0, 0.0, ["insufficient_data"]
    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]
    closes = [_safe_float(c["close"]) for c in candles]
    close = closes[-1]
    tenkan = (max(highs[-9:]) + min(lows[-9:])) / 2
    kijun = (max(highs[-26:]) + min(lows[-26:])) / 2
    senkou_a = (tenkan + kijun) / 2
    senkou_b = (max(highs[-52:]) + min(lows[-52:])) / 2
    long_score = 0.0
    short_score = 0.0
    reasons: list[str] = []
    if tenkan > kijun:
        long_score += 3
        reasons.append("tenkan_cross_up_kijun")
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


def _eval_golden(candles: list[dict], indicators: dict) -> tuple[float, float, list[str]]:
    if len(candles) < 220:
        return 0.0, 0.0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    close = closes[-1]
    ma50 = indicators.get("ema50", 0.0)
    ma200 = indicators.get("ema200", 0.0)
    slope = ma50 - _ema(closes[:-1], 50)
    long_score = 2.0 if ma50 > ma200 and close > ma50 and slope > 0 else 0.0
    short_score = 2.0 if ma50 < ma200 and close < ma50 and slope < 0 else 0.0
    return long_score, short_score, []


def _eval_supertrend(candles: list[dict], indicators: dict) -> tuple[float, float, list[str]]:
    if len(candles) < 120:
        return 0.0, 0.0, ["insufficient_data"]
    prev_indicators = calculate_indicator_snapshot(candles[:-1])
    close = indicators.get("close", 0.0)
    prev_close = _safe_float(candles[-2]["close"])
    ema = indicators.get("ema50", 0.0)
    prev_ema = prev_indicators.get("ema50", ema)
    atr = indicators.get("atr14", 0.0)
    atr_pct = indicators.get("atr_pct", 0.0)
    if atr_pct <= 0.004:
        return 0.0, 0.0, ["price_sideways_inside_atr_band"]
    long_score = 2.0 if prev_close <= prev_ema and close > ema else 0.0
    short_score = 2.0 if prev_close >= prev_ema and close < ema else 0.0
    if close > ema + (atr * 0.2):
        long_score += 1
    if close < ema - (atr * 0.2):
        short_score += 1
    return long_score, short_score, []


def _eval_vortex(candles: list[dict]) -> tuple[float, float, list[str]]:
    now_plus, now_minus, prev_plus, prev_minus = _vortex_values(candles)
    if abs(now_plus - now_minus) <= 0.02:
        return 0.0, 0.0, ["vortex_lines_converge"]
    long_score = 2.0 if prev_plus <= prev_minus and now_plus > now_minus else 0.0
    short_score = 2.0 if prev_minus <= prev_plus and now_minus > now_plus else 0.0
    return long_score, short_score, []


def _eval_bollinger(candles: list[dict]) -> tuple[float, float, list[str]]:
    if len(candles) < 40:
        return 0.0, 0.0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    close = closes[-1]
    prev_close = closes[-2]
    window = closes[-20:]
    sma20 = fmean(window)
    std20 = _rolling_std(window)
    upper = sma20 + (2 * std20)
    lower = sma20 - (2 * std20)
    width_pct = ((upper - lower) / max(sma20, 1e-9))
    if width_pct > 0.06:
        return 0.0, 0.0, ["compression_missing"]
    long_score = 3.0 if close > upper and close > prev_close else 0.0
    short_score = 3.0 if close < lower and close < prev_close else 0.0
    return long_score, short_score, []


def _eval_moving_momentum(candles: list[dict], indicators: dict) -> tuple[float, float, list[str]]:
    if len(candles) < 170:
        return 0.0, 0.0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    ma20 = _ema(closes, 20)
    ma150 = _ema(closes, 150)
    macd_now, signal_line, _, _ = _macd_values(closes[-180:])
    stoch = _stochastic(candles)
    if abs(ma20 - ma150) / max(ma150, 1e-9) < 0.002:
        return 0.0, 0.0, ["ma_slope_flat"]
    long_score = 2.0 if ma20 > ma150 and macd_now > signal_line and 20 < stoch < 50 else 0.0
    short_score = 2.0 if ma20 < ma150 and macd_now < signal_line and 50 < stoch < 80 else 0.0
    return long_score, short_score, []


def _eval_fib_pullback(candles: list[dict], indicators: dict) -> tuple[float, float, list[str]]:
    if len(candles) < 120:
        return 0.0, 0.0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]
    close = closes[-1]
    prev_close = closes[-2]
    ma200 = indicators.get("ema200", _ema(closes, 200))
    swing_low = min(lows[-80:])
    swing_high = max(highs[-80:])
    span = max(swing_high - swing_low, 1e-9)
    fib38 = swing_high - (span * 0.382)
    fib61 = swing_high - (span * 0.618)
    short_fib38 = swing_low + (span * 0.382)
    short_fib61 = swing_low + (span * 0.618)
    long_score = 2.0 if close > ma200 and fib61 <= close <= fib38 and close > prev_close else 0.0
    short_score = 2.0 if close < ma200 and short_fib38 <= close <= short_fib61 and close < prev_close else 0.0
    return long_score, short_score, []


def _eval_macd_impulse(candles: list[dict]) -> tuple[float, float, list[str]]:
    if len(candles) < 80:
        return 0.0, 0.0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    macd_now, signal_line, hist_now, hist_prev = _macd_values(closes)
    recent_high = max(closes[-8:-1])
    recent_low = min(closes[-8:-1])
    close = closes[-1]
    long_score = 2.0 if macd_now > signal_line and hist_now > 0 and close > recent_high else 0.0
    short_score = 2.0 if macd_now < signal_line and hist_now < 0 and close < recent_low else 0.0
    if hist_prev < 0 <= hist_now:
        long_score += 1
    if hist_prev > 0 >= hist_now:
        short_score += 1
    return long_score, short_score, []


def _eval_fisher(candles: list[dict]) -> tuple[float, float, list[str]]:
    current, previous = _fisher_values(candles)
    if abs(current - previous) < 0.03:
        return 0.0, 0.0, ["fisher_stays_flat"]
    long_score = 1.0 if current > previous and current < -1.0 else 0.0
    short_score = 1.0 if current < previous and current > 1.0 else 0.0
    return long_score, short_score, []


def _eval_divergence(candles: list[dict]) -> tuple[float, float, list[str]]:
    if len(candles) < 50:
        return 0.0, 0.0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    rsi_now = _rsi(closes[-30:])
    rsi_prev = _rsi(closes[-36:-6])
    long_score = 1.0 if closes[-1] < closes[-6] and rsi_now > rsi_prev else 0.0
    short_score = 1.0 if closes[-1] > closes[-6] and rsi_now < rsi_prev else 0.0
    return long_score, short_score, []


def _eval_structure(candles: list[dict]) -> tuple[float, float, list[str]]:
    if len(candles) < 60:
        return 0.0, 0.0, ["insufficient_data"]
    closes = [_safe_float(c["close"]) for c in candles]
    close = closes[-1]
    recent_high = max(closes[-25:-1])
    recent_low = min(closes[-25:-1])
    if abs(close - recent_high) / max(recent_high, 1e-9) < 0.001 or abs(close - recent_low) / max(recent_low, 1e-9) < 0.001:
        return 0.0, 0.0, ["false_breakout"]
    long_score = 2.0 if close > recent_high else 0.0
    short_score = 2.0 if close < recent_low else 0.0
    return long_score, short_score, []


def _eval_stoch_exhaustion(candles: list[dict]) -> tuple[float, float, list[str]]:
    if len(candles) < 30:
        return 0.0, 0.0, ["insufficient_data"]
    stoch = _stochastic(candles)
    high_prev = _safe_float(candles[-2]["high"])
    low_prev = _safe_float(candles[-2]["low"])
    close = _safe_float(candles[-1]["close"])
    long_score = 1.0 if stoch < 20 and close > high_prev else 0.0
    short_score = 1.0 if stoch > 80 and close < low_prev else 0.0
    return long_score, short_score, []


def _evaluate_strategy(strategy_id: str, candles: list[dict], indicators: dict) -> tuple[float, float, list[str]]:
    if strategy_id == "ichimoku_trend_continuation":
        return _eval_ichimoku(candles)
    if strategy_id == "golden_cross_regime":
        return _eval_golden(candles, indicators)
    if strategy_id == "supertrend_flip":
        return _eval_supertrend(candles, indicators)
    if strategy_id == "vortex_directional_cross":
        return _eval_vortex(candles)
    if strategy_id == "bollinger_squeeze_breakout":
        return _eval_bollinger(candles)
    if strategy_id == "moving_momentum":
        return _eval_moving_momentum(candles, indicators)
    if strategy_id == "fibonacci_pullback_continuation":
        return _eval_fib_pullback(candles, indicators)
    if strategy_id == "macd_impulse":
        return _eval_macd_impulse(candles)
    if strategy_id == "fisher_reversal":
        return _eval_fisher(candles)
    if strategy_id == "divergence_reversal_suite":
        return _eval_divergence(candles)
    if strategy_id == "structure_breakout":
        return _eval_structure(candles)
    if strategy_id == "stochastic_exhaustion_reentry":
        return _eval_stoch_exhaustion(candles)
    return 0.0, 0.0, ["strategy_not_implemented"]


def _resolve_levels(entry: float, atr: float, decision: str, top_strategy: CanonicalStrategyRegistry | None) -> tuple[float, float, float]:
    if top_strategy is None:
        if decision == "LONG":
            return entry - atr, entry + (atr * 1.5), entry + (atr * 2.5)
        if decision == "SHORT":
            return entry + atr, entry - (atr * 1.5), entry - (atr * 2.5)
        return entry, entry, entry
    stop_cfg = top_strategy.stop_loss or {}
    tp_cfg = top_strategy.take_profit or {}
    atr_mult = _safe_float(stop_cfg.get("multiplier"), 1.5)
    ratio = _safe_float(tp_cfg.get("ratio"), 2.0)
    if decision == "LONG":
        stop = entry - (atr * atr_mult)
        risk = max(entry - stop, atr)
        tp1 = entry + risk * min(ratio, 1.5)
        tp2 = entry + risk * ratio
        return stop, tp1, tp2
    if decision == "SHORT":
        stop = entry + (atr * atr_mult)
        risk = max(stop - entry, atr)
        tp1 = entry - risk * min(ratio, 1.5)
        tp2 = entry - risk * ratio
        return stop, tp1, tp2
    return entry, entry, entry


def scan_canonical_universe_for_signals(
    db: Session,
    cache,
    *,
    max_symbols: int = 50,
    symbols_override: list[str] | None = None,
) -> dict:
    cycle_started = perf_counter()
    universe = build_effective_universe(db, cache)
    advisory_lookup = (universe.get("liquidity_advisory") or {}).get("spot") or {}
    if symbols_override:
        symbols = sorted({str(symbol or "").upper().strip() for symbol in symbols_override if str(symbol or "").strip()})
    else:
        symbols = [symbol.upper() for symbol in (universe.get("spot_symbols") or [])]
    symbols = symbols[: max(1, min(int(max_symbols or 50), 2000))]
    strategies = enabled_production_strategies(db)
    family_gates = {row["family"]: row for row in [strategy_family_gate_payload(item) for item in list_strategy_family_gates(db)]}

    ranked_rows: list[dict] = []
    symbol_perf: list[dict] = []
    strategy_perf: dict[str, dict] = {}
    for symbol in symbols:
        symbol_started = perf_counter()
        candles = get_json(cache, f"market_data_store:{symbol}:15m") or get_json(cache, f"market:candles:{symbol}:15m") or []
        if len(candles) < 80:
            ranked_rows.append(
                {
                    "symbol": symbol,
                    "signal": "none",
                    "final_decision": "NO_TRADE",
                    "signal_score": 0.0,
                    "signal_strength": 0.0,
                    "long_score": 0.0,
                    "short_score": 0.0,
                    "winning_side": "none",
                    "decision_confidence": 0.0,
                    "source_strategies": [],
                    "family_scores": {},
                    "blocked_reason_current": "NO_DATA",
                    "blocked_reason_timeline": [],
                    "risk_state": {"state": "unresolved"},
                    "cooldown_state": {"state": "unresolved"},
                    "regime_state": {"state": "unresolved"},
                    "reason_codes": ["no_data"],
                    "strategy_code": "master_signal_engine",
                    "market_regime": "unresolved",
                    "entry": 0.0,
                    "stop": 0.0,
                    "take_profit_1": 0.0,
                    "take_profit_2": 0.0,
                    "invalidation": {"reason": "no_data"},
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "schema_version": SCHEMA_VERSION,
                    "engine_version": ENGINE_VERSION,
                }
            )
            symbol_perf.append({"symbol": symbol, "elapsed_ms": round((perf_counter() - symbol_started) * 1000, 4)})
            continue

        indicators = calculate_indicator_snapshot(candles)
        regime = _regime_label(candles, indicators)
        entry = _safe_float(indicators.get("close"), 0.0)
        atr = max(_safe_float(indicators.get("atr14"), 0.0), 0.0000001)
        if entry <= 0:
            ranked_rows.append(
                {
                    "symbol": symbol,
                    "signal": "none",
                    "final_decision": "NO_TRADE",
                    "signal_score": 0.0,
                    "signal_strength": 0.0,
                    "long_score": 0.0,
                    "short_score": 0.0,
                    "winning_side": "none",
                    "decision_confidence": 0.0,
                    "source_strategies": [],
                    "family_scores": {},
                    "blocked_reason_current": "STALE_INDICATOR_SNAPSHOT",
                    "blocked_reason_timeline": [],
                    "risk_state": {"state": "unresolved", "reason": "risk_state_unresolved"},
                    "cooldown_state": {"state": "clear"},
                    "regime_state": {"state": "unresolved", "reason": "stale_indicator_snapshot"},
                    "reason_codes": ["stale_indicator_snapshot"],
                    "strategy_code": "master_signal_engine",
                    "market_regime": "unresolved",
                    "dominant_family": None,
                    "supporting_families": [],
                    "top_contributors": [],
                    "entry": 0.0,
                    "entry_zone": {},
                    "stop": 0.0,
                    "take_profit_1": 0.0,
                    "take_profit_2": 0.0,
                    "take_profit": 0.0,
                    "invalidation": {"reason": "stale_indicator_snapshot"},
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "schema_version": SCHEMA_VERSION,
                    "engine_version": ENGINE_VERSION,
                }
            )
            symbol_perf.append({"symbol": symbol, "elapsed_ms": round((perf_counter() - symbol_started) * 1000, 4)})
            continue
        breakout_condition = _safe_float(indicators.get("atr_pct"), 0.0) >= 0.01
        pullback_trend_clear = abs(_safe_float(indicators.get("ema50"), 0) - _safe_float(indicators.get("ema200"), 0)) / max(
            _safe_float(indicators.get("ema200"), 1), 1e-9
        ) >= 0.002

        contributions: list[dict] = []
        family_scores: dict[str, dict] = {}

        for strategy in strategies:
            strategy_started = perf_counter()
            normalized_family = _normalized_family(strategy.strategy_family)
            raw_long, raw_short, reasons = _evaluate_strategy(strategy.strategy_id, candles, indicators)
            strategy_elapsed = (perf_counter() - strategy_started) * 1000
            stat = strategy_perf.setdefault(strategy.strategy_id, {"strategy_id": strategy.strategy_id, "calls": 0, "total_ms": 0.0})
            stat["calls"] += 1
            stat["total_ms"] += strategy_elapsed
            weighted_long = float(raw_long) * float(strategy.weight or 1)
            weighted_short = float(raw_short) * float(strategy.weight or 1)
            raw_signal = _resolve_raw_signal(raw_long, raw_short)
            if str(strategy.direction).lower() == "long" and raw_signal == "short":
                weighted_short = 0.0
                raw_signal = "none"
            if str(strategy.direction).lower() == "short" and raw_signal == "long":
                weighted_long = 0.0
                raw_signal = "none"

            contribution_score = weighted_long if raw_signal == "long" else weighted_short if raw_signal == "short" else 0.0
            normalized_score = round(min(max(abs(contribution_score) / 6, 0), 1), 4)
            status = "accepted" if raw_signal != "none" else "rejected"

            contribution = {
                "strategy_id": strategy.strategy_id,
                "family": normalized_family,
                "direction": strategy.direction,
                "raw_signal": raw_signal,
                "normalized_score": normalized_score,
                "weight": float(strategy.weight or 1),
                "contribution_score": round(float(contribution_score), 4),
                "status": status,
                "weighted_long": round(float(weighted_long), 4),
                "weighted_short": round(float(weighted_short), 4),
                "reasons": reasons,
            }
            contributions.append(contribution)

            family_row = family_scores.setdefault(
                normalized_family,
                {
                    "long_score": 0.0,
                    "short_score": 0.0,
                    "strategies_accepted": 0,
                    "strategies_rejected": 0,
                    "gate_status": "PENDING",
                    "gate_reason": "pending",
                    "threshold_used": {"long": 0, "short": 0},
                    "score_seen": {"long": 0.0, "short": 0.0, "conflict": 0.0},
                },
            )
            family_row["long_score"] += weighted_long
            family_row["short_score"] += weighted_short
            if status == "accepted":
                family_row["strategies_accepted"] += 1
            else:
                family_row["strategies_rejected"] += 1

        reason_codes: list[str] = []
        for family, score_row in family_scores.items():
            gate = family_gates.get(family)
            if gate is None:
                score_row["gate_status"] = "REJECTED"
                score_row["gate_reason"] = "missing_family_gate_config"
                reason_codes.append("family_gate_missing")
                for c in contributions:
                    if c["family"] == family and c["status"] == "accepted":
                        c["status"] = "gated"
                        c["contribution_score"] = 0.0
                        c["weighted_long"] = 0.0
                        c["weighted_short"] = 0.0
                continue

            score_row["threshold_used"] = {"long": gate["long_threshold"], "short": gate["short_threshold"]}
            long_seen = float(score_row["long_score"])
            short_seen = float(score_row["short_score"])
            dominant_side = "long" if long_seen >= short_seen else "short"
            dominant_score = long_seen if dominant_side == "long" else short_seen
            conflict_score = short_seen if dominant_side == "long" else long_seen
            score_row["score_seen"] = {"long": round(long_seen, 4), "short": round(short_seen, 4), "conflict": round(conflict_score, 4)}

            gate_status = "ACCEPTED"
            gate_reason = "gate_passed"
            expected_regime = STRATEGY_FAMILY_REGIME.get(family)
            if not gate["is_enabled"]:
                gate_status = "REJECTED"
                gate_reason = "family_disabled"
            elif gate["regime_match_required"] and expected_regime and regime != expected_regime:
                gate_status = "REJECTED"
                gate_reason = "regime_mismatch"
            elif family == "breakout" and not breakout_condition:
                gate_status = "REJECTED"
                gate_reason = "breakout_condition_missing"
            elif family == "pullback" and not pullback_trend_clear:
                gate_status = "REJECTED"
                gate_reason = "pullback_trend_unclear"
            elif dominant_side == "long" and dominant_score < gate["long_threshold"]:
                gate_status = "REJECTED"
                gate_reason = "long_threshold_not_met"
            elif dominant_side == "short" and dominant_score < gate["short_threshold"]:
                gate_status = "REJECTED"
                gate_reason = "short_threshold_not_met"
            elif score_row["strategies_accepted"] < gate["min_strategy_count"]:
                gate_status = "REJECTED"
                gate_reason = "min_strategy_count_not_met"
            elif conflict_score > gate["max_conflict_score"]:
                gate_status = "REJECTED"
                gate_reason = "conflict_score_exceeded"

            if family == "reversal" and gate.get("reversal_extra_confirmation") and gate_status == "ACCEPTED":
                non_reversal_support = any(
                    fam != "reversal"
                    and row["gate_status"] == "ACCEPTED"
                    and ((dominant_side == "long" and row["long_score"] > 0) or (dominant_side == "short" and row["short_score"] > 0))
                    for fam, row in family_scores.items()
                )
                if not non_reversal_support:
                    gate_status = "REJECTED"
                    gate_reason = "reversal_extra_confirmation_required"

            score_row["gate_status"] = gate_status
            score_row["gate_reason"] = gate_reason

            if gate_status != "ACCEPTED":
                reason_codes.append(gate_reason)
                for c in contributions:
                    if c["family"] == family and c["status"] == "accepted":
                        c["status"] = "gated"
                        c["contribution_score"] = 0.0
                        c["weighted_long"] = 0.0
                        c["weighted_short"] = 0.0

        aggregate_long = sum(c["weighted_long"] for c in contributions if c["status"] == "accepted")
        aggregate_short = sum(c["weighted_short"] for c in contributions if c["status"] == "accepted")
        winning_side = "long" if aggregate_long > aggregate_short else "short" if aggregate_short > aggregate_long else "none"
        confidence = round(min(max(max(aggregate_long, aggregate_short) / 12, 0), 1), 4)
        liquidity_advisory = advisory_lookup.get(symbol) or {}
        confidence_penalty = _safe_float(liquidity_advisory.get("confidence_penalty"), 0.0)
        risk_score_bonus = _safe_float(liquidity_advisory.get("risk_score_bonus"), 0.0)
        if liquidity_advisory.get("data_available") is False:
            reason_codes.append("data_unavailable")
        if liquidity_advisory.get("volume_low"):
            reason_codes.append("liquidity_volume_low")
        if liquidity_advisory.get("spread_high"):
            reason_codes.append("liquidity_spread_high")
        adjusted_confidence = round(max(0.0, min(1.0, confidence - confidence_penalty)), 4)

        final_decision = "NO_TRADE"
        blocked_reason = None
        if aggregate_long >= THRESHOLD and aggregate_short < REJECT_THRESHOLD:
            final_decision = "LONG"
        elif aggregate_short >= THRESHOLD and aggregate_long < REJECT_THRESHOLD:
            final_decision = "SHORT"
        elif aggregate_long >= THRESHOLD or aggregate_short >= THRESHOLD:
            final_decision = "BLOCKED"
            blocked_reason = "opposite_score_reject_conflict"
            reason_codes.append("opposite_score_reject_conflict")
        else:
            reason_codes.append("threshold_not_met")

        if final_decision in {"LONG", "SHORT"}:
            supporting_families = [
                family
                for family, data in family_scores.items()
                if data["gate_status"] == "ACCEPTED"
                and ((final_decision == "LONG" and data["long_score"] > 0) or (final_decision == "SHORT" and data["short_score"] > 0))
            ]
            if final_decision == "LONG" and supporting_families == ["reversal"]:
                final_decision = "BLOCKED"
                blocked_reason = "reversal_requires_confirmation"
                reason_codes.append("reversal_requires_confirmation")
            if final_decision == "SHORT" and supporting_families == ["reversal"]:
                final_decision = "BLOCKED"
                blocked_reason = "reversal_requires_confirmation"
                reason_codes.append("reversal_requires_confirmation")

        signal = "long" if final_decision == "LONG" else "short" if final_decision == "SHORT" else "none"
        accepted_contributors = [c for c in contributions if c["status"] == "accepted"]
        accepted_contributors.sort(key=lambda item: item["contribution_score"], reverse=True)
        dominant_strategy_id = accepted_contributors[0]["strategy_id"] if accepted_contributors else "master_signal_engine"
        dominant_family = accepted_contributors[0]["family"] if accepted_contributors else None
        top_strategy_row = next((row for row in strategies if row.strategy_id == dominant_strategy_id), None)
        stop, tp1, tp2 = _resolve_levels(entry, atr, final_decision, top_strategy_row)
        invalidation = top_strategy_row.invalidation if top_strategy_row is not None else {"rules": ["score_conflict"]}

        top_contributors = []
        for contribution in accepted_contributors[:3]:
            top_contributors.append({
                "strategy_id": contribution["strategy_id"],
                "family": contribution["family"],
                "direction": contribution["direction"],
                "raw_signal": contribution["raw_signal"],
                "normalized_score": contribution["normalized_score"],
                "weight": contribution["weight"],
                "contribution_score": contribution["contribution_score"],
                "status": contribution["status"],
            })

        ranked_rows.append(
            {
                "symbol": symbol,
                "strategy_code": dominant_strategy_id,
                "signal": signal,
                "final_decision": final_decision,
                "signal_score": round(float(max(aggregate_long, aggregate_short)), 4),
                "signal_strength": adjusted_confidence,
                "long_score": round(float(aggregate_long), 4),
                "short_score": round(float(aggregate_short), 4),
                "winning_side": winning_side,
                "decision_confidence": adjusted_confidence,
                "source_strategies": [
                    {
                        "strategy_id": c["strategy_id"],
                        "family": c["family"],
                        "direction": c["direction"],
                        "raw_signal": c["raw_signal"],
                        "normalized_score": c["normalized_score"],
                        "weight": c["weight"],
                        "contribution_score": c["contribution_score"],
                        "status": c["status"],
                    }
                    for c in contributions
                ],
                "family_scores": family_scores,
                "blocked_reason_current": blocked_reason,
                "blocked_reason_timeline": [],
                "risk_state": {
                    "state": "advisory" if risk_score_bonus > 0 else "clear",
                    "reason": "liquidity_advisory" if risk_score_bonus > 0 else "clear",
                    "risk_score_bonus": round(risk_score_bonus, 6),
                },
                "cooldown_state": {"state": "clear"},
                "regime_state": {"state": "resolved", "market_regime": regime},
                "reason_codes": sorted(set(reason_codes)),
                "liquidity_advisory": liquidity_advisory,
                "market_regime": regime,
                "dominant_family": dominant_family,
                "supporting_families": [
                    family
                    for family, data in family_scores.items()
                    if data["gate_status"] == "ACCEPTED"
                    and ((final_decision == "LONG" and data["long_score"] > 0) or (final_decision == "SHORT" and data["short_score"] > 0))
                ],
                "top_contributors": top_contributors,
                "entry": entry,
                "entry_zone": {"min": round(entry - atr * 0.2, 8), "max": round(entry + atr * 0.2, 8)},
                "stop": round(stop, 8),
                "take_profit_1": round(tp1, 8),
                "take_profit_2": round(tp2, 8),
                "take_profit": round(tp2, 8),
                "invalidation": invalidation,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "schema_version": SCHEMA_VERSION,
                "engine_version": ENGINE_VERSION,
            }
        )
        symbol_perf.append({"symbol": symbol, "elapsed_ms": round((perf_counter() - symbol_started) * 1000, 4)})

    priority_map = {"LONG": 4, "SHORT": 3, "BLOCKED": 2, "NO_TRADE": 1}
    ranked_rows.sort(
        key=lambda item: (
            priority_map.get(item.get("final_decision", "NO_TRADE"), 0),
            max(_safe_float(item.get("long_score")), _safe_float(item.get("short_score"))),
        ),
        reverse=True,
    )
    executable = [row for row in ranked_rows if row.get("signal") in {"long", "short"}]
    cycle_duration_ms = (perf_counter() - cycle_started) * 1000
    top_slow_symbols = sorted(symbol_perf, key=lambda item: float(item.get("elapsed_ms") or 0), reverse=True)[:20]
    strategy_perf_rows = []
    for item in strategy_perf.values():
        calls = int(item.get("calls") or 0)
        total_ms = float(item.get("total_ms") or 0.0)
        strategy_perf_rows.append(
            {
                "strategy_id": item.get("strategy_id"),
                "calls": calls,
                "total_ms": round(total_ms, 4),
                "avg_ms": round(total_ms / max(calls, 1), 4),
            }
        )
    strategy_perf_rows.sort(key=lambda item: float(item.get("avg_ms") or 0), reverse=True)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "generated_at": utc_now_iso(),
        "symbol_count": len(symbols),
        "strategies_count": len(strategies),
        "executable_count": len(executable),
        "top_executable": executable[:25],
        "top_ranked": ranked_rows[:250],
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
        "performance": {
            "cycle_duration_ms": round(cycle_duration_ms, 4),
            "symbols_evaluated": len(symbols),
            "avg_symbol_eval_ms": round(cycle_duration_ms / max(len(symbols), 1), 4),
            "top_slow_symbols": top_slow_symbols,
            "top_slow_strategies": strategy_perf_rows[:20],
        },
    }
    set_json(cache, "canonical_strategy:last_scan", payload)
    return payload
