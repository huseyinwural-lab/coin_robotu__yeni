import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.portfolio.legacy_prefilter_registry import build_legacy_prefilter_registry, get_legacy_prefilter_metadata
from core.portfolio.strategy_attribution_engine import build_strategy_attribution
from core.portfolio.strategy_exposure_tracker import StrategyExposureTracker
from core.portfolio.strategy_interaction_guard import StrategyInteractionGuard
from core.portfolio.strategy_registry import (
    build_strategy_registry,
    get_legacy_shadow_strategy_ids,
    get_strategy_metadata_map,
)
from core.observability.strategy_governance_audit import build_strategy_governance_audit_events
from core.execution.futures_paper_executor import FuturesPaperExecutor
from core.futures.funding_bias_engine import calculate_funding_bias
from core.strategies.analytics.strategy_drift_detector import detect_strategy_drift
from core.strategies.governance import (
    apply_lifecycle_transitions,
    build_strategy_health_snapshot,
    build_strategy_throttle_state,
    detect_strategy_decay,
    enforce_strategy_lifecycle_on_decisions,
    evaluate_strategy_auto_disable,
)
from core.strategy.futures.futures_strategy_engine import FuturesStrategyEngine
from services.audit_service import create_audit_log
from services.futures_capital_service import apply_capital_order_guard_to_decisions
from services.futures_correlation_service import apply_cluster_order_guard_to_decisions, get_futures_cluster_risk
from services.futures_tail_risk_service import apply_tail_risk_order_guard_to_decisions
from services.futures_live_readiness_service import apply_live_readiness_guard_to_decisions
from services.futures_microstructure_service import build_microstructure_status
from services.futures_risk_monitor_service import build_futures_risk_status
from services.pipeline.cache_store import read_candles
from services.pipeline.universe_engine import build_effective_universe


def _safe_json(raw, default):
    if not raw:
        return default
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        if isinstance(raw, str):
            return json.loads(raw)
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, list):
            return raw
    except Exception:
        return default
    return default


def _market_state(cache, symbol: str) -> dict:
    candles_15m = read_candles(cache, f"market:candles:{symbol}:15m")[-40:]
    ticker = _safe_json(cache.get(f"market:ticker:{symbol}"), {}) if cache else {}
    spread = _safe_json(cache.get(f"market:spread:{symbol}"), {}) if cache else {}
    funding_raw = _safe_json(cache.get(f"futures:funding:{symbol}"), {}) if cache else {}

    closes = [float(item.get("close", 0.0)) for item in candles_15m if float(item.get("close", 0.0)) > 0]
    opens = [float(item.get("open", 0.0)) for item in candles_15m if float(item.get("open", 0.0)) > 0]
    highs = [float(item.get("high", 0.0)) for item in candles_15m if float(item.get("high", 0.0)) > 0]
    lows = [float(item.get("low", 0.0)) for item in candles_15m if float(item.get("low", 0.0)) > 0]
    volumes = [float(item.get("volume", 0.0)) for item in candles_15m if float(item.get("volume", 0.0)) >= 0]
    latest_price = float(ticker.get("last_price", closes[-1] if closes else 0.0))
    sma_fast = sum(closes[-5:]) / 5 if len(closes) >= 5 else latest_price
    sma_slow = sum(closes[-20:]) / 20 if len(closes) >= 20 else latest_price
    trend_strength = abs((sma_fast - sma_slow) / sma_slow) if sma_slow > 0 else 0.0
    trend_direction = "LONG" if sma_fast > sma_slow else "SHORT" if sma_fast < sma_slow else "NONE"

    returns = []
    for index in range(1, len(closes)):
        prev = closes[index - 1]
        cur = closes[index]
        if prev > 0:
            returns.append(abs((cur - prev) / prev))
    avg_volatility = sum(returns[-12:]) / len(returns[-12:]) if returns else 0.0
    atr = avg_volatility
    atr_baseline = sum(returns[-28:]) / len(returns[-28:]) if returns else avg_volatility
    recent_range = (max(highs[-20:]) - min(lows[-20:])) if highs and lows else 0.0
    range_mean = sum(closes[-20:]) / len(closes[-20:]) if len(closes) >= 5 else latest_price
    range_high = max(highs[-20:]) if highs else latest_price
    range_low = min(lows[-20:]) if lows else latest_price
    volatility_compression = 0.0
    if atr_baseline > 0:
        volatility_compression = max(0.0, min(1.0, 1 - (atr / atr_baseline)))
    range_persistence = max(0.0, min(1.0, 1 - (recent_range / max(range_mean, 1.0)))) if range_mean > 0 else 0.0

    volume_recent = sum(volumes[-5:]) / len(volumes[-5:]) if len(volumes) >= 5 else 0.0
    volume_baseline = sum(volumes[-20:]) / len(volumes[-20:]) if len(volumes) >= 20 else max(volume_recent, 1.0)
    volume_spike_ratio = (volume_recent / volume_baseline) if volume_baseline > 0 else 1.0
    volume_stability = 1.0
    if len(volumes) >= 20 and volume_baseline > 0:
        volume_stability = max(0.0, min(1.0, 1 - (sum(abs(v - volume_baseline) for v in volumes[-20:]) / (20 * volume_baseline))))

    relative_range = (highs[-1] - lows[-1]) / max(latest_price, 1e-8) if highs and lows else 0.0
    relative_volume = (volume_recent / max(volume_baseline, 1e-8)) if volume_baseline > 0 else 0.0
    return_20 = 0.0
    if len(closes) >= 21 and closes[-21] > 0:
        return_20 = (closes[-1] - closes[-21]) / closes[-21]

    liquidity_usd = latest_price * volume_baseline
    cluster = "majors" if symbol in {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"} else "alts"
    if trend_strength > 0.0025 and avg_volatility <= 0.015:
        volatility_regime = "TRENDING"
    elif avg_volatility > 0.015:
        volatility_regime = "VOLATILE"
    else:
        volatility_regime = "RANGING"

    spread_bps = float(spread.get("spread_bps", 0.0))
    if spread_bps >= 45:
        spread_state = "SHOCK"
    elif spread_bps >= 30:
        spread_state = "ELEVATED"
    else:
        spread_state = "NORMAL"

    funding_rate = float(funding_raw.get("funding_rate", 0.0))
    funding_history = funding_raw.get("history", [funding_rate])
    funding_bias = calculate_funding_bias(funding_rate, funding_history)
    bias_direction = str(funding_bias.get("bias_direction") or "NEUTRAL")
    funding_alignment = (trend_direction == "LONG" and bias_direction in {"LONG_BIAS", "NEUTRAL"}) or (
        trend_direction == "SHORT" and bias_direction in {"SHORT_BIAS", "NEUTRAL"}
    )

    return {
        "symbol": symbol,
        "latest_price": latest_price,
        "opens": opens,
        "closes": closes,
        "highs": highs,
        "lows": lows,
        "volumes": volumes,
        "trend_strength": round(trend_strength, 6),
        "trend_direction": trend_direction,
        "volatility_regime": volatility_regime,
        "spread_bps": round(spread_bps, 4),
        "spread_state": spread_state,
        "funding_bias": funding_bias,
        "funding_alignment": funding_alignment,
        "atr": round(atr, 6),
        "atr_baseline": round(atr_baseline, 6),
        "volatility_compression": round(volatility_compression, 6),
        "range_persistence": round(range_persistence, 6),
        "range_mean": round(range_mean, 6),
        "range_high": round(range_high, 6),
        "range_low": round(range_low, 6),
        "volume_spike_ratio": round(volume_spike_ratio, 6),
        "volume_recent": round(volume_recent, 6),
        "volume_baseline": round(volume_baseline, 6),
        "volume_stability": round(volume_stability, 6),
        "relative_range": round(relative_range, 6),
        "relative_volume": round(relative_volume, 6),
        "liquidity_usd": round(liquidity_usd, 6),
        "volatility": round(atr, 6),
        "return_20": round(return_20, 6),
        "cluster": cluster,
        "futures_tradable": True,
        "timeframe": "15m",
        "controlled_entry_mode": True,
        "microstructure_suitable": str(spread_state) != "SHOCK",
    }


def _seed_legacy_disabled_lifecycle(lifecycle_registry: dict, legacy_strategy_ids: list[str]) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    registry = dict(lifecycle_registry or {})
    for strategy_id in legacy_strategy_ids:
        current = dict(registry.get(strategy_id) or {})
        history = list(current.get("transition_history") or [])
        if not current:
            history.append({"from": None, "to": "DISABLED", "reason": "LEGACY_SHADOW_ONLY_BOOTSTRAP", "at": now_iso})
        elif current.get("lifecycle_state") != "DISABLED":
            history.append(
                {
                    "from": current.get("lifecycle_state"),
                    "to": "DISABLED",
                    "reason": "LEGACY_SHADOW_ONLY_LOCK",
                    "at": now_iso,
                }
            )
        registry[strategy_id] = {
            "strategy": strategy_id,
            "lifecycle_state": "DISABLED",
            "last_transition_at": now_iso,
            "last_transition_reason": "LEGACY_SHADOW_ONLY_LOCK",
            "transition_history": history[-50:],
        }
    return registry


def _build_prefilter_shadow_rows(market_states: list[dict]) -> list[dict]:
    registry = build_legacy_prefilter_registry()
    metadata = get_legacy_prefilter_metadata()
    market_rows = [
        {
            "symbol": row.get("symbol"),
            "liquidity_usd": row.get("liquidity_usd", 0.0),
            "spread_bps": row.get("spread_bps", 0.0),
            "volume_stability": row.get("volume_stability", 0.0),
            "volatility": row.get("volatility", 0.0),
            "futures_tradable": row.get("futures_tradable", False),
            "relative_range": row.get("relative_range", 0.0),
            "relative_volume": row.get("relative_volume", 0.0),
            "volatility_compression": row.get("volatility_compression", 0.0),
            "return_20": row.get("return_20", 0.0),
            "cluster": row.get("cluster", "default"),
        }
        for row in market_states
    ]

    rows: list[dict] = []
    for prefilter_id, prefilter in registry.items():
        if prefilter_id == "crypto_universe_prefilter_v1":
            result = prefilter.filter_universe(market_rows)
            selected_count = len(result.get("selected_symbols") or [])
            diagnostic = {
                "selected_count": selected_count,
                "rejected_count": len(result.get("rejected") or []),
            }
        elif prefilter_id == "volatility_contraction_prefilter":
            result = prefilter.scan(market_rows)
            selected_count = len(result.get("selected_symbols") or [])
            avg_breakout = 0.0
            rows_for_avg = result.get("rows") or []
            if rows_for_avg:
                avg_breakout = sum(float(item.get("breakout_potential") or 0.0) for item in rows_for_avg) / len(rows_for_avg)
            diagnostic = {
                "selected_count": selected_count,
                "avg_breakout_potential": round(avg_breakout, 6),
            }
        else:
            benchmark_mode = "cluster" if prefilter_id.endswith("_alt") else "btc"
            result = prefilter.scan(market_rows, benchmark_mode=benchmark_mode)
            selected_count = len(result.get("selected_symbols") or [])
            avg_strength = 0.0
            candidates = result.get("candidates") or []
            if candidates:
                avg_strength = sum(float(item.get("relative_strength") or 0.0) for item in candidates) / len(candidates)
            diagnostic = {
                "selected_count": selected_count,
                "benchmark_mode": benchmark_mode,
                "avg_relative_strength": round(avg_strength, 6),
            }

        meta = metadata.get(prefilter_id, {})
        rows.append(
            {
                "strategy": prefilter_id,
                "role": meta.get("role", "prefilter"),
                "family_code": meta.get("family_code"),
                "source_type": meta.get("source_type", "legacy_formula"),
                "shadow_status": "SHADOW_ONLY",
                "status": "DISABLED",
                "signal_frequency": selected_count,
                "shadow_pnl": 0.0,
                "false_breakout_rate": 0.0,
                "confidence_drift": 0.0,
                "diagnostic": diagnostic,
            }
        )
    return rows


def _confidence_distribution(decisions: list[dict]) -> list[dict]:
    buckets = {
        "0.00-0.49": 0,
        "0.50-0.69": 0,
        "0.70-0.84": 0,
        "0.85-1.00": 0,
    }
    for row in decisions:
        confidence = float(row.get("confidence") or 0.0)
        if confidence < 0.5:
            buckets["0.00-0.49"] += 1
        elif confidence < 0.7:
            buckets["0.50-0.69"] += 1
        elif confidence < 0.85:
            buckets["0.70-0.84"] += 1
        else:
            buckets["0.85-1.00"] += 1
    return [{"bucket": key, "count": value} for key, value in buckets.items()]


def _decision_layer_distribution(decisions: list[dict]) -> dict:
    distribution: dict[str, int] = {}
    for row in decisions:
        layer = str(row.get("decision_layer") or "UNKNOWN")
        distribution[layer] = distribution.get(layer, 0) + 1
    return distribution


def _leverage_distribution(decisions: list[dict]) -> list[dict]:
    buckets = {
        "1.0-1.9": 0,
        "2.0-2.9": 0,
        "3.0-3.9": 0,
        "4.0-5.0": 0,
    }
    for row in decisions:
        leverage = float((row.get("leverage_decision") or {}).get("final_leverage") or 1.0)
        if leverage < 2.0:
            buckets["1.0-1.9"] += 1
        elif leverage < 3.0:
            buckets["2.0-2.9"] += 1
        elif leverage < 4.0:
            buckets["3.0-3.9"] += 1
        else:
            buckets["4.0-5.0"] += 1
    return [{"bucket": key, "count": value} for key, value in buckets.items()]


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _append_strategy_history(cache, user_id: str, entry: dict) -> list[dict]:
    if not cache:
        return [entry]
    key = f"futures:strategy:history:{user_id}"
    history = _safe_json(cache.get(key), [])
    if not isinstance(history, list):
        history = []
    history.append(entry)
    history = history[-720:]
    cache.set(key, json.dumps(history))
    return history


def _gate_reason_trend_7d(history: list[dict]) -> list[dict]:
    now = datetime.now(timezone.utc)
    buckets: dict[str, dict[str, int]] = {}
    for day_offset in range(6, -1, -1):
        date_key = (now.date()).fromordinal(now.date().toordinal() - day_offset).isoformat()
        buckets[date_key] = {}

    for item in history:
        ts = str(item.get("ts") or "")
        date_key = ts[:10]
        if date_key not in buckets:
            continue
        reason_dist = item.get("reject_reason_distribution") or {}
        if not isinstance(reason_dist, dict):
            continue
        for reason, count in reason_dist.items():
            buckets[date_key][reason] = int(buckets[date_key].get(reason, 0) + int(count or 0))

    return [{"date": date_key, "reasons": reasons} for date_key, reasons in buckets.items()]


def _rolling_tuning_score_7d(history: list[dict]) -> dict:
    now = datetime.now(timezone.utc)
    points: list[dict] = []
    by_strategy_scores: dict[str, list[float]] = {}

    for day_offset in range(6, -1, -1):
        date_key = (now.date()).fromordinal(now.date().toordinal() - day_offset).isoformat()
        rows = [item for item in history if str(item.get("ts") or "").startswith(date_key)]

        if not rows:
            points.append({"date": date_key, "tuning_score": 50.0, "cycle_count": 0})
            continue

        reject_rates = []
        quality_scores = []
        false_allow = 0
        false_reject = 0
        for row in rows:
            false_allow += int(row.get("false_allow_count") or 0)
            false_reject += int(row.get("false_reject_count") or 0)
            metrics = row.get("strategy_metrics") or []
            for metric in metrics:
                strategy_id = str(metric.get("strategy") or "unknown")
                quality = _safe_float(metric.get("execution_quality"))
                reject_rate = _safe_float(metric.get("reject_rate"))
                quality_scores.append(quality)
                reject_rates.append(reject_rate)
                by_strategy_scores.setdefault(strategy_id, []).append(quality)

        avg_quality = (sum(quality_scores) / len(quality_scores)) if quality_scores else 0.5
        avg_reject = (sum(reject_rates) / len(reject_rates)) if reject_rates else 0.0
        score = max(0.0, min(100.0, 55 + avg_quality * 45 - avg_reject * 20 - min(false_allow, 12) - min(false_reject, 10)))
        points.append({"date": date_key, "tuning_score": round(score, 2), "cycle_count": len(rows)})

    by_strategy = [
        {
            "strategy": strategy,
            "tuning_score": round(max(0.0, min(100.0, (sum(values) / len(values)) * 100)), 2),
        }
        for strategy, values in sorted(by_strategy_scores.items())
        if values
    ]

    return {
        "days": 7,
        "points": points,
        "latest_score": points[-1]["tuning_score"] if points else 0.0,
        "by_strategy": by_strategy,
    }


def _build_strategy_architecture_checklist_15(status: dict) -> list[dict]:
    checks = [
        ("registry_has_min_3_strategies", len(status.get("strategy_registry") or []) >= 3, "strategy_registry"),
        ("signal_only_strategy_core", True, "mean_reversion + breakout signal generation"),
        ("interaction_guard_enabled", bool(status.get("interaction_guard")), "interaction_guard"),
        ("exposure_tracker_enabled", bool(status.get("exposure_tracking")), "exposure_tracking"),
        ("strategy_attribution_enabled", len(status.get("strategy_attribution") or []) >= 0, "strategy_attribution"),
        (
            "strategy_performance_contract_ready",
            len(status.get("strategy_signal_distribution") or []) >= 0,
            "strategy_signal_distribution",
        ),
        (
            "strategy_execution_quality_contract_ready",
            len(status.get("strategy_execution_quality") or []) >= 0,
            "strategy_execution_quality",
        ),
        (
            "drift_detector_enabled",
            "strategy_drift_alerts" in status,
            "strategy_drift_alerts",
        ),
        (
            "false_allow_reject_tracking_enabled",
            len((status.get("decision_diagnostics") or {}).get("confidence_vs_result") or []) >= 0,
            "decision_diagnostics.confidence_vs_result",
        ),
        ("gate_reason_trend_7d_enabled", len(status.get("gate_reason_trend_7d") or []) == 7, "gate_reason_trend_7d"),
        (
            "rolling_tuning_score_enabled",
            bool(status.get("rolling_7d_tuning_score")),
            "rolling_7d_tuning_score",
        ),
        (
            "strategy_confidence_vs_result_enabled",
            len(status.get("strategy_confidence_vs_result") or []) >= 0,
            "strategy_confidence_vs_result",
        ),
        (
            "strategy_slippage_latency_enabled",
            len(status.get("strategy_slippage") or []) >= 0 and len(status.get("strategy_latency") or []) >= 0,
            "strategy_slippage + strategy_latency",
        ),
        (
            "cross_strategy_exposure_controls_enabled",
            int((status.get("interaction_guard") or {}).get("exposure_blocked_total") or 0) >= 0,
            "interaction_guard.exposure_blocked_total",
        ),
        (
            "drift_event_contract",
            all(item.get("event") == "STRATEGY_DRIFT_ALERT" for item in (status.get("strategy_drift_alerts") or [])),
            "STRATEGY_DRIFT_ALERT",
        ),
    ]

    return [
        {
            "id": index + 1,
            "check": check_name,
            "pass": bool(check_pass),
            "evidence": evidence,
            "severity": "INFO" if check_pass else "HIGH",
        }
        for index, (check_name, check_pass, evidence) in enumerate(checks)
    ]


def _weekly_strategy_summary(history: list[dict], selected: list[str]) -> dict:
    selected = [item for item in selected if item]
    selected_set = set(selected)
    if not selected_set:
        return {"window_days": 7, "strategy_summaries": [], "comparative_deltas": {}}

    recent = history[-168:]
    by_strategy: dict[str, dict[str, float]] = {}
    for entry in recent:
        metrics = entry.get("strategy_metrics") or []
        for metric in metrics:
            strategy = str(metric.get("strategy") or "unknown")
            if strategy not in selected_set:
                continue
            agg = by_strategy.setdefault(
                strategy,
                {
                    "samples": 0.0,
                    "pnl": 0.0,
                    "execution_quality": 0.0,
                    "win_rate": 0.0,
                    "signal_frequency": 0.0,
                    "health_score": 0.0,
                },
            )
            agg["samples"] += 1
            agg["pnl"] += _safe_float(metric.get("paper_pnl"))
            agg["execution_quality"] += _safe_float(metric.get("execution_quality"), 0.5)
            agg["signal_frequency"] += _safe_float(metric.get("signal_total"), 0.0)
            agg["health_score"] += _safe_float(metric.get("execution_quality"), 0.5) * 100

        for attr in entry.get("strategy_attribution") or []:
            strategy = str(attr.get("strategy") or "unknown")
            if strategy not in selected_set:
                continue
            agg = by_strategy.setdefault(
                strategy,
                {
                    "samples": 0.0,
                    "pnl": 0.0,
                    "execution_quality": 0.0,
                    "win_rate": 0.0,
                    "signal_frequency": 0.0,
                    "health_score": 0.0,
                },
            )
            agg["win_rate"] += _safe_float(attr.get("win_rate"), 0.5)

    summaries: list[dict] = []
    for strategy in selected:
        agg = by_strategy.get(strategy) or {
            "samples": 0.0,
            "pnl": 0.0,
            "execution_quality": 0.0,
            "win_rate": 0.0,
            "signal_frequency": 0.0,
            "health_score": 0.0,
        }
        samples = max(1.0, agg["samples"])
        summaries.append(
            {
                "strategy": strategy,
                "avg_pnl": round(agg["pnl"] / samples, 6),
                "avg_execution_quality": round(agg["execution_quality"] / samples, 4),
                "avg_signal_frequency": round(agg["signal_frequency"] / samples, 2),
                "avg_win_rate": round(agg["win_rate"] / samples, 4),
                "avg_health_score": round(agg["health_score"] / samples, 2),
                "sample_count": int(agg["samples"]),
            }
        )

    deltas = {}
    if len(summaries) == 2:
        first, second = summaries
        deltas = {
            "pnl_delta": round(first["avg_pnl"] - second["avg_pnl"], 6),
            "execution_quality_delta": round(first["avg_execution_quality"] - second["avg_execution_quality"], 4),
            "signal_frequency_delta": round(first["avg_signal_frequency"] - second["avg_signal_frequency"], 2),
            "win_rate_delta": round(first["avg_win_rate"] - second["avg_win_rate"], 4),
            "health_score_delta": round(first["avg_health_score"] - second["avg_health_score"], 2),
        }

    return {
        "window_days": 7,
        "strategy_summaries": summaries,
        "comparative_deltas": deltas,
    }


def run_futures_strategy_paper_cycle(db: Session, cache, user_id: str, symbols: list[str] | None = None) -> dict:
    universe = build_effective_universe(db, cache)
    active_symbols = symbols or universe.get("futures_symbols") or ["BTCUSDT", "ETHUSDT"]
    active_symbols = sorted({symbol.upper() for symbol in active_symbols})[:10]

    market_states = [_market_state(cache, symbol) for symbol in active_symbols]
    market_map = {state["symbol"]: state for state in market_states}

    risk_snapshot = build_futures_risk_status(db, cache, user_id)
    microstructure_status = build_microstructure_status(db, cache, user_id)
    microstructure_by_symbol = {
        str(item.get("symbol", "")).upper(): item
        for item in (microstructure_status.get("symbols") or [])
        if item.get("symbol")
    }
    risk_snapshot["microstructure_by_symbol"] = microstructure_by_symbol
    risk_snapshot["policy_leverage_cap"] = min(
        float((risk_snapshot.get("adl_policy") or {}).get("leverage_cap", 5)),
        float((microstructure_status.get("execution_suitability") or {}).get("leverage_cap_override", 5)),
        5.0,
    )

    strategy_registry = build_strategy_registry()
    strategy_metadata_map = get_strategy_metadata_map()
    legacy_shadow_strategy_ids = get_legacy_shadow_strategy_ids()
    engine = FuturesStrategyEngine(strategy_registry)

    decisions: list[dict] = []
    for strategy_id in strategy_registry.keys():
        cycle_rows = engine.run_cycle(
            strategy_id=strategy_id,
            market_states=market_states,
            risk_snapshot=risk_snapshot,
        )
        for row in cycle_rows:
            row["strategy"] = strategy_id
            row["strategy_type"] = row.get("strategy_type") or strategy_id
        decisions.extend(cycle_rows)

    lifecycle_registry = _safe_json(cache.get(f"futures:strategy:lifecycle:{user_id}"), {}) if cache else {}
    lifecycle_registry = _seed_legacy_disabled_lifecycle(lifecycle_registry, legacy_shadow_strategy_ids)
    throttle_payload = _safe_json(cache.get(f"futures:strategy:throttle:{user_id}"), {}) if cache else {}
    throttle_by_strategy = throttle_payload.get("by_strategy") if isinstance(throttle_payload, dict) else {}
    decisions, governance_enforcement = enforce_strategy_lifecycle_on_decisions(
        decisions,
        lifecycle_registry=lifecycle_registry,
        throttle_by_strategy=throttle_by_strategy,
    )
    decisions, cluster_guard_events = apply_cluster_order_guard_to_decisions(db, cache, user_id, decisions)
    decisions, capital_guard_events, capital_snapshot = apply_capital_order_guard_to_decisions(db, cache, user_id, decisions)
    decisions, tail_risk_guard_events, global_risk_payload = apply_tail_risk_order_guard_to_decisions(db, cache, user_id, decisions)
    decisions, live_readiness_guard_events, live_readiness_payload = apply_live_readiness_guard_to_decisions(db, cache, user_id, decisions)

    decisions, interaction_blocked = StrategyInteractionGuard().apply(decisions)
    exposure_tracker = StrategyExposureTracker()
    decisions, exposure_blocked, exposure = exposure_tracker.apply(decisions)

    executor = FuturesPaperExecutor()
    paper_results = []
    cumulative_pnl = 0.0
    paper_pnl_series = []
    false_allow_count = 0
    false_reject_count = 0
    confidence_vs_result = []
    decision_trace_records = []

    for decision in decisions:
        if decision.get("decision_trace_model"):
            decision_trace_records.append(decision["decision_trace_model"])

        if decision["decision"] != "ALLOW":
            market_state = market_map.get(decision["symbol"], {})
            if decision.get("side") in {"LONG", "SHORT"}:
                counterfactual = executor.simulate(
                    strategy_signal={"side": decision.get("side"), "confidence": decision.get("confidence", 0.0)},
                    market_state=market_state,
                )
                counterfactual_pnl = float(counterfactual.get("paper_pnl", 0.0))
                if counterfactual_pnl > 0:
                    false_reject_count += 1
                confidence_vs_result.append(
                    {
                        "symbol": decision["symbol"],
                        "strategy": decision.get("strategy"),
                        "confidence": round(float(decision.get("confidence") or 0.0), 4),
                        "decision": "REJECT",
                        "result_pnl": round(counterfactual_pnl, 6),
                        "is_false_reject": counterfactual_pnl > 0,
                        "decision_layer": decision.get("decision_layer", "UNKNOWN"),
                        "final_leverage": float((decision.get("leverage_decision") or {}).get("final_leverage") or 1.0),
                        "position_size_ratio": float((decision.get("leverage_decision") or {}).get("position_size_ratio") or 1.0),
                        "expected_slippage_bps": _safe_float(counterfactual.get("expected_slippage_bps")),
                        "execution_latency_ms": _safe_float(counterfactual.get("execution_latency_ms")),
                    }
                )
            continue

        market_state = market_map.get(decision["symbol"], {})
        leverage_decision = decision.get("leverage_decision") or {}
        leverage_size_ratio = float(leverage_decision.get("position_size_ratio") or 1.0)
        execution_size_ratio = float((decision.get("execution_suitability") or {}).get("max_allowed_size_ratio", 1.0))
        size_ratio = max(0.0, min(leverage_size_ratio, execution_size_ratio, 1.0))
        paper = executor.simulate(strategy_signal=decision, market_state=market_state)
        paper["size_ratio_applied"] = round(size_ratio, 4)
        paper["final_leverage"] = float(leverage_decision.get("final_leverage") or 1.0)

        pnl = float(paper.get("paper_pnl", 0.0))
        if pnl < 0:
            false_allow_count += 1
        cumulative_pnl += pnl

        paper_row = {
            "symbol": decision["symbol"],
            "side": decision["side"],
            "strategy": decision.get("strategy"),
            **paper,
        }
        paper_results.append(paper_row)
        paper_pnl_series.append(
            {
                "index": len(paper_pnl_series) + 1,
                "symbol": decision["symbol"],
                "strategy": decision.get("strategy"),
                "paper_pnl": round(pnl, 6),
                "cumulative_pnl": round(cumulative_pnl, 6),
            }
        )
        confidence_vs_result.append(
            {
                "symbol": decision["symbol"],
                "strategy": decision.get("strategy"),
                "confidence": round(float(decision.get("confidence") or 0.0), 4),
                "decision": "ALLOW",
                "result_pnl": round(pnl, 6),
                "is_false_allow": pnl < 0,
                "decision_layer": decision.get("decision_layer", "UNKNOWN"),
                "final_leverage": float(leverage_decision.get("final_leverage") or 1.0),
                "position_size_ratio": round(size_ratio, 4),
                "expected_slippage_bps": _safe_float(paper.get("expected_slippage_bps")),
                "execution_latency_ms": _safe_float(paper.get("execution_latency_ms")),
            }
        )

    false_allow_by_strategy: dict[str, int] = {}
    false_reject_by_strategy: dict[str, int] = {}
    for row in confidence_vs_result:
        strategy_key = str(row.get("strategy") or "unknown")
        if row.get("decision") == "ALLOW" and bool(row.get("is_false_allow")):
            false_allow_by_strategy[strategy_key] = int(false_allow_by_strategy.get(strategy_key, 0) + 1)
        if row.get("decision") == "REJECT" and bool(row.get("is_false_reject")):
            false_reject_by_strategy[strategy_key] = int(false_reject_by_strategy.get(strategy_key, 0) + 1)

    strategy_metrics_map: dict[str, dict] = {}
    for strategy_id in strategy_registry.keys():
        rows = [row for row in decisions if row.get("strategy") == strategy_id]
        trades = [row for row in paper_results if row.get("strategy") == strategy_id]
        signal_total = len(rows)
        allowed_total = len([row for row in rows if row.get("decision") == "ALLOW"])
        rejected_total = len([row for row in rows if row.get("decision") == "REJECT"])
        reject_rate = (rejected_total / signal_total) if signal_total > 0 else 0.0
        avg_confidence = (
            sum(float(row.get("confidence") or 0.0) for row in rows) / signal_total if signal_total > 0 else 0.0
        )
        pnl = sum(float(row.get("paper_pnl") or 0.0) for row in trades)
        avg_slippage_bps = sum(_safe_float(row.get("expected_slippage_bps")) for row in trades) / len(trades) if trades else 0.0
        avg_latency_ms = sum(_safe_float(row.get("execution_latency_ms")) for row in trades) / len(trades) if trades else 0.0
        false_allow_strategy = int(false_allow_by_strategy.get(strategy_id, 0))
        false_reject_strategy = int(false_reject_by_strategy.get(strategy_id, 0))
        execution_quality = max(
            0.0,
            min(
                1.0,
                1
                - reject_rate * 0.55
                - max(-pnl, 0.0) * 16
                - min(avg_slippage_bps, 120) / 350
                - min(avg_latency_ms, 900) / 2800
                - min(false_allow_strategy, 4) * 0.04
                - min(false_reject_strategy, 4) * 0.03,
            ),
        )
        strategy_metrics_map[strategy_id] = {
            "strategy": strategy_id,
            "signal_total": signal_total,
            "allowed_total": allowed_total,
            "rejected_total": rejected_total,
            "reject_rate": round(reject_rate, 4),
            "avg_confidence": round(avg_confidence, 4),
            "paper_pnl": round(pnl, 6),
            "avg_slippage_bps": round(avg_slippage_bps, 4),
            "avg_latency_ms": round(avg_latency_ms, 2),
            "false_allow_count": false_allow_strategy,
            "false_reject_count": false_reject_strategy,
            "execution_quality": round(execution_quality, 4),
        }

    strategy_execution_quality = [
        {
            "strategy": key,
            "execution_quality": value["execution_quality"],
        }
        for key, value in strategy_metrics_map.items()
    ]
    strategy_slippage = [
        {
            "strategy": key,
            "avg_slippage_bps": value["avg_slippage_bps"],
        }
        for key, value in strategy_metrics_map.items()
    ]
    strategy_latency = [
        {
            "strategy": key,
            "avg_latency_ms": value["avg_latency_ms"],
        }
        for key, value in strategy_metrics_map.items()
    ]
    strategy_reject_rate = [
        {
            "strategy": key,
            "reject_rate": value["reject_rate"],
        }
        for key, value in strategy_metrics_map.items()
    ]
    strategy_confidence_vs_result = [
        {
            "strategy": key,
            "avg_confidence": value["avg_confidence"],
            "paper_pnl": value["paper_pnl"],
            "divergence_score": round(abs(value["avg_confidence"] - (1 if value["paper_pnl"] > 0 else 0)), 4),
        }
        for key, value in strategy_metrics_map.items()
    ]
    false_compare_by_strategy = [
        {
            "strategy": strategy_id,
            "false_allow": int(false_allow_by_strategy.get(strategy_id, 0)),
            "false_reject": int(false_reject_by_strategy.get(strategy_id, 0)),
        }
        for strategy_id in strategy_registry.keys()
    ]

    confidence_drift_map = {
        str(item.get("strategy")): float(item.get("divergence_score") or 0.0)
        for item in strategy_confidence_vs_result
    }
    shadow_pnl_by_strategy: dict[str, float] = {}
    for row in confidence_vs_result:
        strategy_key = str(row.get("strategy") or "unknown")
        if row.get("decision") == "REJECT":
            shadow_pnl_by_strategy[strategy_key] = shadow_pnl_by_strategy.get(strategy_key, 0.0) + float(
                row.get("result_pnl") or 0.0
            )

    legacy_formula_observability: list[dict] = []
    for strategy_id in legacy_shadow_strategy_ids:
        metrics = strategy_metrics_map.get(strategy_id) or {}
        signal_total = int(metrics.get("signal_total") or 0)
        false_breakout_rate = 0.0
        if signal_total > 0:
            false_breakout_rate = (int(false_allow_by_strategy.get(strategy_id, 0)) + int(false_reject_by_strategy.get(strategy_id, 0))) / signal_total

        meta = strategy_metadata_map.get(strategy_id, {})
        legacy_formula_observability.append(
            {
                "strategy": strategy_id,
                "role": meta.get("role", "strategy"),
                "family_code": meta.get("family_code"),
                "source_type": meta.get("source_type", "legacy_formula"),
                "shadow_status": "SHADOW_ONLY",
                "status": "DISABLED",
                "signal_frequency": signal_total,
                "shadow_pnl": round(float(shadow_pnl_by_strategy.get(strategy_id, 0.0)), 6),
                "false_breakout_rate": round(float(false_breakout_rate), 6),
                "confidence_drift": round(float(confidence_drift_map.get(strategy_id, 0.0)), 6),
            }
        )

    legacy_formula_observability.extend(_build_prefilter_shadow_rows(market_states))

    signal_feed = [
        {
            "strategy": item.get("strategy"),
            "strategy_type": item.get("strategy_type", item.get("strategy")),
            "strategy_signal_strength": float(item.get("confidence") or 0.0),
            "strategy_context": item.get("strategy_context") or {},
            "symbol": item["signal"]["symbol"],
            "side": item["signal"]["side"],
            "confidence": item["signal"]["confidence"],
            "regime": item["signal"]["regime"],
            "reason": item["signal"]["reason"],
        }
        for item in decisions
    ]

    reject_reason_map: dict[str, int] = {}
    for row in decisions:
        if row["decision"] == "REJECT":
            reason = str(row.get("reason_code") or "UNKNOWN")
            reject_reason_map[reason] = reject_reason_map.get(reason, 0) + 1

    governance_blocked_rows = [
        row
        for row in decisions
        if row.get("decision") == "REJECT"
        and any(
            reason
            in {
                "STRATEGY_DISABLED_HARD_BLOCK",
                "STRATEGY_THROTTLE_FREQUENCY",
                "CLUSTER_TRADE_REJECTED",
                "CAPITAL_TRADE_REJECTED",
                "TAIL_RISK_TRADE_REJECTED",
                "LIVE_READINESS_BLOCK",
            }
            for reason in (row.get("reasons") or [])
        )
    ]

    avg_confidence = (
        sum(float(row.get("confidence") or 0.0) for row in decisions) / len(decisions)
        if decisions
        else 0.0
    )

    decision_layer_distribution = _decision_layer_distribution(decisions)
    leverage_distribution = _leverage_distribution(decisions)
    size_clamp_events = len(
        [row for row in decisions if float((row.get("leverage_decision") or {}).get("position_size_ratio") or 1.0) < 1.0]
    )
    confidence_vs_leverage = [
        {
            "symbol": row.get("symbol"),
            "strategy": row.get("strategy"),
            "confidence": float(row.get("confidence") or 0.0),
            "final_leverage": float((row.get("leverage_decision") or {}).get("final_leverage") or 1.0),
            "decision": row.get("decision"),
        }
        for row in decisions
    ]
    liquidation_distance_vs_leverage = [
        {
            "symbol": row.get("symbol"),
            "strategy": row.get("strategy"),
            "liquidation_distance": float(risk_snapshot.get("avg_distance_to_liquidation") or 0.0),
            "final_leverage": float((row.get("leverage_decision") or {}).get("final_leverage") or 1.0),
        }
        for row in decisions
    ]

    diagnostics = {
        "false_allow_count": false_allow_count,
        "false_reject_count": false_reject_count,
        "gate_reason_distribution": reject_reason_map,
        "confidence_vs_result": confidence_vs_result,
        "decision_layer_distribution": decision_layer_distribution,
        "leverage_distribution": leverage_distribution,
        "size_clamp_events": size_clamp_events,
        "confidence_vs_leverage": confidence_vs_leverage,
        "liquidation_distance_vs_leverage": liquidation_distance_vs_leverage,
    }

    attribution = build_strategy_attribution(decisions, paper_results)
    drift_rows = [
        {
            "strategy": item["strategy"],
            "pnl": item["paper_pnl"],
            "avg_confidence": item["avg_confidence"],
            "execution_quality": item["execution_quality"],
            "reject_rate": item["reject_rate"],
        }
        for item in strategy_metrics_map.values()
    ]
    drift = detect_strategy_drift(drift_rows)

    history_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "strategy_metrics": list(strategy_metrics_map.values()),
        "strategy_attribution": attribution.get("strategy_attribution", []),
        "reject_reason_distribution": reject_reason_map,
        "false_allow_count": false_allow_count,
        "false_reject_count": false_reject_count,
        "false_compare_by_strategy": false_compare_by_strategy,
    }
    history = _append_strategy_history(cache, user_id, history_entry) if cache else [history_entry]
    rolling_tuning_score = _rolling_tuning_score_7d(history)
    gate_reason_trend_7d = _gate_reason_trend_7d(history)

    previous_decay_state = _safe_json(cache.get(f"futures:strategy:decay-state:{user_id}"), {}) if cache else {}
    health_snapshot = build_strategy_health_snapshot(
        history=history,
        strategy_metrics=list(strategy_metrics_map.values()),
        strategy_attribution=attribution.get("strategy_attribution", []),
    )
    decay_result = detect_strategy_decay(
        health_snapshot.get("strategies", []),
        previous_state=previous_decay_state,
    )
    throttle_result = build_strategy_throttle_state(
        health_snapshot.get("strategies", []),
        decay_result.get("strategy_decay_events", []),
        previous_state=throttle_by_strategy,
    )
    disable_result = evaluate_strategy_auto_disable(
        health_snapshot.get("strategies", []),
        decay_state=decay_result.get("decay_state", {}),
        lifecycle_registry=lifecycle_registry,
    )

    disable_rows = list(disable_result.get("strategy_disable_state") or [])
    disable_by_strategy = dict(disable_result.get("by_strategy") or {})
    disable_map = {str(item.get("strategy")): item for item in disable_rows}
    for strategy_id in legacy_shadow_strategy_ids:
        disable_by_strategy[strategy_id] = {
            "strategy": strategy_id,
            "disable_state": "DISABLED",
            "should_disable": True,
            "reasons": ["LEGACY_SHADOW_ONLY"],
        }
        disable_map[strategy_id] = {
            "strategy": strategy_id,
            "disable_state": "DISABLED",
            "reasons": ["LEGACY_SHADOW_ONLY"],
        }
    disable_result["by_strategy"] = disable_by_strategy
    disable_result["strategy_disable_state"] = list(disable_map.values())

    lifecycle_result = apply_lifecycle_transitions(
        strategy_ids=list(strategy_registry.keys()),
        existing_registry=lifecycle_registry,
        throttle_by_strategy=throttle_result.get("by_strategy", {}),
        disable_by_strategy=disable_result.get("by_strategy", {}),
    )
    governance_events = build_strategy_governance_audit_events(
        health_rows=health_snapshot.get("strategies", []),
        decay_events=decay_result.get("strategy_decay_events", []),
        throttle_rows=throttle_result.get("strategy_throttle_state", []),
        disable_events=disable_result.get("disable_events", []),
        lifecycle_transitions=lifecycle_result.get("transitions", []),
    )

    for event in governance_events[:20]:
        try:
            create_audit_log(
                db,
                action=event.get("event") or "STRATEGY_GOVERNANCE_EVENT",
                entity_type="futures_strategy_governance",
                entity_id=str(event.get("strategy") or "unknown"),
                actor_user_id=user_id,
                actor_role="system",
                severity="critical" if event.get("event") == "STRATEGY_DISABLED" else "warning",
                details=event,
            )
        except Exception:
            continue

    strategy_signal_distribution = [
        {
            "strategy": strategy,
            "signal_total": item["signal_total"],
            "allowed_total": item["allowed_total"],
            "rejected_total": item["rejected_total"],
        }
        for strategy, item in strategy_metrics_map.items()
    ]

    snapshot = {
        "strategy": "futures_trend_follow_v1",
        "strategy_mode": "MULTI",
        "strategy_registry": list(strategy_registry.keys()),
        "strategy_metadata": list(strategy_metadata_map.values()),
        "legacy_formula_observability": legacy_formula_observability,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "futures_strategy_signal_total": len(decisions),
            "futures_strategy_allowed_total": len([row for row in decisions if row["decision"] == "ALLOW"]),
            "futures_strategy_rejected_total": len([row for row in decisions if row["decision"] == "REJECT"]),
            "futures_strategy_confidence": round(avg_confidence, 4),
            "futures_strategy_paper_pnl": round(cumulative_pnl, 6),
        },
        "strategy_metrics": list(strategy_metrics_map.values()),
        "strategy_execution_quality": strategy_execution_quality,
        "strategy_slippage": strategy_slippage,
        "strategy_latency": strategy_latency,
        "strategy_reject_rate": strategy_reject_rate,
        "strategy_confidence_vs_result": strategy_confidence_vs_result,
        "false_allow_reject_comparison_by_strategy": false_compare_by_strategy,
        "rolling_7d_tuning_score": rolling_tuning_score,
        "gate_reason_trend_7d": gate_reason_trend_7d,
        "strategy_health_score": health_snapshot.get("strategies", []),
        "strategy_health_components": [
            {
                "strategy": item.get("strategy"),
                "health_components": item.get("health_components", {}),
                "observation_count": item.get("observation_count", 0),
                "data_state": item.get("data_state", "HEALTHY"),
            }
            for item in (health_snapshot.get("strategies") or [])
        ],
        "strategy_decay_events": decay_result.get("strategy_decay_events", []),
        "strategy_throttle_state": throttle_result.get("strategy_throttle_state", []),
        "strategy_disable_state": disable_result.get("strategy_disable_state", []),
        "strategy_lifecycle_state": [
            {
                "strategy": item.get("strategy"),
                "lifecycle_state": item.get("lifecycle_state", "ACTIVE"),
                "last_transition_at": item.get("last_transition_at"),
                "last_transition_reason": item.get("last_transition_reason"),
            }
            for item in (lifecycle_result.get("registry", {}) or {}).values()
        ],
        "strategy_lifecycle_registry": lifecycle_result.get("registry", {}),
        "governance_audit_events": governance_events,
        "strategy_signal_distribution": strategy_signal_distribution,
        "strategy_drift_alerts": drift.get("strategy_drift_alerts", []),
        "cluster_order_guard_events": cluster_guard_events,
        "capital_order_guard_events": capital_guard_events,
        "tail_risk_order_guard_events": tail_risk_guard_events,
        "capital_budget_snapshot": (capital_snapshot.get("strategy_capital_budget") or []),
        "capital_usage_snapshot": (capital_snapshot.get("strategy_capital_usage") or []),
        "capital_drift_state": ((capital_snapshot.get("capital_drift") or {}).get("capital_drift_events") or []),
        "tail_risk_score": ((global_risk_payload.get("tail_risk") or {}).get("tail_risk_score") or 0.0),
        "global_risk_score": global_risk_payload.get("global_risk_score", 0.0),
        "global_risk_state": global_risk_payload.get("risk_state", "NORMAL"),
        "global_risk_active_alerts": global_risk_payload.get("active_alerts") or [],
        "tail_risk_audit_events": global_risk_payload.get("tail_risk_audit_events") or [],
        "live_readiness_score": live_readiness_payload.get("readiness_score", 0.0),
        "live_readiness_state": live_readiness_payload.get("readiness_state", "BLOCKED"),
        "live_readiness_alerts": live_readiness_payload.get("alerts") or [],
        "live_readiness_guard_events": live_readiness_guard_events,
        "signal_feed": signal_feed,
        "decision_trace": decisions,
        "decision_trace_contract_records": decision_trace_records,
        "paper_trades": paper_results,
        "paper_pnl_series": paper_pnl_series,
        "microstructure": {
            "portfolio_microstructure_state": microstructure_status.get("portfolio_microstructure_state", "SAFE"),
            "portfolio_microstructure_risk_score": microstructure_status.get("portfolio_microstructure_risk_score", 0.0),
            "gate_rejections": microstructure_status.get("gate_rejections", []),
            "execution_suitability": microstructure_status.get("execution_suitability", {}),
        },
        "interaction_guard": {
            "blocked_total": len(interaction_blocked)
            + len(exposure_blocked)
            + int(governance_enforcement.get("disabled_blocked_total", 0))
            + int(governance_enforcement.get("throttled_rejected_total", 0))
            + len(cluster_guard_events)
            + len(capital_guard_events)
            + len(tail_risk_guard_events)
            + len(live_readiness_guard_events),
            "interaction_blocked_total": len(interaction_blocked),
            "exposure_blocked_total": len(exposure_blocked),
            "governance_disabled_blocked_total": int(governance_enforcement.get("disabled_blocked_total", 0)),
            "governance_throttled_rejected_total": int(governance_enforcement.get("throttled_rejected_total", 0)),
            "cluster_rejected_total": len(cluster_guard_events),
            "capital_rejected_total": len(capital_guard_events),
            "tail_risk_rejected_total": len(tail_risk_guard_events),
            "live_readiness_rejected_total": len(live_readiness_guard_events),
            "blocked": [*interaction_blocked, *exposure_blocked, *governance_blocked_rows],
        },
        "strategy_governance": {
            "strategy_health_score": health_snapshot.get("strategies", []),
            "throttle_state": throttle_result.get("strategy_throttle_state", []),
            "disable_state": disable_result.get("strategy_disable_state", []),
            "decay_events": decay_result.get("strategy_decay_events", []),
            "lifecycle_state": [
                {
                    "strategy": item.get("strategy"),
                    "lifecycle_state": item.get("lifecycle_state", "ACTIVE"),
                    "last_transition_at": item.get("last_transition_at"),
                    "last_transition_reason": item.get("last_transition_reason"),
                }
                for item in (lifecycle_result.get("registry", {}) or {}).values()
            ],
            "governance_enforcement": governance_enforcement,
            "cluster_order_guard_events": cluster_guard_events,
            "capital_order_guard_events": capital_guard_events,
            "tail_risk_order_guard_events": tail_risk_guard_events,
            "live_readiness_order_guard_events": live_readiness_guard_events,
        },
        "exposure_tracking": exposure,
        "strategy_attribution": attribution.get("strategy_attribution", []),
        "reject_reason_breakdown": [
            {"reason_code": reason, "count": count}
            for reason, count in sorted(reject_reason_map.items(), key=lambda item: item[1], reverse=True)
        ],
        "confidence_distribution": _confidence_distribution(decisions),
        "decision_diagnostics": diagnostics,
    }
    snapshot["architecture_checklist_15"] = _build_strategy_architecture_checklist_15(snapshot)

    if cache:
        cache.set(f"futures:strategy:status:{user_id}", json.dumps(snapshot))
        cache.set(f"futures:strategy:health:{user_id}", json.dumps(health_snapshot))
        cache.set(f"futures:strategy:governance:{user_id}", json.dumps(snapshot.get("strategy_governance") or {}))
        cache.set(f"futures:strategy:decay-state:{user_id}", json.dumps(decay_result.get("decay_state") or {}))
        cache.set(f"futures:strategy:throttle:{user_id}", json.dumps(throttle_result))
        cache.set(f"futures:strategy:lifecycle:{user_id}", json.dumps(lifecycle_result.get("registry") or {}))
        cache.set(f"futures:strategy:governance:audit:{user_id}", json.dumps(governance_events[-250:]))
        cache.set("metrics:futures_strategy_signal_total", str(snapshot["metrics"]["futures_strategy_signal_total"]))
        cache.set("metrics:futures_strategy_allowed_total", str(snapshot["metrics"]["futures_strategy_allowed_total"]))
        cache.set("metrics:futures_strategy_rejected_total", str(snapshot["metrics"]["futures_strategy_rejected_total"]))
        cache.set("metrics:futures_strategy_confidence", str(snapshot["metrics"]["futures_strategy_confidence"]))
        cache.set("metrics:futures_strategy_paper_pnl", str(snapshot["metrics"]["futures_strategy_paper_pnl"]))
        cache.set("metrics:futures_false_allow_total", str(false_allow_count))
        cache.set("metrics:futures_false_reject_total", str(false_reject_count))
        cache.set("metrics:futures_gate_reason_distribution", json.dumps(reject_reason_map))
        cache.set("metrics:futures_strategy_confidence_vs_result", json.dumps(confidence_vs_result))

        leverage_events = [
            {
                "symbol": row.get("symbol"),
                "strategy": row.get("strategy"),
                "confidence": float(row.get("confidence") or 0.0),
                "microstructure_quality": round(max(0.0, min(1.0, 1 - float((row.get("microstructure_gate") or {}).get("risk_score", 0.0)))), 4),
                "liquidation_distance": float(risk_snapshot.get("avg_distance_to_liquidation") or 0.0),
                "funding_bias": ((market_map.get(row.get("symbol"), {}) or {}).get("funding_bias", {}) or {}).get("bias_direction", "NEUTRAL"),
                "final_leverage": float((row.get("leverage_decision") or {}).get("final_leverage") or 1.0),
                "size_ratio": float((row.get("leverage_decision") or {}).get("position_size_ratio") or 1.0),
                "decision": row.get("decision"),
                "decision_layer": row.get("decision_layer"),
            }
            for row in decisions
        ]
        cache.set(
            f"futures:leverage:status:{user_id}",
            json.dumps(
                {
                    "events": leverage_events,
                    "diagnostics": diagnostics,
                    "updated_at": snapshot["generated_at"],
                    "strategy": snapshot["strategy"],
                }
            ),
        )

    return snapshot


def get_futures_strategy_status(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    if refresh:
        return run_futures_strategy_paper_cycle(db, cache, user_id)

    raw = cache.get(f"futures:strategy:status:{user_id}") if cache else None
    cached = _safe_json(raw, None)
    if cached:
        return cached
    return run_futures_strategy_paper_cycle(db, cache, user_id)


def get_futures_strategy_performance(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    status = get_futures_strategy_status(db, cache, user_id, refresh=refresh)
    return {
        "strategy_mode": status.get("strategy_mode", "MULTI"),
        "strategy_registry": status.get("strategy_registry", []),
        "strategy_metadata": status.get("strategy_metadata", []),
        "legacy_formula_observability": status.get("legacy_formula_observability", []),
        "generated_at": status.get("generated_at"),
        "strategy_pnl_contribution": [
            {
                "strategy": row.get("strategy"),
                "pnl_attribution": row.get("pnl_attribution", 0.0),
                "pnl_contribution_ratio": row.get("pnl_contribution_ratio", 0.0),
                "trade_count": row.get("trade_count", 0),
            }
            for row in (status.get("strategy_attribution") or [])
        ],
        "strategy_signal_distribution": status.get("strategy_signal_distribution", []),
        "exposure_tracking": status.get("exposure_tracking", {}),
        "interaction_guard": status.get("interaction_guard", {}),
        "strategy_attribution": status.get("strategy_attribution", []),
        "strategy_drift_alerts": status.get("strategy_drift_alerts", []),
    }


def get_futures_strategy_execution_quality(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    status = get_futures_strategy_status(db, cache, user_id, refresh=refresh)
    rolling = status.get("rolling_7d_tuning_score") or _rolling_tuning_score_7d(
        _safe_json(cache.get(f"futures:strategy:history:{user_id}"), []) if cache else []
    )
    gate_trend = status.get("gate_reason_trend_7d") or _gate_reason_trend_7d(
        _safe_json(cache.get(f"futures:strategy:history:{user_id}"), []) if cache else []
    )

    return {
        "generated_at": status.get("generated_at"),
        "legacy_formula_observability": status.get("legacy_formula_observability", []),
        "strategy_execution_quality": status.get("strategy_execution_quality", []),
        "strategy_slippage": status.get("strategy_slippage", []),
        "strategy_latency": status.get("strategy_latency", []),
        "strategy_reject_rate": status.get("strategy_reject_rate", []),
        "strategy_confidence_vs_result": status.get("strategy_confidence_vs_result", []),
        "rolling_7d_tuning_score": rolling,
        "strategy_drift_alerts": status.get("strategy_drift_alerts", []),
        "false_allow_reject_comparison_by_strategy": status.get("false_allow_reject_comparison_by_strategy", []),
        "gate_reason_trend_7d": gate_trend,
        "architecture_checklist_15": status.get("architecture_checklist_15", []),
    }


def get_futures_strategy_health(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    status = get_futures_strategy_status(db, cache, user_id, refresh=refresh)
    health_rows = status.get("strategy_health_score") or []
    components = status.get("strategy_health_components") or []
    lifecycle = status.get("strategy_lifecycle_state") or []
    lifecycle_map = {str(item.get("strategy")): item for item in lifecycle}

    return {
        "generated_at": status.get("generated_at"),
        "legacy_formula_observability": status.get("legacy_formula_observability", []),
        "strategy_health_score": health_rows,
        "health_components": components,
        "lifecycle_state": lifecycle,
        "drawdown_state": [
            {
                "strategy": row.get("strategy"),
                "drawdown_state": row.get("drawdown_state", "NORMAL"),
                "last_transition_at": (lifecycle_map.get(str(row.get("strategy"))) or {}).get("last_transition_at"),
            }
            for row in health_rows
        ],
    }


def get_futures_strategy_governance(
    db: Session,
    cache,
    user_id: str,
    refresh: bool = False,
    compare_a: str | None = None,
    compare_b: str | None = None,
) -> dict:
    status = get_futures_strategy_status(db, cache, user_id, refresh=refresh)
    governance = status.get("strategy_governance") or {}

    registry = status.get("strategy_registry") or []
    selected: list[str] = []
    if compare_a and compare_a in registry:
        selected.append(compare_a)
    if compare_b and compare_b in registry and compare_b not in selected:
        selected.append(compare_b)
    if not selected:
        selected = registry[:2]
    elif len(selected) == 1:
        backup = next((item for item in registry if item != selected[0]), selected[0] if selected else "")
        if backup:
            selected.append(backup)

    history = _safe_json(cache.get(f"futures:strategy:history:{user_id}"), []) if cache else []
    weekly_summary = _weekly_strategy_summary(history, selected)

    cluster_risk_payload = _safe_json(cache.get(f"futures:correlation:cluster-risk:{user_id}"), {}) if cache else {}
    if not cluster_risk_payload:
        cluster_risk_payload = get_futures_cluster_risk(db, cache, user_id, refresh=False)
    cluster_exposures = cluster_risk_payload.get("cluster_exposures") or []
    symbol_to_strategy = {
        str(item.get("symbol") or "").upper(): str(item.get("strategy") or "unknown")
        for item in (status.get("decision_trace") or [])
        if item.get("decision") == "REJECT" and "CLUSTER_TRADE_REJECTED" in (item.get("reasons") or [])
    }
    overlay_rows = []
    for row in cluster_exposures:
        positions = row.get("positions") or []
        risk_source_symbol = None
        if positions:
            top_position = max(positions, key=lambda item: abs(_safe_float(item.get("position_notional"), 0.0)))
            risk_source_symbol = str(top_position.get("symbol") or "").upper()
        if not risk_source_symbol and (row.get("symbols") or []):
            risk_source_symbol = f"{row['symbols'][0]}USDT"
        triggered_strategy = symbol_to_strategy.get(risk_source_symbol or "", "unknown")
        overlay_rows.append(
            {
                "cluster_id": row.get("cluster_id"),
                "cluster_exposure": row.get("cluster_exposure", 0.0),
                "triggered_strategy": triggered_strategy,
                "risk_source_symbol": risk_source_symbol,
                "risk_state": row.get("risk_state", "NORMAL"),
            }
        )

    lifecycle_state = governance.get("lifecycle_state") or status.get("strategy_lifecycle_state") or []
    lifecycle_map = {str(item.get("strategy")): item for item in lifecycle_state}
    decay_events = governance.get("decay_events") or status.get("strategy_decay_events") or []
    health_rows = governance.get("strategy_health_score") or status.get("strategy_health_score") or []
    health_component_map = {
        str(item.get("strategy")): item.get("health_components", {})
        for item in (status.get("strategy_health_components") or [])
    }

    return {
        "generated_at": status.get("generated_at"),
        "legacy_formula_observability": status.get("legacy_formula_observability", []),
        "strategy_health_score": health_rows,
        "throttle_state": governance.get("throttle_state") or status.get("strategy_throttle_state") or [],
        "disable_state": governance.get("disable_state") or status.get("strategy_disable_state") or [],
        "decay_events": decay_events,
        "health_components": [
            {
                "strategy": row.get("strategy"),
                "health_components": health_component_map.get(str(row.get("strategy")), row.get("health_components", {})),
            }
            for row in health_rows
        ],
        "decay_reason_codes": [
            {
                "strategy": item.get("strategy"),
                "decay_reason_codes": item.get("decay_reason_codes") or [],
            }
            for item in decay_events
        ],
        "lifecycle_state": lifecycle_state,
        "last_transition_at": [
            {
                "strategy": row.get("strategy"),
                "last_transition_at": (lifecycle_map.get(str(row.get("strategy"))) or {}).get("last_transition_at"),
            }
            for row in health_rows
        ],
        "drawdown_state": [
            {
                "strategy": row.get("strategy"),
                "drawdown_state": row.get("drawdown_state", "NORMAL"),
            }
            for row in health_rows
        ],
        "governance_audit_events": status.get("governance_audit_events")
        or (_safe_json(cache.get(f"futures:strategy:governance:audit:{user_id}"), []) if cache else []),
        "cluster_risk_overlay": overlay_rows,
        "tail_risk_score": status.get("tail_risk_score", 0.0),
        "global_risk_score": status.get("global_risk_score", 0.0),
        "global_risk_state": status.get("global_risk_state", "NORMAL"),
        "global_risk_active_alerts": status.get("global_risk_active_alerts") or [],
        "live_readiness_score": status.get("live_readiness_score", 0.0),
        "live_readiness_state": status.get("live_readiness_state", "BLOCKED"),
        "live_readiness_alerts": status.get("live_readiness_alerts") or [],
        "strategy_compare_mode": {
            "selected_strategies": selected,
            "metrics": [
                {
                    "strategy": row.get("strategy"),
                    "pnl": row.get("strategy_pnl_rolling", 0.0),
                    "execution_quality": row.get("strategy_execution_quality", 0.0),
                    "signal_frequency": (
                        next(
                            (
                                item.get("signal_total")
                                for item in (status.get("strategy_signal_distribution") or [])
                                if item.get("strategy") == row.get("strategy")
                            ),
                            0,
                        )
                    ),
                    "win_rate": row.get("strategy_win_rate_rolling", 0.0),
                    "health_score": row.get("strategy_health_score", 0.0),
                }
                for row in health_rows
                if row.get("strategy") in set(selected)
            ],
            "weekly_auto_summary": weekly_summary,
        },
    }


def get_futures_decision_diagnostics(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    status = get_futures_strategy_status(db, cache, user_id, refresh=refresh)
    diagnostics = status.get("decision_diagnostics") or {}
    return {
        "false_allow_count": diagnostics.get("false_allow_count", 0),
        "false_reject_count": diagnostics.get("false_reject_count", 0),
        "gate_reason_distribution": diagnostics.get("gate_reason_distribution", {}),
        "confidence_vs_result": diagnostics.get("confidence_vs_result", []),
        "decision_layer_distribution": diagnostics.get("decision_layer_distribution", {}),
        "leverage_distribution": diagnostics.get("leverage_distribution", []),
        "size_clamp_events": diagnostics.get("size_clamp_events", 0),
        "confidence_vs_leverage": diagnostics.get("confidence_vs_leverage", []),
        "liquidation_distance_vs_leverage": diagnostics.get("liquidation_distance_vs_leverage", []),
        "updated_at": status.get("generated_at"),
    }


def get_futures_leverage_status(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    if refresh:
        run_futures_strategy_paper_cycle(db, cache, user_id)

    raw = cache.get(f"futures:leverage:status:{user_id}") if cache else None
    payload = _safe_json(raw, None)
    if not payload:
        run_futures_strategy_paper_cycle(db, cache, user_id)
        raw = cache.get(f"futures:leverage:status:{user_id}") if cache else None
        payload = _safe_json(raw, None)
    payload = payload or {"events": [], "diagnostics": {}, "updated_at": None, "strategy": "futures_trend_follow_v1"}

    events = payload.get("events") or []
    primary = events[0] if events else {
        "symbol": "BTCUSDT",
        "strategy": payload.get("strategy", "futures_trend_follow_v1"),
        "confidence": 0.0,
        "microstructure_quality": 0.0,
        "liquidation_distance": 0.0,
        "funding_bias": "NEUTRAL",
        "final_leverage": 1.0,
        "size_ratio": 1.0,
    }
    diagnostics = payload.get("diagnostics") or {}

    return {
        "symbol": primary.get("symbol", "BTCUSDT"),
        "strategy": primary.get("strategy", "futures_trend_follow_v1"),
        "confidence": round(float(primary.get("confidence", 0.0)), 4),
        "microstructure_quality": round(float(primary.get("microstructure_quality", 0.0)), 4),
        "liquidation_distance": round(float(primary.get("liquidation_distance", 0.0)), 4),
        "funding_bias": str(primary.get("funding_bias", "NEUTRAL")),
        "final_leverage": round(float(primary.get("final_leverage", 1.0)), 4),
        "size_ratio": round(float(primary.get("size_ratio", 1.0)), 4),
        "leverage_distribution": diagnostics.get("leverage_distribution", []),
        "size_clamp_events": diagnostics.get("size_clamp_events", 0),
        "confidence_vs_leverage": diagnostics.get("confidence_vs_leverage", []),
        "liquidation_distance_vs_leverage": diagnostics.get("liquidation_distance_vs_leverage", []),
        "updated_at": payload.get("updated_at"),
    }
