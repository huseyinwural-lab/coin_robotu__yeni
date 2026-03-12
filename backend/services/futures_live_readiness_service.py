import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.live.balance_integrity_guard import validate_balance_integrity
from core.live.exchange_latency_guard import evaluate_exchange_latency
from core.live.live_readiness_guard import evaluate_live_readiness_guard
from core.live.order_reconciliation_engine import reconcile_order_state
from core.live.position_sync_engine import reconcile_position_state
from core.live.readiness_score_engine import compute_readiness_score
from core.observability.live_readiness_audit import build_live_readiness_audit_events
from models import ExecutionMetric, PaperPosition
from services.pipeline.position_sizing_engine import compute_position_sizing


def _safe_json(raw, default):
    if not raw:
        return default
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        if isinstance(raw, str):
            return json.loads(raw)
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return raw
    except Exception:
        return default
    return default


def _engine_positions(db: Session, user_id: str) -> list[dict]:
    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.market_type == "futures", PaperPosition.status == "open")
        .all()
    )
    output: list[dict] = []
    for row in rows:
        output.append(
            {
                "symbol": row.symbol,
                "position_size": float(row.quantity),
                "entry_price": float(row.entry_price),
                "leverage": float(row.leverage or 1.0),
                "unrealized_pnl": float(row.unrealized_pnl or 0.0),
            }
        )
    return output


def _engine_orders(db: Session, user_id: str) -> list[dict]:
    rows = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.user_id == user_id, ExecutionMetric.market_type == "futures")
        .order_by(ExecutionMetric.created_at.desc())
        .limit(200)
        .all()
    )
    output: list[dict] = []
    for row in rows:
        output.append(
            {
                "order_id": row.order_id,
                "symbol": row.symbol,
                "side": row.side,
                "price": float(row.price_avg or row.mid_price),
                "quantity": float(row.executed_qty or row.quote_qty),
                "status": row.final_status,
            }
        )
    return output


def _engine_balance(db: Session, cache, user_id: str) -> dict:
    ticker_raw = _safe_json(cache.get("market:ticker:BTCUSDT"), {}) if cache else {}
    mark = float((ticker_raw or {}).get("last_price") or 100.0)
    sizing = compute_position_sizing(db, user_id, mark)

    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.market_type == "futures", PaperPosition.status == "open")
        .all()
    )
    used_margin = 0.0
    for row in rows:
        notional = abs(float(row.entry_price) * float(row.quantity))
        leverage = max(float(row.leverage or 1.0), 1.0)
        used_margin += notional / leverage

    equity = float(sizing.get("equity") or 10000.0)
    return {
        "wallet_balance": equity,
        "available_balance": max(equity - used_margin, 0.0),
        "used_margin": used_margin,
    }


def get_futures_live_readiness(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    cache_key = f"futures:live-readiness:{user_id}"
    if cache and not refresh:
        cached = _safe_json(cache.get(cache_key), None)
        if isinstance(cached, dict):
            return cached

    engine_positions = _engine_positions(db, user_id)
    exchange_positions = _safe_json(cache.get("exchange:futures:positions"), []) if cache else []
    position_sync = reconcile_position_state(engine_positions, exchange_positions)

    engine_orders = _engine_orders(db, user_id)
    exchange_orders = _safe_json(cache.get("exchange:futures:orders"), []) if cache else []
    order_reconciliation = reconcile_order_state(engine_orders, exchange_orders)

    engine_balance = _engine_balance(db, cache, user_id)
    exchange_balance = _safe_json(cache.get("exchange:futures:balance"), {}) if cache else {}
    balance_integrity = validate_balance_integrity(engine_balance, exchange_balance)

    latency = evaluate_exchange_latency(
        {
            "order_ack_latency": float((_safe_json(cache.get("exchange:order:ack"), {}) or {}).get("ack_delay_ms") or 350),
            "api_response_latency": float((_safe_json(cache.get("exchange:api:latency"), {}) or {}).get("latency_ms") or 280),
            "websocket_delay": float((_safe_json(cache.get("exchange:websocket:delay"), {}) or {}).get("delay_ms") or 90),
            "heartbeat_gap": float((_safe_json(cache.get("exchange:heartbeat"), {}) or {}).get("age_sec") or 2),
        }
    )

    score_payload = compute_readiness_score(
        position_sync_state=position_sync.get("position_sync_state", "UNVERIFIED"),
        order_reconciliation_state=order_reconciliation.get("order_reconciliation_state", "UNVERIFIED"),
        balance_integrity_state=balance_integrity.get("balance_integrity_state", "UNVERIFIED"),
        exchange_latency_state=latency.get("exchange_latency_state", "ELEVATED"),
    )
    readiness_guard = evaluate_live_readiness_guard(score_payload)

    alerts = [
        item
        for item in [
            position_sync.get("event"),
            order_reconciliation.get("event"),
            balance_integrity.get("event"),
            latency.get("event"),
            score_payload.get("event"),
            readiness_guard.get("event"),
        ]
        if item
    ]
    audit_events = build_live_readiness_audit_events(
        position_event=position_sync.get("event"),
        order_event=order_reconciliation.get("event"),
        balance_event=balance_integrity.get("event"),
        latency_event=latency.get("event"),
        readiness_event=score_payload.get("event"),
        readiness_block_event=readiness_guard.get("event"),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "readiness_score": score_payload.get("readiness_confidence_score", 0.0),
        "readiness_state": score_payload.get("readiness_state", "BLOCKED"),
        "position_sync_state": position_sync.get("position_sync_state", "UNVERIFIED"),
        "order_reconciliation_state": order_reconciliation.get("order_reconciliation_state", "UNVERIFIED"),
        "balance_integrity_state": balance_integrity.get("balance_integrity_state", "UNVERIFIED"),
        "exchange_latency_state": latency.get("exchange_latency_state", "ELEVATED"),
        "alerts": alerts,
        "position_sync": position_sync,
        "order_reconciliation": order_reconciliation,
        "balance_integrity": balance_integrity,
        "exchange_latency": latency,
        "readiness_components": score_payload.get("component_scores") or {},
        "readiness_weights": score_payload.get("weights") or {},
        "readiness_guard": readiness_guard,
        "audit_events": audit_events,
    }

    if cache:
        cache.set(cache_key, json.dumps(payload))
        cache.set(f"futures:live-readiness:audit:{user_id}", json.dumps(audit_events[-250:]))
    return payload


def get_futures_readiness_score(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    payload = get_futures_live_readiness(db, cache, user_id, refresh=refresh)
    return {
        "generated_at": payload.get("generated_at"),
        "readiness_score": payload.get("readiness_score", 0.0),
        "readiness_state": payload.get("readiness_state", "BLOCKED"),
        "position_sync_state": payload.get("position_sync_state", "UNVERIFIED"),
        "order_reconciliation_state": payload.get("order_reconciliation_state", "UNVERIFIED"),
        "balance_integrity_state": payload.get("balance_integrity_state", "UNVERIFIED"),
        "exchange_latency_state": payload.get("exchange_latency_state", "ELEVATED"),
        "alerts": payload.get("alerts") or [],
    }


def apply_live_readiness_guard_to_decisions(db: Session, cache, user_id: str, decisions: list[dict]) -> tuple[list[dict], list[dict], dict]:
    readiness = get_futures_live_readiness(db, cache, user_id, refresh=False)
    guard = readiness.get("readiness_guard") or {}
    action = str(guard.get("action") or "ALLOW")
    size_multiplier = float(guard.get("size_multiplier") or 1.0)

    events: list[dict] = []
    adjusted: list[dict] = []
    for row in decisions:
        item = {**row}
        if item.get("decision") != "ALLOW":
            adjusted.append(item)
            continue

        if action == "BLOCK":
            item["decision"] = "REJECT"
            item["decision_layer"] = "LIVE_READINESS"
            item["reason_code"] = "GATE_REJECT"
            item["reasons"] = sorted(set((item.get("reasons") or []) + ["LIVE_READINESS_BLOCK"]))
            if guard.get("event"):
                events.append(guard["event"])
        elif action == "DOWNSHIFT":
            leverage_decision = {**(item.get("leverage_decision") or {})}
            old_ratio = float(leverage_decision.get("position_size_ratio") or 1.0)
            leverage_decision["position_size_ratio"] = round(max(0.05, old_ratio * size_multiplier), 4)
            item["leverage_decision"] = leverage_decision
            item["reasons"] = sorted(set((item.get("reasons") or []) + ["LIVE_READINESS_DOWNSHIFT"]))

        adjusted.append(item)

    return adjusted, events, readiness
