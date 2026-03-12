import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.observability.cluster_governance_audit import build_cluster_governance_audit_events
from core.risk.correlation.cluster_exposure_calculator import calculate_cluster_exposure
from core.risk.correlation.cluster_order_guard import evaluate_cluster_order_guard
from core.risk.correlation.cluster_risk_governor import evaluate_cluster_risk
from core.risk.correlation.correlation_cluster_builder import build_correlation_clusters
from core.risk.correlation.correlation_matrix_engine import build_correlation_matrix
from models import PaperPosition
from services.pipeline.position_sizing_engine import compute_position_sizing


DEFAULT_CLUSTER_SYMBOLS = ["BTC", "ETH", "SOL", "AVAX", "BNB", "LINK", "MATIC", "ARB"]


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


def _symbol_label(symbol: str) -> str:
    value = str(symbol or "").upper()
    return value[:-4] if value.endswith("USDT") else value


def _active_symbol_set(symbols: list[str] | None) -> list[str]:
    pool = symbols or DEFAULT_CLUSTER_SYMBOLS
    normalized = sorted({_symbol_label(symbol) for symbol in pool if symbol})
    return normalized or list(DEFAULT_CLUSTER_SYMBOLS)


def _portfolio_equity(db: Session, cache, user_id: str) -> float:
    ticker_raw = _safe_json(cache.get("market:ticker:BTCUSDT"), {}) if cache else {}
    mark = float((ticker_raw or {}).get("last_price") or 100.0)
    sizing = compute_position_sizing(db, user_id, mark)
    return float(sizing.get("equity") or 10000.0)


def _load_open_positions(db: Session, user_id: str) -> list[dict]:
    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.market_type == "futures", PaperPosition.status == "open")
        .all()
    )
    positions: list[dict] = []
    for row in rows:
        notional = abs(float(row.entry_price) * float(row.quantity))
        positions.append(
            {
                "symbol": row.symbol,
                "side": str(row.side).upper(),
                "position_notional": round(notional, 4),
                "leverage": float(row.leverage or 1),
                "source": "OPEN_POSITION",
            }
        )
    return positions


def _load_projected_positions(cache, user_id: str, equity: float) -> list[dict]:
    status = _safe_json(cache.get(f"futures:strategy:status:{user_id}"), {}) if cache else {}
    decisions = status.get("decision_trace") or []
    projected: list[dict] = []
    for row in decisions:
        if row.get("decision") != "ALLOW":
            continue
        leverage = float((row.get("leverage_decision") or {}).get("final_leverage") or 1.0)
        size_ratio = float((row.get("leverage_decision") or {}).get("position_size_ratio") or 1.0)
        notional = equity * 0.08 * leverage * max(0.1, min(size_ratio, 1.0))
        projected.append(
            {
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "position_notional": round(notional, 4),
                "leverage": leverage,
                "source": "PROJECTED_SIGNAL",
                "strategy": row.get("strategy"),
            }
        )
    return projected


def get_futures_correlation_matrix(cache, symbols: list[str] | None = None, refresh: bool = False) -> dict:
    universe = _active_symbol_set(symbols)
    matrix_payload = build_correlation_matrix(
        cache,
        universe,
        timeframe="15m",
        window=96,
        cache_ttl_seconds=60,
        refresh=refresh,
    )
    matrix_payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    return matrix_payload


def get_futures_correlation_clusters(cache, symbols: list[str] | None = None, refresh: bool = False) -> dict:
    matrix_payload = get_futures_correlation_matrix(cache, symbols=symbols, refresh=refresh)
    clusters = build_correlation_clusters(matrix_payload, threshold=0.75)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timeframe": matrix_payload.get("timeframe"),
        "window": matrix_payload.get("window"),
        "symbols": matrix_payload.get("symbols") or [],
        "correlation_clusters": clusters.get("correlation_clusters") or [],
        "threshold": clusters.get("threshold", 0.75),
    }


def get_futures_cluster_risk(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    matrix_payload = get_futures_correlation_matrix(cache, refresh=refresh)
    clusters_payload = get_futures_correlation_clusters(cache, refresh=refresh)

    equity = _portfolio_equity(db, cache, user_id)
    open_positions = _load_open_positions(db, user_id)
    projected_positions = _load_projected_positions(cache, user_id, equity)
    merged_positions = [*open_positions, *projected_positions]

    exposure_payload = calculate_cluster_exposure(
        clusters=clusters_payload.get("correlation_clusters") or [],
        positions=merged_positions,
        portfolio_equity=equity,
    )
    risk_payload = evaluate_cluster_risk(
        cluster_exposures=exposure_payload.get("cluster_exposures") or [],
        cluster_exposure_limit=0.35,
        cluster_position_limit=3,
        cluster_direction_limit=0.85,
    )

    order_events: list[dict] = []
    for position in projected_positions:
        decision = evaluate_cluster_order_guard(
            order=position,
            clusters=clusters_payload.get("correlation_clusters") or [],
            cluster_exposures=risk_payload.get("cluster_exposures") or [],
            portfolio_equity=equity,
            cluster_exposure_limit=0.35,
        )
        if decision.get("event"):
            order_events.append(decision["event"])

    audit_events = build_cluster_governance_audit_events(
        matrix_payload=matrix_payload,
        clusters_payload=clusters_payload,
        risk_payload=risk_payload,
        order_events=order_events,
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cluster_id_count": len(clusters_payload.get("correlation_clusters") or []),
        "symbols": matrix_payload.get("symbols") or [],
        "correlation_matrix": matrix_payload.get("correlation_matrix") or {},
        "correlation_clusters": clusters_payload.get("correlation_clusters") or [],
        "cluster_exposures": risk_payload.get("cluster_exposures") or [],
        "cluster_risk_alerts": risk_payload.get("cluster_risk_alerts") or [],
        "risk_state": risk_payload.get("risk_state", "NORMAL"),
        "cluster_limits": risk_payload.get("cluster_limits") or {},
        "order_guard_events": order_events,
        "governance_audit_events": audit_events,
        "portfolio_equity": exposure_payload.get("portfolio_equity", equity),
    }

    if cache:
        cache.set(f"futures:correlation:cluster-risk:{user_id}", json.dumps(payload))
    return payload


def apply_cluster_order_guard_to_decisions(db: Session, cache, user_id: str, decisions: list[dict]) -> tuple[list[dict], list[dict]]:
    get_futures_correlation_matrix(cache)
    clusters_payload = get_futures_correlation_clusters(cache)
    equity = _portfolio_equity(db, cache, user_id)
    open_positions = _load_open_positions(db, user_id)
    exposure_payload = calculate_cluster_exposure(
        clusters=clusters_payload.get("correlation_clusters") or [],
        positions=open_positions,
        portfolio_equity=equity,
    )
    running_exposures = [*exposure_payload.get("cluster_exposures")]

    events: list[dict] = []
    adjusted: list[dict] = []
    for row in decisions:
        item = {**row}
        if item.get("decision") != "ALLOW":
            adjusted.append(item)
            continue

        leverage = float((item.get("leverage_decision") or {}).get("final_leverage") or 1.0)
        size_ratio = float((item.get("leverage_decision") or {}).get("position_size_ratio") or 1.0)
        order_notional = equity * 0.08 * leverage * max(0.1, min(size_ratio, 1.0))
        decision = evaluate_cluster_order_guard(
            order={
                "symbol": item.get("symbol"),
                "side": item.get("side"),
                "position_notional": order_notional,
                "position_size_ratio": size_ratio,
            },
            clusters=clusters_payload.get("correlation_clusters") or [],
            cluster_exposures=running_exposures,
            portfolio_equity=equity,
            cluster_exposure_limit=0.35,
        )

        action = decision.get("action")
        if action == "REJECT":
            item["decision"] = "REJECT"
            item["decision_layer"] = "CORRELATION_RISK"
            item["reason_code"] = "GATE_REJECT"
            item["reasons"] = sorted(set((item.get("reasons") or []) + ["CLUSTER_TRADE_REJECTED"]))
            if decision.get("event"):
                events.append(decision["event"])
        elif action == "REDUCE_SIZE":
            leverage_decision = {**(item.get("leverage_decision") or {})}
            leverage_decision["position_size_ratio"] = float(decision.get("adjusted_position_size_ratio") or size_ratio)
            item["leverage_decision"] = leverage_decision
            item["reasons"] = sorted(set((item.get("reasons") or []) + ["CLUSTER_POSITION_SIZE_REDUCED"]))

        if item.get("decision") == "ALLOW":
            symbol = _symbol_label(item.get("symbol"))
            for exposure in running_exposures:
                if symbol in set(exposure.get("symbols") or []):
                    exposure["cluster_exposure_notional"] = round(
                        float(exposure.get("cluster_exposure_notional") or 0.0) + order_notional,
                        4,
                    )
                    exposure["cluster_exposure"] = round(
                        float(exposure.get("cluster_exposure_notional") or 0.0) / max(equity, 1.0),
                        6,
                    )
                    exposure["cluster_position_count"] = int(exposure.get("cluster_position_count") or 0) + 1
                    break

        adjusted.append(item)

    if cache and events:
        cache.set(f"futures:correlation:order-events:{user_id}", json.dumps(events[-200:]))

    return adjusted, events
