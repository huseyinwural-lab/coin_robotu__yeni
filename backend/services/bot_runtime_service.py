from __future__ import annotations

from datetime import datetime, timezone
import logging

from core.bot_runtime_engine import bind_bot_runtime, heartbeat_bot_runtime, initialize_bot_runtime, set_bot_runtime_state
from db import redis_client
from models import BotProfile, ExecutionMetric, PaperPosition, PendingSignal, RiskPolicy, SignalEvent, UserExchangeConnection, UserScannerResult, UserScannerSymbolSelection
from services.strategy_template_resolution_service import resolve_effective_strategy_config

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _fallback_bot_runtime_summary(bot: BotProfile, reason: str) -> dict:
    snapshot = getattr(bot, "symbol_resolution_snapshot", {}) or {}
    strategy_template_ids = [
        str(value).strip()
        for value in list(snapshot.get("strategy_template_ids") or [])
        if str(value).strip()
    ]
    return {
        "id": bot.id,
        "name": bot.name,
        "exchange": bot.exchange,
        "market_type": bot.market_type,
        "strategy_type": bot.strategy_type,
        "strategy_template_id": getattr(bot, "strategy_template_id", None),
        "strategy_template_ids": strategy_template_ids,
        "risk_adaptive_confirmed": bool(snapshot.get("risk_adaptive_confirmed")),
        "symbols": list(bot.symbols or []),
        "leverage": _safe_int(getattr(bot, "leverage", 1), 1),
        "is_enabled": bool(getattr(bot, "is_enabled", True)),
        "is_running": bool(getattr(bot, "is_running", False)),
        "symbol_source_type": str(getattr(bot, "symbol_source_type", "manual") or "manual"),
        "scanner_id": getattr(bot, "scanner_id", None),
        "selected_exchange_connection_id": str(snapshot.get("selected_exchange_connection_id") or "") or None,
        "selected_exchange_connection_label": str(snapshot.get("selected_exchange_connection_label") or "") or None,
        "selected_risk_policy_id": str(snapshot.get("selected_risk_policy_id") or "") or None,
        "selected_risk_policy_name": str(snapshot.get("selected_risk_policy_name") or "") or None,
        "status": "ERROR",
        "mode": "live_ready",
        "strategy_id": None,
        "risk_profile_id": None,
        "execution_profile_id": None,
        "last_heartbeat": _now_iso(),
        "runtime_context": {"error": "summary_fallback", "reason": reason},
        "symbol_source": "manual",
        "symbol_source_summary": {
            "ok": False,
            "source_type": str(getattr(bot, "symbol_source_type", "manual") or "manual"),
            "scanner_id": getattr(bot, "scanner_id", None),
            "symbols": list(bot.symbols or []),
            "summary": "fallback",
            "last_resolution_time": _now_iso(),
            "resolution_status": "failed",
        },
        "binding_validation": {
            "strategy_bound": False,
            "risk_bound": False,
            "execution_bound": False,
            "symbols_resolved": False,
        },
        "compatibility": {
            "parity": "unknown",
            "market_strategy_compatible": False,
            "execution_profile_source": None,
            "risk_source": None,
        },
        "pnl": 0.0,
        "today_pnl": 0.0,
        "risk_exposure": 0.0,
        "bot_risk_contribution": {
            "exposure": 0.0,
            "avg_leverage": 1.0,
            "direction_mix": {"long": 0, "short": 0},
        },
        "active_positions": 0,
        "last_signal": None,
        "last_signal_at": None,
        "strategy_name": None,
        "last_action": "ERROR",
        "anomaly_flag": True,
        "dynamic_parameters": {
            "position_size_multiplier": 0.5,
            "risk_multiplier": 0.5,
            "regime_adjustment": "fallback",
        },
        "health": "ERROR",
    }


def _resolve_bindings(db, bot: BotProfile) -> dict:
    try:
        resolved_template = resolve_effective_strategy_config(
            db,
            template_id=getattr(bot, "strategy_template_id", None),
            strategy_type=bot.strategy_type,
        )
    except Exception as exc:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.exception(
            "BOT_STRATEGY_RESOLUTION_FALLBACK",
            extra={"bot_id": getattr(bot, "id", None), "strategy_type": getattr(bot, "strategy_type", None)},
        )
        resolved_template = {
            "template_id": None,
            "template_code": None,
            "validation_result": {
                "ok": False,
                "reason": f"strategy_resolution_exception:{exc.__class__.__name__}",
                "runtime_eligible": True,
            },
            "effective_runtime_config": {},
        }

    runtime_strategy_type = str(getattr(bot, "strategy_type", "") or "").strip()
    validation_result = dict((resolved_template or {}).get("validation_result") or {})
    validation_reason = str(validation_result.get("reason") or "").strip().lower()
    if runtime_strategy_type and (not validation_result.get("ok")) and validation_reason in {"template_not_found", "template_not_found_for_strategy_type"}:
        resolved_template = {
            **(resolved_template or {}),
            "template_id": None,
            "template_code": runtime_strategy_type,
            "effective_runtime_config": {
                "strategy_type": runtime_strategy_type,
                "template_name": "legacy_runtime_strategy_fallback",
                "parameters": {},
                "logic_schema": {},
                "indicator_schema": {},
                "execution_profile_ref": None,
                "risk_hint_ref": None,
                "allowed_venues": [str(getattr(bot, "exchange", "binance") or "binance")],
                "allowed_modes": ["live_ready"],
            },
            "validation_result": {
                "ok": True,
                "errors": [],
                "override_used": False,
                "execution_compatibility": "PASS",
                "runtime_eligible": True,
                "lifecycle_state": "LEGACY_FALLBACK",
                "reason": "template_not_found_fallback_to_strategy_type",
            },
        }
    risk_policy = (
        db.query(RiskPolicy)
        .filter(RiskPolicy.user_id == bot.user_id)
        .order_by(RiskPolicy.updated_at.desc())
        .first()
    )
    snapshot = getattr(bot, "symbol_resolution_snapshot", {}) or {}
    selected_connection_id = str(snapshot.get("selected_exchange_connection_id") or "").strip()

    connection_query = db.query(UserExchangeConnection).filter(UserExchangeConnection.user_id == bot.user_id)
    connection = None
    if selected_connection_id:
        connection = connection_query.filter(UserExchangeConnection.id == selected_connection_id).first()

    if connection is None:
        connection = (
            connection_query.order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc()).first()
        )

    execution_source = connection.account_label if connection else "default"
    if selected_connection_id and connection and connection.id == selected_connection_id:
        execution_source = f"selected:{connection.account_label}"
    elif selected_connection_id and connection:
        execution_source = f"fallback_default:{connection.account_label}"

    return {
        "strategy_id": resolved_template.get("template_code") or bot.strategy_type,
        "strategy_resolution": resolved_template,
        "risk_profile_id": risk_policy.id if risk_policy else None,
        "risk_source": "user_active_policy" if risk_policy else "default",
        "execution_profile_id": connection.id if connection else None,
        "execution_profile_source": execution_source,
        "selected_exchange_connection_id": selected_connection_id or (connection.id if connection else None),
        "selected_exchange_connection_label": connection.account_label if connection else None,
    }


def _resolve_symbol_source(db, bot: BotProfile) -> dict:
    source_type = str(getattr(bot, "symbol_source_type", "manual") or "manual")
    if source_type == "scanner" and str(getattr(bot, "scanner_id", "") or "").strip():
        scanner_id = str(getattr(bot, "scanner_id", "") or "").strip()
        selection_row = (
            db.query(UserScannerSymbolSelection)
            .filter(UserScannerSymbolSelection.user_id == bot.user_id, UserScannerSymbolSelection.scanner_id == scanner_id)
            .first()
        )
        selected_symbols = [
            str(symbol).upper().strip()
            for symbol in list((selection_row.selected_symbols if selection_row else []) or [])
            if str(symbol).strip()
        ]
        selected_set = set(selected_symbols)
        rows = (
            db.query(UserScannerResult)
            .filter(UserScannerResult.user_id == bot.user_id)
            .order_by(UserScannerResult.generated_at.desc())
            .limit(25)
            .all()
        )
        symbols = []
        for row in rows:
            symbol = str(getattr(row, "symbol", "") or "").upper().strip()
            if selected_set and symbol not in selected_set:
                continue
            if symbol and symbol not in symbols:
                symbols.append(symbol)
        if not symbols:
            resolution_reason = "scanner_selection_empty" if selected_set else "scanner_source_empty"
            return {
                "ok": False,
                "source_type": "scanner",
                "scanner_id": scanner_id,
                "symbols": [],
                "summary": resolution_reason,
                "selected_symbols": selected_symbols,
                "last_resolution_time": None,
                "resolution_status": "failed",
            }
        return {
            "ok": True,
            "source_type": "scanner",
            "scanner_id": scanner_id,
            "symbols": symbols,
            "summary": f"scanner:{scanner_id}",
            "selected_symbols": selected_symbols,
            "last_resolution_time": rows[0].generated_at if rows else None,
            "resolution_status": "resolved",
        }
    manual_symbols = [str(item).upper().strip() for item in list(bot.symbols or []) if str(item).strip()]
    return {"ok": bool(manual_symbols), "source_type": "manual", "scanner_id": None, "symbols": manual_symbols, "summary": "manual_symbols", "last_resolution_time": _now_iso(), "resolution_status": "resolved" if manual_symbols else "failed"}


def _ensure_runtime(db, bot: BotProfile) -> dict:
    bindings = _resolve_bindings(db, bot)
    runtime = initialize_bot_runtime(redis_client, bot=bot, strategy_id=bindings["strategy_id"], risk_profile_id=bindings["risk_profile_id"], execution_profile_id=bindings["execution_profile_id"])
    runtime = bind_bot_runtime(
        redis_client,
        bot=bot,
        strategy_id=bindings["strategy_id"],
        risk_profile_id=bindings["risk_profile_id"],
        execution_profile_id=bindings["execution_profile_id"],
        mode="live_ready",
    )
    runtime.setdefault("runtime_context", {})["binding_sources"] = bindings
    runtime.setdefault("runtime_context", {})["strategy_resolution"] = bindings.get("strategy_resolution") or {}
    return runtime


def _build_binding_blocks(db, bot: BotProfile, runtime: dict, symbol_resolution: dict) -> tuple[dict, dict, dict, dict, dict]:
    binding_sources = dict((runtime.get("runtime_context") or {}).get("binding_sources") or {})
    strategy_resolution = dict((runtime.get("runtime_context") or {}).get("strategy_resolution") or {})
    strategy_binding = {
        "selected_strategy_id": bot.strategy_type,
        "selected_strategy_template_id": getattr(bot, "strategy_template_id", None),
        "selected_template_code": strategy_resolution.get("template_code"),
        "selected_template_version": strategy_resolution.get("version_num"),
        "selected_template_lifecycle_state": strategy_resolution.get("lifecycle_state"),
        "effective_runtime_strategy_id": runtime.get("strategy_id"),
        "effective_params": {
            "timeframe": bot.timeframe,
            "trend_timeframe": bot.trend_timeframe,
            "market_type": bot.market_type,
            **((strategy_resolution.get("effective_runtime_config") or {}).get("parameters") or {}),
        },
        "override": bool(getattr(bot, "strategy_template_id", None)),
        "validation_result": strategy_resolution.get("validation_result") or {},
        "last_resolved_at": runtime.get("last_heartbeat"),
    }
    risk_binding = {
        "risk_source": binding_sources.get("risk_source", "default"),
        "resolved_risk_profile_id": runtime.get("risk_profile_id"),
        "validation_result": "ok" if runtime.get("risk_profile_id") or binding_sources.get("risk_source") == "default" else "missing",
    }
    execution_binding = {
        "execution_source": binding_sources.get("execution_profile_source", "default"),
        "resolved_execution_profile_id": runtime.get("execution_profile_id"),
        "venue_mode_compatibility": "ok",
    }
    binding_validation = {
        "selected": {
            "strategy_id": bot.strategy_type,
            "risk_profile_id": runtime.get("risk_profile_id"),
            "execution_profile_id": runtime.get("execution_profile_id"),
            "symbol_source": symbol_resolution.get("source_type"),
        },
        "resolved": {
            "strategy_id": runtime.get("strategy_id"),
            "strategy_template_id": getattr(bot, "strategy_template_id", None),
            "resolved_symbols": symbol_resolution.get("symbols") or [],
            "resolved_symbol_count": len(symbol_resolution.get("symbols") or []),
            "resolution_timestamp": runtime.get("last_heartbeat"),
        },
        "result": "ok" if symbol_resolution.get("ok") and runtime.get("execution_profile_id") and runtime.get("strategy_id") and strategy_resolution.get("validation_result", {}).get("ok", True) else "failed",
    }
    compatibility = {
        "parity": "ok",
        "market_strategy_compatible": True,
        "execution_profile_source": binding_sources.get("execution_profile_source"),
        "risk_source": binding_sources.get("risk_source"),
    }
    return strategy_binding, risk_binding, execution_binding, binding_validation, compatibility


def build_bot_runtime_summary(db, bot: BotProfile) -> dict:
    runtime = _ensure_runtime(db, bot)
    snapshot = getattr(bot, "symbol_resolution_snapshot", {}) or {}
    preferred_mode = str(snapshot.get("preferred_mode") or "live_ready").strip().lower()
    if preferred_mode != "live_ready":
        preferred_mode = "live_ready"
    runtime_mode = "live_ready"
    mode_value = runtime_mode if str(runtime.get("status") or "").upper() == "RUNNING" else preferred_mode
    symbol_resolution = _resolve_symbol_source(db, bot)
    strategy_template_ids = [
        str(value).strip()
        for value in list(snapshot.get("strategy_template_ids") or [])
        if str(value).strip()
    ]
    strategy_binding, risk_binding, execution_binding, binding_validation, compatibility = _build_binding_blocks(db, bot, runtime, symbol_resolution)
    positions = db.query(PaperPosition).filter(PaperPosition.user_id == bot.user_id, PaperPosition.status == "open", PaperPosition.symbol.in_(list(bot.symbols or []))).all()
    resolved_symbols = list(symbol_resolution.get("symbols") or list(bot.symbols or []))
    trade_rows_query = db.query(ExecutionMetric).filter(ExecutionMetric.user_id == bot.user_id, ExecutionMetric.strategy_type == bot.strategy_type)
    if resolved_symbols:
        trade_rows_query = trade_rows_query.filter(ExecutionMetric.symbol.in_(resolved_symbols))
    trade_rows = trade_rows_query.order_by(ExecutionMetric.created_at.desc()).limit(500).all()
    signal = (
        db.query(SignalEvent)
        .filter(SignalEvent.bot_profile_id == bot.id)
        .order_by(SignalEvent.generated_at.desc())
        .first()
    )
    pending = 0
    if resolved_symbols:
        pending = db.query(PendingSignal).filter(PendingSignal.user_id == bot.user_id, PendingSignal.symbol.in_(resolved_symbols)).count()
    pnl = sum(float(getattr(row, "slippage_pct", 0.0) or 0.0) for row in trade_rows)
    today_pnl = sum(float(getattr(row, "slippage_pct", 0.0) or 0.0) for row in trade_rows if getattr(row, "created_at", None) and getattr(row, "created_at").date() == datetime.now(timezone.utc).date())
    exposure = sum(abs(float(getattr(row, "size", 0.0) or 0.0) * float(getattr(row, "current_price", getattr(row, "entry_price", 0.0)) or 0.0)) for row in positions)
    leverage_values = [float(getattr(row, "leverage", 1) or 1) for row in positions]
    direction_mix = {"long": len([row for row in positions if str(getattr(row, "side", "")).lower() == "buy"]), "short": len([row for row in positions if str(getattr(row, "side", "")).lower() == "sell"])}
    heartbeat_age = 0.0
    try:
        heartbeat_age = (datetime.now(timezone.utc) - datetime.fromisoformat(str(runtime.get("last_heartbeat") or _now_iso()).replace("Z", "+00:00"))).total_seconds()
    except Exception:
        heartbeat_age = 99999
    reject_spike = len([row for row in trade_rows if str(getattr(row, "final_status", "")).upper() in {"REJECTED", "FAILED", "CANCELED"}])
    binding_summary = {
        "strategy_bound": bool(runtime.get("strategy_id")),
        "risk_bound": bool(runtime.get("risk_profile_id") or risk_binding.get("risk_source") == "default"),
        "execution_bound": bool(runtime.get("execution_profile_id")),
        "symbols_resolved": bool(symbol_resolution.get("ok")),
    }
    health = "HEALTHY"
    last_error = str((runtime.get("runtime_context") or {}).get("last_error") or "").lower()
    if runtime.get("status") == "ERROR" or not symbol_resolution.get("ok"):
        health = "ERROR"
    elif heartbeat_age > 120 or reject_spike >= 3 or pending > 5 or any(token in last_error for token in ["binding", "scanner", "provider", "queue"]):
        health = "DEGRADED"
    dynamic_parameters = {
        "position_size_multiplier": round(0.7 if abs(today_pnl) > 0.05 else 0.85 if reject_spike >= 2 else 1.0, 4),
        "risk_multiplier": round(0.75 if health == "DEGRADED" else 0.5 if health == "ERROR" else 1.0, 4),
        "regime_adjustment": "reduced_risk" if abs(today_pnl) > 0.05 else "default",
    }
    return {
        "id": bot.id,
        "name": bot.name,
        "exchange": bot.exchange,
        "market_type": bot.market_type,
        "strategy_type": bot.strategy_type,
        "strategy_template_id": getattr(bot, "strategy_template_id", None),
        "strategy_template_ids": strategy_template_ids,
        "risk_adaptive_confirmed": bool(snapshot.get("risk_adaptive_confirmed")),
        "symbols": list(bot.symbols or []),
        "leverage": _safe_int(getattr(bot, "leverage", 1), 1),
        "is_enabled": bool(getattr(bot, "is_enabled", True)),
        "is_running": bool(getattr(bot, "is_running", False)),
        "symbol_source_type": str(getattr(bot, "symbol_source_type", "manual") or "manual"),
        "scanner_id": getattr(bot, "scanner_id", None),
        "selected_exchange_connection_id": str(snapshot.get("selected_exchange_connection_id") or "") or None,
        "selected_exchange_connection_label": str(snapshot.get("selected_exchange_connection_label") or "") or None,
        "selected_risk_policy_id": str(snapshot.get("selected_risk_policy_id") or "") or None,
        "selected_risk_policy_name": str(snapshot.get("selected_risk_policy_name") or "") or None,
        "status": runtime.get("status", "IDLE"),
        "mode": mode_value,
        "strategy_id": runtime.get("strategy_id"),
        "risk_profile_id": runtime.get("risk_profile_id"),
        "execution_profile_id": runtime.get("execution_profile_id"),
        "last_heartbeat": runtime.get("last_heartbeat"),
        "runtime_context": runtime.get("runtime_context") or {},
        "symbol_source": runtime.get("symbol_source", "manual"),
        "symbol_source_summary": symbol_resolution,
        "binding_validation": binding_summary,
        "compatibility": compatibility,
        "pnl": round(pnl, 6),
        "today_pnl": round(today_pnl, 6),
        "risk_exposure": round(exposure, 6),
        "bot_risk_contribution": {
            "exposure": round(exposure, 6),
            "avg_leverage": round(sum(leverage_values) / len(leverage_values), 6) if leverage_values else 1.0,
            "direction_mix": direction_mix,
        },
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
        "last_action": runtime.get("status", "IDLE"),
        "anomaly_flag": bool(health in {"DEGRADED", "ERROR"}),
        "dynamic_parameters": dynamic_parameters,
        "health": health,
    }


def get_bot_runtime_detail(db, *, bot: BotProfile) -> dict:
    runtime = _ensure_runtime(db, bot)
    symbol_resolution = _resolve_symbol_source(db, bot)
    strategy_binding, risk_binding, execution_binding, binding_validation, compatibility = _build_binding_blocks(db, bot, runtime, symbol_resolution)
    summary = build_bot_runtime_summary(db, bot)
    logs = get_bot_runtime_logs(db, bot=bot)
    trades = get_bot_runtime_trades(db, bot=bot)
    last_execution_summary = {
        "last_signal_time": summary.get("last_signal_at"),
        "last_risk_check_result": "ok" if risk_binding.get("validation_result") == "ok" else "failed",
        "last_queue_event": (logs[0].get("queue_trace") if logs else None),
        "last_execution_result": trades[0] if trades else None,
        "last_position_update": summary.get("active_positions"),
    }
    return {
        "config_summary": {
            "bot_id": bot.id,
            "name": bot.name,
            "exchange": bot.exchange,
            "market_type": bot.market_type,
            "strategy_type": bot.strategy_type,
            "strategy_template_id": getattr(bot, "strategy_template_id", None),
            "mode": summary.get("mode"),
            "symbol_source_type": getattr(bot, "symbol_source_type", "manual"),
            "scanner_id": getattr(bot, "scanner_id", None),
            "symbols": list(bot.symbols or []),
            "symbol_resolution_snapshot": getattr(bot, "symbol_resolution_snapshot", {}) or {},
        },
        "runtime_summary": summary,
        "strategy_binding": strategy_binding,
        "risk_binding": risk_binding,
        "execution_binding": execution_binding,
        "binding_validation": binding_validation,
        "compatibility": compatibility,
        "last_execution_summary": last_execution_summary,
    }


def aggregate_bot_portfolio_control(db, *, user_id: str) -> dict:
    bots = list_bot_runtime_summaries(db, user_id=user_id)
    total_exposure = sum(float((item.get("bot_risk_contribution") or {}).get("exposure", 0.0) or 0.0) for item in bots)
    avg_leverage = 0.0
    leverage_values = [float((item.get("bot_risk_contribution") or {}).get("avg_leverage", 1.0) or 1.0) for item in bots]
    if leverage_values:
        avg_leverage = sum(leverage_values) / len(leverage_values)
    allocator = []
    total_bots = max(len(bots), 1)
    for item in bots:
        contribution = float((item.get("bot_risk_contribution") or {}).get("exposure", 0.0) or 0.0)
        allocation_share = round(contribution / total_exposure, 6) if total_exposure > 0 else round(1 / total_bots, 6)
        throttled = bool(item.get("health") == "DEGRADED" or item.get("health") == "ERROR")
        allocator.append(
            {
                "bot_id": item.get("id"),
                "strategy_id": item.get("strategy_id"),
                "capital_share": allocation_share,
                "throttled": throttled,
                "throttle_reason": "health_guard" if throttled else None,
                "dynamic_parameters": item.get("dynamic_parameters") or {},
            }
        )
    return {
        "bot_count": len(bots),
        "total_exposure": round(total_exposure, 6),
        "avg_leverage": round(avg_leverage, 6),
        "allocator": allocator,
        "portfolio_health": "DEGRADED" if any(item.get("health") == "DEGRADED" for item in bots) else "ERROR" if any(item.get("health") == "ERROR" for item in bots) else "HEALTHY",
    }


def list_bot_runtime_summaries(db, *, user_id: str) -> list[dict]:
    rows = (
        db.query(BotProfile)
        .filter(BotProfile.user_id == user_id, BotProfile.is_deleted.is_(False))
        .order_by(BotProfile.updated_at.desc())
        .all()
    )
    items = []
    for row in rows:
        try:
            items.append(build_bot_runtime_summary(db, row))
        except Exception as exc:
            logger.exception("BOT_RUNTIME_SUMMARY_FAILED", extra={"bot_id": row.id, "user_id": user_id})
            items.append(_fallback_bot_runtime_summary(row, reason=str(exc)))
    return items


def start_bot_runtime(db, *, bot: BotProfile, actor_id: str) -> dict:
    bindings = _resolve_bindings(db, bot)
    symbol_resolution = _resolve_symbol_source(db, bot)
    strategy_resolution = dict(bindings.get("strategy_resolution") or {})
    strategy_ok = bool(strategy_resolution.get("validation_result", {}).get("runtime_eligible", True))
    preferred_mode = "live_ready"
    if not bindings["strategy_id"] or not bindings["execution_profile_id"] or not symbol_resolution.get("ok") or not strategy_ok:
        runtime = set_bot_runtime_state(redis_client, bot_id=bot.id, state="ERROR", error="binding_failed")
        runtime["mode"] = preferred_mode
        runtime.setdefault("runtime_context", {})["preferred_mode"] = preferred_mode
        return {**runtime, "binding_ok": False}
    bot.symbol_resolution_snapshot = _json_safe(
        {
            **(getattr(bot, "symbol_resolution_snapshot", {}) or {}),
            "last_symbol_resolution": symbol_resolution,
        }
    )
    runtime = bind_bot_runtime(
        redis_client,
        bot=bot,
        strategy_id=bindings["strategy_id"],
        risk_profile_id=bindings["risk_profile_id"],
        execution_profile_id=bindings["execution_profile_id"],
        mode=preferred_mode,
    )
    runtime["symbol_source"] = symbol_resolution.get("source_type", "manual")
    runtime.setdefault("runtime_context", {})["symbol_resolution_snapshot"] = symbol_resolution
    runtime.setdefault("runtime_context", {})["binding_sources"] = bindings
    runtime.setdefault("runtime_context", {})["binding_validation_result"] = {
        "strategy_id": bindings["strategy_id"],
        "strategy_template_id": getattr(bot, "strategy_template_id", None),
        "risk_profile_id": bindings["risk_profile_id"],
        "execution_profile_id": bindings["execution_profile_id"],
        "symbol_source": symbol_resolution.get("source_type"),
        "resolved_symbols": symbol_resolution.get("symbols") or [],
        "compatibility": "ok" if strategy_ok else "failed",
    }
    runtime.setdefault("runtime_context", {})["queue_registration"] = {
        "queue_name": "execution_queue",
        "registered_at": _now_iso(),
        "graceful_stop": True,
        "force_close_default": False,
    }
    runtime.setdefault("runtime_context", {})["correlation_namespace"] = f"bot:{bot.id}"
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
    runtime = _ensure_runtime(db, bot)
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
                "correlation_namespace": (runtime.get("runtime_context") or {}).get("correlation_namespace"),
            },
            "generated_at": row.generated_at,
        }
        for row in rows
    ]


def get_bot_runtime_trades(db, *, bot: BotProfile) -> list[dict]:
    runtime = _ensure_runtime(db, bot)
    resolved_symbols = list((_resolve_symbol_source(db, bot).get("symbols") or list(bot.symbols or [])))
    rows = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.user_id == bot.user_id, ExecutionMetric.symbol.in_(resolved_symbols), ExecutionMetric.strategy_type == bot.strategy_type)
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
                "correlation_namespace": (runtime.get("runtime_context") or {}).get("correlation_namespace"),
                "execution_pipeline": "signal -> risk_check -> execution_queue -> execution_result -> position_update",
            },
            "created_at": row.created_at,
        }
        for row in rows
    ]