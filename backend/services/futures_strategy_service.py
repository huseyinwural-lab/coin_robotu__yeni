import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.portfolio.strategy_attribution_engine import build_strategy_attribution
from core.portfolio.strategy_exposure_tracker import track_strategy_exposure
from core.portfolio.strategy_interaction_guard import StrategyInteractionGuard
from core.execution.futures_paper_executor import FuturesPaperExecutor
from core.futures.funding_bias_engine import calculate_funding_bias
from core.strategies.analytics.strategy_drift_detector import detect_strategy_drift
from core.strategies.strategy_registry import build_strategy_registry
from core.strategy.futures.futures_strategy_engine import FuturesStrategyEngine
from services.futures_execution_quality_service import build_execution_quality_rolling_7d, build_execution_quality_snapshot
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
        "microstructure_suitable": str(spread_state) != "SHOCK",
    }


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

    decisions, interaction_blocked = StrategyInteractionGuard().apply(decisions)

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
            }
        )

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
        execution_quality = max(0.0, min(1.0, 1 - reject_rate * 0.65 - max(-pnl, 0.0) * 18))
        strategy_metrics_map[strategy_id] = {
            "strategy": strategy_id,
            "signal_total": signal_total,
            "allowed_total": allowed_total,
            "rejected_total": rejected_total,
            "reject_rate": round(reject_rate, 4),
            "avg_confidence": round(avg_confidence, 4),
            "paper_pnl": round(pnl, 6),
            "execution_quality": round(execution_quality, 4),
        }

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

    exposure = track_strategy_exposure(decisions)
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
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "futures_strategy_signal_total": len(decisions),
            "futures_strategy_allowed_total": len([row for row in decisions if row["decision"] == "ALLOW"]),
            "futures_strategy_rejected_total": len([row for row in decisions if row["decision"] == "REJECT"]),
            "futures_strategy_confidence": round(avg_confidence, 4),
            "futures_strategy_paper_pnl": round(cumulative_pnl, 6),
        },
        "strategy_metrics": list(strategy_metrics_map.values()),
        "strategy_signal_distribution": strategy_signal_distribution,
        "strategy_drift_alerts": drift.get("strategy_drift_alerts", []),
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
            "blocked_total": len(interaction_blocked),
            "blocked": interaction_blocked,
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

    if cache:
        cache.set(f"futures:strategy:status:{user_id}", json.dumps(snapshot))
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
