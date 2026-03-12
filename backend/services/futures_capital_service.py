import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.observability.capital_governance_audit import build_capital_governance_audit_events
from core.risk.capital.capital_drift_detector import detect_capital_drift
from core.risk.capital.capital_order_guard import evaluate_capital_order_guard
from core.risk.capital.capital_risk_governor import enforce_capital_risk
from core.risk.capital.portfolio_capital_registry import build_portfolio_capital_registry
from core.risk.capital.position_size_policy import apply_position_size_policy
from core.risk.capital.strategy_capital_allocator import allocate_strategy_capital
from core.strategies.strategy_registry import build_strategy_registry
from models import PaperPosition
from services.futures_correlation_service import get_futures_cluster_risk
from services.pipeline.position_sizing_engine import compute_position_sizing


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


def _portfolio_equity(db: Session, cache, user_id: str) -> float:
    ticker_raw = _safe_json(cache.get("market:ticker:BTCUSDT"), {}) if cache else {}
    mark = float((ticker_raw or {}).get("last_price") or 100.0)
    sizing = compute_position_sizing(db, user_id, mark)
    return float(sizing.get("equity") or 10000.0)


def _strategy_usage_from_status(cache, user_id: str, equity: float) -> dict[str, float]:
    status = _safe_json(cache.get(f"futures:strategy:status:{user_id}"), {}) if cache else {}
    usage: dict[str, float] = {}
    for row in status.get("decision_trace") or []:
        if row.get("decision") != "ALLOW":
            continue
        strategy = str(row.get("strategy") or "unknown")
        leverage = float((row.get("leverage_decision") or {}).get("final_leverage") or 1.0)
        size_ratio = float((row.get("leverage_decision") or {}).get("position_size_ratio") or 1.0)
        notional = equity * 0.08 * leverage * max(0.1, min(size_ratio, 1.0))
        usage[strategy] = round(usage.get(strategy, 0.0) + notional, 4)
    return usage


def _used_margin(db: Session, user_id: str) -> float:
    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.market_type == "futures", PaperPosition.status == "open")
        .all()
    )
    margin = 0.0
    for row in rows:
        notional = abs(float(row.entry_price) * float(row.quantity))
        leverage = max(float(row.leverage or 1.0), 1.0)
        margin += notional / leverage
    return margin


def get_futures_capital_snapshot(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    cache_key = f"futures:capital:snapshot:{user_id}"
    if cache and not refresh:
        cached = _safe_json(cache.get(cache_key), None)
        if isinstance(cached, dict):
            return cached

    equity = _portfolio_equity(db, cache, user_id)
    strategy_ids = sorted(build_strategy_registry().keys())
    usage_by_strategy = _strategy_usage_from_status(cache, user_id, equity)
    total_allocated = equity * min(1.0, len(strategy_ids) * 0.20)
    portfolio_registry = build_portfolio_capital_registry(
        portfolio_equity=equity,
        used_margin=_used_margin(db, user_id),
        allocated_capital=total_allocated,
        risk_budget_ratio=0.8,
    )

    allocation = allocate_strategy_capital(
        strategy_ids=strategy_ids,
        portfolio_equity=equity,
        capital_usage_by_strategy=usage_by_strategy,
        max_strategy_capital_ratio=0.20,
        soft_warning_ratio=0.15,
    )
    previous_usage = _safe_json(cache.get(f"futures:capital:usage-prev:{user_id}"), {}) if cache else {}
    drift = detect_capital_drift(allocation.get("strategy_allocation") or [], previous_usage=previous_usage)
    governor = enforce_capital_risk(allocation.get("strategy_allocation") or [], drift.get("capital_drift_events") or [])

    cluster_payload = get_futures_cluster_risk(db, cache, user_id, refresh=False)
    capital_reject_events = _safe_json(cache.get(f"futures:capital:order-events:{user_id}"), []) if cache else []
    audit_events = build_capital_governance_audit_events(
        capital_limit_events=governor.get("capital_limit_events") or [],
        capital_drift_events=drift.get("capital_drift_events") or [],
        capital_trade_reject_events=capital_reject_events,
        capital_reallocation_rows=[
            {
                **row,
                "portfolio_equity": equity,
            }
            for row in (allocation.get("strategy_allocation") or [])
        ],
    )

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio_capital_registry": portfolio_registry,
        "strategy_capital_budget": allocation.get("strategy_allocation") or [],
        "strategy_capital_usage": [
            {
                "strategy_id": row.get("strategy_id"),
                "capital_used": row.get("strategy_capital_used", 0.0),
                "capital_remaining": row.get("strategy_capital_available", 0.0),
                "risk_state": row.get("risk_state", "NORMAL"),
            }
            for row in (allocation.get("strategy_allocation") or [])
        ],
        "capital_drift": drift,
        "capital_risk_actions": governor.get("capital_risk_actions") or [],
        "capital_limit_events": governor.get("capital_limit_events") or [],
        "capital_governance_audit_events": audit_events,
        "cluster_risk_state": cluster_payload.get("risk_state", "NORMAL"),
        "cluster_risk_alerts": cluster_payload.get("cluster_risk_alerts") or [],
    }

    if cache:
        cache.set(cache_key, json.dumps(snapshot))
        cache.set(f"futures:capital:usage-prev:{user_id}", json.dumps(usage_by_strategy))
        cache.set(f"futures:capital:audit:{user_id}", json.dumps(audit_events[-250:]))
    return snapshot


def apply_capital_order_guard_to_decisions(db: Session, cache, user_id: str, decisions: list[dict]) -> tuple[list[dict], list[dict], dict]:
    snapshot = get_futures_capital_snapshot(db, cache, user_id, refresh=False)
    registry = snapshot.get("portfolio_capital_registry") or {}
    budget_rows = snapshot.get("strategy_capital_budget") or []
    budget_map = {str(item.get("strategy_id")): {**item} for item in budget_rows}
    cluster_state = str(snapshot.get("cluster_risk_state") or "NORMAL")

    order_events: list[dict] = []
    adjusted: list[dict] = []
    for row in decisions:
        item = {**row}
        if item.get("decision") != "ALLOW":
            adjusted.append(item)
            continue

        strategy_id = str(item.get("strategy") or item.get("strategy_id") or "unknown")
        budget_row = budget_map.get(strategy_id) or {
            "strategy_id": strategy_id,
            "strategy_capital_budget": float(registry.get("risk_budget_total") or 0.0) * 0.2,
            "strategy_capital_used": 0.0,
            "strategy_capital_available": float(registry.get("available_capital") or 0.0),
            "warning_threshold": float(registry.get("risk_budget_total") or 0.0) * 0.15,
        }

        leverage = float((item.get("leverage_decision") or {}).get("final_leverage") or 1.0)
        size_ratio = float((item.get("leverage_decision") or {}).get("position_size_ratio") or 1.0)
        projected_order_notional = float(registry.get("portfolio_equity") or 10000.0) * 0.08 * leverage * max(0.1, min(size_ratio, 1.0))

        guard = evaluate_capital_order_guard(
            strategy_id=strategy_id,
            projected_order_notional=projected_order_notional,
            strategy_budget_row=budget_row,
            portfolio_registry=registry,
            cluster_risk_state=cluster_state,
        )

        if guard.get("action") == "REJECT":
            item["decision"] = "REJECT"
            item["decision_layer"] = "CAPITAL_RISK"
            item["reason_code"] = "GATE_REJECT"
            item["reasons"] = sorted(set((item.get("reasons") or []) + ["CAPITAL_TRADE_REJECTED"]))
            if guard.get("event"):
                order_events.append({**guard["event"], "portfolio_equity": registry.get("portfolio_equity", 0.0)})
            adjusted.append(item)
            continue

        risk_weight = 0.7 if guard.get("action") == "REDUCE_SIZE" else 1.0
        volatility_modifier = 0.8 if str((item.get("signal") or {}).get("regime") or "").upper() == "HIGH_VOL" else 1.0
        cluster_modifier = 0.8 if cluster_state == "ALERT" else 1.0
        policy = apply_position_size_policy(
            strategy_capital_available=budget_row.get("strategy_capital_available", 0.0),
            strategy_capital_budget=budget_row.get("strategy_capital_budget", 1.0),
            base_position_size_ratio=size_ratio,
            strategy_risk_weight=risk_weight,
            market_volatility_modifier=volatility_modifier,
            cluster_risk_modifier=cluster_modifier,
        )

        leverage_decision = {**(item.get("leverage_decision") or {})}
        adjusted_ratio = min(float(policy.get("adjusted_position_size_ratio") or size_ratio), size_ratio)
        if guard.get("action") == "REDUCE_SIZE":
            adjusted_ratio = min(adjusted_ratio, size_ratio * float(guard.get("size_multiplier") or 1.0))
        leverage_decision["position_size_ratio"] = round(max(0.05, adjusted_ratio), 4)
        item["leverage_decision"] = leverage_decision
        if adjusted_ratio < size_ratio:
            item["reasons"] = sorted(set((item.get("reasons") or []) + ["CAPITAL_SIZE_REDUCED"]))

        budget_row["strategy_capital_used"] = round(float(budget_row.get("strategy_capital_used") or 0.0) + projected_order_notional, 4)
        budget_row["strategy_capital_available"] = round(
            max(float(budget_row.get("strategy_capital_budget") or 0.0) - float(budget_row.get("strategy_capital_used") or 0.0), 0.0),
            4,
        )
        budget_map[strategy_id] = budget_row
        adjusted.append(item)

    if cache:
        cache.set(f"futures:capital:order-events:{user_id}", json.dumps(order_events[-250:]))
    return adjusted, order_events, snapshot


def get_futures_capital_budget(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    snapshot = get_futures_capital_snapshot(db, cache, user_id, refresh=refresh)
    return {
        "generated_at": snapshot.get("generated_at"),
        "portfolio_capital_registry": snapshot.get("portfolio_capital_registry") or {},
        "strategy_capital_budget": snapshot.get("strategy_capital_budget") or [],
    }


def get_futures_capital_usage(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    snapshot = get_futures_capital_snapshot(db, cache, user_id, refresh=refresh)
    return {
        "generated_at": snapshot.get("generated_at"),
        "strategy_capital_usage": snapshot.get("strategy_capital_usage") or [],
        "portfolio_risk_budget": (snapshot.get("portfolio_capital_registry") or {}).get("risk_budget_total", 0.0),
        "capital_risk_actions": snapshot.get("capital_risk_actions") or [],
    }


def get_futures_capital_drift(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    snapshot = get_futures_capital_snapshot(db, cache, user_id, refresh=refresh)
    drift = snapshot.get("capital_drift") or {}
    return {
        "generated_at": snapshot.get("generated_at"),
        "drift_state": "ALERT" if len(drift.get("capital_drift_events") or []) > 0 else "NORMAL",
        "capital_drift_events": drift.get("capital_drift_events") or [],
        "capital_drift_by_strategy": drift.get("capital_drift_by_strategy") or {},
        "capital_governance_audit_events": snapshot.get("capital_governance_audit_events") or [],
    }
