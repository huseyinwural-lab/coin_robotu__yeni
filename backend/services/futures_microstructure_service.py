import json

from core.futures.microstructure.execution_suitability_evaluator import ExecutionSuitabilityEvaluator
from core.futures.microstructure.liquidity_disappearance_heuristic import LiquidityDisappearanceHeuristic
from core.futures.microstructure.liquidity_vacuum_detector import LiquidityVacuumDetector
from core.futures.microstructure.microstructure_gate import MicrostructureGate
from core.futures.microstructure.microstructure_risk_aggregator import MicrostructureRiskAggregator
from core.futures.microstructure.microstructure_snapshot import build_microstructure_snapshot
from core.futures.microstructure.orderbook_thinning_detector import OrderbookThinningDetector
from core.futures.microstructure.quote_stability_detector import QuoteStabilityDetector
from core.futures.microstructure.slippage_anomaly_estimator import SlippageAnomalyEstimator
from core.futures.microstructure.spread_shock_detector import SpreadShockDetector
from services.execution_microstructure_service import build_microstructure_venue_summary
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
    except Exception:
        return default
    return default


def _risk_rank(level: str) -> int:
    return {
        "SAFE": 0,
        "WARNING": 1,
        "CRITICAL": 2,
        "BLOCKED": 3,
    }.get(level, 0)


def _symbol_microstructure(cache, symbol: str) -> dict:
    ticker_payload = _safe_json(cache.get(f"market:ticker:{symbol}"), {}) if cache else {}
    spread_payload = _safe_json(cache.get(f"market:spread:{symbol}"), {}) if cache else {}
    orderbook_payload = _safe_json(cache.get(f"futures:orderbook:{symbol}"), {}) if cache else {}
    trade_stats_payload = _safe_json(cache.get(f"futures:trade-stats:{symbol}"), {}) if cache else {}
    snapshot = build_microstructure_snapshot(
        symbol=symbol,
        ticker_payload=ticker_payload,
        spread_payload=spread_payload,
        orderbook_payload=orderbook_payload,
        trade_stats_payload=trade_stats_payload,
    )

    baseline_raw = _safe_json(cache.get(f"futures:microstructure:baseline:{symbol}"), {}) if cache else {}
    spread_detector = SpreadShockDetector()
    thinning_detector = OrderbookThinningDetector()
    vacuum_detector = LiquidityVacuumDetector()
    quote_detector = QuoteStabilityDetector()
    slippage_detector = SlippageAnomalyEstimator()
    disappearance_detector = LiquidityDisappearanceHeuristic()
    risk_aggregator = MicrostructureRiskAggregator()
    gate = MicrostructureGate()
    suitability = ExecutionSuitabilityEvaluator()

    spread_result = spread_detector.evaluate(snapshot, baseline_spread_bps=float(baseline_raw.get("spread_bps") or 8.0))
    thinning_result = thinning_detector.evaluate(
        snapshot,
        baseline_depth={
            "bid_depth_top_n": float(baseline_raw.get("bid_depth_top_n") or snapshot.get("bid_depth_top_n") or 1.0),
            "ask_depth_top_n": float(baseline_raw.get("ask_depth_top_n") or snapshot.get("ask_depth_top_n") or 1.0),
        },
    )
    vacuum_result = vacuum_detector.evaluate(snapshot, thinning_result)
    quote_result = quote_detector.evaluate(snapshot)
    slippage_result = slippage_detector.evaluate(snapshot, spread_result, vacuum_result)
    disappearance_result = disappearance_detector.evaluate(snapshot, thinning_result, quote_result)
    aggregate_result = risk_aggregator.aggregate(
        snapshot=snapshot,
        spread_result=spread_result,
        thinning_result=thinning_result,
        vacuum_result=vacuum_result,
        quote_result=quote_result,
        slippage_result=slippage_result,
        disappearance_result=disappearance_result,
    )
    gate_result = gate.evaluate(
        spread_result=spread_result,
        thinning_result=thinning_result,
        vacuum_result=vacuum_result,
        quote_result=quote_result,
        slippage_result=slippage_result,
        aggregate_result=aggregate_result,
        stale_data=bool(snapshot.get("stale_data", False)),
    )
    suitability_result = suitability.evaluate(aggregate_result, gate_result)

    baseline_payload = {
        "spread_bps": round(float(snapshot.get("spread_bps") or 0.0), 4),
        "bid_depth_top_n": round(float(snapshot.get("bid_depth_top_n") or 1.0), 6),
        "ask_depth_top_n": round(float(snapshot.get("ask_depth_top_n") or 1.0), 6),
    }
    if cache:
        cache.set(f"futures:microstructure:baseline:{symbol}", json.dumps(baseline_payload))

    return {
        "symbol": symbol,
        "snapshot": snapshot,
        "spread": spread_result,
        "thinning": thinning_result,
        "vacuum": vacuum_result,
        "quote_stability": quote_result,
        "slippage": slippage_result,
        "liquidity_disappearance": disappearance_result,
        "aggregate": aggregate_result,
        "gate": gate_result,
        "execution_suitability": suitability_result,
    }


def build_microstructure_status(db, cache, user_id: str) -> dict:
    universe = build_effective_universe(db, cache)
    symbols = sorted({symbol.upper() for symbol in (universe.get("futures_symbols") or ["BTCUSDT", "ETHUSDT"])})[:12]
    symbol_rows = [_symbol_microstructure(cache, symbol) for symbol in symbols]

    if not symbol_rows:
        return {
            "portfolio_microstructure_state": "SAFE",
            "portfolio_microstructure_risk_score": 0.0,
            "symbols_at_risk": [],
            "gate_rejections": [],
            "execution_suitability": {
                "execution_suitable": True,
                "severity": "LOW",
                "max_allowed_size_ratio": 1.0,
                "leverage_cap_override": 5,
                "side_risk": "NONE",
            },
            "symbols": [],
            "updated_at": None,
        }

    risk_score = sum(float(item["aggregate"]["microstructure_risk_score"]) for item in symbol_rows) / len(symbol_rows)
    state = max(
        [item["aggregate"]["risk_level"] for item in symbol_rows],
        key=_risk_rank,
    )
    symbols_at_risk = [
        {
            "symbol": item["symbol"],
            "risk_level": item["aggregate"]["risk_level"],
            "risk_score": item["aggregate"]["microstructure_risk_score"],
            "dominant_factor": item["aggregate"]["dominant_factor"],
        }
        for item in symbol_rows
        if item["aggregate"]["risk_level"] in {"WARNING", "CRITICAL", "BLOCKED"}
    ]
    gate_rejections = [
        {
            "symbol": item["symbol"],
            "gate_reason": item["gate"]["gate_reason"],
            "risk_score": item["gate"]["risk_score"],
        }
        for item in symbol_rows
        if not item["gate"]["gate_pass"]
    ]

    suitability_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "BLOCKED": 3}
    execution_suitability = min(
        [item["execution_suitability"] for item in symbol_rows],
        key=lambda row: (
            1 if row["execution_suitable"] else 0,
            -suitability_rank.get(str(row.get("severity") or "LOW").upper(), 0),
            row.get("max_allowed_size_ratio", 1.0),
        ),
    )

    metrics_payload = {
        "futures_microstructure_risk_score": round(risk_score, 4),
        "futures_spread_shock_total": len([item for item in symbol_rows if item["spread"]["spread_state"] == "SHOCK"]),
        "futures_orderbook_thinning_total": len([item for item in symbol_rows if item["thinning"]["thinning_state"] == "CRITICAL"]),
        "futures_liquidity_vacuum_score": round(
            sum(float(item["vacuum"]["vacuum_score"]) for item in symbol_rows) / len(symbol_rows),
            4,
        ),
        "futures_quote_instability_total": len([item for item in symbol_rows if item["quote_stability"]["quote_stability_state"] == "CHAOTIC"]),
        "futures_slippage_anomaly_total": len([item for item in symbol_rows if item["slippage"]["slippage_state"] == "ANOMALY"]),
        "futures_microstructure_gate_rejection_total": len(gate_rejections),
        "futures_execution_suitability_state": execution_suitability.get("severity", "LOW"),
    }
    if cache:
        cache.set("futures:microstructure:metrics", json.dumps(metrics_payload))

    venue_summary = build_microstructure_venue_summary(cache, symbols) if cache else {"tracked_symbols": symbols, "venues": {}}

    return {
        "portfolio_microstructure_state": state,
        "portfolio_microstructure_risk_score": round(risk_score, 4),
        "symbols_at_risk": symbols_at_risk,
        "gate_rejections": gate_rejections,
        "execution_suitability": execution_suitability,
        "symbols": symbol_rows,
        "metrics": metrics_payload,
        "venue_summary": venue_summary,
        "updated_at": symbol_rows[0]["snapshot"]["timestamp"],
    }
