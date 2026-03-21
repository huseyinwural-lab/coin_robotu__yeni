from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.policy.quote_policy import extract_quote
from models import AuditLog, ExecutionIntent, ExecutionMetric, LiveActivationConfig, PaperPosition, UserExecutionIntent
from services.quote_asset_constraints import INVALID_QUOTE_ASSET_ERROR_CODE, INVALID_QUOTE_ASSET_MESSAGE
from services.audit_service import create_audit_log
from services.observability_service import collect_observability_snapshot
from services.system_alert_service import create_system_alert

REASON_TRADING_DISABLED = "TRADING_DISABLED"
REASON_MAX_TOTAL_EXPOSURE_EXCEEDED = "MAX_TOTAL_EXPOSURE_EXCEEDED"
REASON_MAX_ACTIVE_POSITIONS_EXCEEDED = "MAX_ACTIVE_POSITIONS_EXCEEDED"
REASON_CANARY_SYMBOL_BLOCKED = "CANARY_SYMBOL_BLOCKED"
REASON_CANARY_CAPITAL_LIMIT_EXCEEDED = "CANARY_CAPITAL_LIMIT_EXCEEDED"
REASON_CANARY_MAX_POSITIONS_EXCEEDED = "CANARY_MAX_POSITIONS_EXCEEDED"
REASON_INVALID_QUOTE_ASSET = INVALID_QUOTE_ASSET_ERROR_CODE

CANARY_ALERT_ERROR_RATE_THRESHOLD = 0.05
CANARY_ALERT_REJECT_RATE_THRESHOLD = 0.35
CANARY_ALERT_LATENCY_P95_MS_THRESHOLD = 1500.0

ACTIVE_POSITION_STATES = {"open"}
PENDING_USER_INTENT_STATES = {"QUEUED", "APPROVED"}
PENDING_RUNTIME_INTENT_STATES = {"pending", "created", "queued"}


@dataclass
class ExecutionSafetyViolation(Exception):
    reason_code: str
    message: str
    details: dict


def _safe_float(value: float | int | None, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: int | float | None, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_symbols(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for item in list(values or []):
        symbol = str(item or "").strip().upper()
        if symbol and symbol not in normalized:
            normalized.append(symbol)
    return normalized


def _is_canary_symbol(symbol: str, allowed_symbols: list[str]) -> bool:
    if not allowed_symbols:
        return True
    return str(symbol or "").strip().upper() in allowed_symbols


def get_or_create_execution_safety_state(db: Session) -> LiveActivationConfig:
    row = db.query(LiveActivationConfig).filter(LiveActivationConfig.id == "global").first()
    if row is not None:
        return row

    row = LiveActivationConfig(id="global")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _current_open_positions_exposure(db: Session) -> float:
    rows = (
        db.query(PaperPosition.entry_price, PaperPosition.quantity)
        .filter(func.lower(PaperPosition.status).in_(ACTIVE_POSITION_STATES))
        .all()
    )
    total = 0.0
    for entry_price, quantity in rows:
        total += abs(_safe_float(entry_price) * _safe_float(quantity))
    return float(total)


def _pending_user_intent_exposure(db: Session) -> tuple[float, int]:
    rows = (
        db.query(UserExecutionIntent.notional)
        .filter(
            UserExecutionIntent.intent_type == "OPEN_POSITION",
            UserExecutionIntent.status.in_(PENDING_USER_INTENT_STATES),
        )
        .all()
    )
    total = sum(abs(_safe_float(item[0])) for item in rows)
    return float(total), len(rows)


def _pending_runtime_intent_exposure(db: Session) -> tuple[float, int]:
    rows = (
        db.query(ExecutionIntent.quantity)
        .filter(func.lower(ExecutionIntent.status).in_(PENDING_RUNTIME_INTENT_STATES))
        .all()
    )
    total = sum(abs(_safe_float(item[0])) for item in rows)
    return float(total), len(rows)


def _canary_open_positions_state(db: Session, symbols: list[str]) -> tuple[float, int]:
    rows = (
        db.query(PaperPosition.symbol, PaperPosition.entry_price, PaperPosition.quantity)
        .filter(func.lower(PaperPosition.status).in_(ACTIVE_POSITION_STATES))
        .all()
    )
    total = 0.0
    count = 0
    for symbol, entry_price, quantity in rows:
        if symbols and not _is_canary_symbol(str(symbol or ""), symbols):
            continue
        total += abs(_safe_float(entry_price) * _safe_float(quantity))
        count += 1
    return float(total), count


def _canary_pending_user_intents_state(db: Session, symbols: list[str]) -> tuple[float, int]:
    rows = (
        db.query(UserExecutionIntent.symbol, UserExecutionIntent.notional)
        .filter(
            UserExecutionIntent.intent_type == "OPEN_POSITION",
            UserExecutionIntent.status.in_(PENDING_USER_INTENT_STATES),
        )
        .all()
    )
    total = 0.0
    count = 0
    for symbol, notional in rows:
        if symbols and not _is_canary_symbol(str(symbol or ""), symbols):
            continue
        total += abs(_safe_float(notional))
        count += 1
    return float(total), count


def _canary_pending_runtime_intents_state(db: Session, symbols: list[str]) -> tuple[float, int]:
    rows = (
        db.query(ExecutionIntent.symbol, ExecutionIntent.quantity)
        .filter(func.lower(ExecutionIntent.status).in_(PENDING_RUNTIME_INTENT_STATES))
        .all()
    )
    total = 0.0
    count = 0
    for symbol, quantity in rows:
        if symbols and not _is_canary_symbol(str(symbol or ""), symbols):
            continue
        total += abs(_safe_float(quantity))
        count += 1
    return float(total), count


def execution_safety_snapshot(db: Session) -> dict:
    config = get_or_create_execution_safety_state(db)
    canary_symbols = _normalize_symbols(getattr(config, "canary_symbols", []))
    canary_enabled = bool(getattr(config, "canary_enabled", False))

    open_positions_exposure = _current_open_positions_exposure(db)
    pending_user_exposure, pending_user_count = _pending_user_intent_exposure(db)
    pending_runtime_exposure, pending_runtime_count = _pending_runtime_intent_exposure(db)

    canary_open_exposure, canary_open_count = _canary_open_positions_state(db, canary_symbols)

    current_total_exposure = open_positions_exposure + pending_user_exposure + pending_runtime_exposure
    active_positions_count = (
        _safe_int(
            db.query(func.count(PaperPosition.id)).filter(func.lower(PaperPosition.status).in_(ACTIVE_POSITION_STATES)).scalar(),
            0,
        )
        + pending_user_count
        + pending_runtime_count
    )

    capital_factor = max(_safe_float(getattr(config, "max_position_pct", 0.1), 0.1), 0.01)
    canary_capital_used = canary_open_exposure * capital_factor
    canary_position_count = canary_open_count

    return {
        "config": config,
        "trading_enabled": bool(getattr(config, "trading_enabled", False)),
        "max_total_exposure": _safe_float(getattr(config, "max_total_exposure", 0.0), 0.0),
        "max_active_positions": _safe_int(getattr(config, "max_active_positions", 0), 0),
        "max_position_pct": _safe_float(getattr(config, "max_position_pct", 0.1), 0.1),
        "open_positions_exposure": open_positions_exposure,
        "pending_user_exposure": pending_user_exposure,
        "pending_runtime_exposure": pending_runtime_exposure,
        "current_total_exposure": current_total_exposure,
        "open_positions_count": _safe_int(
            db.query(func.count(PaperPosition.id)).filter(func.lower(PaperPosition.status).in_(ACTIVE_POSITION_STATES)).scalar(),
            0,
        ),
        "pending_user_intents_count": pending_user_count,
        "pending_runtime_intents_count": pending_runtime_count,
        "current_active_positions": active_positions_count,
        "canary_enabled": canary_enabled,
        "canary_symbols": canary_symbols,
        "canary_max_capital_usdt": _safe_float(getattr(config, "canary_max_capital_usdt", 50), 50.0),
        "canary_max_positions": _safe_int(getattr(config, "canary_max_positions", 1), 1),
        "canary_capital_used": canary_capital_used,
        "canary_position_count": canary_position_count,
    }


def _raise_block(
    *,
    reason_code: str,
    message: str,
    source: str,
    proposed_notional: float,
    symbol: str,
    snapshot: dict,
) -> None:
    details = {
        "reason_code": reason_code,
        "source": source,
        "proposed_notional": round(proposed_notional, 6),
        "current_total_exposure": round(_safe_float(snapshot.get("current_total_exposure")), 6),
        "max_total_exposure": round(_safe_float(snapshot.get("max_total_exposure")), 6),
        "current_active_positions": _safe_int(snapshot.get("current_active_positions")),
        "max_active_positions": _safe_int(snapshot.get("max_active_positions")),
        "trading_enabled": bool(snapshot.get("trading_enabled")),
        "symbol": str(symbol or "").upper(),
        "canary_enabled": bool(snapshot.get("canary_enabled")),
        "canary_symbols": list(snapshot.get("canary_symbols") or []),
        "canary_capital_used": round(_safe_float(snapshot.get("canary_capital_used")), 6),
        "canary_max_capital_usdt": round(_safe_float(snapshot.get("canary_max_capital_usdt")), 6),
        "canary_position_count": _safe_int(snapshot.get("canary_position_count")),
        "canary_max_positions": _safe_int(snapshot.get("canary_max_positions")),
    }
    raise ExecutionSafetyViolation(reason_code=reason_code, message=message, details=details)


def assert_execution_open_allowed(db: Session, *, proposed_notional: float, source: str, symbol: str = "") -> dict:
    snapshot = execution_safety_snapshot(db)
    proposed = max(_safe_float(proposed_notional), 0.0)
    normalized_symbol = str(symbol or "").strip().upper()

    if normalized_symbol and extract_quote(normalized_symbol) is None:
        _raise_block(
            reason_code=REASON_INVALID_QUOTE_ASSET,
            message=INVALID_QUOTE_ASSET_MESSAGE,
            source=source,
            proposed_notional=proposed,
            symbol=normalized_symbol,
            snapshot=snapshot,
        )

    if bool(snapshot.get("canary_enabled")):
        canary_symbols = list(snapshot.get("canary_symbols") or [])
        if canary_symbols and normalized_symbol and normalized_symbol not in canary_symbols:
            _raise_block(
                reason_code=REASON_CANARY_SYMBOL_BLOCKED,
                message="Symbol is outside canary whitelist",
                source=source,
                proposed_notional=proposed,
                symbol=normalized_symbol,
                snapshot=snapshot,
            )

        canary_cap_limit = _safe_float(snapshot.get("canary_max_capital_usdt"), 0.0)
        capital_factor = max(_safe_float(snapshot.get("max_position_pct"), 0.1), 0.01)
        projected_canary_capital = _safe_float(snapshot.get("canary_capital_used"), 0.0) + (proposed * capital_factor)
        if canary_cap_limit > 0 and projected_canary_capital > canary_cap_limit:
            _raise_block(
                reason_code=REASON_CANARY_CAPITAL_LIMIT_EXCEEDED,
                message="Projected canary capital exceeds limit",
                source=source,
                proposed_notional=proposed,
                symbol=normalized_symbol,
                snapshot={**snapshot, "canary_capital_used": projected_canary_capital},
            )

        canary_max_positions = _safe_int(snapshot.get("canary_max_positions"), 0)
        projected_canary_positions = _safe_int(snapshot.get("canary_position_count"), 0) + 1
        if canary_max_positions >= 0 and projected_canary_positions > canary_max_positions:
            _raise_block(
                reason_code=REASON_CANARY_MAX_POSITIONS_EXCEEDED,
                message="Projected canary positions exceeds limit",
                source=source,
                proposed_notional=proposed,
                symbol=normalized_symbol,
                snapshot={**snapshot, "canary_position_count": projected_canary_positions},
            )

    if not bool(snapshot.get("trading_enabled")):
        _raise_block(
            reason_code=REASON_TRADING_DISABLED,
            message="Trading is disabled by kill switch",
            source=source,
            proposed_notional=proposed,
            symbol=normalized_symbol,
            snapshot=snapshot,
        )

    max_total_exposure = _safe_float(snapshot.get("max_total_exposure"), 0.0)
    projected_exposure = _safe_float(snapshot.get("current_total_exposure"), 0.0) + proposed
    if max_total_exposure > 0 and projected_exposure > max_total_exposure:
        _raise_block(
            reason_code=REASON_MAX_TOTAL_EXPOSURE_EXCEEDED,
            message="Projected total exposure exceeds limit",
            source=source,
            proposed_notional=proposed,
            symbol=normalized_symbol,
            snapshot={**snapshot, "current_total_exposure": projected_exposure},
        )

    max_active_positions = _safe_int(snapshot.get("max_active_positions"), 0)
    projected_positions = _safe_int(snapshot.get("current_active_positions"), 0) + 1
    if max_active_positions > 0 and projected_positions > max_active_positions:
        _raise_block(
            reason_code=REASON_MAX_ACTIVE_POSITIONS_EXCEEDED,
            message="Projected active positions exceeds limit",
            source=source,
            proposed_notional=proposed,
            symbol=normalized_symbol,
            snapshot={**snapshot, "current_active_positions": projected_positions},
        )

    return {
        **snapshot,
        "projected_total_exposure": projected_exposure,
        "projected_active_positions": projected_positions,
        "projected_canary_capital": _safe_float(snapshot.get("canary_capital_used"), 0.0)
        + (proposed * max(_safe_float(snapshot.get("max_position_pct"), 0.1), 0.01)),
        "projected_canary_positions": _safe_int(snapshot.get("canary_position_count"), 0) + 1,
    }


def enforce_execution_open_allowed_or_raise(
    db: Session,
    *,
    proposed_notional: float,
    symbol: str = "",
    source: str,
    actor_user_id: str | None,
    actor_role: str,
    entity_type: str,
    entity_id: str,
) -> dict:
    try:
        snapshot = assert_execution_open_allowed(db, proposed_notional=proposed_notional, source=source, symbol=symbol)
        return snapshot
    except ExecutionSafetyViolation as exc:
        create_audit_log(
            db,
            action="EXECUTION_BLOCKED",
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            severity="warning",
            details={
                "reason_code": exc.reason_code,
                "message": exc.message,
                **(exc.details or {}),
            },
        )
        raise


def _recent_canary_violations(db: Session, *, minutes: int = 60) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(minutes, 1))
    rows = (
        db.query(AuditLog.details)
        .filter(AuditLog.action == "EXECUTION_BLOCKED", AuditLog.created_at >= cutoff)
        .order_by(AuditLog.created_at.desc())
        .limit(2000)
        .all()
    )
    total = 0
    for (details,) in rows:
        reason_code = str((details or {}).get("reason_code") or "")
        if reason_code.startswith("CANARY_"):
            total += 1
    return total


def _canary_metrics_snapshot(db: Session, snapshot: dict, *, window_minutes: int = 60) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(window_minutes, 1))
    canary_symbols = set(snapshot.get("canary_symbols") or [])

    obs = collect_observability_snapshot(db, minutes=min(max(window_minutes, 1), 60))
    error_rate = float(obs.get("error_rate", 0.0) or 0.0)
    latency_p95 = float(obs.get("latency_ms_p95", 0.0) or 0.0)

    order_rows = (
        db.query(ExecutionMetric.symbol, ExecutionMetric.final_status)
        .filter(ExecutionMetric.created_at >= cutoff)
        .all()
    )
    filtered_orders = [
        row
        for row in order_rows
        if (not canary_symbols) or (str(row[0] or "").upper() in canary_symbols)
    ]
    total_orders = len(filtered_orders)
    failed_orders = len([row for row in filtered_orders if str(row[1] or "").upper() not in {"FILLED", "PARTIALLY_FILLED"}])
    order_fail_rate = (failed_orders / total_orders) if total_orders else 0.0

    intent_rows = (
        db.query(UserExecutionIntent.symbol, UserExecutionIntent.status, UserExecutionIntent.reject_reason_codes)
        .filter(UserExecutionIntent.created_at >= cutoff, UserExecutionIntent.intent_type == "OPEN_POSITION")
        .all()
    )
    filtered_intents = [
        row
        for row in intent_rows
        if (not canary_symbols) or (str(row[0] or "").upper() in canary_symbols)
    ]
    total_intents = len(filtered_intents)
    rejected_intents = len(
        [
            row
            for row in filtered_intents
            if str(row[1] or "").upper() in {"REJECTED", "REJECTED_BY_POLICY"}
            or any(str(code).startswith("CANARY_") for code in (row[2] or []))
        ]
    )
    reject_rate = (rejected_intents / total_intents) if total_intents else 0.0

    pnl_rows = (
        db.query(PaperPosition.symbol, PaperPosition.unrealized_pnl)
        .filter(func.lower(PaperPosition.status).in_(ACTIVE_POSITION_STATES))
        .all()
    )
    pnl_sum = sum(
        _safe_float(pnl)
        for symbol, pnl in pnl_rows
        if (not canary_symbols) or (str(symbol or "").upper() in canary_symbols)
    )
    capital_used = _safe_float(snapshot.get("canary_capital_used"), 0.0)
    pnl_drift = abs(pnl_sum) / capital_used if capital_used > 0 else 0.0

    return {
        "error_rate": round(error_rate, 6),
        "latency_ms_p95": round(latency_p95, 2),
        "order_fail_rate": round(order_fail_rate, 6),
        "reject_rate": round(reject_rate, 6),
        "pnl_drift": round(pnl_drift, 6),
    }


def _emit_canary_alerts(db: Session, *, metrics: dict, symbols: list[str]) -> list[str]:
    alert_ids: list[str] = []
    symbol_key = ",".join(symbols) if symbols else "all"

    if float(metrics.get("error_rate", 0.0)) >= CANARY_ALERT_ERROR_RATE_THRESHOLD:
        alert = create_system_alert(
            db,
            alert_type="canary_error_spike",
            severity="CRITICAL",
            message="Canary error rate spike detected",
            details={"metrics": metrics, "symbols": symbols},
            entity_key=symbol_key,
            root_cause_code="CANARY_ERROR_SPIKE",
            dedupe_window_seconds=300,
        )
        alert_ids.append(alert.id)

    if float(metrics.get("reject_rate", 0.0)) >= CANARY_ALERT_REJECT_RATE_THRESHOLD:
        alert = create_system_alert(
            db,
            alert_type="canary_reject_spike",
            severity="WARNING",
            message="Canary reject rate spike detected",
            details={"metrics": metrics, "symbols": symbols},
            entity_key=symbol_key,
            root_cause_code="CANARY_REJECT_SPIKE",
            dedupe_window_seconds=300,
        )
        alert_ids.append(alert.id)

    if float(metrics.get("latency_ms_p95", 0.0)) >= CANARY_ALERT_LATENCY_P95_MS_THRESHOLD:
        alert = create_system_alert(
            db,
            alert_type="canary_latency_spike",
            severity="WARNING",
            message="Canary latency spike detected",
            details={"metrics": metrics, "symbols": symbols},
            entity_key=symbol_key,
            root_cause_code="CANARY_LATENCY_SPIKE",
            dedupe_window_seconds=300,
        )
        alert_ids.append(alert.id)

    return alert_ids


def canary_status_snapshot(db: Session, *, with_alerts: bool = True) -> dict:
    snapshot = execution_safety_snapshot(db)
    metrics = _canary_metrics_snapshot(db, snapshot)
    symbols = list(snapshot.get("canary_symbols") or [])
    alert_ids = _emit_canary_alerts(db, metrics=metrics, symbols=symbols) if with_alerts else []

    return {
        "enabled": bool(snapshot.get("canary_enabled")),
        "active_symbols": symbols,
        "capital_used": round(_safe_float(snapshot.get("canary_capital_used")), 6),
        "position_count": _safe_int(snapshot.get("canary_position_count")),
        "violations": _recent_canary_violations(db, minutes=60),
        "error_rate": metrics["error_rate"],
        "latency_ms_p95": metrics["latency_ms_p95"],
        "order_fail_rate": metrics["order_fail_rate"],
        "reject_rate": metrics["reject_rate"],
        "pnl_drift": metrics["pnl_drift"],
        "alert_ids": alert_ids,
    }


def update_execution_safety_state(
    db: Session,
    *,
    trading_enabled: bool,
    reason: str | None,
    requested_by: str | None,
    effective_at: str | None,
    actor_user_id: str,
    actor_role: str,
    max_total_exposure: float | None = None,
    max_active_positions: int | None = None,
) -> dict:
    config = get_or_create_execution_safety_state(db)
    previous = {
        "trading_enabled": bool(getattr(config, "trading_enabled", False)),
        "max_total_exposure": _safe_float(getattr(config, "max_total_exposure", 0.0)),
        "max_active_positions": _safe_int(getattr(config, "max_active_positions", 0)),
    }

    config.trading_enabled = bool(trading_enabled)
    if max_total_exposure is not None:
        config.max_total_exposure = max(_safe_float(max_total_exposure), 0.0)
    if max_active_positions is not None:
        config.max_active_positions = max(_safe_int(max_active_positions), 0)
    config.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(config)

    current = {
        "trading_enabled": bool(getattr(config, "trading_enabled", False)),
        "max_total_exposure": _safe_float(getattr(config, "max_total_exposure", 0.0)),
        "max_active_positions": _safe_int(getattr(config, "max_active_positions", 0)),
    }
    changed = previous != current

    create_audit_log(
        db,
        action="ADMIN_KILL_SWITCH_UPDATED" if changed else "ADMIN_KILL_SWITCH_NOOP",
        entity_type="execution_safety_state",
        entity_id="global",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning" if not current["trading_enabled"] else "info",
        details={
            "reason_code": REASON_TRADING_DISABLED if not current["trading_enabled"] else "TRADING_ENABLED",
            "reason": reason,
            "requested_by": requested_by,
            "effective_at": effective_at,
            "previous": previous,
            "current": current,
            "idempotent": not changed,
        },
    )

    snapshot = execution_safety_snapshot(db)
    return {
        "idempotent": not changed,
        "reason_code": REASON_TRADING_DISABLED if not snapshot["trading_enabled"] else "TRADING_ENABLED",
        **snapshot,
    }
