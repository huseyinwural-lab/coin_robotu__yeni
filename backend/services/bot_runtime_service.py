from __future__ import annotations

from datetime import datetime, timezone

from core.bot_runtime_engine import bind_bot_runtime, heartbeat_bot_runtime, initialize_bot_runtime, load_bot_runtime, set_bot_runtime_state
from db import redis_client
from models import BotProfile, ExecutionMetric, PaperPosition, PendingSignal, RiskPolicy, SignalEvent, UserExchangeConnection, UserScannerResult


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
        "risk_source": "user_active_policy" if risk_policy else "default",
        "execution_profile_id": connection.id if connection else None,
        "execution_profile_source": connection.account_label if connection else "default",
    }


def _resolve_symbol_source(db, bot: BotProfile) -> dict:
    source_type = str(getattr(bot, "symbol_source_type", "manual") or "manual")
    if source_type == "scanner" and str(getattr(bot, "scanner_id", "") or "").strip():
        rows = (
            db.query(UserScannerResult)
            .filter(UserScannerResult.user_id == bot.user_id)
            .order_by(UserScannerResult.created_at.desc())
            .limit(25)
            .all()
        )
        symbols = []
        for row in rows:
            symbol = str(getattr(row, "symbol", "") or "").upper().strip()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
        if not symbols:
            return {"ok": False, "source_type": "scanner", "scanner_id": bot.scanner_id, "symbols": [], "summary": "scanner_source_empty"}
        return {"ok": True, "source_type": "scanner", "scanner_id": bot.scanner_id, "symbols": symbols, "summary": f"scanner:{bot.scanner_id}"}
    manual_symbols = [str(item).upper().strip() for item in list(bot.symbols or []) if str(item).strip()]
    return {"ok": bool(manual_symbols), "source_type": "manual", "scanner_id": None, "symbols": manual_symbols, "summary": "manual_symbols"}


def _ensure_runtime(db, bot: BotProfile) -> dict:
    bindings = _resolve_bindings(db, bot)
    runtime = initialize_bot_runtime(redis_client, bot=bot, strategy_id=bindings["strategy_id"], risk_profile_id=bindings["risk_profile_id"], execution_profile_id=bindings["execution_profile_id"])
    runtime.setdefault("runtime_context", {})["binding_sources"] = bindings
    return runtime


def build_bot_runtime_summary(db, bot: BotProfile) -> dict:
    runtime = _ensure_runtime(db, bot)
    symbol_resolution = _resolve_symbol_source(db, bot)
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
    today_pnl = sum(float(getattr(row, "slippage_pct", 0.0) or 0.0) for row in trade_rows if getattr(row, "created_at", None) and getattr(row, "created_at").date() == datetime.now(timezone.utc).date())
    heartbeat_age = 0.0
    try:
        heartbeat_age = (datetime.now(timezone.utc) - datetime.fromisoformat(str(runtime.get("last_heartbeat") or _now_iso()).replace("Z", "+00:00"))).total_seconds()
    except Exception:
        heartbeat_age = 99999
    reject_spike = len([row for row in trade_rows if str(getattr(row, "final_status", "")).upper() in {"REJECTED", "FAILED", "CANCELED"}])
    binding_validation = {
        "strategy_bound": bool(runtime.get("strategy_id")),
        "risk_bound": bool(runtime.get("risk_profile_id")),
        "execution_bound": bool(runtime.get("execution_profile_id")),
        "symbols_resolved": bool(symbol_resolution.get("ok")),
    }
    health = "HEALTHY"
    if runtime.get("status") == "ERROR" or not symbol_resolution.get("ok"):
        health = "ERROR"
    elif heartbeat_age > 120 or reject_spike >= 3 or pending > 5:
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
        "symbol_source_summary": symbol_resolution,
        "binding_validation": binding_validation,
        "compatibility": {
            "market_strategy_compatible": True,
            "execution_profile_source": (runtime.get("runtime_context") or {}).get("binding_sources", {}).get("execution_profile_source"),
            "risk_source": (runtime.get("runtime_context") or {}).get("binding_sources", {}).get("risk_source"),
        },
        "pnl": round(pnl, 6),
        "today_pnl": round(today_pnl, 6),
        "active_positions": len(positions),
        "last_signal": {
            "signal": getattr(signal, "signal", None),
            "symbol": getattr(signal, "symbol", None),
            "generated_at": getattr(signal, "generated_at", None),
        }
        if signal
        else None,
        "last_signal_at": getattr(signal, "generated_at", None) if signal else None,
        "strategy_name": runtime.get("strategy_id"),
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
    symbol_resolution = _resolve_symbol_source(db, bot)
    if not bindings["strategy_id"] or not bindings["execution_profile_id"] or not symbol_resolution.get("ok"):
        runtime = set_bot_runtime_state(redis_client, bot_id=bot.id, state="ERROR", error="binding_failed")
        return {**runtime, "binding_ok": False}
    bot.symbol_resolution_snapshot = symbol_resolution
    runtime = bind_bot_runtime(redis_client, bot=bot, strategy_id=bindings["strategy_id"], risk_profile_id=bindings["risk_profile_id"], execution_profile_id=bindings["execution_profile_id"], mode="live_ready_disabled")
    runtime["symbol_source"] = symbol_resolution.get("source_type", "manual")
    runtime.setdefault("runtime_context", {})["symbol_resolution_snapshot"] = symbol_resolution
    runtime.setdefault("runtime_context", {})["binding_sources"] = bindings
    runtime.setdefault("runtime_context", {})["binding_validation_result"] = {
        "strategy_id": bindings["strategy_id"],
        "risk_profile_id": bindings["risk_profile_id"],
        "execution_profile_id": bindings["execution_profile_id"],
        "symbol_source": symbol_resolution.get("source_type"),
        "resolved_symbols": symbol_resolution.get("symbols") or [],
        "compatibility": "ok",
    }
    runtime.setdefault("runtime_context", {})["queue_registration"] = {
        "queue_name": "execution_queue",
        "registered_at": _now_iso(),
        "graceful_stop": True,
        "force_close_default": False,
    }
    runtime = heartbeat_bot_runtime(redis_client, bot.id, patch=runtime.get("runtime_context") or {})
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
            "queue_trace": {
                "registered": True,
                "queue_name": "execution_queue",
                "correlation_id": f"signal:{row.id}",
            },
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
            "queue_trace": {
                "correlation_id": ((row.raw_exchange_status or {}).get("exchange_result") or {}).get("correlation_id"),
                "execution_pipeline": "signal -> risk_check -> execution_queue -> execution_result -> position_update",
            },
            "created_at": row.created_at,
        }
        for row in rows
    ]