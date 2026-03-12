import json
from datetime import datetime, timezone
from math import sqrt

from sqlalchemy.orm import Session

from core.observability.tail_risk_audit import build_tail_risk_audit_events
from core.risk.tail_risk.exchange_outage_guard import evaluate_exchange_health
from core.risk.tail_risk.extreme_volatility_guard import detect_extreme_volatility
from core.risk.tail_risk.global_risk_score_engine import compute_global_risk_score
from core.risk.tail_risk.liquidation_cascade_guard import detect_liquidation_cascade
from core.risk.tail_risk.tail_risk_detector import compute_tail_risk_score
from core.risk.tail_risk.tail_risk_order_guard import evaluate_tail_risk_order_guard
from services.futures_capital_service import get_futures_capital_drift
from services.futures_correlation_service import get_futures_cluster_risk
from services.futures_microstructure_service import build_microstructure_status
from services.futures_risk_monitor_service import build_futures_risk_status


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


def _returns(closes: list[float]) -> list[float]:
    output: list[float] = []
    for idx in range(1, len(closes)):
        prev = closes[idx - 1]
        if prev <= 0:
            continue
        output.append((closes[idx] - prev) / prev)
    return output


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((item - mean) ** 2 for item in values) / len(values)
    return sqrt(max(var, 0.0))


def _tail_market_metrics(db: Session, cache, user_id: str) -> dict:
    candles = _safe_json(cache.get("market:candles:BTCUSDT:15m"), []) if cache else []
    closes = [float(item.get("close") or 0.0) for item in candles if float(item.get("close") or 0.0) > 0][-120:]
    fallback_mode = len(closes) < 30
    rets = _returns(closes)

    volatility_pct = _std(rets[-48:]) * 100 if rets else 0.0
    long_volatility_pct = _std(rets[-96:]) * 100 if rets else 0.0
    atr_ratio = (volatility_pct / long_volatility_pct) if long_volatility_pct > 0 else 1.0
    price_delta_pct = ((closes[-1] - closes[-6]) / closes[-6]) * 100 if len(closes) >= 6 and closes[-6] > 0 else 0.0
    rapid_price_drop_pct = ((closes[-1] - closes[-12]) / closes[-12]) * 100 if len(closes) >= 12 and closes[-12] > 0 else 0.0
    volatility_percentile = min(max(volatility_pct / 1.2, 0.0), 1.0)

    risk_status = build_futures_risk_status(db, cache, user_id)
    micro_status = build_microstructure_status(db, cache, user_id)
    liquidation_pressure_input = float(risk_status.get("liquidation_risk_score") or 0.0)
    liquidation_volume_spike = max(1.0, float((risk_status.get("adl_state") or {}).get("portfolio_adl_risk") or 0.0) * 3 + 1)

    spread_state = _safe_json(cache.get("market:spread:BTCUSDT"), {}) if cache else {}
    spread_bps = float(spread_state.get("spread_bps") or 0.0)

    liquidity_depth_score = float((micro_status.get("execution_suitability") or {}).get("market_quality_score") or 0.5)
    funding_rate_anomaly = float((_safe_json(cache.get("market:funding:BTCUSDT"), {}) or {}).get("rate") or 0.0)

    exchange_metrics = {
        "api_latency_ms": float((_safe_json(cache.get("exchange:api:latency"), {}) or {}).get("latency_ms") or 350.0),
        "ack_delay_ms": float((_safe_json(cache.get("exchange:order:ack"), {}) or {}).get("ack_delay_ms") or 400.0),
        "order_reject_rate": float((_safe_json(cache.get("exchange:order:reject-rate"), {}) or {}).get("reject_rate") or 0.05),
        "heartbeat_age_sec": float((_safe_json(cache.get("exchange:heartbeat"), {}) or {}).get("age_sec") or 3.0),
    }

    return {
        "fallback_mode": fallback_mode,
        "volatility_pct": volatility_pct,
        "liquidation_pressure_input": liquidation_pressure_input,
        "liquidity_depth_score": liquidity_depth_score,
        "spread_bps": spread_bps,
        "rapid_price_drop_pct": rapid_price_drop_pct,
        "liquidation_volume_spike": liquidation_volume_spike,
        "funding_rate_anomaly": funding_rate_anomaly,
        "atr_ratio": atr_ratio,
        "price_delta_pct": price_delta_pct,
        "volatility_percentile": volatility_percentile,
        **exchange_metrics,
    }


def get_futures_tail_risk(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    cache_key = f"futures:tail-risk:snapshot:{user_id}"
    if cache and not refresh:
        cached = _safe_json(cache.get(cache_key), None)
        if isinstance(cached, dict):
            return cached

    metrics = _tail_market_metrics(db, cache, user_id)
    detector = compute_tail_risk_score(metrics)
    cascade = detect_liquidation_cascade(metrics)
    volatility = detect_extreme_volatility(metrics)
    exchange = evaluate_exchange_health(metrics)

    alerts = [item for item in [cascade.get("event"), volatility.get("event"), exchange.get("event")] if item]
    risk_state = "NORMAL"
    if detector.get("tail_risk_score", 0) > 80 or exchange.get("active"):
        risk_state = "HIGH"
    elif detector.get("tail_risk_score", 0) > 60 or cascade.get("active") or volatility.get("active"):
        risk_state = "ELEVATED"

    history = _safe_json(cache.get(f"futures:tail-risk:history:{user_id}"), []) if cache else []
    history.append({"ts": datetime.now(timezone.utc).isoformat(), "tail_risk_score": detector.get("tail_risk_score", 0.0)})
    history = history[-120:]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tail_risk_score": detector.get("tail_risk_score", 0.0),
        "risk_state": risk_state,
        "active_alerts": alerts,
        "volatility_score": detector.get("volatility_score", 0.0),
        "liquidation_pressure": detector.get("liquidation_pressure", 0.0),
        "liquidity_score": detector.get("liquidity_score", 0.0),
        "spread_anomaly": detector.get("spread_anomaly", 0.0),
        "liquidation_cascade": cascade,
        "extreme_volatility": volatility,
        "exchange_health": exchange,
        "tail_risk_history": history,
    }
    if cache:
        cache.set(cache_key, json.dumps(payload))
        cache.set(f"futures:tail-risk:history:{user_id}", json.dumps(history))
    return payload


def get_futures_global_risk(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    tail_payload = get_futures_tail_risk(db, cache, user_id, refresh=refresh)
    strategy_status = _safe_json(cache.get(f"futures:strategy:status:{user_id}"), {}) if cache else {}
    health_rows = strategy_status.get("strategy_health_score") or []
    avg_health_score = (
        sum(float(item.get("strategy_health_score") or 0.0) for item in health_rows) / len(health_rows)
        if health_rows
        else 50.0
    )

    cluster_state = str((get_futures_cluster_risk(db, cache, user_id, refresh=False) or {}).get("risk_state") or "NORMAL")
    capital_state = str((get_futures_capital_drift(db, cache, user_id, refresh=False) or {}).get("drift_state") or "NORMAL")

    global_payload = compute_global_risk_score(
        strategy_health_score=avg_health_score,
        cluster_risk_state=cluster_state,
        capital_drift_state=capital_state,
        tail_risk_score=float(tail_payload.get("tail_risk_score") or 0.0),
        weights={
            "strategy": 0.25,
            "cluster": 0.25,
            "capital": 0.20,
            "tail_risk": 0.30,
        },
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tail_risk_score": tail_payload.get("tail_risk_score", 0.0),
        "global_risk_score": global_payload.get("global_risk_score", 0.0),
        "risk_state": global_payload.get("risk_state", "NORMAL"),
        "active_alerts": [*(tail_payload.get("active_alerts") or []), *(global_payload.get("active_events") or [])],
        "components": global_payload.get("components") or {},
        "weights": global_payload.get("weights") or {},
    }
    if cache:
        cache.set(f"futures:tail-risk:global:{user_id}", json.dumps(payload))
    return payload


def apply_tail_risk_order_guard_to_decisions(db: Session, cache, user_id: str, decisions: list[dict]) -> tuple[list[dict], list[dict], dict]:
    tail_payload = get_futures_tail_risk(db, cache, user_id, refresh=False)
    global_payload = get_futures_global_risk(db, cache, user_id, refresh=False)

    events: list[dict] = []
    adjusted: list[dict] = []
    for row in decisions:
        item = {**row}
        if item.get("decision") != "ALLOW":
            adjusted.append(item)
            continue

        guard = evaluate_tail_risk_order_guard(
            strategy_id=str(item.get("strategy") or "unknown"),
            global_risk_score=float(global_payload.get("global_risk_score") or 0.0),
            risk_state=str(global_payload.get("risk_state") or "NORMAL"),
            active_alerts=global_payload.get("active_alerts") or [],
        )

        if guard.get("action") == "REJECT":
            item["decision"] = "REJECT"
            item["decision_layer"] = "TAIL_RISK"
            item["reason_code"] = "GATE_REJECT"
            item["reasons"] = sorted(set((item.get("reasons") or []) + ["TAIL_RISK_TRADE_REJECTED"]))
            if guard.get("event"):
                events.append(guard["event"])
        elif guard.get("action") == "REDUCE_SIZE":
            leverage_decision = {**(item.get("leverage_decision") or {})}
            old_size = float(leverage_decision.get("position_size_ratio") or 1.0)
            leverage_decision["position_size_ratio"] = round(max(0.05, old_size * float(guard.get("size_multiplier") or 1.0)), 4)
            item["leverage_decision"] = leverage_decision
            item["reasons"] = sorted(set((item.get("reasons") or []) + ["TAIL_RISK_SIZE_REDUCED"]))

        adjusted.append(item)

    audit_events = build_tail_risk_audit_events(
        tail_risk_score=float(tail_payload.get("tail_risk_score") or 0.0),
        detector_events=tail_payload.get("active_alerts") or [],
        global_events=global_payload.get("active_alerts") or [],
        order_events=events,
        affected_symbols=sorted({str(item.get("symbol") or "") for item in decisions if item.get("symbol")}),
    )
    if cache:
        cache.set(f"futures:tail-risk:audit:{user_id}", json.dumps(audit_events[-300:]))

    merged_payload = {**global_payload, "tail_risk": tail_payload, "tail_risk_audit_events": audit_events}
    return adjusted, events, merged_payload
