import os

from sqlalchemy.orm import Session

from models import User
from services.audit_service import create_audit_log


def _is_true(value: str | None) -> bool:
    return str(value or "false").strip().lower() == "true"


def evaluate_canary_constraints(
    db: Session,
    *,
    user_id: str,
    strategy_name: str,
    size: float,
    mark_price: float,
) -> dict:
    canary_enabled = _is_true(os.environ.get("CANARY_MODE"))
    if not canary_enabled:
        return {"allowed": True, "mode": "disabled", "reject_reason": None}

    max_notional = float(os.environ.get("CANARY_MAX_NOTIONAL") or 100)
    allowed_strategies = {
        item.strip()
        for item in str(os.environ.get("CANARY_ALLOWED_STRATEGIES") or "ema_rsi").split(",")
        if item.strip()
    }
    allowed_user_ids = {
        item.strip()
        for item in str(os.environ.get("CANARY_ALLOWED_USER_IDS") or "").split(",")
        if item.strip()
    }

    user = db.query(User).filter(User.id == user_id).first()
    user_is_admin = bool(user and user.role.value in {"super_admin", "admin", "ops"})

    if allowed_user_ids:
        user_allowed = user_id in allowed_user_ids
    else:
        user_allowed = user_is_admin

    if not user_allowed:
        reason = "canary_user_not_allowed"
        create_audit_log(
            db,
            action="canary_reject",
            entity_type="execution_job",
            entity_id=f"{user_id}:{strategy_name}",
            actor_user_id=user_id,
            actor_role=user.role.value if user else "user",
            severity="warning",
            details={"reason": reason, "strategy_name": strategy_name},
        )
        return {"allowed": False, "mode": "enabled", "reject_reason": reason}

    if strategy_name not in allowed_strategies:
        reason = "canary_strategy_not_allowed"
        return {"allowed": False, "mode": "enabled", "reject_reason": reason}

    notional = float(size or 0) * float(mark_price or 0)
    if notional > max_notional:
        reason = "canary_max_notional_exceeded"
        create_audit_log(
            db,
            action="canary_reject",
            entity_type="execution_job",
            entity_id=f"{user_id}:{strategy_name}",
            actor_user_id=user_id,
            actor_role=user.role.value if user else "user",
            severity="warning",
            details={"reason": reason, "notional": notional, "max_notional": max_notional},
        )
        return {"allowed": False, "mode": "enabled", "reject_reason": reason}

    return {
        "allowed": True,
        "mode": "enabled",
        "reject_reason": None,
        "max_notional": max_notional,
        "actual_notional": round(notional, 8),
    }
