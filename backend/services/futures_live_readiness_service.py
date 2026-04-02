import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from services.audit_service import create_audit_log
from services.pipeline.cache_store import get_json
from core.live.balance_integrity_guard import validate_balance_integrity
from core.live.exchange_latency_guard import evaluate_exchange_latency
from core.live.live_readiness_guard import evaluate_live_readiness_guard
from core.live.order_reconciliation_engine import reconcile_order_state
from core.live.position_sync_engine import reconcile_position_state
from core.live.readiness_score_engine import compute_readiness_score
from core.readiness.go_live_validator import evaluate_go_live_readiness
from core.observability.live_readiness_audit import build_live_readiness_audit_events
from models import ExecutionMetric, PaperPosition, UserExecutionIntent
from services.risk_engine_service import build_admin_risk_status
from services.universe_service import get_full_market_universe
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


def _window_since(hours: int = 24) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=max(int(hours or 24), 1))


def _to_pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((float(part) / float(total)) * 100.0, 4)


def _compute_symbol_integrity_metrics(intents: list[UserExecutionIntent]) -> dict:
    scanner_match_total = 0
    scanner_matches = 0
    failure_intent_ids: set[str] = set()
    symbol_reject_codes = {
        "scanner_execution_symbol_mismatch",
        "invalid_quote_asset",
        "unsupported_quote_asset",
        "quote_asset_mismatch",
        "symbol_required_for_execution_intent",
        "symbol_required_for_execution_order",
    }

    for row in intents:
        row_id = str(row.id or "")
        payload = row.normalized_order_payload or {}
        scanner_snapshot = payload.get("scanner_signal_snapshot") or {}
        order_symbol = str(row.symbol or payload.get("symbol") or "").upper().strip()
        scanner_symbol = str(scanner_snapshot.get("symbol") or "").upper().strip()

        reject_reason_codes = {str(code) for code in (row.reject_reason_codes or [])}
        if reject_reason_codes.intersection(symbol_reject_codes):
            failure_intent_ids.add(row_id)

        is_scanner_source = str(row.source_type or "").lower() == "scanner"
        if not is_scanner_source:
            continue

        if scanner_symbol and order_symbol:
            scanner_match_total += 1
            if scanner_symbol == order_symbol:
                scanner_matches += 1
            else:
                failure_intent_ids.add(row_id)

    scanner_match_pct = _to_pct(scanner_matches, scanner_match_total)
    return {
        "symbol_integrity_failures": len(failure_intent_ids),
        "scanner_to_execution_match_rate_pct": scanner_match_pct,
        "scanner_to_execution_matches": int(scanner_matches),
        "scanner_to_execution_total": int(scanner_match_total),
        "scanner_to_execution_match_rate": f"{scanner_match_pct:.1f}% ({scanner_matches}/{scanner_match_total})",
    }


def _cluster_bias_distribution(db: Session, cache) -> dict[str, float]:
    risk_status = build_admin_risk_status(db, cache)
    rows = risk_status.get("cluster_exposure") or []
    total = sum(float(item.get("exposure_usdt") or 0.0) for item in rows)
    if total <= 0:
        return {}
    return {
        str(item.get("cluster") or "UNCLUSTERED"): round((float(item.get("exposure_usdt") or 0.0) / total) * 100.0, 4)
        for item in rows
    }


def _market_bias_regime(cache) -> str:
    selection = get_json(cache, "spot_strategy:latest_selection") or {}
    value = str(selection.get("market_bias_regime") or selection.get("market_regime") or "UNKNOWN").strip()
    return value or "UNKNOWN"


def _active_universe_count(db: Session, cache) -> int:
    universe = get_full_market_universe(db, cache, scanner_mode="all_market_symbols", selected_symbols=[], top_n=50)
    return int(universe.get("combined_universe_size") or 0)


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
    cached = None
    if cache and not refresh:
        cached = _safe_json(cache.get(cache_key), None)
        if isinstance(cached, dict) and cached.get("go_live_validator"):
            return cached

    validator = evaluate_go_live_readiness(db, cache, user_id=user_id, refresh=refresh)

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

    readiness_guard = evaluate_live_readiness_guard(
        {
            "readiness_state": validator.get("readiness_state"),
            "readiness_confidence_score": validator.get("score"),
        }
    )

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

    recent_intents = (
        db.query(UserExecutionIntent)
        .filter(UserExecutionIntent.created_at >= _window_since(24))
        .order_by(UserExecutionIntent.created_at.desc())
        .limit(2000)
        .all()
    )
    integrity_metrics = _compute_symbol_integrity_metrics(recent_intents)
    cluster_bias_distribution = _cluster_bias_distribution(db, cache)
    market_bias_regime = _market_bias_regime(cache)
    active_universe_count = _active_universe_count(db, cache)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "readiness_score": validator.get("score", 0.0),
        "readiness_state": validator.get("readiness_state", "UNKNOWN"),
        "go_live_allowed": validator.get("go_live_allowed", False),
        "execution_allowed": validator.get("execution_allowed", False),
        "reason_codes": validator.get("reason_codes") or [],
        "summary": validator.get("summary") or {},
        "steps": validator.get("steps") or [],
        "scores": validator.get("scores") or {},
        "by_layer": validator.get("by_layer") or {},
        "blocking_failures": validator.get("blocking_failures") or [],
        "warnings": validator.get("warnings") or [],
        "unknowns": validator.get("unknowns") or [],
        "exchange_readiness": validator.get("exchange_readiness") or {},
        "symbol_readiness": validator.get("symbol_readiness") or {},
        "strategy_readiness": validator.get("strategy_readiness") or {},
        "readiness_matrix": validator.get("readiness_matrix") or {},
        "execution_proof": validator.get("execution_proof") or {},
        "latency_metrics": validator.get("latency_metrics") or {},
        "latency_config": validator.get("latency_config") or {},
        "timeout_policy": validator.get("timeout_policy") or {},
        "data_quality_config": validator.get("data_quality_config") or {},
        "venue_config_checklist": validator.get("venue_config_checklist") or {},
        "adapter_credential_summary": validator.get("adapter_credential_summary") or {},
        "degraded": validator.get("degraded", True),
        "data_freshness": validator.get("data_freshness") or {},
        "execution_mode": validator.get("execution_mode"),
        "required_venues": validator.get("required_venues") or ["binance"],
        "venue_policy": validator.get("venue_policy") or "binance_only",
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
        "symbol_integrity_failures": integrity_metrics["symbol_integrity_failures"],
        "scanner_to_execution_match_rate": integrity_metrics["scanner_to_execution_match_rate"],
        "scanner_to_execution_match_rate_pct": integrity_metrics["scanner_to_execution_match_rate_pct"],
        "scanner_to_execution_matches": integrity_metrics["scanner_to_execution_matches"],
        "scanner_to_execution_total": integrity_metrics["scanner_to_execution_total"],
        "active_universe_count": active_universe_count,
        "cluster_bias_distribution": cluster_bias_distribution,
        "market_bias_regime": market_bias_regime,
        "legacy_readiness_score": score_payload.get("readiness_confidence_score", 0.0),
        "legacy_readiness_state": score_payload.get("readiness_state", "BLOCKED"),
        "go_live_validator": validator,
    }

    if refresh or cached is None:
        create_audit_log(
            db,
            action="GO_LIVE_VALIDATOR_RUN",
            entity_type="futures_live_readiness",
            entity_id=str(user_id),
            actor_user_id=user_id,
            actor_role="system",
            severity="info" if payload.get("readiness_state") == "READY" else "warning",
            details={
                "readiness_state": payload.get("readiness_state"),
                "scores": payload.get("scores"),
                "blocking_failures": payload.get("blocking_failures"),
                "warnings": payload.get("warnings"),
                "unknowns": payload.get("unknowns"),
                "exchange_readiness": payload.get("exchange_readiness"),
                "readiness_matrix": payload.get("readiness_matrix"),
                "execution_proof": payload.get("execution_proof"),
                "latency_metrics": payload.get("latency_metrics"),
                "latency_config": payload.get("latency_config"),
                "timeout_policy": payload.get("timeout_policy"),
                "data_quality_config": payload.get("data_quality_config"),
                "venue_config_checklist": payload.get("venue_config_checklist"),
            },
        )
        db.commit()

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
        "go_live_allowed": payload.get("go_live_allowed", False),
        "execution_allowed": payload.get("execution_allowed", False),
        "reason_codes": payload.get("reason_codes") or [],
        "summary": payload.get("summary") or {},
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

        adjusted.append(item)

    return adjusted, events, readiness
