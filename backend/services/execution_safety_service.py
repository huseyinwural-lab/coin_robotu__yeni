from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import ExecutionIntent, LiveActivationConfig, PaperPosition, UserExecutionIntent
from services.audit_service import create_audit_log

REASON_TRADING_DISABLED = "TRADING_DISABLED"
REASON_MAX_TOTAL_EXPOSURE_EXCEEDED = "MAX_TOTAL_EXPOSURE_EXCEEDED"
REASON_MAX_ACTIVE_POSITIONS_EXCEEDED = "MAX_ACTIVE_POSITIONS_EXCEEDED"

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


def execution_safety_snapshot(db: Session) -> dict:
    config = get_or_create_execution_safety_state(db)

    open_positions_exposure = _current_open_positions_exposure(db)
    pending_user_exposure, pending_user_count = _pending_user_intent_exposure(db)
    pending_runtime_exposure, pending_runtime_count = _pending_runtime_intent_exposure(db)

    current_total_exposure = open_positions_exposure + pending_user_exposure + pending_runtime_exposure
    active_positions_count = (
        _safe_int(
            db.query(func.count(PaperPosition.id)).filter(func.lower(PaperPosition.status).in_(ACTIVE_POSITION_STATES)).scalar(),
            0,
        )
        + pending_user_count
        + pending_runtime_count
    )

    return {
        "config": config,
        "trading_enabled": bool(getattr(config, "trading_enabled", False)),
        "max_total_exposure": _safe_float(getattr(config, "max_total_exposure", 0.0), 0.0),
        "max_active_positions": _safe_int(getattr(config, "max_active_positions", 0), 0),
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
    }


def _raise_block(
    *,
    reason_code: str,
    message: str,
    source: str,
    proposed_notional: float,
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
    }
    raise ExecutionSafetyViolation(reason_code=reason_code, message=message, details=details)


def assert_execution_open_allowed(db: Session, *, proposed_notional: float, source: str) -> dict:
    snapshot = execution_safety_snapshot(db)
    proposed = max(_safe_float(proposed_notional), 0.0)

    if not bool(snapshot.get("trading_enabled")):
        _raise_block(
            reason_code=REASON_TRADING_DISABLED,
            message="Trading is disabled by kill switch",
            source=source,
            proposed_notional=proposed,
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
            snapshot={**snapshot, "current_active_positions": projected_positions},
        )

    return {
        **snapshot,
        "projected_total_exposure": projected_exposure,
        "projected_active_positions": projected_positions,
    }


def enforce_execution_open_allowed_or_raise(
    db: Session,
    *,
    proposed_notional: float,
    source: str,
    actor_user_id: str | None,
    actor_role: str,
    entity_type: str,
    entity_id: str,
) -> dict:
    try:
        snapshot = assert_execution_open_allowed(db, proposed_notional=proposed_notional, source=source)
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
