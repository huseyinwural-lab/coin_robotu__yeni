from __future__ import annotations

from datetime import datetime, timezone

from core.bot_runtime_engine import bind_bot_runtime, heartbeat_bot_runtime, initialize_bot_runtime, load_bot_runtime, set_bot_runtime_state
from db import redis_client
from models import BotProfile, ExecutionMetric, PaperPosition, PendingSignal, RiskPolicy, SignalEvent, UserExchangeConnection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_bindings(db, bot: BotProfile) -> dict:
    risk_policy = (
        db.query(RiskPolicy)
        .filter(RiskPolicy.user_id == bot.user_id)
        .order_by(RiskPolicy.updated_at.desc())
        .first()
    )
    connection = (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.user_id == bot.user_id)
        .order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc())
        .first()
    )
    return {
        "strategy_id": bot.strategy_type,
        "risk_profile_id": risk_policy.id if risk_policy else None,
        "execution_profile_id": connection.id if connection else None,
    }


def _ensure_runtime(db, bot: BotProfile) -> dict:
    bindings = _resolve_bindings(db, bot)
    return initialize_bot_runtime(redis_client, bot=bot, **bindings)


def build_bot_runtime_summary(db, bot: BotProfile) -> dict:
    runtime = _ensure_runtime(db, bot)
    positions = db.query(PaperPosition).filter(PaperPosition.user_id == bot.user_id, PaperPosition.status == "open", PaperPosition.symbol.in_(list(bot.symbols or []))).all()
    trade_rows = db.query(ExecutionMetric).filter(ExecutionMetric.user_id == bot.user_id, ExecutionMetric.symbol.in_(list(bot.symbols or []))).all()
    signal = (
        db.query(SignalEvent)
        .filter(SignalEvent.bot_profile_id == bot.id)
        .order_by(SignalEvent.generated_at.desc())
        .first()
    )
    pending = db.query(PendingSignal).filter(PendingSignal.user_id == bot.user_id, PendingSignal.symbol.in_(list(bot.symbols or []))).count()
    pnl = sum(float(getattr(row, "slippage_pct", 0.0) or 0.0) for row in trade_rows)
    health = "HEALTHY"
    if runtime.get("status") == "ERROR":
        health = "ERROR"
    elif pending > 5:
        health = "DEGRADED"
    return {
        "id": bot.id,
        "name": bot.name,
        "status": runtime.get("status", "IDLE"),
        "mode": runtime.get("mode", "live_ready_disabled"),
        "strategy_id": runtime.get("strategy_id"),
        "risk_profile_id": runtime.get("risk_profile_id"),
        "execution_profile_id": runtime.get("execution_profile_id"),
        "last_heartbeat": runtime.get("last_heartbeat"),
        "runtime_context": runtime.get("runtime_context") or {},
        "symbol_source": runtime.get("symbol_source", "manual"),
        "pnl": round(pnl, 6),
        "active_positions": len(positions),
        "last_signal": {
            "signal": getattr(signal, "signal", None),
            "symbol": getattr(signal, "symbol", None),
            "generated_at": getattr(signal, "generated_at", None),
        }
        if signal
        else None,
        "health": health,
    }


def list_bot_runtime_summaries(db, *, user_id: str) -> list[dict]:
    rows = (
        db.query(BotProfile)
        .filter(BotProfile.user_id == user_id, BotProfile.is_deleted.is_(False))
        .order_by(BotProfile.updated_at.desc())
        .all()
    )
    return [build_bot_runtime_summary(db, row) for row in rows]


def start_bot_runtime(db, *, bot: BotProfile, actor_id: str) -> dict:
    bindings = _resolve_bindings(db, bot)
    if not bindings["strategy_id"] or not bindings["execution_profile_id"]:
        runtime = set_bot_runtime_state(redis_client, bot_id=bot.id, state="ERROR", error="binding_failed")
        return {**runtime, "binding_ok": False}
    runtime = bind_bot_runtime(redis_client, bot=bot, mode="live_ready_disabled", **bindings)
    runtime = set_bot_runtime_state(redis_client, bot_id=bot.id, state="RUNNING")
    bot.is_running = True
    db.commit()
    return {**runtime, "binding_ok": True, "actor_id": actor_id, "activated_at": _now_iso()}


def pause_bot_runtime(db, *, bot: BotProfile, actor_id: str) -> dict:
    runtime = set_bot_runtime_state(redis_client, bot_id=bot.id, state="PAUSED")
    runtime.setdefault("runtime_context", {})["pause_policy"] = "new_trades_blocked_existing_managed"
    heartbeat_bot_runtime(redis_client, bot.id, patch=runtime.get("runtime_context") or {})
    bot.is_running = False
    db.commit()
    return {**runtime, "actor_id": actor_id, "paused_at": _now_iso()}


def stop_bot_runtime(db, *, bot: BotProfile, actor_id: str) -> dict:
    runtime = set_bot_runtime_state(redis_client, bot_id=bot.id, state="STOPPED")
    runtime.setdefault("runtime_context", {})["graceful_stop"] = True
    runtime.setdefault("runtime_context", {})["policy_force_close_enabled"] = False
    heartbeat_bot_runtime(redis_client, bot.id, patch=runtime.get("runtime_context") or {})
    bot.is_running = False
    db.commit()
    return {**runtime, "actor_id": actor_id, "stopped_at": _now_iso(), "force_close_available": True}


def get_bot_runtime_status(db, *, bot: BotProfile) -> dict:
    return build_bot_runtime_summary(db, bot)


def get_bot_runtime_performance(db, *, bot: BotProfile) -> dict:
    trade_rows = db.query(ExecutionMetric).filter(ExecutionMetric.user_id == bot.user_id, ExecutionMetric.symbol.in_(list(bot.symbols or []))).all()
    filled = [row for row in trade_rows if str(row.final_status or "") == "FILLED"]
    wins = [row for row in filled if float(getattr(row, "slippage_pct", 0.0) or 0.0) >= 0]
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for row in filled:
        cumulative += float(getattr(row, "slippage_pct", 0.0) or 0.0)
        peak = max(peak, cumulative)
        drawdown = min(drawdown, cumulative - peak)
    return {
        "bot_id": bot.id,
        "pnl": round(sum(float(getattr(row, "slippage_pct", 0.0) or 0.0) for row in filled), 6),
        "win_rate": round((len(wins) / len(filled) * 100) if filled else 0.0, 6),
        "drawdown": round(drawdown, 6),
        "trade_count": len(filled),
        "avg_rr": 0.0,
    }


def get_bot_runtime_logs(db, *, bot: BotProfile) -> list[dict]:
    rows = (
        db.query(SignalEvent)
        .filter(SignalEvent.bot_profile_id == bot.id)
        .order_by(SignalEvent.generated_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "signal": row.signal,
            "symbol": row.symbol,
            "direction": row.direction,
            "confidence": row.confidence,
            "reason_codes": row.reason_codes or [],
            "generated_at": row.generated_at,
        }
        for row in rows
    ]


def get_bot_runtime_trades(db, *, bot: BotProfile) -> list[dict]:
    rows = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.user_id == bot.user_id, ExecutionMetric.symbol.in_(list(bot.symbols or [])))
        .order_by(ExecutionMetric.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "order_id": row.order_id,
            "symbol": row.symbol,
            "side": row.side,
            "status": row.final_status,
            "executed_qty": row.executed_qty,
            "price_avg": row.price_avg,
            "execution_time_ms": row.execution_time_ms,
            "quality_score": row.execution_quality_score,
            "created_at": row.created_at,
        }
        for row in rows
    ]