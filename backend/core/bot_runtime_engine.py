from __future__ import annotations

from datetime import datetime, timezone

from services.pipeline.cache_store import get_json, set_json


BOT_RUNTIME_PREFIX = "bot:runtime"
BOT_RUNTIME_ALLOWED_MODES = {"live_ready_disabled", "paper", "mock"}
BOT_STATES = {"CREATED", "IDLE", "RUNNING", "PAUSED", "STOPPED", "ERROR"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_key(bot_id: str) -> str:
    return f"{BOT_RUNTIME_PREFIX}:{bot_id}"


def build_bot_runtime_config(*, bot, strategy_id: str, risk_profile_id: str | None, execution_profile_id: str | None) -> dict:
    return {
        "bot_id": bot.id,
        "strategy_id": strategy_id,
        "risk_profile_id": risk_profile_id,
        "execution_profile_id": execution_profile_id,
        "symbol_source": "manual",
        "symbol_source_ref": None,
        "mode": "live_ready_disabled",
        "status": "CREATED",
        "last_heartbeat": _now_iso(),
        "runtime_context": {
            "exchange": bot.exchange,
            "market_type": bot.market_type,
            "timeframe": bot.timeframe,
            "trend_timeframe": bot.trend_timeframe,
            "symbols": list(bot.symbols or []),
            "graceful_stop": True,
            "force_close_available": True,
            "force_close_default": False,
            "policy_force_close_enabled": False,
        },
    }


def load_bot_runtime(cache, bot_id: str) -> dict | None:
    return get_json(cache, _runtime_key(bot_id))


def save_bot_runtime(cache, payload: dict) -> dict:
    runtime = dict(payload or {})
    runtime["last_heartbeat"] = _now_iso()
    set_json(cache, _runtime_key(runtime["bot_id"]), runtime)
    return runtime


def initialize_bot_runtime(cache, *, bot, strategy_id: str, risk_profile_id: str | None, execution_profile_id: str | None) -> dict:
    existing = load_bot_runtime(cache, bot.id)
    if existing:
        return existing
    runtime = build_bot_runtime_config(
        bot=bot,
        strategy_id=strategy_id,
        risk_profile_id=risk_profile_id,
        execution_profile_id=execution_profile_id,
    )
    runtime["status"] = "IDLE"
    return save_bot_runtime(cache, runtime)


def bind_bot_runtime(cache, *, bot, strategy_id: str, risk_profile_id: str | None, execution_profile_id: str | None, mode: str | None = None) -> dict:
    runtime = initialize_bot_runtime(cache, bot=bot, strategy_id=strategy_id, risk_profile_id=risk_profile_id, execution_profile_id=execution_profile_id)
    runtime.update(
        {
            "strategy_id": strategy_id,
            "risk_profile_id": risk_profile_id,
            "execution_profile_id": execution_profile_id,
            "mode": mode if mode in BOT_RUNTIME_ALLOWED_MODES else runtime.get("mode", "live_ready_disabled"),
        }
    )
    return save_bot_runtime(cache, runtime)


def set_bot_runtime_state(cache, *, bot_id: str, state: str, error: str | None = None) -> dict:
    runtime = load_bot_runtime(cache, bot_id) or {
        "bot_id": bot_id,
        "strategy_id": None,
        "risk_profile_id": None,
        "execution_profile_id": None,
        "mode": "live_ready_disabled",
        "status": "CREATED",
        "runtime_context": {},
    }
    normalized = str(state or "IDLE").upper()
    runtime["status"] = normalized if normalized in BOT_STATES else "ERROR"
    if error:
        runtime.setdefault("runtime_context", {})["last_error"] = error
    return save_bot_runtime(cache, runtime)


def heartbeat_bot_runtime(cache, bot_id: str, *, patch: dict | None = None) -> dict:
    runtime = load_bot_runtime(cache, bot_id) or {"bot_id": bot_id, "runtime_context": {}, "status": "IDLE", "mode": "live_ready_disabled"}
    if patch:
        runtime.setdefault("runtime_context", {}).update(dict(patch))
    return save_bot_runtime(cache, runtime)
