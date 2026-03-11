import json
from dataclasses import dataclass

from services.pipeline.cache_store import get_json, set_json, utc_now_iso
from services.pipeline.spot_strategy_service import (
    _pullback_quality,
    _safe_float,
    _trend_strength,
    calculate_indicator_snapshot,
)

MARKET_REGIMES = {"TRENDING", "RANGING", "VOLATILE"}
MULTIPLIER_VERSION = "v1"
MULTIPLIER_MIN = 0.75
MULTIPLIER_MAX = 1.25

DEFAULT_STRATEGY_CONFIG = {
    "max_open_positions": 3,
    "min_adjusted_score": 55,
    "freeze_duration_candles": 2,
    "multiplier_bounds": {"min": MULTIPLIER_MIN, "max": MULTIPLIER_MAX},
    "active_strategies": ["spot_pullback_v1", "spot_range_reversion_v1", "spot_volatility_breakout_v1"],
}

REGIME_STRATEGY_MAP = {
    "TRENDING": "spot_pullback_v1",
    "RANGING": "spot_range_reversion_v1",
    "VOLATILE": "spot_volatility_breakout_v1",
}

STRATEGY_NAME_MAP = {
    "spot_pullback_v1": "SPOT_TREND_PULLBACK",
    "spot_range_reversion_v1": "SPOT_RANGE_REVERSION",
    "spot_volatility_breakout_v1": "SPOT_VOLATILITY_BREAKOUT",
}

REGIME_MULTIPLIERS = {
    "TRENDING": {
        "trend_quality_multiplier": 1.25,
        "pullback_quality_multiplier": 1.2,
        "relative_volume_multiplier": 1.0,
        "volatility_quality_multiplier": 0.9,
        "structure_quality_multiplier": 1.05,
    },
    "RANGING": {
        "trend_quality_multiplier": 0.9,
        "pullback_quality_multiplier": 1.05,
        "relative_volume_multiplier": 1.1,
        "volatility_quality_multiplier": 1.0,
        "structure_quality_multiplier": 1.0,
    },
    "VOLATILE": {
        "trend_quality_multiplier": 0.95,
        "pullback_quality_multiplier": 0.95,
        "relative_volume_multiplier": 1.2,
        "volatility_quality_multiplier": 1.2,
        "structure_quality_multiplier": 0.9,
    },
}


@dataclass
class BtcContext:
    market_regime: str
    btc_regime: str
    freeze_active: bool
    freeze_reason: str | None
    multiplier_set: dict
    multiplier_version: str
    multiplier_clamp_events: list[dict]
    regime_state: dict


def get_spot_strategy_config(cache, params: dict | None = None) -> dict:
    params = params or {}
    raw = get_json(cache, "spot_strategy:config") or {}
    cfg = {
        **DEFAULT_STRATEGY_CONFIG,
        **raw,
    }
    if isinstance(params, dict):
        if params.get("min_adjusted_score") is not None:
            cfg["min_adjusted_score"] = _safe_float(params.get("min_adjusted_score"), cfg["min_adjusted_score"])
        if params.get("max_open_positions") is not None:
            cfg["max_open_positions"] = int(params.get("max_open_positions"))
        if params.get("freeze_duration_candles") is not None:
            cfg["freeze_duration_candles"] = int(params.get("freeze_duration_candles"))
        if params.get("active_strategies") is not None:
            value = params.get("active_strategies")
            if isinstance(value, list):
                cfg["active_strategies"] = [str(item) for item in value]
    return cfg


def _derive_btc_signal_regime(btc_candles: list[dict]) -> str:
    if len(btc_candles) < 60:
        return "neutral"
    indicators = calculate_indicator_snapshot(btc_candles)
    btc_close = indicators["close"]
    btc_ema50 = indicators["ema50"]
    btc_rsi = indicators["rsi14"]
    recent = btc_candles[-4:]

    breakdown = False
    for candle in recent:
        open_price = _safe_float(candle.get("open"))
        close_price = _safe_float(candle.get("close"))
        move_pct = ((close_price - open_price) / open_price) * 100 if open_price else 0.0
        if move_pct <= -1.5:
            breakdown = True
            break

    if breakdown:
        return "hostile"
    if btc_close > btc_ema50 and btc_rsi >= 48:
        return "supportive"
    return "neutral"


def _classify_market_regime(btc_candles: list[dict]) -> str:
    if len(btc_candles) < 120:
        return "RANGING"
    indicators = calculate_indicator_snapshot(btc_candles)
    atr_pct = indicators.get("atr_pct", 0.0)
    ema50 = indicators.get("ema50", 0.0)
    ema200 = indicators.get("ema200", 0.0)
    rsi14 = indicators.get("rsi14", 50.0)

    if atr_pct >= 0.02:
        return "VOLATILE"
    if ema50 > ema200 and rsi14 >= 52:
        return "TRENDING"
    return "RANGING"


def _update_market_regime_state(cache, btc_candles: list[dict]) -> dict:
    raw_state = get_json(cache, "spot_strategy:market_regime_state") or {}
    raw_regime = _classify_market_regime(btc_candles)
    last_candle_end = str((btc_candles[-1] or {}).get("end")) if btc_candles else "-"
    active_regime = raw_state.get("active_regime", raw_regime)
    pending_regime = raw_state.get("pending_regime")
    pending_count = int(raw_state.get("pending_count", 0))
    last_processed_candle = raw_state.get("last_candle_end")
    changed = False

    if last_processed_candle != last_candle_end:
        if raw_regime == active_regime:
            pending_regime = None
            pending_count = 0
        else:
            if pending_regime == raw_regime:
                pending_count += 1
            else:
                pending_regime = raw_regime
                pending_count = 1

            if pending_count >= 2:
                active_regime = raw_regime
                pending_regime = None
                pending_count = 0
                changed = True

    payload = {
        "active_regime": active_regime,
        "raw_regime": raw_regime,
        "pending_regime": pending_regime,
        "pending_count": pending_count,
        "last_candle_end": last_candle_end,
        "changed": changed,
        "generated_at": utc_now_iso(),
    }
    set_json(cache, "spot_strategy:market_regime_state", payload)
    return payload


def _clamp_multiplier_set(multiplier_set: dict) -> tuple[dict, list[dict]]:
    clamped: dict = {}
    events: list[dict] = []
    for key, value in multiplier_set.items():
        raw = _safe_float(value, 1.0)
        bounded = min(max(raw, MULTIPLIER_MIN), MULTIPLIER_MAX)
        clamped[key] = bounded
        if bounded != raw:
            events.append({"key": key, "raw": raw, "clamped": bounded})
    return clamped, events


def _resolve_multiplier_payload(regime: str) -> dict:
    base = REGIME_MULTIPLIERS.get(regime, REGIME_MULTIPLIERS["RANGING"])
    clamped, clamp_events = _clamp_multiplier_set(base)
    return {
        "market_regime": regime,
        "multiplier_version": MULTIPLIER_VERSION,
        "multiplier_set": clamped,
        "multiplier_clamp_events": clamp_events,
        "generated_at": utc_now_iso(),
    }


def _update_btc_freeze_guard(cache, btc_candles: list[dict], freeze_duration_candles: int) -> dict:
    raw_state = get_json(cache, "spot_strategy:freeze_guard_state") or {}
    remaining = int(raw_state.get("remaining_candles", 0))
    active = bool(raw_state.get("active", False))
    reason = raw_state.get("reason")
    last_candle_end = str((btc_candles[-1] or {}).get("end")) if btc_candles else "-"
    last_processed_candle = raw_state.get("last_candle_end")

    if not btc_candles:
        return {
            "active": active,
            "remaining_candles": remaining,
            "reason": reason,
            "last_candle_end": last_processed_candle,
        }

    if last_processed_candle != last_candle_end:
        if len(btc_candles) >= 1:
            open_price = _safe_float(btc_candles[-1].get("open"))
            close_price = _safe_float(btc_candles[-1].get("close"))
            move_1 = ((close_price - open_price) / open_price) * 100 if open_price else 0.0
        else:
            move_1 = 0.0

        if len(btc_candles) >= 3:
            recent = btc_candles[-3:]
            first_open = _safe_float(recent[0].get("open"))
            last_close = _safe_float(recent[-1].get("close"))
            move_3 = ((last_close - first_open) / first_open) * 100 if first_open else 0.0
        else:
            move_3 = 0.0

        trigger = move_1 <= -1.5 or move_3 <= -2.2
        if trigger:
            remaining = max(freeze_duration_candles, 1)
            active = True
            reason = "btc_hostile_freeze_triggered"
        elif active and remaining > 0:
            remaining -= 1
            if remaining <= 0:
                active = False
                reason = None

    payload = {
        "active": active,
        "remaining_candles": max(remaining, 0),
        "reason": reason,
        "last_candle_end": last_candle_end,
        "generated_at": utc_now_iso(),
    }
    set_json(cache, "spot_strategy:freeze_guard_state", payload)
    return payload


def _derive_component_scores(candles: list[dict], indicators: dict, strategy_id: str) -> dict:
    trend_strength = _trend_strength(candles, indicators)
    pullback_quality = _pullback_quality(candles, indicators)
    relative_volume = indicators.get("relative_volume", 0.0)
    atr_pct = indicators.get("atr_pct", 0.0)
    close = indicators.get("close", 0.0)
    ema50 = indicators.get("ema50", 0.0)
    ema200 = indicators.get("ema200", 0.0)
    vwap = indicators.get("vwap", 0.0)
    compression_range_pct = 0.0
    breakout_strength = 0.0
    wick_cleanliness_ratio = 0.0

    if strategy_id == "spot_volatility_breakout_v1":
        lookback = candles[-21:-1] if len(candles) > 21 else candles[:-1]
        high_20 = max((_safe_float(item.get("high")) for item in lookback), default=close)
        low_20 = min((_safe_float(item.get("low")) for item in lookback), default=close)
        compression_range_pct = ((high_20 - low_20) / close) * 100 if close else 0.0
        breakout_strength = ((close - high_20) / close) * 100 if close else 0.0
        breakout_candle = candles[-2] if len(candles) >= 2 else candles[-1]
        b_open = _safe_float(breakout_candle.get("open"))
        b_close = _safe_float(breakout_candle.get("close"))
        b_high = _safe_float(breakout_candle.get("high"))
        body = abs(b_close - b_open)
        upper_wick = max(b_high - max(b_open, b_close), 0.0)
        wick_cleanliness_ratio = upper_wick / max(body, 0.0001)

        trend_alignment = {"weak": 35.0, "medium": 70.0, "strong": 90.0}.get(trend_strength, 35.0)
        structure_break = min(max((breakout_strength * 180) + 40, 20), 98)
        volume_expansion = min(max(relative_volume * 50, 15), 100)
        volatility_quality = 92.0 if compression_range_pct <= 2.5 else 62.0 if compression_range_pct <= 3.5 else 35.0
        wick_cleanliness = 90.0 if upper_wick < max(body, 0.0001) else 55.0

        trend_quality = trend_alignment
        pullback_score = structure_break
        relative_volume_score = volume_expansion
        structure_cleanliness = wick_cleanliness
    elif strategy_id == "spot_range_reversion_v1":
        ema_spread_pct = abs(((ema50 - ema200) / ema200) * 100) if ema200 else 0.0
        range_fit = 92.0 if ema_spread_pct <= 0.35 else 72.0 if ema_spread_pct <= 0.75 else 45.0
        trend_quality = range_fit

        price_to_vwap_pct = ((vwap - close) / close) * 100 if close else 0.0
        if price_to_vwap_pct >= 0.8:
            pullback_score = 90.0
        elif price_to_vwap_pct >= 0.25:
            pullback_score = 72.0
        else:
            pullback_score = 45.0

        if 0.9 <= relative_volume <= 1.8:
            relative_volume_score = 84.0
        elif 0.7 <= relative_volume <= 2.2:
            relative_volume_score = 66.0
        else:
            relative_volume_score = 42.0

        if 0.006 <= atr_pct <= 0.02:
            volatility_quality = 84.0
        elif 0.004 <= atr_pct <= 0.03:
            volatility_quality = 62.0
        else:
            volatility_quality = 35.0

        rsi_center_distance = abs(indicators.get("rsi14", 50.0) - 46)
        structure_cleanliness = max(25.0, 92.0 - (rsi_center_distance * 2.1))
    else:
        trend_quality = {"weak": 30.0, "medium": 70.0, "strong": 92.0}.get(trend_strength, 30.0)
        pullback_score = {"low": 25.0, "acceptable": 68.0, "strong": 90.0}.get(pullback_quality, 25.0)
        relative_volume_score = min(max(relative_volume * 45, 0), 100)

        if atr_pct < 0.008:
            volatility_quality = 20.0
        elif atr_pct <= 0.03:
            volatility_quality = min(95.0, 55 + (atr_pct * 1000))
        else:
            volatility_quality = 65.0

        if close <= 0:
            structure_cleanliness = 20.0
        else:
            ema_gap = abs((close - ema50) / close) if close else 0.0
            vwap_gap = abs((close - vwap) / close) if close else 0.0
            structure_cleanliness = max(20.0, 95.0 - (ema_gap * 800) - (vwap_gap * 600))

    return {
        "trend_strength": trend_strength,
        "pullback_quality": pullback_quality,
        "relative_volume": round(relative_volume, 4),
        "trend_quality": round(trend_quality, 4),
        "pullback_quality_score": round(pullback_score, 4),
        "relative_volume_score": round(relative_volume_score, 4),
        "volatility_quality": round(volatility_quality, 4),
        "structure_cleanliness": round(structure_cleanliness, 4),
        "atr_pct": round(atr_pct, 6),
        "rsi14": round(indicators.get("rsi14", 50.0), 4),
        "compression_range_pct": round(compression_range_pct, 6),
        "breakout_strength": round(breakout_strength, 6),
        "wick_cleanliness_ratio": round(wick_cleanliness_ratio, 6),
    }


def _base_and_adjusted_scores(component_scores: dict, multiplier_set: dict) -> tuple[float, float]:
    trend_quality = component_scores["trend_quality"]
    pullback_quality_score = component_scores["pullback_quality_score"]
    relative_volume_score = component_scores["relative_volume_score"]
    volatility_quality = component_scores["volatility_quality"]
    structure_cleanliness = component_scores["structure_cleanliness"]

    base_score = (
        trend_quality * 0.30
        + pullback_quality_score * 0.25
        + relative_volume_score * 0.20
        + volatility_quality * 0.15
        + structure_cleanliness * 0.10
    )

    adjusted_score = (
        trend_quality * 0.30 * multiplier_set["trend_quality_multiplier"]
        + pullback_quality_score * 0.25 * multiplier_set["pullback_quality_multiplier"]
        + relative_volume_score * 0.20 * multiplier_set["relative_volume_multiplier"]
        + volatility_quality * 0.15 * multiplier_set["volatility_quality_multiplier"]
        + structure_cleanliness * 0.10 * multiplier_set["structure_quality_multiplier"]
    )
    return round(base_score, 4), round(adjusted_score, 4)


def _prepare_btc_context(cache, btc_candles: list[dict], cfg: dict) -> BtcContext:
    regime_state = _update_market_regime_state(cache, btc_candles)
    freeze_state = _update_btc_freeze_guard(cache, btc_candles, int(cfg.get("freeze_duration_candles", 2)))
    multiplier_payload = _resolve_multiplier_payload(regime_state["active_regime"])
    set_json(cache, "spot_strategy:multiplier_contract", multiplier_payload)
    btc_regime = _derive_btc_signal_regime(btc_candles)
    return BtcContext(
        market_regime=regime_state["active_regime"],
        btc_regime=btc_regime,
        freeze_active=bool(freeze_state.get("active", False)),
        freeze_reason=freeze_state.get("reason"),
        multiplier_set=multiplier_payload["multiplier_set"],
        multiplier_version=multiplier_payload["multiplier_version"],
        multiplier_clamp_events=multiplier_payload.get("multiplier_clamp_events", []),
        regime_state=regime_state,
    )


def _evaluate_symbol_candidate(
    symbol: str,
    candles: list[dict],
    btc_context: BtcContext,
    open_symbols: set[str],
    threshold: float,
    strategy_id: str,
    strategy_active: bool,
) -> dict:
    indicators = calculate_indicator_snapshot(candles)
    close = indicators.get("close", 0.0)
    trend = "bullish" if indicators.get("ema50", 0.0) > indicators.get("ema200", 0.0) else "bearish"
    component_scores = _derive_component_scores(candles, indicators, strategy_id)
    strategy_name = STRATEGY_NAME_MAP.get(strategy_id, strategy_id.upper())

    hard_rejections: list[str] = []
    if component_scores["trend_strength"] == "weak":
        hard_rejections.append("trend_strength_weak")
    if btc_context.btc_regime == "hostile":
        hard_rejections.append("btc_regime_hostile")
    if btc_context.freeze_active:
        hard_rejections.append("freeze_guard_active")
    if symbol.upper() in open_symbols:
        hard_rejections.append("symbol_position_open")
    if not strategy_active:
        hard_rejections.append("strategy_not_activated")

    setup_rejections: list[str] = []
    if strategy_id == "spot_volatility_breakout_v1":
        lookback = candles[-21:-1] if len(candles) > 21 else candles[:-1]
        high_20 = max((_safe_float(item.get("high")) for item in lookback), default=close)
        low_20 = min((_safe_float(item.get("low")) for item in lookback), default=close)
        range_midpoint = (high_20 + low_20) / 2

        breakout_candle = candles[-2] if len(candles) >= 2 else candles[-1]
        confirmation_candle = candles[-1]
        breakout_close = _safe_float(breakout_candle.get("close"))
        breakout_open = _safe_float(breakout_candle.get("open"))
        breakout_high = _safe_float(breakout_candle.get("high"))
        breakout_body_pct = ((breakout_close - breakout_open) / breakout_open) * 100 if breakout_open else 0.0

        compression_ok = component_scores["compression_range_pct"] < 2.5
        breakout_ok = breakout_close > high_20
        volume_ok = component_scores["relative_volume"] >= 1.5
        confirmation_ok = _safe_float(confirmation_candle.get("close")) > breakout_close or breakout_body_pct >= 0.6
        wick_ok = (breakout_high - breakout_close) < max((breakout_close - breakout_open), 0.0001)
        midpoint_ok = breakout_close > range_midpoint

        if not compression_ok:
            setup_rejections.append("compression_missing")
        if not breakout_ok:
            setup_rejections.append("breakout_not_confirmed")
        if not volume_ok:
            setup_rejections.append("relative_volume_too_low")
        if not confirmation_ok:
            setup_rejections.append("confirmation_missing")
        if not wick_ok:
            setup_rejections.append("wick_rejection_high")
        if not midpoint_ok:
            setup_rejections.append("range_midpoint_not_reclaimed")
    elif strategy_id == "spot_range_reversion_v1":
        vwap = indicators.get("vwap", 0.0)
        if trend == "bullish" and component_scores["trend_strength"] == "strong":
            setup_rejections.append("market_not_ranging_enough")
        if close > (vwap * 1.003 if vwap else close):
            setup_rejections.append("price_not_below_mean")
        if component_scores["rsi14"] > 52:
            setup_rejections.append("rsi_not_reversion_ready")
        if component_scores["relative_volume"] < 0.8:
            setup_rejections.append("relative_volume_too_low")
        if not (0.006 <= component_scores["atr_pct"] <= 0.03):
            setup_rejections.append("volatility_out_of_range")
    else:
        if trend != "bullish":
            setup_rejections.append("trend_not_bullish")
        if close > indicators.get("ema50", 0.0):
            setup_rejections.append("price_above_ema50")
        if component_scores["rsi14"] >= 45:
            setup_rejections.append("rsi_not_ready")
        if component_scores["atr_pct"] <= 0.008:
            setup_rejections.append("volatility_too_low")

    base_score = 0.0
    adjusted_score = 0.0
    score_delta = 0.0
    threshold_pass = False

    if not hard_rejections:
        base_score, adjusted_score = _base_and_adjusted_scores(component_scores, btc_context.multiplier_set)
        score_delta = round(adjusted_score - base_score, 4)
        threshold_pass = adjusted_score >= threshold

    status = "candidate"
    reason_codes: list[str] = []
    if hard_rejections:
        status = "rejected_hard_gate"
        reason_codes = hard_rejections
    elif setup_rejections:
        status = "rejected_signal_setup"
        reason_codes = setup_rejections
    elif not threshold_pass:
        status = "rejected_below_threshold"
        reason_codes = ["adjusted_score_below_threshold"]

    entry = round(close, 6)
    stop = round(close * 0.99, 6)
    take_profit = round(close * 1.02, 6)

    return {
        "symbol": symbol.upper(),
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "status": status,
        "reason_codes": reason_codes,
        "signal": "long" if status == "candidate" else "none",
        "direction": "long" if status == "candidate" else "none",
        "entry": entry,
        "stop": stop,
        "take_profit": take_profit,
        "base_score": round(base_score, 4),
        "adjusted_score": round(adjusted_score, 4),
        "score_delta": round(score_delta, 4),
        "hard_gate_pass": len(hard_rejections) == 0,
        "threshold_pass": threshold_pass,
        "market_regime": btc_context.market_regime,
        "btc_regime": btc_context.btc_regime,
        "multiplier_version": btc_context.multiplier_version,
        "multiplier_set": btc_context.multiplier_set,
        "trend_strength": component_scores["trend_strength"],
        "pullback_quality": component_scores["pullback_quality"],
        "relative_volume": component_scores["relative_volume"],
        "component_scores": {
            "trend_quality": component_scores["trend_quality"],
            "pullback_quality": component_scores["pullback_quality_score"],
            "relative_volume": component_scores["relative_volume_score"],
            "volatility_quality": component_scores["volatility_quality"],
            "structure_cleanliness": component_scores["structure_cleanliness"],
        },
        "metadata": {
            "trend": trend,
            "rsi14": component_scores["rsi14"],
            "atr_pct": component_scores["atr_pct"],
            "ema50": round(indicators.get("ema50", 0.0), 6),
            "ema200": round(indicators.get("ema200", 0.0), 6),
            "vwap": round(indicators.get("vwap", 0.0), 6),
            "freeze_guard_active": btc_context.freeze_active,
            "strategy_name": strategy_name,
            "breakout_level": round(
                max((_safe_float(item.get("high")) for item in (candles[-21:-1] if len(candles) > 21 else candles[:-1])), default=close),
                6,
            )
            if strategy_id == "spot_volatility_breakout_v1"
            else None,
            "compression_range": component_scores.get("compression_range_pct", 0),
            "breakout_strength": component_scores.get("breakout_strength", 0),
            "confirmation_candle": (
                {
                    "open": _safe_float(candles[-1].get("open")),
                    "close": _safe_float(candles[-1].get("close")),
                    "high": _safe_float(candles[-1].get("high")),
                    "low": _safe_float(candles[-1].get("low")),
                }
                if strategy_id == "spot_volatility_breakout_v1" and candles
                else None
            ),
        },
    }


def _build_selection_metrics(candidates: list[dict], selected: list[dict]) -> dict:
    selected_by_strategy: dict[str, int] = {}
    total_by_strategy: dict[str, int] = {}
    for item in candidates:
        strategy_id = str(item.get("strategy_id", "unknown"))
        total_by_strategy[strategy_id] = total_by_strategy.get(strategy_id, 0) + 1
    for item in selected:
        strategy_id = str(item.get("strategy_id", "unknown"))
        selected_by_strategy[strategy_id] = selected_by_strategy.get(strategy_id, 0) + 1

    return {
        "signals_total": len(candidates),
        "signals_after_hard_gate": sum(1 for item in candidates if item.get("hard_gate_pass")),
        "signals_above_threshold": sum(1 for item in candidates if item.get("threshold_pass")),
        "signals_selected": len(selected),
        "signals_rejected_trend_strength": sum(
            1 for item in candidates if "trend_strength_weak" in item.get("reason_codes", [])
        ),
        "signals_rejected_btc_regime": sum(
            1 for item in candidates if "btc_regime_hostile" in item.get("reason_codes", [])
        ),
        "signals_rejected_freeze_guard": sum(
            1 for item in candidates if "freeze_guard_active" in item.get("reason_codes", [])
        ),
        "signals_rejected_threshold": sum(
            1 for item in candidates if "adjusted_score_below_threshold" in item.get("reason_codes", [])
        ),
        "signals_rejected_strategy_inactive": sum(
            1 for item in candidates if "strategy_not_activated" in item.get("reason_codes", [])
        ),
        "signals_per_strategy": total_by_strategy,
        "selected_signals_per_strategy": selected_by_strategy,
    }


def run_dynamic_selection_cycle(
    cache,
    symbols: list[str],
    open_symbols: set[str],
    available_slots: int,
    params: dict | None = None,
) -> dict:
    cfg = get_spot_strategy_config(cache, params)
    threshold = _safe_float(cfg.get("min_adjusted_score"), 55.0)
    normalized_symbols = sorted({symbol.upper() for symbol in symbols if symbol})
    btc_candles = get_json(cache, "market_data_store:BTCUSDT:15m") or get_json(cache, "market:candles:BTCUSDT:15m") or []
    btc_context = _prepare_btc_context(cache, btc_candles, cfg)
    active_strategy_id = REGIME_STRATEGY_MAP.get(btc_context.market_regime, "spot_pullback_v1")
    strategy_active_set = {str(item) for item in cfg.get("active_strategies", [])}
    strategy_active = active_strategy_id in strategy_active_set
    active_strategy_name = STRATEGY_NAME_MAP.get(active_strategy_id, active_strategy_id.upper())

    candidates: list[dict] = []
    for symbol in normalized_symbols:
        candles = get_json(cache, f"market_data_store:{symbol}:15m") or get_json(cache, f"market:candles:{symbol}:15m") or []
        if len(candles) < 220:
            candidates.append(
                {
                    "symbol": symbol,
                    "strategy_id": active_strategy_id,
                    "strategy_name": active_strategy_name,
                    "status": "rejected_signal_setup",
                    "reason_codes": ["insufficient_data"],
                    "signal": "none",
                    "direction": "none",
                    "entry": 0,
                    "stop": 0,
                    "take_profit": 0,
                    "base_score": 0,
                    "adjusted_score": 0,
                    "score_delta": 0,
                    "hard_gate_pass": False,
                    "threshold_pass": False,
                    "market_regime": btc_context.market_regime,
                    "btc_regime": btc_context.btc_regime,
                    "multiplier_version": btc_context.multiplier_version,
                    "multiplier_set": btc_context.multiplier_set,
                    "trend_strength": "weak",
                    "pullback_quality": "low",
                    "relative_volume": 0,
                    "component_scores": {},
                    "metadata": {"freeze_guard_active": btc_context.freeze_active},
                }
            )
            continue

        candidates.append(
            _evaluate_symbol_candidate(
                symbol,
                candles[-500:],
                btc_context,
                open_symbols,
                threshold,
                strategy_id=active_strategy_id,
                strategy_active=strategy_active,
            )
        )

    executable = [
        item
        for item in candidates
        if item.get("status") == "candidate" and item.get("signal") == "long" and item.get("threshold_pass")
    ]
    executable.sort(key=lambda item: (-item.get("adjusted_score", 0.0), item.get("symbol", "")))
    selected = executable[: max(available_slots, 0)]
    for index, item in enumerate(selected, start=1):
        item["selection_rank"] = index

    metrics = _build_selection_metrics(candidates, selected)
    if selected:
        avg_adjusted = sum(item.get("adjusted_score", 0.0) for item in selected) / len(selected)
    else:
        avg_adjusted = 0.0

    payload = {
        "generated_at": utc_now_iso(),
        "market_regime": btc_context.market_regime,
        "active_strategy_id": active_strategy_id,
        "active_strategy_name": active_strategy_name,
        "active_strategy_enabled": strategy_active,
        "regime_strategy_map": REGIME_STRATEGY_MAP,
        "btc_regime": btc_context.btc_regime,
        "regime_state": btc_context.regime_state,
        "multiplier_version": btc_context.multiplier_version,
        "multiplier_set": btc_context.multiplier_set,
        "multiplier_clamp_events": btc_context.multiplier_clamp_events,
        "freeze_guard": {
            "active": btc_context.freeze_active,
            "reason": btc_context.freeze_reason,
        },
        "threshold": threshold,
        "available_slots": max(available_slots, 0),
        "symbol_count": len(candidates),
        "metrics": {
            **metrics,
            "avg_adjusted_score_selected": round(avg_adjusted, 4),
        },
        "selected": selected,
        "ranked": sorted(candidates, key=lambda item: (-item.get("adjusted_score", 0.0), item.get("symbol", ""))),
    }
    set_json(cache, "spot_strategy:last_scan", payload)
    return payload


def serialize_for_audit(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
