from datetime import datetime, timezone
import json

from sqlalchemy.orm import Session

from models import AdminControl, BotProfile, ExecutionMetric, FailedEvent, PaperPosition, UserRiskSetting
from services.audit_service import create_audit_log
from services.pipeline.execution_engine import manual_close_position
from services.system_alert_service import create_system_alert

KILL_SWITCH_EXECUTION_ERROR_THRESHOLD = 5
KILL_SWITCH_RISK_ANOMALY_THRESHOLD = 3
KILL_SWITCH_ORDER_REJECT_RATE_THRESHOLD = 0.35


def _flash_crash_detected(cache) -> bool:
    raw = cache.get("market:candles:BTCUSDT:15m") if cache else None
    if not raw:
        return False
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        candles = json.loads(raw)
        if not candles:
            return False
        last = candles[-1]
        open_price = float(last.get("open", 0))
        close_price = float(last.get("close", 0))
        move_pct = ((close_price - open_price) / open_price) * 100 if open_price else 0
        return move_pct <= -10
    except Exception:
        return False


def _execution_health_flags(db: Session) -> dict:
    rows = (
        db.query(ExecutionMetric)
        .order_by(ExecutionMetric.timestamp.desc())
        .limit(120)
        .all()
    )
    if not rows:
        return {"slippage_spike": False, "reject_rate_high": False, "reject_rate": 0, "recent_slippage": 0, "baseline_slippage": 0}

    recent = rows[:20]
    baseline = rows[20:] if len(rows) > 20 else rows

    recent_slippage = sum(abs(float(item.slippage_pct or 0)) for item in recent) / max(len(recent), 1)
    baseline_slippage = sum(abs(float(item.slippage_pct or 0)) for item in baseline) / max(len(baseline), 1)
    slippage_spike = baseline_slippage > 0 and recent_slippage > (baseline_slippage * 3)

    reject_statuses = {"rejected", "error", "failed", "timeout"}
    reject_count = sum(1 for item in recent if str(item.final_status or "").lower() in reject_statuses)
    reject_rate = reject_count / max(len(recent), 1)
    reject_rate_high = reject_rate >= KILL_SWITCH_ORDER_REJECT_RATE_THRESHOLD

    return {
        "slippage_spike": slippage_spike,
        "reject_rate_high": reject_rate_high,
        "reject_rate": round(reject_rate, 4),
        "recent_slippage": round(recent_slippage, 4),
        "baseline_slippage": round(baseline_slippage, 4),
    }


def _today_daily_loss_exceeded_users(db: Session) -> list[str]:
    users = db.query(UserRiskSetting).all()
    start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    exceeded_users: list[str] = []

    for user in users:
        rows = (
            db.query(PaperPosition)
            .filter(
                PaperPosition.user_id == user.user_id,
                PaperPosition.closed_at.is_not(None),
                PaperPosition.closed_at >= start_of_day,
            )
            .all()
        )
        daily_loss = abs(sum(float(row.realized_pnl or 0) for row in rows if float(row.realized_pnl or 0) < 0))
        if daily_loss >= (float(user.base_capital) * (float(user.daily_loss_limit_pct) / 100)):
            exceeded_users.append(user.user_id)

    return exceeded_users


def evaluate_kill_switch(db: Session, cache, market_data_engine) -> dict:
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    reasons: list[str] = []

    ws_status = market_data_engine.websocket_status
    heartbeat_raw = market_data_engine.last_heartbeat
    heartbeat_stale = True
    try:
        heartbeat_dt = datetime.fromisoformat(str(heartbeat_raw).replace("Z", "+00:00"))
        if heartbeat_dt.tzinfo is None:
            heartbeat_dt = heartbeat_dt.replace(tzinfo=timezone.utc)
        heartbeat_stale = (datetime.now(timezone.utc) - heartbeat_dt).total_seconds() > 120
    except Exception:
        heartbeat_stale = True

    if ws_status != "connected" and heartbeat_stale:
        reasons.append("exchange_unreachable")

    execution_errors_5m = int(cache.get("metrics:execution_errors:5m") or 0)
    if execution_errors_5m >= KILL_SWITCH_EXECUTION_ERROR_THRESHOLD:
        reasons.append("execution_errors_spike")

    risk_anomalies_5m = int(cache.get("metrics:risk_anomalies:5m") or 0)
    if risk_anomalies_5m >= KILL_SWITCH_RISK_ANOMALY_THRESHOLD:
        reasons.append("risk_engine_anomaly")

    exceeded_users = _today_daily_loss_exceeded_users(db)
    if exceeded_users:
        reasons.append("daily_loss_exceeded")

    failed_events_pending = (
        db.query(FailedEvent)
        .filter(FailedEvent.status.in_(["pending", "retrying"]))
        .count()
    )
    if failed_events_pending >= 20:
        reasons.append("failed_events_overload")

    if _flash_crash_detected(cache):
        reasons.append("flash_crash_detected")

    execution_health = _execution_health_flags(db)
    if execution_health["slippage_spike"]:
        reasons.append("slippage_spike")
    if execution_health["reject_rate_high"]:
        reasons.append("exchange_error_reject_rate_high")

    if "daily_loss_exceeded" in reasons:
        create_system_alert(
            db,
            alert_type="daily_loss_limit_hit",
            severity="CRITICAL",
            message="Daily loss limit exceeded (kill switch trigger)",
            details={"affected_users": exceeded_users},
            entity_key="global",
            root_cause_code="daily_loss_exceeded",
            state_key="daily_loss_exceeded",
        )

    triggered = bool(reasons)
    current_active = bool(control and control.emergency_mode)

    if control is not None and triggered and not current_active:
        control.emergency_mode = True
        db.commit()
        create_audit_log(
            db,
            action="kill_switch_triggered",
            entity_type="admin_control",
            entity_id=control.id,
            actor_user_id="system",
            actor_role="system",
            severity="critical",
            details={"reasons": reasons},
        )
        create_system_alert(
            db,
            alert_type="global_kill_switch_triggered",
            severity="CRITICAL",
            message="Global kill switch triggered",
            details={"reasons": reasons},
            entity_key="global",
            root_cause_code="kill_switch_triggered",
            state_key="kill_switch_triggered",
        )
    elif control is not None and not triggered and not current_active:
        # remain inactive
        pass

    effective_active = bool(control.emergency_mode) if control else triggered
    if effective_active and not reasons:
        reasons = ["manual_emergency_mode"]

    payload = {
        "triggered": bool(control.emergency_mode) if control else triggered,
        "active": effective_active,
        "reasons": reasons,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "execution_errors_5m": execution_errors_5m,
        "risk_anomalies_5m": risk_anomalies_5m,
        "daily_loss_exceeded_users": exceeded_users,
        "failed_events_pending": failed_events_pending,
        "execution_health": execution_health,
    }
    cache.set("pipeline:kill_switch", json.dumps(payload))
    return payload


def liquidate_open_positions_for_kill_switch(db: Session) -> list[str]:
    open_positions = db.query(PaperPosition).filter(PaperPosition.status == "open").all()
    closed_ids: list[str] = []
    for position in open_positions:
        manual_close_position(db, position, reason="kill_switch_close")
        closed_ids.append(position.id)
    return closed_ids


def pause_all_bots_for_kill_switch(db: Session) -> int:
    running = db.query(BotProfile).filter(BotProfile.is_deleted.is_(False), BotProfile.is_running.is_(True)).all()
    for bot in running:
        bot.is_running = False
    db.commit()
    return len(running)


def reset_kill_switch(db: Session, cache) -> dict:
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    if control is not None:
        control.emergency_mode = False
        db.commit()
        create_audit_log(
            db,
            action="kill_switch_reset",
            entity_type="admin_control",
            entity_id=control.id,
            actor_user_id="system",
            actor_role="system",
            severity="info",
            details={"manual_reset": True},
        )

    payload = {
        "triggered": False,
        "active": False,
        "reasons": [],
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }
    cache.set("pipeline:kill_switch", json.dumps(payload))
    return payload


def kill_switch_state(cache) -> dict:
    raw = cache.get("pipeline:kill_switch")
    if not raw:
        return {"triggered": False, "active": False, "reasons": []}
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        return json.loads(raw)
    except Exception:
        return {"triggered": False, "active": False, "reasons": []}