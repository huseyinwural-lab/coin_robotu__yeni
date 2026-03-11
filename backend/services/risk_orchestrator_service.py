from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from models import AdminControl, ExecutionIntent, ExecutionIntentEvent, RiskOrchestratorPolicy
from services.runtime_execution_service import map_decision_to_intent
from services.system_alert_service import create_system_alert


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_policy(db: Session) -> RiskOrchestratorPolicy:
    policy = db.query(RiskOrchestratorPolicy).filter(RiskOrchestratorPolicy.id == "global").first()
    if policy is not None:
        return policy

    policy = RiskOrchestratorPolicy(id="global")
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def update_policy(db: Session, *, payload: dict) -> RiskOrchestratorPolicy:
    policy = get_or_create_policy(db)
    policy.reference_equity_usd = float(payload.get("reference_equity_usd", policy.reference_equity_usd))
    policy.account_max_notional_pct = float(payload.get("account_max_notional_pct", policy.account_max_notional_pct))
    policy.symbol_max_notional_pct = float(payload.get("symbol_max_notional_pct", policy.symbol_max_notional_pct))
    policy.strategy_max_concurrent_positions = int(
        payload.get("strategy_max_concurrent_positions", policy.strategy_max_concurrent_positions)
    )
    policy.strategy_cooldown_seconds = int(payload.get("strategy_cooldown_seconds", policy.strategy_cooldown_seconds))
    policy.max_order_frequency_per_min = int(payload.get("max_order_frequency_per_min", policy.max_order_frequency_per_min))
    policy.max_order_burst_per_10s = int(payload.get("max_order_burst_per_10s", policy.max_order_burst_per_10s))
    policy.daily_loss_limit_pct = float(payload.get("daily_loss_limit_pct", policy.daily_loss_limit_pct))
    policy.duplicate_suppression_window_seconds = int(
        payload.get("duplicate_suppression_window_seconds", policy.duplicate_suppression_window_seconds)
    )
    db.commit()
    db.refresh(policy)
    return policy


def _intent_notional(intent: ExecutionIntent) -> float:
    price_ref = intent.price_reference or {}
    price = price_ref.get("value") or price_ref.get("last_price") or price_ref.get("price") or 0
    price = float(price) if price is not None else 0
    return abs(float(intent.quantity or 0) * float(price or 0))


def _decision_notional(decision_result: dict, context_payload: dict) -> float:
    price_ref = decision_result.get("price_reference") or {}
    price = price_ref.get("value") or price_ref.get("last_price")
    if price is None:
        price = context_payload.get("market_snapshot", {}).get("last_price")
    price = float(price or 0)
    return abs(float(decision_result.get("size") or 0) * float(price or 0))


def _load_intents(
    db: Session,
    *,
    since: datetime | None = None,
    strategy_id: str | None = None,
    symbol: str | None = None,
    account_id: str | None = None,
) -> list[ExecutionIntent]:
    query = db.query(ExecutionIntent)
    if since is not None:
        query = query.filter(ExecutionIntent.created_at >= since)
    if strategy_id:
        query = query.filter(ExecutionIntent.strategy_id == strategy_id)
    if symbol:
        query = query.filter(ExecutionIntent.symbol == symbol)
    if account_id:
        query = query.filter(ExecutionIntent.account_id == account_id)
    return query.all()


def _open_intents(intents: Iterable[ExecutionIntent], db: Session) -> list[ExecutionIntent]:
    intents = list(intents)
    if not intents:
        return []
    intent_ids = [intent.intent_id for intent in intents]
    finalized = (
        db.query(ExecutionIntentEvent)
        .filter(
            ExecutionIntentEvent.intent_id.in_(intent_ids),
            ExecutionIntentEvent.event_type == "execution.order.finalized",
        )
        .all()
    )
    closed_ids = {event.intent_id for event in finalized}
    return [intent for intent in intents if intent.intent_id not in closed_ids]


def _build_exposure_rows(intents: list[ExecutionIntent], *, key_fn) -> list[dict]:
    buckets: dict[str, dict] = {}
    for intent in intents:
        key = key_fn(intent)
        if key not in buckets:
            buckets[key] = {"key": key, "open_count": 0, "notional": 0.0}
        buckets[key]["open_count"] += 1
        buckets[key]["notional"] += _intent_notional(intent)
    rows = list(buckets.values())
    rows.sort(key=lambda item: item["notional"], reverse=True)
    return rows


def build_status_snapshot(db: Session) -> dict:
    policy = get_or_create_policy(db)
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    since = _now() - timedelta(hours=24)
    open_intents = _open_intents(_load_intents(db, since=since), db)
    return {
        "policy": policy,
        "kill_switch_active": bool(control.emergency_mode) if control else False,
        "kill_switch_reasons": ["emergency_mode"] if control and control.emergency_mode else [],
        "open_intents": len(open_intents),
        "open_intents_by_symbol": _build_exposure_rows(open_intents, key_fn=lambda intent: intent.symbol),
        "open_intents_by_strategy": _build_exposure_rows(open_intents, key_fn=lambda intent: intent.strategy_id),
    }


def _emit_risk_alerts(db: Session, *, reason_codes: list[str], strategy_id: str, symbol: str | None) -> None:
    if not reason_codes:
        return
    if "daily_loss_limit_exceeded" in reason_codes:
        create_system_alert(
            db,
            alert_type="daily_loss_limit_hit",
            severity="CRITICAL",
            message="Daily loss limit breached",
            details={"strategy_id": strategy_id, "symbol": symbol, "reason_codes": reason_codes},
        )
    if any(code in {"account_max_notional_exceeded", "symbol_max_exposure_exceeded"} for code in reason_codes):
        create_system_alert(
            db,
            alert_type="exposure_limit_breach",
            severity="CRITICAL",
            message="Exposure limit breach detected",
            details={"strategy_id": strategy_id, "symbol": symbol, "reason_codes": reason_codes},
        )
    if any(code in {"duplicate_decision_hash", "duplicate_intent_hash"} for code in reason_codes):
        create_system_alert(
            db,
            alert_type="duplicate_execution_attempt",
            severity="CRITICAL",
            message="Duplicate execution attempt detected",
            details={"strategy_id": strategy_id, "symbol": symbol, "reason_codes": reason_codes},
        )


def evaluate_pre_trade(
    db: Session,
    *,
    strategy_id: str,
    decision_result: dict,
    context_payload: dict,
) -> dict:
    policy = get_or_create_policy(db)
    action = decision_result.get("action")
    if action in {"REJECT", "HOLD"}:
        return {"approved": True, "reason_codes": [], "metrics": {}}

    intent_payload = map_decision_to_intent(
        strategy_id=strategy_id,
        correlation_id=context_payload.get("correlation_id") or "",
        decision_result=decision_result,
        context_payload=context_payload,
    )
    if intent_payload is None:
        return {"approved": True, "reason_codes": [], "metrics": {}}

    account_id = intent_payload.get("account_id") or context_payload.get("account_id")
    reason_codes: list[str] = []

    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    if control and control.emergency_mode:
        reason_codes.append("kill_switch_active")

    since = _now() - timedelta(hours=24)
    account_intents = _load_intents(db, since=since, account_id=account_id) if account_id else []
    if account_id and not account_intents:
        account_intents = _load_intents(db, since=since, strategy_id=strategy_id)
    if not account_id:
        account_intents = _load_intents(db, since=since, strategy_id=strategy_id)

    symbol_intents = _load_intents(
        db,
        since=since,
        symbol=intent_payload.get("symbol"),
        account_id=account_id,
    )
    if account_id and not symbol_intents:
        symbol_intents = _load_intents(db, since=since, symbol=intent_payload.get("symbol"), strategy_id=strategy_id)
    if not account_id:
        symbol_intents = _load_intents(db, since=since, symbol=intent_payload.get("symbol"), strategy_id=strategy_id)

    strategy_intents = _load_intents(db, since=since, strategy_id=strategy_id)

    open_account_intents = _open_intents(account_intents, db)
    open_symbol_intents = _open_intents(symbol_intents, db)
    open_strategy_intents = _open_intents(strategy_intents, db)

    account_notional = sum(_intent_notional(intent) for intent in open_account_intents)
    symbol_notional = sum(_intent_notional(intent) for intent in open_symbol_intents)

    proposed_notional = _decision_notional(decision_result, context_payload)

    account_state = context_payload.get("account_state_projection", {}) or {}
    equity = float(account_state.get("equity") or policy.reference_equity_usd or 0)

    account_limit = equity * (policy.account_max_notional_pct / 100)
    symbol_limit = equity * (policy.symbol_max_notional_pct / 100)

    if account_limit > 0 and (account_notional + proposed_notional) > account_limit:
        reason_codes.append("account_max_notional_exceeded")
    if symbol_limit > 0 and (symbol_notional + proposed_notional) > symbol_limit:
        reason_codes.append("symbol_max_exposure_exceeded")

    if len(open_strategy_intents) >= policy.strategy_max_concurrent_positions:
        reason_codes.append("strategy_concurrent_limit")

    latest_intent = (
        db.query(ExecutionIntent)
        .filter(ExecutionIntent.strategy_id == strategy_id)
        .order_by(ExecutionIntent.created_at.desc())
        .first()
    )
    if latest_intent is not None:
        cooldown_seconds = policy.strategy_cooldown_seconds
        if cooldown_seconds > 0:
            elapsed = (_now() - latest_intent.created_at).total_seconds()
            if elapsed < cooldown_seconds:
                reason_codes.append("strategy_cooldown_active")

    one_minute = _now() - timedelta(seconds=60)
    recent_count = (
        db.query(ExecutionIntent)
        .filter(ExecutionIntent.strategy_id == strategy_id, ExecutionIntent.created_at >= one_minute)
        .count()
    )
    if recent_count >= policy.max_order_frequency_per_min:
        reason_codes.append("order_frequency_limit")

    ten_seconds = _now() - timedelta(seconds=10)
    burst_count = (
        db.query(ExecutionIntent)
        .filter(ExecutionIntent.strategy_id == strategy_id, ExecutionIntent.created_at >= ten_seconds)
        .count()
    )
    if burst_count >= policy.max_order_burst_per_10s:
        reason_codes.append("order_burst_limit")

    duplicate_window = _now() - timedelta(seconds=policy.duplicate_suppression_window_seconds)
    duplicate_decision = (
        db.query(ExecutionIntent)
        .filter(
            ExecutionIntent.decision_hash == decision_result.get("decision_hash"),
            ExecutionIntent.created_at >= duplicate_window,
        )
        .first()
    )
    if duplicate_decision is not None:
        reason_codes.append("duplicate_decision_hash")

    duplicate_intent = (
        db.query(ExecutionIntent)
        .filter(ExecutionIntent.intent_hash == intent_payload.get("intent_hash"))
        .first()
    )
    if duplicate_intent is not None:
        reason_codes.append("duplicate_intent_hash")

    daily_loss_pct = float(account_state.get("daily_loss_pct") or 0)
    daily_loss_usd = float(account_state.get("daily_loss_usd") or 0)
    if daily_loss_pct >= policy.daily_loss_limit_pct:
        reason_codes.append("daily_loss_limit_exceeded")
    if equity > 0 and daily_loss_usd >= (equity * (policy.daily_loss_limit_pct / 100)):
        reason_codes.append("daily_loss_limit_exceeded")

    if reason_codes:
        _emit_risk_alerts(
            db,
            reason_codes=reason_codes,
            strategy_id=strategy_id,
            symbol=intent_payload.get("symbol"),
        )

    return {
        "approved": len(reason_codes) == 0,
        "reason_codes": reason_codes,
        "metrics": {
            "account_notional": account_notional,
            "symbol_notional": symbol_notional,
            "proposed_notional": proposed_notional,
            "open_strategy_intents": len(open_strategy_intents),
            "open_account_intents": len(open_account_intents),
            "open_symbol_intents": len(open_symbol_intents),
            "recent_count": recent_count,
            "burst_count": burst_count,
            "equity": equity,
        },
    }


def run_in_trade_supervisor(db: Session) -> dict:
    snapshot = build_status_snapshot(db)
    policy: RiskOrchestratorPolicy = snapshot["policy"]
    breaches: list[dict] = []
    reference_equity = float(policy.reference_equity_usd or 0)

    for row in snapshot["open_intents_by_strategy"]:
        if row["open_count"] > policy.strategy_max_concurrent_positions:
            breaches.append(
                {
                    "breach_type": "strategy_concurrent_limit",
                    "key": row["key"],
                    "open_count": row["open_count"],
                    "notional": row["notional"],
                    "limit_pct": None,
                }
            )
        if reference_equity > 0:
            limit = reference_equity * (policy.account_max_notional_pct / 100)
            if row["notional"] > limit:
                breaches.append(
                    {
                        "breach_type": "account_max_notional_exceeded",
                        "key": row["key"],
                        "open_count": row["open_count"],
                        "notional": row["notional"],
                        "limit_pct": policy.account_max_notional_pct,
                    }
                )

    for row in snapshot["open_intents_by_symbol"]:
        if reference_equity > 0:
            limit = reference_equity * (policy.symbol_max_notional_pct / 100)
            if row["notional"] > limit:
                breaches.append(
                    {
                        "breach_type": "symbol_max_exposure_exceeded",
                        "key": row["key"],
                        "open_count": row["open_count"],
                        "notional": row["notional"],
                        "limit_pct": policy.symbol_max_notional_pct,
                    }
                )

    return {
        "evaluated_at": _now(),
        "breaches": breaches,
    }
