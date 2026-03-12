import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.execution.futures_paper_executor import FuturesPaperExecutor
from core.futures.funding_bias_engine import calculate_funding_bias
from core.strategy.futures.futures_strategy_engine import FuturesStrategyEngine
from core.strategy.futures.futures_trend_follow_v1 import FuturesTrendFollowV1
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


def run_futures_strategy_paper_cycle(db: Session, cache, user_id: str, symbols: list[str] | None = None) -> dict:
    universe = build_effective_universe(db, cache)
    active_symbols = symbols or universe.get("futures_symbols") or ["BTCUSDT", "ETHUSDT"]
    active_symbols = sorted({symbol.upper() for symbol in active_symbols})[:10]

    market_states = [_market_state(cache, symbol) for symbol in active_symbols]
    risk_snapshot = build_futures_risk_status(db, cache, user_id)
    risk_snapshot["policy_leverage_cap"] = min(
        float((risk_snapshot.get("adl_policy") or {}).get("leverage_cap", 5)),
        5.0,
    )

    engine = FuturesStrategyEngine({"futures_trend_follow_v1": FuturesTrendFollowV1()})
    decisions = engine.run_cycle(
        strategy_id="futures_trend_follow_v1",
        market_states=market_states,
        risk_snapshot=risk_snapshot,
    )

    market_map = {state["symbol"]: state for state in market_states}
    executor = FuturesPaperExecutor()
    paper_results = []
    cumulative_pnl = 0.0
    paper_pnl_series = []
    for decision in decisions:
        if decision["decision"] != "ALLOW":
            continue
        paper = executor.simulate(strategy_signal=decision, market_state=market_map.get(decision["symbol"], {}))
        cumulative_pnl += float(paper.get("paper_pnl", 0.0))
        paper_results.append({"symbol": decision["symbol"], "side": decision["side"], **paper})
        paper_pnl_series.append(
            {
                "index": len(paper_pnl_series) + 1,
                "symbol": decision["symbol"],
                "paper_pnl": round(float(paper.get("paper_pnl", 0.0)), 6),
                "cumulative_pnl": round(cumulative_pnl, 6),
            }
        )

    signal_feed = [
        {
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

    snapshot = {
        "strategy": "futures_trend_follow_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "futures_strategy_signal_total": len(decisions),
            "futures_strategy_allowed_total": len([row for row in decisions if row["decision"] == "ALLOW"]),
            "futures_strategy_rejected_total": len([row for row in decisions if row["decision"] == "REJECT"]),
            "futures_strategy_confidence": round(avg_confidence, 4),
            "futures_strategy_paper_pnl": round(cumulative_pnl, 6),
        },
        "signal_feed": signal_feed,
        "decision_trace": decisions,
        "paper_trades": paper_results,
        "paper_pnl_series": paper_pnl_series,
        "reject_reason_breakdown": [
            {"reason_code": reason, "count": count}
            for reason, count in sorted(reject_reason_map.items(), key=lambda item: item[1], reverse=True)
        ],
        "confidence_distribution": _confidence_distribution(decisions),
    }

    if cache:
        cache.set(f"futures:strategy:status:{user_id}", json.dumps(snapshot))
        cache.set("metrics:futures_strategy_signal_total", str(snapshot["metrics"]["futures_strategy_signal_total"]))
        cache.set("metrics:futures_strategy_allowed_total", str(snapshot["metrics"]["futures_strategy_allowed_total"]))
        cache.set("metrics:futures_strategy_rejected_total", str(snapshot["metrics"]["futures_strategy_rejected_total"]))
        cache.set("metrics:futures_strategy_confidence", str(snapshot["metrics"]["futures_strategy_confidence"]))
        cache.set("metrics:futures_strategy_paper_pnl", str(snapshot["metrics"]["futures_strategy_paper_pnl"]))

    return snapshot


def get_futures_strategy_status(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    if refresh:
        return run_futures_strategy_paper_cycle(db, cache, user_id)

    raw = cache.get(f"futures:strategy:status:{user_id}") if cache else None
    cached = _safe_json(raw, None)
    if cached:
        return cached
    return run_futures_strategy_paper_cycle(db, cache, user_id)
