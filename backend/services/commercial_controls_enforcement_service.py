from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from models import CommercialOperationalControlState
from services.audit_service import create_audit_log

COMMERCIAL_TRADING_DISABLED = "COMMERCIAL_TRADING_DISABLED"
COMMERCIAL_EMERGENCY_STOP = "COMMERCIAL_EMERGENCY_STOP"
COMMERCIAL_CAPITAL_FROZEN = "COMMERCIAL_CAPITAL_FROZEN"
COMMERCIAL_WITHDRAW_LOCKED = "COMMERCIAL_WITHDRAW_LOCKED"

_REASON_MESSAGES = {
    COMMERCIAL_TRADING_DISABLED: "Trading disabled by commercial operational control",
    COMMERCIAL_EMERGENCY_STOP: "Emergency stop active for user",
    COMMERCIAL_CAPITAL_FROZEN: "Capital is frozen for user",
    COMMERCIAL_WITHDRAW_LOCKED: "Withdraw/fund transfer locked for user",
}

_TRADE_OPERATIONS = {"trade_intent", "execution_submit", "position_increase", "capital_allocation"}
_WITHDRAW_OPERATIONS = {"withdraw", "fund_transfer_out", "fund_exit"}


@dataclass
class CommercialControlViolation(Exception):
    reason_code: str
    message: str
    details: dict

    def __str__(self) -> str:
        return self.reason_code


def _default_state(user_id: str):
    return {
        "user_id": user_id,
        "trading_enabled": True,
        "capital_frozen": False,
        "withdraw_locked": False,
        "emergency_stop": False,
    }


def get_user_operational_control_state(db: Session, user_id: str) -> dict:
    row = db.query(CommercialOperationalControlState).filter(CommercialOperationalControlState.user_id == user_id).first()
    if row is None:
        return _default_state(user_id)
    return {
        "user_id": user_id,
        "trading_enabled": bool(getattr(row, "trading_enabled", True)),
        "capital_frozen": bool(getattr(row, "capital_frozen", False)),
        "withdraw_locked": bool(getattr(row, "withdraw_locked", False)),
        "emergency_stop": bool(getattr(row, "emergency_stop", False)),
    }


def _resolve_reason_code(state: dict, operation: str) -> str | None:
    operation_code = str(operation or "trade_intent").strip().lower()
    if bool(state.get("emergency_stop")) and operation_code in (_TRADE_OPERATIONS | _WITHDRAW_OPERATIONS):
        return COMMERCIAL_EMERGENCY_STOP
    if operation_code in _TRADE_OPERATIONS:
        if not bool(state.get("trading_enabled", True)):
            return COMMERCIAL_TRADING_DISABLED
        if bool(state.get("capital_frozen")):
            return COMMERCIAL_CAPITAL_FROZEN
    if operation_code in _WITHDRAW_OPERATIONS and bool(state.get("withdraw_locked")):
        return COMMERCIAL_WITHDRAW_LOCKED
    return None


def enforce_commercial_control_or_raise(
    db: Session,
    *,
    user_id: str,
    operation: str,
    actor_user_id: str,
    actor_role: str,
    entity_type: str,
    entity_id: str,
    source: str,
    metadata: dict | None = None,
) -> dict:
    state = get_user_operational_control_state(db, user_id)
    reason_code = _resolve_reason_code(state, operation)
    if reason_code is None:
        return state

    message = _REASON_MESSAGES.get(reason_code, "Commercial control blocked operation")
    payload = {
        "reason_code": reason_code,
        "operation": operation,
        "source": source,
        "state": state,
        "metadata": metadata or {},
    }
    create_audit_log(
        db,
        action="COMMERCIAL_OPERATION_BLOCKED",
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        details=payload,
    )
    raise CommercialControlViolation(reason_code=reason_code, message=message, details=payload)
