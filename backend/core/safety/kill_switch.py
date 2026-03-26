import json
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.risk_engine import DEFAULT_RUNTIME_LIMITS
from core.runtime_alert_thresholds import get_runtime_alert_thresholds
from db import redis_client
from models import CommercialTrade, ExecutionJob
from services.system_alert_service import create_system_alert


KILL_SWITCH_STATE_KEY = "execution:kill_switch:state"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_kill_switch_state() -> dict:
    raw = redis_client.get(KILL_SWITCH_STATE_KEY)
    if not raw:
        return {"active": False, "source": None, "reason": None, "updated_at": None}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        payload = json.loads(raw)
    except Exception:  # noqa: BLE001
        payload = {"active": True, "source": "unknown", "reason": "malformed_state", "updated_at": _now_iso()}
    payload.setdefault("active", True)
    return payload


def activate_kill_switch(*, source: str, reason: str, metadata: dict | None = None) -> dict:
    payload = {
        "active": True,
        "source": source,
        "reason": reason,
        "metadata": metadata or {},
        "updated_at": _now_iso(),
    }
    redis_client.set(KILL_SWITCH_STATE_KEY, json.dumps(payload, ensure_ascii=False))
    return payload


def deactivate_kill_switch(*, source: str, reason: str = "manual_reset") -> dict:
    payload = {
        "active": False,
        "source": source,
        "reason": reason,
        "updated_at": _now_iso(),
    }
    redis_client.set(KILL_SWITCH_STATE_KEY, json.dumps(payload, ensure_ascii=False))
    return payload


def is_kill_switch_active() -> bool:
    return bool(get_kill_switch_state().get("active"))


def evaluate_auto_kill_switch(db: Session) -> dict:
    thresholds = get_runtime_alert_thresholds()
    window = int(thresholds.get("failed_orders_window") or 20)
    fail_threshold = 6
    latency_threshold = 2000

    recent_jobs = db.query(ExecutionJob).order_by(ExecutionJob.created_at.desc()).limit(window).all()
    failed_count = sum(1 for row in recent_jobs if str(row.state).upper() == "FAILED")
    latency_spikes = sum(1 for row in recent_jobs if (row.total_ms or 0) >= latency_threshold)

    daily_loss_limit = float(DEFAULT_RUNTIME_LIMITS.get("max_daily_loss_usd") or 250.0)
    daily_realized_total = (
        db.query(func.coalesce(func.sum(CommercialTrade.realized_pnl_usd), 0.0))
        .scalar()
        or 0.0
    )
    daily_loss_breach = float(daily_realized_total) <= -abs(daily_loss_limit)

    reason = None
    if failed_count >= fail_threshold:
        reason = "fail_rate_spike"
    elif latency_spikes >= fail_threshold:
        reason = "latency_spike"
    elif daily_loss_breach:
        reason = "daily_loss_limit_breach"

    if reason:
        state = activate_kill_switch(
            source="auto",
            reason=reason,
            metadata={
                "failed_count": failed_count,
                "latency_spikes": latency_spikes,
                "daily_realized_total": float(daily_realized_total),
                "daily_loss_limit": daily_loss_limit,
            },
        )
        create_system_alert(
            db,
            alert_type="runtime_kill_switch_activated",
            severity="CRITICAL",
            message=f"Kill switch activated: {reason}",
            details=state,
            entity_key="global",
            root_cause_code=reason,
            state_key="runtime_kill_switch_activated",
        )
        return state

    return get_kill_switch_state()
