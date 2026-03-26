from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.alerts.runtime_alert_triggers import check_daily_loss_trigger
from db import redis_client
from models import CommercialTrade, Position
from services.audit_service import create_audit_log


KILL_SWITCH_KEY = "execution:kill_switch:global"

DEFAULT_RUNTIME_LIMITS = {
    "max_position_pct": 10.0,
    "max_daily_loss_usd": 250.0,
    "leverage_cap": 3,
    "per_user_notional_cap": 5000.0,
    "kill_switch_drawdown_threshold_usd": 250.0,
}


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def is_kill_switch_active() -> bool:
    return bool(redis_client.get(KILL_SWITCH_KEY))


def block_all_trades(*, reason: str, actor_user_id: str | None = None) -> None:
    redis_client.set(KILL_SWITCH_KEY, reason)
    redis_client.expire(KILL_SWITCH_KEY, 24 * 60 * 60)


def clear_kill_switch() -> None:
    redis_client.delete(KILL_SWITCH_KEY)


def evaluate_risk(
    db: Session,
    *,
    user_id: str,
    symbol: str,
    side: str,
    size: float,
    leverage: int,
    mark_price: float,
    limits: dict | None = None,
) -> dict:
    cfg = {**DEFAULT_RUNTIME_LIMITS, **(limits or {})}
    reject_reasons: list[str] = []

    if is_kill_switch_active():
        reject_reasons.append("kill_switch_active")

    proposed_notional = max(0.0, _to_float(size) * max(_to_float(mark_price), 0.0))
    max_position_notional = _to_float(cfg["per_user_notional_cap"]) * (_to_float(cfg["max_position_pct"]) / 100.0)

    if proposed_notional > max_position_notional:
        reject_reasons.append("max_position_pct_exceeded")

    if int(leverage) > int(cfg["leverage_cap"]):
        reject_reasons.append("leverage_cap_exceeded")

    open_notional = (
        db.query(func.coalesce(func.sum(func.abs(Position.size * Position.current_price)), 0.0))
        .filter(Position.user_id == user_id, Position.status == "open")
        .scalar()
        or 0.0
    )
    if open_notional + proposed_notional > _to_float(cfg["per_user_notional_cap"]):
        reject_reasons.append("per_user_notional_cap_exceeded")

    since = datetime.now(timezone.utc) - timedelta(days=1)
    daily_realized_pnl = (
        db.query(func.coalesce(func.sum(CommercialTrade.realized_pnl_usd), 0.0))
        .filter(CommercialTrade.user_id == user_id, CommercialTrade.trade_time >= since)
        .scalar()
        or 0.0
    )
    if daily_realized_pnl <= -abs(_to_float(cfg["max_daily_loss_usd"])):
        reject_reasons.append("max_daily_loss_exceeded")
        check_daily_loss_trigger(
            db,
            user_id=user_id,
            daily_loss_usd=abs(float(daily_realized_pnl)),
            configured_limit=abs(_to_float(cfg["max_daily_loss_usd"])),
        )
        if abs(daily_realized_pnl) > abs(_to_float(cfg["kill_switch_drawdown_threshold_usd"])):
            block_all_trades(reason="daily_drawdown_threshold_breached", actor_user_id=user_id)
            reject_reasons.append("kill_switch_triggered")

    allowed = len(reject_reasons) == 0
    decision = {
        "allowed": allowed,
        "reject_reason": reject_reasons[0] if reject_reasons else None,
        "reject_reasons": reject_reasons,
        "metrics": {
            "proposed_notional": round(proposed_notional, 8),
            "open_notional": round(float(open_notional), 8),
            "daily_realized_pnl": round(float(daily_realized_pnl), 8),
            "leverage": int(leverage),
        },
        "limits": {
            "max_position_pct": _to_float(cfg["max_position_pct"]),
            "max_daily_loss_usd": _to_float(cfg["max_daily_loss_usd"]),
            "leverage_cap": int(cfg["leverage_cap"]),
            "per_user_notional_cap": _to_float(cfg["per_user_notional_cap"]),
        },
    }

    if not allowed:
        create_audit_log(
            db,
            action="runtime_risk_reject",
            entity_type="execution_job",
            entity_id=f"{user_id}:{symbol}:{side}",
            actor_user_id=user_id,
            actor_role="user",
            severity="warning",
            details=decision,
        )

    return decision
