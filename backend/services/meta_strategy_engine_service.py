from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from models import ExecutionMetric, SignalEvent, StrategyAllocation


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


ALLOWED_STATES = {"ACTIVE", "THROTTLED", "DISABLED"}
DOUBLE_CONFIRM_PRIMARY = "CONFIRM"
DOUBLE_CONFIRM_SECONDARY = "STATE CHANGE"
EXPOSURE_WARNING_THRESHOLD_PCT = 80.0
DRAWDOWN_WARNING_THRESHOLD_PCT = 8.0
DRAWDOWN_ENFORCE_THRESHOLD_PCT = 12.0
DRAWDOWN_REDUCE_RATIO = 0.15


def _normalized_state(value: str | None, fallback: str = "ACTIVE") -> str:
    state = str(value or fallback).upper().strip()
    return state if state in ALLOWED_STATES else fallback


def _validate_non_empty_strategy_id(strategy_id: str) -> str:
    key = str(strategy_id or "").strip()
    if not key:
        raise ValueError("strategy_id boş olamaz")
    if len(key) > 80:
        raise ValueError("strategy_id 80 karakterden uzun olamaz")
    return key


def _assert_non_negative_numeric(field_name: str, value: float) -> float:
    val = _safe_float(value, float("nan"))
    if val != val:  # NaN check
        raise ValueError(f"{field_name} sayısal olmalı")
    if val < 0:
        raise ValueError(f"{field_name} negatif olamaz")
    return val


def _assert_positive_numeric(field_name: str, value: float) -> float:
    val = _safe_float(value, float("nan"))
    if val != val:
        raise ValueError(f"{field_name} sayısal olmalı")
    if val <= 0:
        raise ValueError(f"{field_name} 0'dan büyük olmalı")
    return val


def _compute_strategy_exposure_ratio_pct(row: StrategyAllocation) -> float:
    max_capital = max(_safe_float(row.max_capital, 0), 0)
    current_capital = max(_safe_float(row.current_capital, 0), 0)
    if max_capital <= 0:
        return 0.0
    return round((current_capital / max_capital) * 100, 4)


def _compute_strategy_drawdown_pct(row: StrategyAllocation) -> float:
    realized_return = _safe_float(row.realized_return, 0)
    if realized_return >= 0:
        return 0.0
    return round(abs(realized_return), 4)


def _compute_suggested_reduced_capital(row: StrategyAllocation) -> float:
    current_capital = max(_safe_float(row.current_capital, 0), 0)
    suggested = current_capital * (1 - DRAWDOWN_REDUCE_RATIO)
    return round(max(suggested, 0.0), 4)


def _build_drift_reason(row: StrategyAllocation, *, requested_state: str | None = None) -> tuple[str, str, bool]:
    state = _normalized_state(row.state)
    metrics = {
        "signal_decay": round(_safe_float(row.signal_decay, 0), 4),
        "execution_quality_score": round(_safe_float(row.execution_quality_score, 0), 4),
        "performance_score": round(_safe_float(row.performance_score, 0), 4),
    }
    severe = metrics["signal_decay"] >= 0.8 or metrics["execution_quality_score"] < 40
    medium = (
        metrics["signal_decay"] >= 0.55
        or metrics["execution_quality_score"] < 60
        or metrics["performance_score"] < 35
    )

    requested = _normalized_state(requested_state, state) if requested_state else None
    if state == "DISABLED" and severe:
        code = "AUTO_DISABLED_BY_DRIFT"
    elif state == "THROTTLED" and medium:
        code = "AUTO_THROTTLED_BY_DRIFT"
    else:
        code = "MANUAL_STATE"

    detail = (
        f"decay={metrics['signal_decay']} · quality={metrics['execution_quality_score']} · "
        f"performance={metrics['performance_score']}"
    )
    is_override = requested is not None and requested != state and code.startswith("AUTO_")
    return code, detail, is_override


def _apply_critical_drawdown_reduce(rows: list[StrategyAllocation]) -> list[dict]:
    enforced: list[dict] = []
    for row in rows:
        drawdown_pct = _compute_strategy_drawdown_pct(row)
        if drawdown_pct < DRAWDOWN_ENFORCE_THRESHOLD_PCT:
            continue
        suggested = _compute_suggested_reduced_capital(row)
        current = max(_safe_float(row.current_capital, 0), 0)
        if current <= suggested:
            continue
        row.current_capital = suggested
        row.updated_at = _now()
        enforced.append(
            {
                "strategy_id": row.strategy_id,
                "previous_current_capital": round(current, 4),
                "new_current_capital": round(suggested, 4),
                "drawdown_pct": drawdown_pct,
                "reason_code": "AUTO_REDUCE_BY_DRAWDOWN",
            }
        )
    return enforced


def _serialize_strategy_allocation_row(row: StrategyAllocation, *, requested_state: str | None = None) -> dict:
    code, detail, is_override = _build_drift_reason(row, requested_state=requested_state)
    drawdown_pct = _compute_strategy_drawdown_pct(row)
    suggested_capital = _compute_suggested_reduced_capital(row)
    exposure_ratio_pct = _compute_strategy_exposure_ratio_pct(row)

    return {
        "strategy_id": row.strategy_id,
        "capital_weight": round(_safe_float(row.capital_weight, 0), 8),
        "max_capital": round(_safe_float(row.max_capital, 0), 4),
        "current_capital": round(_safe_float(row.current_capital, 0), 4),
        "confidence_score": round(_safe_float(row.confidence_score, 0), 4),
        "performance_score": round(_safe_float(row.performance_score, 0), 4),
        "state": _normalized_state(row.state),
        "expected_return": round(_safe_float(row.expected_return, 0), 4),
        "realized_return": round(_safe_float(row.realized_return, 0), 4),
        "signal_decay": round(_safe_float(row.signal_decay, 0), 4),
        "execution_quality_score": round(_safe_float(row.execution_quality_score, 0), 4),
        "updated_at": row.updated_at,
        "state_reason_code": code,
        "state_reason_detail": detail,
        "is_drift_override": is_override,
        "drawdown_pct": drawdown_pct,
        "exposure_ratio_pct": exposure_ratio_pct,
        "suggested_reduced_capital": suggested_capital,
        "is_auto_reduce_candidate": drawdown_pct >= DRAWDOWN_WARNING_THRESHOLD_PCT,
    }


def _collect_summary(rows: list[StrategyAllocation]) -> dict:
    total_weight = round(sum(_safe_float(row.capital_weight, 0) for row in rows), 6)
    total_capital = round(sum(_safe_float(row.max_capital, 0) for row in rows), 4)
    used_capital = round(sum(_safe_float(row.current_capital, 0) for row in rows), 4)
    available_capital = round(max(total_capital - used_capital, 0.0), 4)

    over_allocated = []
    for row in rows:
        current = _safe_float(row.current_capital, 0)
        maximum = _safe_float(row.max_capital, 0)
        if current > maximum:
            over_allocated.append(
                {
                    "strategy_id": row.strategy_id,
                    "current_capital": round(current, 4),
                    "max_capital": round(maximum, 4),
                    "overflow": round(current - maximum, 4),
                }
            )

    total_exposure_ratio_pct = round((used_capital / total_capital) * 100, 4) if total_capital > 0 else 0.0
    exposure_warning_state = "WARNING" if total_exposure_ratio_pct >= EXPOSURE_WARNING_THRESHOLD_PCT else "NORMAL"

    drawdown_candidates = []
    for row in rows:
        drawdown_pct = _compute_strategy_drawdown_pct(row)
        if drawdown_pct < DRAWDOWN_WARNING_THRESHOLD_PCT:
            continue
        drawdown_candidates.append(
            {
                "strategy_id": row.strategy_id,
                "drawdown_pct": drawdown_pct,
                "current_capital": round(_safe_float(row.current_capital, 0), 4),
                "suggested_reduced_capital": _compute_suggested_reduced_capital(row),
                "enforced_required": drawdown_pct >= DRAWDOWN_ENFORCE_THRESHOLD_PCT,
                "reason_code": "AUTO_REDUCE_BY_DRAWDOWN" if drawdown_pct >= DRAWDOWN_ENFORCE_THRESHOLD_PCT else "SUGGESTED_REDUCE_BY_DRAWDOWN",
            }
        )

    return {
        "total_strategies": len(rows),
        "total_weight": total_weight,
        "weight_balance_delta": round(total_weight - 1.0, 6),
        "total_capital": total_capital,
        "used_capital": used_capital,
        "available_capital": available_capital,
        "over_allocated_count": len(over_allocated),
        "over_allocated_strategies": over_allocated,
        "total_exposure_ratio_pct": total_exposure_ratio_pct,
        "exposure_warning_threshold_pct": EXPOSURE_WARNING_THRESHOLD_PCT,
        "exposure_warning_state": exposure_warning_state,
        "drawdown_threshold_pct": DRAWDOWN_WARNING_THRESHOLD_PCT,
        "drawdown_enforce_threshold_pct": DRAWDOWN_ENFORCE_THRESHOLD_PCT,
        "drawdown_candidates": drawdown_candidates,
    }


def _ensure_weight_is_one(rows: list[StrategyAllocation], *, tolerance: float = 0.0001) -> None:
    summary = _collect_summary(rows)
    if abs(summary["weight_balance_delta"]) > tolerance:
        raise ValueError(
            f"Toplam weight 1 olmalı. current_total={summary['total_weight']} delta={summary['weight_balance_delta']}"
        )


def _ensure_capital_limit(rows: list[StrategyAllocation]) -> None:
    summary = _collect_summary(rows)
    if summary["over_allocated_count"] > 0:
        first = (summary["over_allocated_strategies"] or [])[0]
        raise ValueError(
            "Capital limit aşıldı: "
            f"{first.get('strategy_id')} current={first.get('current_capital')} "
            f"> max={first.get('max_capital')} overflow={first.get('overflow')}"
        )


def _apply_normalize(rows: list[StrategyAllocation]) -> None:
    if not rows:
        return
    total_weight = sum(max(_safe_float(row.capital_weight, 0), 0) for row in rows)
    if total_weight <= 0:
        equal_weight = round(1 / len(rows), 8)
        for row in rows:
            row.capital_weight = equal_weight
            row.updated_at = _now()
        rows[-1].capital_weight = round(1 - sum(_safe_float(r.capital_weight, 0) for r in rows[:-1]), 8)
        return

    normalized_values = []
    for row in rows:
        normalized_values.append(max(_safe_float(row.capital_weight, 0), 0) / total_weight)

    rounded_values = [round(value, 8) for value in normalized_values]
    if rounded_values:
        rounded_values[-1] = round(1 - sum(rounded_values[:-1]), 8)

    for idx, row in enumerate(rows):
        row.capital_weight = max(rounded_values[idx], 0)
        row.updated_at = _now()


def _state_change_requires_double_confirm(before_state: str, after_state: str) -> bool:
    return _normalized_state(before_state) != _normalized_state(after_state)


def _ensure_double_confirm(payload: dict) -> None:
    primary = str(payload.get("confirm_primary") or "").strip().upper()
    secondary = str(payload.get("confirm_secondary") or "").strip().upper()
    if primary != DOUBLE_CONFIRM_PRIMARY or secondary != DOUBLE_CONFIRM_SECONDARY:
        raise ValueError(
            "State change için double confirm zorunlu (confirm_primary=CONFIRM, confirm_secondary=STATE CHANGE)"
        )


def get_or_create_strategy_allocation(db: Session, strategy_id: str) -> StrategyAllocation:
    key = _validate_non_empty_strategy_id(strategy_id)
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


def get_existing_strategy_allocation(db: Session, strategy_id: str) -> StrategyAllocation:
    key = _validate_non_empty_strategy_id(strategy_id)
    row = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id == key).first()
    if not row:
        raise ValueError(f"Strategy bulunamadı: {key}")
    return row


def recalculate_strategy_drift(db: Session, strategy_id: str) -> StrategyAllocation:
    row = get_or_create_strategy_allocation(db, strategy_id)
    manual_lock = str(row.state or "").upper() in {"DISABLED", "THROTTLED"}
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

    if not manual_lock:
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


def list_strategy_allocation_dashboard_rows(db: Session, limit: int = 200) -> list[dict]:
    rows = list_strategy_allocations(db, limit=limit)
    return [_serialize_strategy_allocation_row(row) for row in rows]


def build_strategy_allocation_row_payload(row: StrategyAllocation, *, requested_state: str | None = None) -> dict:
    return _serialize_strategy_allocation_row(row, requested_state=requested_state)


def get_strategy_allocation_summary(db: Session) -> dict:
    rows = list_strategy_allocations(db, limit=500)
    return _collect_summary(rows)


def create_strategy_allocation(db: Session, payload: dict) -> StrategyAllocation:
    strategy_id = _validate_non_empty_strategy_id(payload.get("strategy_id"))
    exists = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id == strategy_id).first()
    if exists:
        raise ValueError(f"Strategy zaten mevcut: {strategy_id}")

    capital_weight = _assert_non_negative_numeric("capital_weight", payload.get("capital_weight", 0.0))
    if capital_weight > 1:
        raise ValueError("capital_weight 1'i aşamaz")
    max_capital = _assert_non_negative_numeric("max_capital", payload.get("max_capital", 0.0))
    current_capital = _assert_non_negative_numeric("current_capital", payload.get("current_capital", 0.0))
    if current_capital > max_capital:
        raise ValueError("current_capital max_capital değerini aşamaz")

    row = StrategyAllocation(
        strategy_id=strategy_id,
        capital_weight=capital_weight,
        max_capital=max_capital,
        current_capital=current_capital,
        confidence_score=max(_safe_float(payload.get("confidence_score"), 0), 0),
        performance_score=max(_safe_float(payload.get("performance_score"), 0), 0),
        state=_normalized_state(payload.get("state"), "ACTIVE"),
        expected_return=max(_safe_float(payload.get("expected_return"), 0), 0),
        realized_return=_safe_float(payload.get("realized_return"), 0),
        signal_decay=max(_safe_float(payload.get("signal_decay"), 0), 0),
        execution_quality_score=max(_safe_float(payload.get("execution_quality_score"), 0), 0),
        updated_at=_now(),
    )
    db.add(row)

    try:
        db.flush()
        all_rows = db.query(StrategyAllocation).order_by(StrategyAllocation.strategy_id.asc()).all()
        _apply_critical_drawdown_reduce(all_rows)
        _ensure_capital_limit(all_rows)
        _ensure_weight_is_one(all_rows)
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        db.rollback()
        raise


def delete_strategy_allocation(db: Session, strategy_id: str, *, auto_normalize: bool = False) -> dict:
    key = _validate_non_empty_strategy_id(strategy_id)
    row = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id == key).first()
    if not row:
        raise ValueError(f"Strategy bulunamadı: {key}")

    db.delete(row)
    try:
        db.flush()
        remaining = db.query(StrategyAllocation).order_by(StrategyAllocation.strategy_id.asc()).all()
        if remaining and auto_normalize:
            _apply_normalize(remaining)
        if remaining:
            _ensure_capital_limit(remaining)
            _ensure_weight_is_one(remaining)
        summary = _collect_summary(remaining)
        db.commit()
        return {
            "deleted_strategy_id": key,
            "auto_normalized": bool(auto_normalize),
            "summary": summary,
            "trace_id": f"strategy_alloc_delete_{uuid4().hex[:10]}",
        }
    except Exception:
        db.rollback()
        raise


def normalize_strategy_allocations(db: Session) -> dict:
    rows = db.query(StrategyAllocation).order_by(StrategyAllocation.strategy_id.asc()).all()
    if not rows:
        raise ValueError("Normalize için strategy allocation satırı bulunamadı")

    try:
        _apply_normalize(rows)
        _ensure_capital_limit(rows)
        _ensure_weight_is_one(rows)
        summary = _collect_summary(rows)
        db.commit()
        return {
            "status": "normalized",
            "trace_id": f"strategy_alloc_norm_{uuid4().hex[:10]}",
            "summary": summary,
        }
    except Exception:
        db.rollback()
        raise


def update_strategy_allocation(db: Session, strategy_id: str, payload: dict) -> StrategyAllocation:
    row = get_existing_strategy_allocation(db, strategy_id)
    previous_state = _normalized_state(row.state)
    requested_state = payload.get("state")

    if "capital_weight" in payload:
        row.capital_weight = _assert_non_negative_numeric("capital_weight", payload.get("capital_weight"))
        if row.capital_weight > 1:
            raise ValueError("capital_weight 1'i aşamaz")
    if "max_capital" in payload:
        row.max_capital = _assert_non_negative_numeric("max_capital", payload.get("max_capital"))
    if "current_capital" in payload:
        row.current_capital = _assert_non_negative_numeric("current_capital", payload.get("current_capital"))
    if "state" in payload:
        state = _normalized_state(payload.get("state"), previous_state)
        if _state_change_requires_double_confirm(previous_state, state):
            _ensure_double_confirm(payload)
        row.state = state

    if row.current_capital > row.max_capital:
        raise ValueError("current_capital max_capital değerini aşamaz")

    row.updated_at = _now()
    try:
        if requested_state is not None and _normalized_state(requested_state, previous_state) == "ACTIVE":
            recalculate_strategy_drift(db, row.strategy_id)

        rows = db.query(StrategyAllocation).order_by(StrategyAllocation.strategy_id.asc()).all()
        _apply_critical_drawdown_reduce(rows)
        _ensure_capital_limit(rows)
        _ensure_weight_is_one(rows)
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        db.rollback()
        raise


def toggle_strategy_throttle(db: Session, strategy_id: str, payload: dict) -> StrategyAllocation:
    row = get_existing_strategy_allocation(db, strategy_id)
    if _normalized_state(row.state) == "DISABLED":
        raise ValueError("DISABLED strategy throttle toggle ile değiştirilemez")

    _ensure_double_confirm(payload)
    row.state = "ACTIVE" if _normalized_state(row.state) == "THROTTLED" else "THROTTLED"
    row.updated_at = _now()
    try:
        rows = db.query(StrategyAllocation).order_by(StrategyAllocation.strategy_id.asc()).all()
        _apply_critical_drawdown_reduce(rows)
        _ensure_capital_limit(rows)
        _ensure_weight_is_one(rows)
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        db.rollback()
        raise


def bulk_update_strategy_allocations(db: Session, payload: dict) -> dict:
    updates = payload.get("updates") or []
    if not updates:
        raise ValueError("Bulk update için en az 1 strategy gerekli")

    updated_ids: list[str] = []
    requested_state_map: dict[str, str] = {}
    for item in updates:
        strategy_id = _validate_non_empty_strategy_id(item.get("strategy_id"))
        row = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id == strategy_id).first()
        if not row:
            raise ValueError(f"Strategy bulunamadı: {strategy_id}")

        prev_state = _normalized_state(row.state)
        if "capital_weight" in item and item.get("capital_weight") is not None:
            row.capital_weight = _assert_non_negative_numeric("capital_weight", item.get("capital_weight"))
            if row.capital_weight > 1:
                raise ValueError(f"capital_weight 1'i aşamaz ({strategy_id})")
        if "max_capital" in item and item.get("max_capital") is not None:
            row.max_capital = _assert_non_negative_numeric("max_capital", item.get("max_capital"))
        if "current_capital" in item and item.get("current_capital") is not None:
            row.current_capital = _assert_non_negative_numeric("current_capital", item.get("current_capital"))
        if "state" in item and item.get("state"):
            next_state = _normalized_state(item.get("state"), prev_state)
            if _state_change_requires_double_confirm(prev_state, next_state):
                _ensure_double_confirm(item)
            row.state = next_state
            requested_state_map[strategy_id] = next_state

        if row.current_capital > row.max_capital:
            raise ValueError(f"current_capital max_capital değerini aşamaz ({strategy_id})")
        row.updated_at = _now()
        updated_ids.append(strategy_id)

    if payload.get("auto_normalize"):
        _apply_normalize(db.query(StrategyAllocation).order_by(StrategyAllocation.strategy_id.asc()).all())

    try:
        for strategy_id, requested_state in requested_state_map.items():
            if requested_state == "ACTIVE":
                recalculate_strategy_drift(db, strategy_id)

        rows = db.query(StrategyAllocation).order_by(StrategyAllocation.strategy_id.asc()).all()
        enforced = _apply_critical_drawdown_reduce(rows)
        _ensure_capital_limit(rows)
        _ensure_weight_is_one(rows)
        db.commit()
        updated_rows = (
            db.query(StrategyAllocation)
            .filter(StrategyAllocation.strategy_id.in_(updated_ids))
            .order_by(StrategyAllocation.strategy_id.asc())
            .all()
        )
        return {
            "trace_id": f"strategy_alloc_bulk_{uuid4().hex[:10]}",
            "updated_count": len(updated_rows),
            "updated_rows": updated_rows,
            "summary": _collect_summary(rows),
            "enforced_reduce_rows": enforced,
        }
    except Exception:
        db.rollback()
        raise
