from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from models import ManualOverrideLog, PendingSignal, Position, SignalEvent, StrategyAllocation
from services.capital_rebalance_engine import run_dynamic_capital_rebalance
from services.hedging_suggestion_engine import detect_hedge_opportunity
from services.strategy_conflict_engine import detect_conflicts_for_signal, load_conflict_rules


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_confidence_adjusted_risk_score(simulation_payload: dict, projected_risk: float) -> float:
    volatility = max(_safe_float(simulation_payload.get("volatility_pct"), 0), 0)
    notional = max(_safe_float(simulation_payload.get("notional"), 0), 0)
    confidence_hint = _safe_float(simulation_payload.get("confidence_score"), 0.65)
    confidence = confidence_hint if confidence_hint <= 1 else confidence_hint / 100
    confidence = min(max(confidence, 0.05), 0.95)

    volatility_penalty = min(volatility / 100, 0.4)
    notional_penalty = min(notional / 100000, 0.25)
    adjusted_multiplier = 1 + volatility_penalty + notional_penalty - (confidence * 0.3)
    adjusted = projected_risk * adjusted_multiplier
    return round(min(max(adjusted, 0), 1.5), 6)


def _build_strategy_stats(db: Session, strategy_ids: set[str]) -> dict:
    rows = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id.in_(list(strategy_ids))).all() if strategy_ids else []
    stats = {
        row.strategy_id: {
            "state": row.state,
            "performance_score": _safe_float(row.performance_score),
            "signal_decay": _safe_float(row.signal_decay),
            "confidence_score": _safe_float(row.confidence_score),
            "execution_quality_score": _safe_float(row.execution_quality_score),
            "capital_weight": _safe_float(row.capital_weight),
            "current_capital": _safe_float(row.current_capital),
            "max_capital": _safe_float(row.max_capital),
            "realized_return": _safe_float(row.realized_return),
            "risk_score": max(0.0, min(1.0, _safe_float(row.signal_decay))),
        }
        for row in rows
    }

    for strategy_id in strategy_ids:
        stats.setdefault(
            strategy_id,
            {
                "state": "ACTIVE",
                "performance_score": 0.0,
                "signal_decay": 0.0,
                "confidence_score": 0.0,
                "execution_quality_score": 70.0,
                "capital_weight": 1.0,
                "current_capital": 0.0,
                "max_capital": 10000.0,
                "realized_return": 0.0,
                "risk_score": 0.2,
            },
        )
    return stats


def _active_signal_pool(db: Session, user_id: str, symbol: str | None = None) -> list[dict]:
    since = _now() - timedelta(hours=2)
    query = db.query(SignalEvent).filter(SignalEvent.user_id == user_id, SignalEvent.generated_at >= since)
    if symbol:
        query = query.filter(SignalEvent.symbol == symbol)
    rows = query.order_by(SignalEvent.generated_at.desc()).limit(200).all()

    payload: list[dict] = []
    for row in rows:
        direction = str(row.signal or "").lower()
        if direction in {"none", "flat", ""}:
            continue
        payload.append(
            {
                "strategy_id": row.strategy_id or "unknown_strategy",
                "symbol": row.symbol,
                "signal_direction": direction,
                "confidence_score": _safe_float(row.confidence),
                "generated_at": row.generated_at,
            }
        )

    pending_rows = (
        db.query(PendingSignal)
        .filter(PendingSignal.user_id == user_id, PendingSignal.created_at >= since)
        .order_by(PendingSignal.created_at.desc())
        .limit(200)
        .all()
    )
    for row in pending_rows:
        direction = "buy"
        if "short" in str(row.strategy_code or "").lower():
            direction = "sell"
        payload.append(
            {
                "strategy_id": row.strategy_code or "unknown_strategy",
                "symbol": row.symbol,
                "signal_direction": direction,
                "confidence_score": _safe_float(row.confidence),
                "generated_at": row.created_at,
            }
        )
    return payload


def evaluate_conflict_warning(
    db: Session,
    *,
    user_id: str,
    strategy_id: str,
    symbol: str,
    signal_direction: str,
    confidence_score: float,
) -> dict:
    active_signals = _active_signal_pool(db, user_id, symbol=symbol)
    strategy_ids = {strategy_id} | {str(item.get("strategy_id") or "unknown_strategy") for item in active_signals}
    strategy_stats = _build_strategy_stats(db, strategy_ids)
    conflict_rules = load_conflict_rules()
    conflict = detect_conflicts_for_signal(
        active_signals=active_signals,
        strategy_id=strategy_id,
        symbol=symbol,
        signal_direction=signal_direction,
        confidence_score=confidence_score,
        strategy_stats=strategy_stats,
        conflict_rules=conflict_rules,
    )
    warning = None
    if conflict.get("conflict_detected"):
        warning = (
            f"{symbol} için strateji çatışması: winner={conflict.get('winning_strategy')} "
            f"reason={conflict.get('resolution_reason')}"
        )

    return {
        **conflict,
        "strategy_conflict_warning": warning,
    }


def evaluate_capital_rebalance(db: Session, *, user_id: str, apply_changes: bool = False) -> dict:
    _ = user_id
    rows = db.query(StrategyAllocation).order_by(StrategyAllocation.updated_at.desc()).limit(300).all()
    metrics = [
        {
            "strategy_id": row.strategy_id,
            "capital_weight": _safe_float(row.capital_weight),
            "max_capital": _safe_float(row.max_capital),
            "current_capital": _safe_float(row.current_capital),
            "last_rebalanced_at": row.updated_at,
            "performance_score": _safe_float(row.performance_score),
            "confidence_score": _safe_float(row.confidence_score),
            "signal_decay": _safe_float(row.signal_decay),
            "execution_quality_score": _safe_float(row.execution_quality_score),
            "realized_return": _safe_float(row.realized_return),
            "risk_score": max(0.0, min(1.0, _safe_float(row.signal_decay))),
        }
        for row in rows
    ]
    result = run_dynamic_capital_rebalance(metrics)

    if apply_changes and rows:
        event_map = {event["strategy_id"]: event for event in result.get("events", [])}
        for row in rows:
            event = event_map.get(row.strategy_id)
            if not event:
                continue
            if bool(event.get("cadence_window_blocked")):
                continue
            row.capital_weight = float(event.get("new_strategy_weight") or row.capital_weight)
            if bool(event.get("throttle_signal")) and row.state == "ACTIVE":
                row.state = "THROTTLED"
            row.updated_at = _now()
        db.flush()

    adjustment_notice = None
    governance_summary = result.get("governance_summary") or {}
    cadence_blocked = int(governance_summary.get("cadence_blocked_strategies") or 0)
    if cadence_blocked > 0:
        adjustment_notice = f"rebalance_cadence_hold aktif: {cadence_blocked} strategy pencere içinde"

    high_drift = [event for event in result.get("events", []) if event.get("allocation_drift", 0) > 0.08]
    if high_drift and not adjustment_notice:
        first = high_drift[0]
        adjustment_notice = (
            f"allocation_drift yüksek: {first.get('strategy_id')} -> new_weight={first.get('new_strategy_weight')}"
        )

    return {
        **result,
        "allocation_adjustment_notice": adjustment_notice,
    }


def _portfolio_exposure_for_user(db: Session, user_id: str) -> dict:
    rows = db.query(Position).filter(Position.user_id == user_id, Position.status == "open").all()
    cluster_exposure: dict[str, float] = {}
    total_notional = 0.0
    symbols: list[str] = []
    for row in rows:
        notional = abs(_safe_float(row.size) * _safe_float(row.current_price) * max(int(row.leverage or 1), 1))
        total_notional += notional
        cluster = row.cluster_id or "UNCLUSTERED"
        cluster_exposure[cluster] = round(cluster_exposure.get(cluster, 0.0) + notional, 6)
        symbols.append(str(row.symbol).upper())
    return {
        "total_notional": round(total_notional, 6),
        "cluster_exposure": cluster_exposure,
        "symbols": symbols,
    }


def evaluate_hedge_suggestion(
    db: Session,
    *,
    user_id: str,
    volatility: float,
    market_correlation: dict | None = None,
) -> dict:
    exposure = _portfolio_exposure_for_user(db, user_id)
    cluster_exposure = exposure.get("cluster_exposure") or {}
    total_notional = max(_safe_float(exposure.get("total_notional"), 0), 1)
    cluster_risk = {
        key: round(_safe_float(value, 0) / total_notional, 6)
        for key, value in cluster_exposure.items()
    }
    correlation_map = market_correlation or {key: 0.74 for key in cluster_exposure}
    suggestion = detect_hedge_opportunity(
        portfolio_exposure=exposure,
        cluster_risk=cluster_risk,
        market_correlation=correlation_map,
        volatility=volatility,
    )
    return suggestion


def build_strategy_intelligence_snapshot(db: Session, *, user_id: str) -> dict:
    active_signals = _active_signal_pool(db, user_id)
    strategy_ids = {str(item.get("strategy_id") or "unknown_strategy") for item in active_signals}
    strategy_stats = _build_strategy_stats(db, strategy_ids)

    conflicts: list[dict] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    for signal in active_signals:
        key = (str(signal.get("strategy_id") or "unknown_strategy"), str(signal.get("symbol") or ""), str(signal.get("signal_direction") or ""))
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        conflict_result = detect_conflicts_for_signal(
            active_signals=active_signals,
            strategy_id=key[0],
            symbol=key[1],
            signal_direction=key[2],
            confidence_score=_safe_float(signal.get("confidence_score"), 0),
            strategy_stats=strategy_stats,
            conflict_rules=load_conflict_rules(),
        )
        if conflict_result.get("conflict_detected"):
            conflicts.append(conflict_result)

    rebalance = evaluate_capital_rebalance(db, user_id=user_id, apply_changes=False)
    hedge = evaluate_hedge_suggestion(db, user_id=user_id, volatility=4.0)
    return {
        "generated_at": _now(),
        "strategy_conflicts": conflicts,
        "capital_rebalance_events": rebalance.get("events", []),
        "governance_summary": rebalance.get("governance_summary", {}),
        "allocation_drift": rebalance.get("allocation_drift", 0.0),
        "strategy_performance_delta": rebalance.get("strategy_performance_delta", 0.0),
        "risk_adjusted_return": rebalance.get("risk_adjusted_return", 0.0),
        "hedge_suggestions": [hedge] if hedge.get("hedge_symbol") else [],
    }


def record_manual_override(
    db: Session,
    *,
    admin_id: str,
    action_type: str,
    reason: str,
    payload: dict,
    scope: str = "strategy_intelligence",
    target_type: str = "user",
    target_id: str | None = None,
    simulation_id: str | None = None,
    confirmation_id: str | None = None,
    previous_state: dict | None = None,
    next_state: dict | None = None,
    impact_preview: dict | None = None,
    expires_at: datetime | None = None,
    actor_role: str | None = None,
) -> ManualOverrideLog:
    merged_payload = {
        **(payload or {}),
        "scope": scope,
        "target_type": target_type,
        "target_id": target_id,
        "simulation_id": simulation_id,
        "confirmation_id": confirmation_id,
        "previous_state": previous_state or {},
        "next_state": next_state or {},
        "impact_preview": impact_preview or {},
        "expires_at": expires_at.isoformat() if expires_at else None,
        "actor_role": actor_role,
        "current_status": "active",
        "revoked_at": None,
        "revoked_by": None,
    }
    row = ManualOverrideLog(
        admin_id=admin_id,
        action_type=str(action_type or "manual_override"),
        reason=str(reason or ""),
        payload=merged_payload,
        timestamp=_now(),
    )
    db.add(row)
    db.flush()
    return row


def list_manual_overrides(db: Session, limit: int = 100) -> list[ManualOverrideLog]:
    return db.query(ManualOverrideLog).order_by(ManualOverrideLog.timestamp.desc()).limit(limit).all()


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _ensure_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    return {"value": value}


def normalize_manual_override_row(row: ManualOverrideLog) -> dict:
    payload = row.payload if isinstance(row.payload, dict) else {"raw_payload": row.payload}
    expires_at = _parse_dt(payload.get("expires_at"))
    revoked_at = _parse_dt(payload.get("revoked_at"))
    status = str(payload.get("current_status") or "active")
    if revoked_at:
        status = "revoked"
    elif expires_at and expires_at <= _now():
        status = "expired"

    return {
        "override_id": row.override_id,
        "admin_id": row.admin_id,
        "actor_role": payload.get("actor_role"),
        "scope": payload.get("scope") or "unknown",
        "target_type": payload.get("target_type") or "user",
        "target_id": payload.get("target_id"),
        "action_type": row.action_type,
        "reason": row.reason,
        "simulation_id": payload.get("simulation_id"),
        "confirmation_id": payload.get("confirmation_id"),
        "previous_state": _ensure_dict(payload.get("previous_state")),
        "next_state": _ensure_dict(payload.get("next_state")),
        "impact_preview": _ensure_dict(payload.get("impact_preview")),
        "expires_at": expires_at,
        "current_status": status,
        "revoked_at": revoked_at,
        "revoked_by": payload.get("revoked_by"),
        "payload": payload,
        "timestamp": row.timestamp,
    }


def list_active_manual_overrides(db: Session, limit: int = 100) -> list[dict]:
    rows = list_manual_overrides(db, limit=limit)
    normalized = [normalize_manual_override_row(row) for row in rows]
    return [
        row
        for row in normalized
        if row.get("current_status") == "active" and row.get("scope") == "strategy_intelligence"
    ]


def revoke_manual_override(
    db: Session,
    *,
    override_id: str,
    revoked_by: str,
    reason: str,
) -> dict:
    from sqlalchemy.orm.attributes import flag_modified
    
    row = db.query(ManualOverrideLog).filter(ManualOverrideLog.override_id == override_id).first()
    if not row:
        raise ValueError(f"override bulunamadı: {override_id}")

    payload = row.payload if isinstance(row.payload, dict) else {"raw_payload": row.payload}
    if payload.get("revoked_at"):
        raise ValueError("override zaten revoke edilmiş")

    revoked_at = _now()
    payload["revoked_at"] = revoked_at.isoformat()
    payload["revoked_by"] = revoked_by
    payload["revoke_reason"] = reason
    payload["current_status"] = "revoked"
    row.payload = payload
    flag_modified(row, "payload")
    db.flush()
    return {
        "override_id": override_id,
        "status": "revoked",
        "revoked_at": revoked_at,
        "revoked_by": revoked_by,
        "message": "override revoke edildi",
    }


def simulate_risk_impact(
    *,
    simulation_payload: dict,
    conflict_result: dict,
    rebalance_result: dict,
    hedge_result: dict,
    risk_payload: dict,
) -> dict:
    projected_risk = _safe_float(risk_payload.get("risk_score"), 0)
    if conflict_result.get("conflict_detected"):
        projected_risk = min(1.0, projected_risk + 0.07)
    if hedge_result.get("risk_reduction_score"):
        projected_risk = max(0.0, projected_risk - (_safe_float(hedge_result.get("risk_reduction_score"), 0) * 0.2))

    before_exposure = _safe_float(simulation_payload.get("position_size_value") or simulation_payload.get("notional"), 0)
    after_exposure = max(before_exposure * (0.95 if hedge_result.get("hedge_symbol") else 1.03), 0)
    projected_pnl = round((1 - projected_risk) * max(before_exposure, 1) * 0.015, 4)
    projected_drawdown = round(projected_risk * 0.12, 6)
    projected_var = round(projected_risk * max(after_exposure, 1) * 0.08, 4)
    projected_liquidity_impact = round(min(1.0, (after_exposure / 100000.0)), 6)

    before_state = {
        "risk_score": round(_safe_float(risk_payload.get("base_risk_score") or risk_payload.get("risk_score"), projected_risk), 6),
        "gate_decision": str(risk_payload.get("base_decision") or risk_payload.get("decision") or "ALLOW"),
        "exposure": round(before_exposure, 4),
        "pnl_estimate": round(max(before_exposure, 1) * 0.01, 4),
    }
    after_state = {
        "risk_score": round(projected_risk, 6),
        "gate_decision": str(risk_payload.get("decision") or "ALLOW"),
        "exposure": round(after_exposure, 4),
        "pnl_estimate": projected_pnl,
    }

    risk_delta = round(after_state["risk_score"] - before_state["risk_score"], 6)
    decision_delta = "UNCHANGED"
    if before_state["gate_decision"] != after_state["gate_decision"]:
        decision_delta = f"{before_state['gate_decision']}->{after_state['gate_decision']}"

    confidence_adjusted_risk_score = calculate_confidence_adjusted_risk_score(simulation_payload, projected_risk)

    return {
        "simulation_id": f"sim_{uuid4().hex[:12]}",
        "dry_run": True,
        "simulation_payload": simulation_payload,
        "strategy_conflict": conflict_result,
        "allocation_adjustment": {
            "allocation_drift": rebalance_result.get("allocation_drift", 0.0),
            "notice": rebalance_result.get("allocation_adjustment_notice"),
            "events": rebalance_result.get("events", []),
        },
        "hedge_suggestion": hedge_result,
        "projected_risk_score": round(projected_risk, 6),
        "projected_gate_decision": risk_payload.get("decision", "ALLOW"),
        "projected_pnl": projected_pnl,
        "projected_drawdown": projected_drawdown,
        "projected_exposure": round(after_exposure, 4),
        "projected_var": projected_var,
        "projected_liquidity_impact": projected_liquidity_impact,
        "confidence_adjusted_risk_score": confidence_adjusted_risk_score,
        "before_state": before_state,
        "after_state": after_state,
        "decision_summary": {
            "conflict_detected": bool(conflict_result.get("conflict_detected")),
            "hedge_required": bool(hedge_result.get("hedge_symbol")),
            "allocation_notice": rebalance_result.get("allocation_adjustment_notice"),
            "decision_delta": decision_delta,
        },
        "risk_delta": risk_delta,
        "decision_delta": decision_delta,
    }
