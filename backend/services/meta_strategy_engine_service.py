from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from models import ExecutionMetric, SignalEvent, StrategyAllocation
from services.canonical_strategy_registry_service import CANONICAL_STRATEGIES


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


ALLOWED_STATES = {"ACTIVE", "DISABLED"}
DOUBLE_CONFIRM_PRIMARY = "CONFIRM"
DOUBLE_CONFIRM_SECONDARY = "STATE CHANGE"
EXPOSURE_WARNING_THRESHOLD_PCT = 80.0
DRAWDOWN_WARNING_THRESHOLD_PCT = 8.0
DRAWDOWN_ENFORCE_THRESHOLD_PCT = 12.0
DRAWDOWN_REDUCE_RATIO = 0.15
WEIGHT_SUM_TOLERANCE = 0.0001


def _normalize_confidence_for_projection(value: float) -> float:
    raw = _safe_float(value, 0)
    if raw > 1:
        raw = raw / 100
    return max(min(raw, 1), 0)


def _normalize_performance_for_projection(value: float) -> float:
    raw = _safe_float(value, 0)
    normalized = (raw + 100) / 200
    return max(min(normalized, 1), 0)


def _normalize_decay_for_projection(value: float) -> float:
    return max(min(_safe_float(value, 0), 1), 0)


def _compute_weight_projection_metrics(
    *,
    strategy_id: str,
    current_weight: float,
    suggested_weight: float,
    confidence: float,
    performance_norm: float,
    decay: float,
) -> dict:
    delta = round(_safe_float(suggested_weight, 0) - _safe_float(current_weight, 0), 8)
    projected_return_delta_pct = round(delta * (_safe_float(performance_norm, 0) * 40 + _safe_float(confidence, 0) * 20), 4)
    projected_risk_delta_pct = round(delta * ((1 - _safe_float(confidence, 0)) * 25 + _safe_float(decay, 0) * 15), 4)
    return {
        "strategy_id": str(strategy_id),
        "current_weight": round(_safe_float(current_weight, 0), 8),
        "suggested_weight": round(_safe_float(suggested_weight, 0), 8),
        "weight_delta": delta,
        "confidence": round(_safe_float(confidence, 0), 4),
        "performance_norm": round(_safe_float(performance_norm, 0), 4),
        "decay": round(_safe_float(decay, 0), 4),
        "projected_return_delta_pct": projected_return_delta_pct,
        "projected_risk_delta_pct": projected_risk_delta_pct,
    }


def build_projection_from_rebalance_suggestions(suggestions: list[dict]) -> dict:
    rows: list[dict] = []
    total_return_delta = 0.0
    total_risk_delta = 0.0
    for item in suggestions:
        row = _compute_weight_projection_metrics(
            strategy_id=str(item.get("strategy_id") or "unknown_strategy"),
            current_weight=_safe_float(item.get("current_weight"), 0),
            suggested_weight=_safe_float(item.get("suggested_weight"), 0),
            confidence=_normalize_confidence_for_projection(item.get("confidence")),
            performance_norm=max(min(_safe_float(item.get("performance_norm"), 0), 1), 0),
            decay=_normalize_decay_for_projection(item.get("decay")),
        )
        rows.append(row)
        total_return_delta += row["projected_return_delta_pct"]
        total_risk_delta += row["projected_risk_delta_pct"]

    return {
        "rows": rows,
        "projected_portfolio_return_delta_pct": round(total_return_delta, 4),
        "projected_portfolio_risk_delta_pct": round(total_risk_delta, 4),
    }


def build_projection_from_rows(rows: list[StrategyAllocation], target_weights: dict[str, float] | None = None) -> dict:
    planned_weights = target_weights or {}
    payload_rows: list[dict] = []
    total_return_delta = 0.0
    total_risk_delta = 0.0

    for row in rows:
        strategy_id = str(row.strategy_id)
        current_weight = _safe_float(row.capital_weight, 0)
        suggested_weight = _safe_float(planned_weights.get(strategy_id), current_weight)
        projection_row = _compute_weight_projection_metrics(
            strategy_id=strategy_id,
            current_weight=current_weight,
            suggested_weight=suggested_weight,
            confidence=_normalize_confidence_for_projection(row.confidence_score),
            performance_norm=_normalize_performance_for_projection(row.performance_score),
            decay=_normalize_decay_for_projection(row.signal_decay),
        )
        payload_rows.append(projection_row)
        total_return_delta += projection_row["projected_return_delta_pct"]
        total_risk_delta += projection_row["projected_risk_delta_pct"]

    return {
        "rows": payload_rows,
        "projected_portfolio_return_delta_pct": round(total_return_delta, 4),
        "projected_portfolio_risk_delta_pct": round(total_risk_delta, 4),
    }


def _apply_revision_metadata(
    row: StrategyAllocation,
    *,
    actor_id: str | None,
    change_reason: str | None,
    is_new: bool = False,
) -> None:
    if is_new:
        row.revision_id = 1
    else:
        current_revision = int(_safe_float(getattr(row, "revision_id", 1), 1))
        row.revision_id = max(current_revision, 1) + 1
    row.updated_by = str(actor_id or "system")
    row.change_reason = str(change_reason or "manual_update").strip() or "manual_update"
    row.updated_at = _now()


def _normalized_state(value: str | None, fallback: str = "ACTIVE") -> str:
    state = str(value or fallback).upper().strip()
    if state in {"THROTTLED", "PASSIVE", "PASIF", "INACTIVE"}:
        return "DISABLED"
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
    requested = _normalized_state(requested_state, state) if requested_state else None
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
        "revision_id": int(_safe_float(getattr(row, "revision_id", 1), 1)),
        "updated_by": str(getattr(row, "updated_by", "system") or "system"),
        "change_reason": str(getattr(row, "change_reason", "") or ""),
        "updated_at": row.updated_at,
        "state_reason_code": code,
        "state_reason_detail": detail,
        "is_drift_override": is_override,
        "drawdown_pct": drawdown_pct,
        "exposure_ratio_pct": exposure_ratio_pct,
        "suggested_reduced_capital": suggested_capital,
        "is_auto_reduce_candidate": drawdown_pct >= DRAWDOWN_WARNING_THRESHOLD_PCT,
        "trend_5d_line": "5g trend unavailable",
        "trend_5d_available": False,
    }


def _compute_5d_trend_summary(db: Session, row: StrategyAllocation) -> tuple[str, bool]:
    lookback_from = _now() - timedelta(days=5)
    strategy_id = str(row.strategy_id)

    exec_old = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.strategy_type == strategy_id, ExecutionMetric.created_at >= lookback_from)
        .order_by(ExecutionMetric.created_at.asc())
        .first()
    )
    signal_old = (
        db.query(SignalEvent)
        .filter(SignalEvent.strategy_id == strategy_id, SignalEvent.generated_at >= lookback_from)
        .order_by(SignalEvent.generated_at.asc())
        .first()
    )

    if not exec_old and not signal_old:
        return "5g trend unavailable", False

    current_quality = _safe_float(row.execution_quality_score, 0)
    old_quality = _safe_float(exec_old.execution_quality_score if exec_old else None, current_quality)
    quality_delta = round(current_quality - old_quality, 1)

    current_perf = _safe_float(row.performance_score, 0)
    if exec_old or signal_old:
        old_conf = _safe_float(signal_old.confidence if signal_old else None, _safe_float(row.confidence_score, 0))
        old_expected = max(0.5, old_conf * 6)
        old_realized = round((_safe_float(exec_old.execution_quality_score if exec_old else old_quality, 0) - 50) / 10, 4)
        old_perf = round((old_realized / max(old_expected, 0.1)) * 100, 4)
    else:
        old_perf = current_perf
    perf_delta = round(current_perf - old_perf, 1)

    current_decay = _safe_float(row.signal_decay, 0)
    old_decay = 1.0 if signal_old and str(signal_old.signal).lower() == "none" else 0.0
    decay_delta = round(current_decay - old_decay, 1)

    quality_arrow = "↑" if quality_delta >= 0 else "↓"
    perf_arrow = "↑" if perf_delta >= 0 else "↓"
    decay_arrow = "↑" if decay_delta >= 0 else "↓"

    line = (
        f"5g trend → quality {quality_arrow}{abs(quality_delta)}, "
        f"perf {perf_arrow}{abs(perf_delta)}, "
        f"decay {decay_arrow}{abs(decay_delta)}"
    )
    return line, True


def _build_rebalance_suggestions(rows: list[StrategyAllocation], selected_ids: list[str] | None = None) -> dict:
    if not rows:
        return {
            "status": "empty",
            "message": "Suggestion için strategy bulunamadı",
            "suggestions": [],
            "selection_count": 0,
            "trace_id": f"strategy_alloc_rebalance_{uuid4().hex[:10]}",
        }

    selected_set = {str(item).strip() for item in (selected_ids or []) if str(item).strip()}
    target_rows = [row for row in rows if row.strategy_id in selected_set] if selected_set else list(rows)
    if not target_rows:
        target_rows = list(rows)

    score_rows = []
    for row in target_rows:
        confidence = _safe_float(row.confidence_score, 0)
        confidence_norm = max(min(confidence if confidence <= 1 else confidence / 100, 1), 0)
        performance = _safe_float(row.performance_score, 0)
        performance_norm = max(min((performance + 100) / 200, 1), 0)
        decay_norm = max(min(_safe_float(row.signal_decay, 0), 1), 0)

        score = (confidence_norm * 0.45) + (performance_norm * 0.4) + ((1 - decay_norm) * 0.15)
        score_rows.append(
            {
                "strategy_id": row.strategy_id,
                "current_weight": round(_safe_float(row.capital_weight, 0), 8),
                "confidence": round(confidence_norm, 4),
                "performance_norm": round(performance_norm, 4),
                "decay": round(decay_norm, 4),
                "score": max(score, 0.0001),
            }
        )

    total_score = sum(item["score"] for item in score_rows)
    current_budget = sum(item["current_weight"] for item in score_rows)
    budget = current_budget if selected_set else 1.0
    if budget <= 0:
        budget = 1.0 if not selected_set else max(current_budget, 0.0001)

    suggestions = []
    for item in score_rows:
        suggested_weight = round((item["score"] / total_score) * budget, 8)
        suggestions.append(
            {
                **item,
                "suggested_weight": suggested_weight,
                "delta": round(suggested_weight - item["current_weight"], 8),
            }
        )

    if suggestions:
        suggestions[-1]["suggested_weight"] = round(
            budget - sum(row["suggested_weight"] for row in suggestions[:-1]),
            8,
        )
        suggestions[-1]["delta"] = round(suggestions[-1]["suggested_weight"] - suggestions[-1]["current_weight"], 8)

    return {
        "status": "success",
        "message": "Rule-based rebalance suggestion hazır",
        "suggestions": suggestions,
        "selection_count": len(selected_set),
        "applied_budget": round(budget, 8),
        "trace_id": f"strategy_alloc_rebalance_{uuid4().hex[:10]}",
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
    _ = (before_state, after_state)
    return False


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
        revision_id=1,
        updated_by="system",
        change_reason="system_auto_create",
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

    row.state = _normalized_state(row.state, "DISABLED")

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
    canonical_ids = list(CANONICAL_STRATEGIES.keys())
    default_weight = round(1 / max(len(canonical_ids), 1), 8)
    for strategy_id in canonical_ids:
        row = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id == strategy_id).first()
        if not row:
            row = StrategyAllocation(
                strategy_id=strategy_id,
                capital_weight=default_weight,
                max_capital=100000,
                current_capital=0,
                confidence_score=0,
                performance_score=0,
                state="DISABLED",
                expected_return=2.0,
                realized_return=0,
                signal_decay=0,
                execution_quality_score=75,
                revision_id=1,
                updated_by="system",
                change_reason="canonical_auto_seed",
                updated_at=_now(),
            )
            db.add(row)
        else:
            row.state = _normalized_state(row.state, "DISABLED")

    rows = (
        db.query(StrategyAllocation)
        .filter(StrategyAllocation.strategy_id.in_(canonical_ids))
        .order_by(StrategyAllocation.strategy_id.asc())
        .limit(limit)
        .all()
    )
    for row in rows:
        recalculate_strategy_drift(db, row.strategy_id)
    db.commit()
    return (
        db.query(StrategyAllocation)
        .filter(StrategyAllocation.strategy_id.in_(canonical_ids))
        .order_by(StrategyAllocation.strategy_id.asc())
        .limit(limit)
        .all()
    )


def list_strategy_allocation_dashboard_rows(db: Session, limit: int = 200) -> list[dict]:
    rows = list_strategy_allocations(db, limit=limit)
    payloads = []
    for row in rows:
        payload = _serialize_strategy_allocation_row(row)
        trend_line, trend_available = _compute_5d_trend_summary(db, row)
        payload["trend_5d_line"] = trend_line
        payload["trend_5d_available"] = trend_available
        payloads.append(payload)
    return payloads


def build_strategy_allocation_row_payload(
    row: StrategyAllocation,
    *,
    db: Session | None = None,
    requested_state: str | None = None,
) -> dict:
    payload = _serialize_strategy_allocation_row(row, requested_state=requested_state)
    if db is None:
        return payload
    trend_line, trend_available = _compute_5d_trend_summary(db, row)
    payload["trend_5d_line"] = trend_line
    payload["trend_5d_available"] = trend_available
    return payload


def generate_rebalance_suggestions(db: Session, *, strategy_ids: list[str] | None = None) -> dict:
    rows = list_strategy_allocations(db, limit=500)
    return _build_rebalance_suggestions(rows, selected_ids=strategy_ids)


def get_strategy_allocation_summary(db: Session) -> dict:
    rows = list_strategy_allocations(db, limit=500)
    return _collect_summary(rows)


def create_strategy_allocation(
    db: Session,
    payload: dict,
    *,
    actor_id: str | None = None,
    change_reason: str | None = None,
) -> StrategyAllocation:
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
        revision_id=1,
        updated_by=str(actor_id or "system"),
        change_reason=str(change_reason or "manual_create"),
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


def delete_strategy_allocation(
    db: Session,
    strategy_id: str,
    *,
    auto_normalize: bool = False,
    actor_id: str | None = None,
    change_reason: str | None = None,
) -> dict:
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
            for item in remaining:
                _apply_revision_metadata(
                    item,
                    actor_id=actor_id,
                    change_reason=change_reason or "delete_auto_normalize",
                )
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


def normalize_strategy_allocations(
    db: Session,
    *,
    actor_id: str | None = None,
    change_reason: str | None = None,
) -> dict:
    rows = db.query(StrategyAllocation).order_by(StrategyAllocation.strategy_id.asc()).all()
    if not rows:
        raise ValueError("Normalize için strategy allocation satırı bulunamadı")

    try:
        _apply_normalize(rows)
        for row in rows:
            _apply_revision_metadata(
                row,
                actor_id=actor_id,
                change_reason=change_reason or "normalize_weights",
            )
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


def update_strategy_allocation(
    db: Session,
    strategy_id: str,
    payload: dict,
    *,
    actor_id: str | None = None,
    change_reason: str | None = None,
) -> StrategyAllocation:
    row = get_existing_strategy_allocation(db, strategy_id)
    previous_state = _normalized_state(row.state)

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

    try:
        rows = db.query(StrategyAllocation).order_by(StrategyAllocation.strategy_id.asc()).all()
        _apply_critical_drawdown_reduce(rows)
        _ensure_capital_limit(rows)
        _ensure_weight_is_one(rows)
        _apply_revision_metadata(
            row,
            actor_id=actor_id,
            change_reason=change_reason or "update_allocation",
        )
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        db.rollback()
        raise


def toggle_strategy_throttle(
    db: Session,
    strategy_id: str,
    payload: dict,
    *,
    actor_id: str | None = None,
    change_reason: str | None = None,
) -> StrategyAllocation:
    row = get_existing_strategy_allocation(db, strategy_id)
    _ensure_double_confirm(payload)
    row.state = "ACTIVE" if _normalized_state(row.state) == "DISABLED" else "DISABLED"
    try:
        rows = db.query(StrategyAllocation).order_by(StrategyAllocation.strategy_id.asc()).all()
        _apply_critical_drawdown_reduce(rows)
        _ensure_capital_limit(rows)
        _ensure_weight_is_one(rows)
        _apply_revision_metadata(
            row,
            actor_id=actor_id,
            change_reason=change_reason or "toggle_throttle",
        )
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        db.rollback()
        raise


def bulk_update_strategy_allocations(
    db: Session,
    payload: dict,
    *,
    actor_id: str | None = None,
    change_reason: str | None = None,
) -> dict:
    updates = payload.get("updates") or []
    if not updates:
        raise ValueError("Bulk update için en az 1 strategy gerekli")

    updated_ids: list[str] = []
    requested_state_map: dict[str, str] = {}
    target_weight_map: dict[str, float] = {}
    touched_rows_by_id: dict[str, StrategyAllocation] = {}
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
            target_weight_map[strategy_id] = _safe_float(row.capital_weight, 0)
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
        updated_ids.append(strategy_id)
        touched_rows_by_id[strategy_id] = row

    if payload.get("auto_normalize"):
        all_rows_for_normalize = db.query(StrategyAllocation).order_by(StrategyAllocation.strategy_id.asc()).all()
        _apply_normalize(all_rows_for_normalize)
        for item in all_rows_for_normalize:
            touched_rows_by_id[item.strategy_id] = item
            target_weight_map[item.strategy_id] = _safe_float(item.capital_weight, 0)

    try:
        rows = db.query(StrategyAllocation).order_by(StrategyAllocation.strategy_id.asc()).all()
        enforced = _apply_critical_drawdown_reduce(rows)
        _ensure_capital_limit(rows)
        _ensure_weight_is_one(rows)
        for item in touched_rows_by_id.values():
            _apply_revision_metadata(
                item,
                actor_id=actor_id,
                change_reason=change_reason or "bulk_update_allocation",
            )

        projection_preview = build_projection_from_rows(rows, target_weights=target_weight_map)
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
            "projection_preview": projection_preview,
        }
    except Exception:
        db.rollback()
        raise
