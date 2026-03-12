from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import ExecutionMetric, SignalEvent, StrategyAllocation


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def get_or_create_strategy_allocation(db: Session, strategy_id: str) -> StrategyAllocation:
    key = str(strategy_id or "unknown_strategy").strip() or "unknown_strategy"
    row = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id == key).first()
    if row:
        return row

    row = StrategyAllocation(
        strategy_id=key,
        capital_weight=1.0,
        max_capital=10000,
        current_capital=0,
        confidence_score=0,
        performance_score=0,
        state="ACTIVE",
        expected_return=2.0,
        realized_return=0,
        signal_decay=0,
        execution_quality_score=75,
    )
    db.add(row)
    db.flush()
    return row


def recalculate_strategy_drift(db: Session, strategy_id: str) -> StrategyAllocation:
    row = get_or_create_strategy_allocation(db, strategy_id)
    disabled_lock = str(row.state or "").upper() == "DISABLED"
    lookback_from = _now() - timedelta(days=7)

    exec_rows = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.strategy_type == strategy_id, ExecutionMetric.created_at >= lookback_from)
        .all()
    )
    signal_rows = (
        db.query(SignalEvent)
        .filter(SignalEvent.strategy_id == strategy_id, SignalEvent.generated_at >= lookback_from)
        .all()
    )

    quality = (
        sum(_safe_float(item.execution_quality_score, 0) for item in exec_rows) / len(exec_rows)
        if exec_rows
        else _safe_float(row.execution_quality_score, 75)
    )
    confidence = (
        sum(_safe_float(item.confidence, 0) for item in signal_rows) / len(signal_rows)
        if signal_rows
        else _safe_float(row.confidence_score, 0)
    )

    reject_like = len([item for item in signal_rows if str(item.signal).lower() == "none"])
    decay_ratio = (reject_like / len(signal_rows)) if signal_rows else _safe_float(row.signal_decay, 0)
    expected_return = max(0.5, confidence * 6)
    realized_return = round((quality - 50) / 10, 4)

    row.execution_quality_score = round(quality, 4)
    row.confidence_score = round(confidence, 4)
    row.signal_decay = round(decay_ratio, 4)
    row.expected_return = round(expected_return, 4)
    row.realized_return = round(realized_return, 4)
    row.performance_score = round((row.realized_return / max(row.expected_return, 0.1)) * 100, 4)

    if not disabled_lock:
        if row.signal_decay >= 0.8 or row.execution_quality_score < 40:
            row.state = "DISABLED"
        elif row.signal_decay >= 0.55 or row.execution_quality_score < 60 or row.performance_score < 35:
            row.state = "THROTTLED"
        else:
            row.state = "ACTIVE"

    row.updated_at = _now()
    db.flush()
    return row


def run_meta_strategy_engine(
    db: Session,
    *,
    user_id: str,
    strategy_id: str,
    symbol: str,
    signal_confidence: float,
    requested_notional: float,
) -> dict:
    _ = user_id
    allocation = recalculate_strategy_drift(db, strategy_id)

    allocation.confidence_score = round(max(_safe_float(signal_confidence, 0), 0), 4)
    allocation.updated_at = _now()

    requested = max(_safe_float(requested_notional, 0), 0)
    weight = max(_safe_float(allocation.capital_weight, 1), 0.05)
    max_capital = max(_safe_float(allocation.max_capital, 0), 0)
    effective_capital_budget = max_capital * weight
    remaining_capital = max(effective_capital_budget - _safe_float(allocation.current_capital, 0), 0)

    meta_decision = "ALLOW"
    allocation_source = "weight_based"
    allocation_reason = "normal_allocation"
    adjusted_notional = requested

    if allocation.state == "DISABLED":
        meta_decision = "DISABLED"
        allocation_source = "drift_monitor"
        allocation_reason = "strategy_disabled_by_drift"
        adjusted_notional = 0
    elif allocation.state == "THROTTLED":
        meta_decision = "THROTTLED"
        allocation_source = "drift_monitor"
        allocation_reason = "strategy_throttled_by_drift"
        adjusted_notional = min(requested * 0.7, remaining_capital if remaining_capital > 0 else requested * 0.5)
    elif requested > remaining_capital and remaining_capital > 0:
        meta_decision = "THROTTLED"
        allocation_source = "capital_limit"
        allocation_reason = "allocation_capped_by_max_capital"
        adjusted_notional = remaining_capital
    elif remaining_capital <= 0 and requested > 0:
        meta_decision = "THROTTLED"
        allocation_source = "capital_limit"
        allocation_reason = "no_remaining_strategy_capital"
        adjusted_notional = 0

    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "meta_engine_decision": meta_decision,
        "allocation_source": allocation_source,
        "strategy_allocation_reason": allocation_reason,
        "strategy_weight": round(weight, 4),
        "state": allocation.state,
        "requested_notional": round(requested, 4),
        "adjusted_notional": round(max(adjusted_notional, 0), 4),
        "remaining_capital": round(remaining_capital, 4),
        "max_capital": round(max_capital, 4),
        "expected_return": round(_safe_float(allocation.expected_return, 0), 4),
        "realized_return": round(_safe_float(allocation.realized_return, 0), 4),
        "signal_decay": round(_safe_float(allocation.signal_decay, 0), 4),
        "execution_quality_score": round(_safe_float(allocation.execution_quality_score, 0), 4),
    }


def list_strategy_allocations(db: Session, limit: int = 200) -> list[StrategyAllocation]:
    rows = db.query(StrategyAllocation).order_by(StrategyAllocation.updated_at.desc()).limit(limit).all()
    for row in rows:
        recalculate_strategy_drift(db, row.strategy_id)
    db.commit()
    return db.query(StrategyAllocation).order_by(StrategyAllocation.updated_at.desc()).limit(limit).all()


def update_strategy_allocation(db: Session, strategy_id: str, payload: dict) -> StrategyAllocation:
    row = get_or_create_strategy_allocation(db, strategy_id)

    if "capital_weight" in payload:
        row.capital_weight = max(_safe_float(payload.get("capital_weight"), row.capital_weight), 0.01)
    if "max_capital" in payload:
        row.max_capital = max(_safe_float(payload.get("max_capital"), row.max_capital), 0)
    if "current_capital" in payload:
        row.current_capital = max(_safe_float(payload.get("current_capital"), row.current_capital), 0)
    if "state" in payload:
        state = str(payload.get("state") or row.state).upper()
        if state in {"ACTIVE", "THROTTLED", "DISABLED"}:
            row.state = state

    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row
