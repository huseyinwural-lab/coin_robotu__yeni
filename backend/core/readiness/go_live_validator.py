from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.live.readiness_score_engine import compute_readiness_score
from core.safety.kill_switch import get_kill_switch_state
from db import redis_client
from models import CommercialTrade, ExecutionMetric, LiveActivationConfig, Order, PaperPosition, Position, UserExchangeConnection
from runtime_control.pipeline_controller import PIPELINE_QUEUE_KEYS
from services.execution_mode_control_service import get_execution_mode, normalize_execution_mode
from services.exchange_adapter.execution_adapter import ExchangeExecutionAdapter
from services.live_mode_service import (
    _rate_limit_health,
    _risk_orchestrator_enabled,
    _worker_lag_seconds,
    get_market_ticker,
    get_or_create_live_config,
    release_gate_view,
)
from services.pipeline.cache_store import get_json

BLOCKING_CHECKS = {
    "mode_integrity",
    "explicit_live_enabled",
    "kill_switch_clear",
    "release_gate_pass",
    "exchange_connection_ready",
    "credentials_env_match",
    "balances_present",
    "positions_present",
    "open_orders_present",
    "market_data_present",
}

LAYER_KEYS = ["core", "trading_state", "exchange", "execution", "risk", "infra"]

RISK_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "risk_engine_config.json"
RISK_CONFIG_BACKUP_PATH = Path(__file__).resolve().parents[2] / "config" / "risk_engine_config_backup.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_risk_config() -> dict:
    for path in [RISK_CONFIG_PATH, RISK_CONFIG_BACKUP_PATH]:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


def _parse_timestamp(raw: Any) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_stale(raw: Any, *, threshold_sec: int) -> bool:
    stamp = _parse_timestamp(raw)
    if stamp is None:
        return True
    return (_utcnow() - stamp).total_seconds() > threshold_sec


def _normalize_mode(value: str | None) -> str | None:
    return normalize_execution_mode(value)


def _latest_connection(db: Session, user_id: str | None) -> UserExchangeConnection | None:
    query = db.query(UserExchangeConnection)
    if user_id:
        query = query.filter(UserExchangeConnection.user_id == user_id)
    return query.order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc()).first()


def _build_step(
    *,
    step_key: str,
    status: str,
    blocking: bool,
    reason_code: str,
    message: str,
    details: dict | None,
    data_source: str,
    started_at: float,
) -> dict:
    now = _utcnow()
    duration_ms = max(int((time.perf_counter() - started_at) * 1000), 0)
    return {
        "step_key": step_key,
        "status": status,
        "blocking": bool(blocking),
        "reason_code": reason_code,
        "message": message,
        "details": details or {},
        "duration_ms": duration_ms,
        "data_source": data_source,
        "timestamp": now.isoformat(),
    }


def _resolve_data_source(
    *,
    cache,
    key: str,
    fallback_fn=None,
    allow_list: bool = True,
    source_name: str,
) -> dict:
    payload = None
    data_source = "cache"
    fallback_used = False
    error = None
    try:
        payload = get_json(cache, key) if cache else None
    except Exception as exc:  # pragma: no cover - defensive
        payload = None
        error = f"cache_error:{exc}"

    if payload is None and fallback_fn is not None:
        try:
            payload = fallback_fn()
            fallback_used = True
            data_source = "fallback"
        except Exception as exc:  # pragma: no cover - defensive
            payload = None
            error = f"fallback_error:{exc}"

    available = payload is not None
    if allow_list and available and not isinstance(payload, list):
        available = False
    return {
        "key": key,
        "source_name": source_name,
        "data_source": data_source,
        "fallback_used": fallback_used,
        "available": available,
        "payload": payload,
        "timestamp": payload.get("timestamp") if isinstance(payload, dict) else None,
        "error": error,
    }


def _extract_latency_ms(snapshot: dict) -> int:
    latency_ms = snapshot.get("validation_latency_ms") or snapshot.get("latency_ms") or 0
    try:
        return max(int(float(latency_ms)), 0)
    except (TypeError, ValueError):
        return 0


def build_go_live_context(
    db: Session,
    cache,
    *,
    user_id: str | None = None,
    overrides: dict | None = None,
) -> dict:
    overrides = overrides or {}
    config = overrides.get("config") or get_or_create_live_config(db)
    execution_mode = overrides.get("execution_mode") or get_execution_mode(db, cache)
    env_mode = _normalize_mode(os.environ.get("EXECUTION_MODE"))

    kill_switch_payload = overrides.get("kill_switch")
    if kill_switch_payload is None:
        kill_switch_payload = get_kill_switch_state()
    kill_switch_active = bool(kill_switch_payload.get("active"))

    release_gate = overrides.get("release_gate")
    if release_gate is None:
        try:
            release_gate = release_gate_view(db, environment="prod")
        except Exception:  # pragma: no cover - defensive
            release_gate = {"status": "UNKNOWN", "reason_codes": ["release_gate_runtime_error"]}

    connection = overrides.get("connection") or _latest_connection(db, user_id)
    readiness_snapshot = dict(connection.readiness_snapshot or {}) if connection else {}
    connection_health = str(readiness_snapshot.get("connection_health") or "unknown").lower()
    can_trade = bool(readiness_snapshot.get("can_trade"))
    validation_success = bool(readiness_snapshot.get("validation_success") or readiness_snapshot.get("is_valid"))

    connection_payload = {
        "exists": connection is not None,
        "connection_health": connection_health,
        "can_trade": can_trade,
        "validation_success": validation_success,
        "environment": str(connection.environment or "") if connection else "",
        "exchange": str(connection.exchange or "") if connection else "",
        "market_type": str(connection.market_type or "") if connection else "",
        "latency_ms": _extract_latency_ms(readiness_snapshot),
        "source": "exchange_connection_snapshot" if connection else "missing",
    }

    positions_source = overrides.get("positions_source") or _resolve_data_source(
        cache=cache,
        key="exchange:futures:positions",
        allow_list=True,
        source_name="positions",
        fallback_fn=lambda: [
            {
                "symbol": row.symbol,
                "quantity": float(row.quantity),
                "entry_price": float(row.entry_price),
            }
            for row in db.query(PaperPosition)
            .filter(PaperPosition.market_type == "futures", PaperPosition.status == "open")
            .all()
        ],
    )

    orders_source = overrides.get("orders_source") or _resolve_data_source(
        cache=cache,
        key="exchange:futures:orders",
        allow_list=True,
        source_name="open_orders",
        fallback_fn=lambda: [
            {
                "order_id": row.order_id,
                "symbol": row.symbol,
                "side": row.side,
            }
            for row in db.query(ExecutionMetric)
            .order_by(ExecutionMetric.created_at.desc())
            .limit(50)
            .all()
        ],
    )

    balances_source = overrides.get("balances_source") or _resolve_data_source(
        cache=cache,
        key="exchange:futures:balance",
        allow_list=False,
        source_name="balances",
        fallback_fn=lambda: {"wallet_balance": 0.0, "available_balance": 0.0, "fallback": True},
    )

    def _fallback_market():
        snapshot = get_market_ticker("BTCUSDT")
        return snapshot

    market_source = overrides.get("market_source") or _resolve_data_source(
        cache=cache,
        key="market:ticker:BTCUSDT",
        allow_list=False,
        source_name="market_data",
        fallback_fn=_fallback_market,
    )

    risk_config = overrides.get("risk_config") or _load_risk_config()
    risk_orchestrator_enabled = _risk_orchestrator_enabled(db)

    positions_query = db.query(Position).filter(Position.status == "open")
    if user_id:
        positions_query = positions_query.filter(Position.user_id == user_id)
    engine_positions = positions_query.all()

    orders_query = db.query(Order).filter(Order.state.in_(["CREATED", "OPEN", "PARTIALLY_FILLED"]))
    if user_id:
        orders_query = orders_query.filter(Order.user_id == user_id)
    engine_orders = orders_query.all()

    partial_fill_count = 0
    try:
        partial_query = db.query(Order).filter(Order.state == "PARTIALLY_FILLED")
        if user_id:
            partial_query = partial_query.filter(Order.user_id == user_id)
        partial_fill_count = partial_query.count()
    except Exception:
        partial_fill_count = 0

    total_exposure = 0.0
    for row in engine_positions:
        price = float(row.current_price or row.entry_price or 0)
        total_exposure += abs(float(row.size or 0)) * price

    funding_available = False
    funding_error = None
    funding_count = 0
    try:
        threshold = _utcnow() - timedelta(days=1)
        funding_query = db.query(CommercialTrade).filter(CommercialTrade.ingested_at >= threshold)
        funding_query = funding_query.filter(CommercialTrade.funding_fee_usd != 0)
        if user_id:
            funding_query = funding_query.filter(CommercialTrade.user_id == user_id)
        funding_count = funding_query.count()
        funding_available = funding_count > 0
    except Exception as exc:
        funding_error = str(exc)

    exec_adapter = ExchangeExecutionAdapter()
    test_exchange = connection_payload.get("exchange") or "bybit"
    test_symbol = "BTCUSDT"
    try:
        precision_result = exec_adapter.validate_precision_and_lot_size(
            exchange=test_exchange,
            symbol=test_symbol,
            price=50000,
            qty=0.001,
            leverage=1,
        )
        submit_result = exec_adapter.submit_order(
            exchange=test_exchange,
            symbol=test_symbol,
            side="buy",
            price=50000,
            qty=0.001,
            leverage=1,
            environment="testnet",
        )
        cancel_result = exec_adapter.cancel_order(
            exchange=test_exchange,
            symbol=test_symbol,
            order_id="readiness-dry",
            environment="testnet",
        )
    except Exception as exc:  # pragma: no cover - defensive
        precision_result = {"status": "ERROR", "error": str(exc)}
        submit_result = {"status": "ERROR", "error": str(exc), "mocked": True}
        cancel_result = {"status": "ERROR", "error": str(exc), "mocked": True}

    websocket_snapshot = get_json(cache, "exchange:heartbeat") if cache else {}
    rate_limit_status = _rate_limit_health(db)

    db_ok = True
    try:
        db.execute(text("select 1"))
    except Exception:
        db_ok = False

    redis_ok = False
    queue_sizes: dict[str, int] = {}
    worker_events = 0
    if redis_client is not None:
        try:
            redis_ok = bool(redis_client.ping())
        except Exception:
            redis_ok = False
    if redis_ok:
        for key in PIPELINE_QUEUE_KEYS:
            try:
                if hasattr(redis_client, "llen"):
                    queue_sizes[key] = int(redis_client.llen(key))
                else:
                    queue_sizes[key] = len(redis_client.lrange(key, 0, -1)) if hasattr(redis_client, "lrange") else 0
            except Exception:
                queue_sizes[key] = 0
        try:
            worker_events = int(redis_client.llen("runtime:events:all"))
        except Exception:
            worker_events = 0

    worker_lag_sec = _worker_lag_seconds() if redis_ok else None

    return {
        "generated_at": _utcnow().isoformat(),
        "config": config,
        "execution_mode": execution_mode,
        "env_mode": env_mode,
        "kill_switch_active": kill_switch_active,
        "kill_switch_payload": kill_switch_payload,
        "release_gate": release_gate,
        "connection": connection_payload,
        "data_sources": {
            "balances": balances_source,
            "positions": positions_source,
            "open_orders": orders_source,
            "market_data": market_source,
        },
        "risk_config": risk_config,
        "risk_orchestrator_enabled": risk_orchestrator_enabled,
        "trading_state": {
            "engine_positions": engine_positions,
            "engine_orders": engine_orders,
            "position_count": len(engine_positions),
            "order_count": len(engine_orders),
            "total_exposure": total_exposure,
            "partial_fill_count": partial_fill_count,
            "funding_available": funding_available,
            "funding_count": funding_count,
            "funding_error": funding_error,
        },
        "execution_tests": {
            "precision": precision_result,
            "submit": submit_result,
            "cancel": cancel_result,
        },
        "exchange_metrics": {
            "websocket": websocket_snapshot,
            "rate_limit_status": rate_limit_status,
        },
        "infra": {
            "db_ok": db_ok,
            "redis_ok": redis_ok,
            "queue_sizes": queue_sizes,
            "worker_events": worker_events,
            "worker_lag_sec": worker_lag_sec,
            "strategy_engine_status": "unknown",
        },
    }




def run_go_live_validator(context: dict) -> dict:
    steps: list[dict] = []
    by_layer = {layer: [] for layer in LAYER_KEYS}

    def add_step(layer: str, step: dict) -> None:
        step["layer"] = layer
        steps.append(step)
        by_layer[layer].append(step)

    execution_mode = str(context.get("execution_mode") or "SIM").upper()
    env_mode = context.get("env_mode")
    config: LiveActivationConfig | None = context.get("config")
    release_gate = context.get("release_gate") or {}
    connection = context.get("connection") or {}
    data_sources = context.get("data_sources") or {}
    trading_state = context.get("trading_state") or {}
    execution_tests = context.get("execution_tests") or {}
    exchange_metrics = context.get("exchange_metrics") or {}
    infra = context.get("infra") or {}
    risk_config = context.get("risk_config") or {}
    risk_orchestrator_enabled = bool(context.get("risk_orchestrator_enabled"))

    degraded = False

    mode_start = time.perf_counter()
    mode_ok = execution_mode == "LIVE"
    if env_mode and env_mode != execution_mode:
        mode_ok = False
    add_step(
        "core",
        _build_step(
            step_key="mode_integrity",
            status="PASS" if mode_ok else "FAIL",
            blocking=True,
            reason_code="MODE_MISMATCH" if not mode_ok else "PASS",
            message="Execution mode LIVE olmalı" if not mode_ok else "Mode LIVE",
            details={"execution_mode": execution_mode, "env_mode": env_mode},
            data_source="execution_mode_control",
            started_at=mode_start,
        ),
    )

    live_start = time.perf_counter()
    explicit_live = bool(config.live_mode_enabled) if config else False
    safe_mode = bool(config.safe_mode_enabled) if config else False
    explicit_ok = explicit_live and not safe_mode
    add_step(
        "core",
        _build_step(
            step_key="explicit_live_enabled",
            status="PASS" if explicit_ok else "FAIL",
            blocking=True,
            reason_code="EXPLICIT_LIVE_DISABLED" if not explicit_ok else "PASS",
            message="Live enable flag zorunlu" if not explicit_ok else "Live flag açık",
            details={"live_mode_enabled": explicit_live, "safe_mode_enabled": safe_mode},
            data_source="live_activation_config",
            started_at=live_start,
        ),
    )

    kill_start = time.perf_counter()
    kill_switch_active = bool(context.get("kill_switch_active"))
    config_kill_switch = bool(config.kill_switch_enabled) if config else False
    kill_ok = not kill_switch_active and not config_kill_switch
    add_step(
        "core",
        _build_step(
            step_key="kill_switch_clear",
            status="PASS" if kill_ok else "FAIL",
            blocking=True,
            reason_code="KILL_SWITCH_ACTIVE" if not kill_ok else "PASS",
            message="Kill switch aktif" if not kill_ok else "Kill switch pasif",
            details={"kill_switch_active": kill_switch_active, "config_kill_switch": config_kill_switch},
            data_source="redis:execution:kill_switch:state",
            started_at=kill_start,
        ),
    )

    gate_start = time.perf_counter()
    gate_status = str(release_gate.get("status") or "UNKNOWN").upper()
    gate_ok = gate_status == "PASS"
    add_step(
        "core",
        _build_step(
            step_key="release_gate_pass",
            status="PASS" if gate_ok else "FAIL" if gate_status != "UNKNOWN" else "UNKNOWN",
            blocking=True,
            reason_code="PASS" if gate_ok else str(release_gate.get("reason_code") or "RELEASE_GATE_BLOCKED"),
            message="Release gate PASS değil" if not gate_ok else "Release gate PASS",
            details={"status": gate_status, "reason_codes": release_gate.get("reason_codes")},
            data_source="release_gate_view",
            started_at=gate_start,
        ),
    )

    conn_start = time.perf_counter()
    connection_exists = bool(connection.get("exists"))
    connection_health = str(connection.get("connection_health") or "unknown").lower()
    can_trade = bool(connection.get("can_trade"))
    validation_success = bool(connection.get("validation_success"))
    connection_ok = connection_exists and connection_health in {"online", "degraded"} and can_trade and validation_success
    conn_status = "PASS" if connection_ok else "UNKNOWN" if not connection_exists else "FAIL"
    add_step(
        "core",
        _build_step(
            step_key="exchange_connection_ready",
            status=conn_status,
            blocking=True,
            reason_code="PASS" if connection_ok else "EXCHANGE_CONNECTION_MISSING" if not connection_exists else "EXCHANGE_CONNECTION_UNHEALTHY",
            message="Exchange bağlantısı hazır değil" if not connection_ok else "Exchange bağlantısı hazır",
            details={
                "connection_health": connection_health,
                "can_trade": can_trade,
                "validation_success": validation_success,
            },
            data_source=str(connection.get("source") or "connection_snapshot"),
            started_at=conn_start,
        ),
    )

    env_start = time.perf_counter()
    connection_env = str(connection.get("environment") or "").lower()
    env_ok = False
    if connection_exists:
        if execution_mode == "LIVE":
            env_ok = connection_env in {"live", "prod", "production"}
        elif execution_mode == "TESTNET":
            env_ok = connection_env in {"testnet", "paper"}
        elif execution_mode == "SIM":
            env_ok = connection_env in {"testnet", "paper", "sim", "mock"}
    env_status = "PASS" if env_ok else "UNKNOWN" if not connection_exists else "FAIL"
    add_step(
        "core",
        _build_step(
            step_key="credentials_env_match",
            status=env_status,
            blocking=True,
            reason_code="CREDENTIAL_ENV_MISMATCH" if not env_ok else "PASS",
            message="Credential environment uyuşmuyor" if not env_ok else "Credential environment uyumlu",
            details={"connection_environment": connection_env, "execution_mode": execution_mode},
            data_source="connection_environment",
            started_at=env_start,
        ),
    )

    def _data_step(name: str, reason_code: str, message: str):
        nonlocal degraded
        data = data_sources.get(name) or {}
        available = bool(data.get("available"))
        fallback_used = bool(data.get("fallback_used"))
        status = "PASS" if available and not fallback_used else "UNKNOWN"
        if not available or fallback_used:
            degraded = True
        return _build_step(
            step_key=f"{name}_present",
            status=status,
            blocking=True,
            reason_code=reason_code,
            message=message if status != "PASS" else f"{name} mevcut",
            details={"fallback_used": fallback_used, "source": data.get("data_source")},
            data_source=str(data.get("data_source") or "cache"),
            started_at=time.perf_counter(),
        )

    for key, reason, message in [
        ("balances", "BALANCE_DATA_MISSING", "Balance verisi eksik"),
        ("positions", "POSITION_DATA_MISSING", "Position verisi eksik"),
        ("open_orders", "OPEN_ORDERS_DATA_MISSING", "Open orders verisi eksik"),
        ("market_data", "MARKET_DATA_MISSING", "Market data verisi eksik"),
    ]:
        add_step("core", _data_step(key, reason, message))

    # Trading state checks
    stale_threshold_sec = int(_safe_float(risk_config.get("stale_data_threshold_ms"), 120000) or 120000) // 1000
    balances_payload = (data_sources.get("balances") or {}).get("payload") or {}
    balance_available = bool((data_sources.get("balances") or {}).get("available"))
    balance_stale = _is_stale(balances_payload.get("timestamp"), threshold_sec=stale_threshold_sec) if balance_available else False
    available_balance = _safe_float(
        balances_payload.get("available_balance")
        or balances_payload.get("free_balance")
        or balances_payload.get("available")
    )
    wallet_balance = _safe_float(
        balances_payload.get("wallet_balance")
        or balances_payload.get("total_balance")
        or balances_payload.get("equity")
    )

    if not balance_available:
        balance_status = "UNKNOWN"
        balance_reason = "BALANCE_DATA_MISSING"
    elif balance_stale:
        balance_status = "FAIL"
        balance_reason = "BALANCE_DATA_STALE"
    elif available_balance is None and wallet_balance is None:
        balance_status = "UNKNOWN"
        balance_reason = "BALANCE_DATA_INCOMPLETE"
    elif (available_balance is not None and available_balance <= 0) or (wallet_balance is not None and wallet_balance <= 0):
        balance_status = "FAIL"
        balance_reason = "BALANCE_INSUFFICIENT"
    else:
        balance_status = "PASS"
        balance_reason = "PASS"

    add_step(
        "trading_state",
        _build_step(
            step_key="balance_check",
            status=balance_status,
            blocking=True,
            reason_code=balance_reason,
            message="Balance hazır" if balance_status == "PASS" else "Balance doğrulama başarısız",
            details={
                "available_balance": available_balance,
                "wallet_balance": wallet_balance,
                "stale": balance_stale,
            },
            data_source="balances",
            started_at=time.perf_counter(),
        ),
    )

    exchange_positions = (data_sources.get("positions") or {}).get("payload")
    exchange_positions_count = len(exchange_positions) if isinstance(exchange_positions, list) else None
    engine_positions_count = int(trading_state.get("position_count") or 0)
    if exchange_positions_count is None:
        position_status = "UNKNOWN"
        position_reason = "POSITION_DATA_MISSING"
    else:
        position_status = "PASS" if exchange_positions_count == engine_positions_count else "FAIL"
        position_reason = "POSITION_SYNC_MISMATCH" if position_status == "FAIL" else "PASS"

    add_step(
        "trading_state",
        _build_step(
            step_key="position_sync",
            status=position_status,
            blocking=True,
            reason_code=position_reason,
            message="Position sync ok" if position_status == "PASS" else "Position sync başarısız",
            details={"engine": engine_positions_count, "exchange": exchange_positions_count},
            data_source="positions",
            started_at=time.perf_counter(),
        ),
    )

    exchange_orders = (data_sources.get("open_orders") or {}).get("payload")
    exchange_orders_count = len(exchange_orders) if isinstance(exchange_orders, list) else None
    engine_orders_count = int(trading_state.get("order_count") or 0)
    if exchange_orders_count is None:
        order_status = "UNKNOWN"
        order_reason = "OPEN_ORDERS_DATA_MISSING"
    else:
        order_status = "PASS" if exchange_orders_count == engine_orders_count else "FAIL"
        order_reason = "OPEN_ORDERS_MISMATCH" if order_status == "FAIL" else "PASS"

    add_step(
        "trading_state",
        _build_step(
            step_key="open_orders_sync",
            status=order_status,
            blocking=True,
            reason_code=order_reason,
            message="Open orders sync ok" if order_status == "PASS" else "Open orders sync başarısız",
            details={"engine": engine_orders_count, "exchange": exchange_orders_count},
            data_source="open_orders",
            started_at=time.perf_counter(),
        ),
    )

    max_margin_usage = _safe_float(risk_config.get("max_margin_usage_pct"))
    margin_usage_pct = _safe_float(balances_payload.get("margin_usage_pct") or balances_payload.get("margin_usage_ratio"))
    if margin_usage_pct is None and available_balance is None:
        margin_status = "UNKNOWN"
        margin_reason = "MARGIN_DATA_MISSING"
    elif max_margin_usage is not None and margin_usage_pct is not None and margin_usage_pct > max_margin_usage:
        margin_status = "FAIL"
        margin_reason = "MARGIN_USAGE_HIGH"
    elif available_balance is not None and available_balance <= 0:
        margin_status = "FAIL"
        margin_reason = "MARGIN_INSUFFICIENT"
    else:
        margin_status = "PASS"
        margin_reason = "PASS"

    add_step(
        "trading_state",
        _build_step(
            step_key="margin_availability",
            status=margin_status,
            blocking=True,
            reason_code=margin_reason,
            message="Margin yeterli" if margin_status == "PASS" else "Margin yetersiz",
            details={"available_balance": available_balance, "margin_usage_pct": margin_usage_pct},
            data_source="balances",
            started_at=time.perf_counter(),
        ),
    )

    funding_available = bool(trading_state.get("funding_available"))
    funding_error = trading_state.get("funding_error")
    if funding_error:
        funding_status = "UNKNOWN"
        funding_reason = "FUNDING_DATA_ERROR"
    elif funding_available:
        funding_status = "PASS"
        funding_reason = "PASS"
    else:
        funding_status = "UNKNOWN"
        funding_reason = "FUNDING_DATA_MISSING"

    add_step(
        "trading_state",
        _build_step(
            step_key="funding_status",
            status=funding_status,
            blocking=False,
            reason_code=funding_reason,
            message="Funding data mevcut" if funding_status == "PASS" else "Funding data yok",
            details={"funding_count": trading_state.get("funding_count", 0)},
            data_source="commercial_trades",
            started_at=time.perf_counter(),
        ),
    )

    if engine_positions_count == 0:
        liquidation_status = "PASS"
        liquidation_reason = "PASS"
    else:
        liquidation_status = "UNKNOWN"
        liquidation_reason = "LIQUIDATION_DATA_MISSING"
    add_step(
        "trading_state",
        _build_step(
            step_key="liquidation_risk",
            status=liquidation_status,
            blocking=True,
            reason_code=liquidation_reason,
            message="Liquidation risk uygun" if liquidation_status == "PASS" else "Liquidation riski doğrulanamadı",
            details={"position_count": engine_positions_count},
            data_source="risk_config",
            started_at=time.perf_counter(),
        ),
    )

    # Exchange checks
    api_status = "PASS" if connection_ok else "UNKNOWN" if not connection_exists else "FAIL"
    api_reason = "PASS" if api_status == "PASS" else "EXCHANGE_API_UNAVAILABLE"
    add_step(
        "exchange",
        _build_step(
            step_key="api_connectivity",
            status=api_status,
            blocking=True,
            reason_code=api_reason,
            message="API connectivity ok" if api_status == "PASS" else "API connectivity başarısız",
            details={"connection_health": connection_health, "can_trade": can_trade},
            data_source="exchange_connection_snapshot",
            started_at=time.perf_counter(),
        ),
    )

    ws_snapshot = exchange_metrics.get("websocket") or {}
    ws_age = _safe_float(ws_snapshot.get("age_sec") or ws_snapshot.get("heartbeat_age_sec") or ws_snapshot.get("latency_sec"))
    if ws_age is None:
        ws_status = "UNKNOWN"
        ws_reason = "WEBSOCKET_MISSING"
    elif ws_age > 90:
        ws_status = "FAIL"
        ws_reason = "WEBSOCKET_STALE"
    elif ws_age > 30:
        ws_status = "WARN"
        ws_reason = "WEBSOCKET_DELAY"
    else:
        ws_status = "PASS"
        ws_reason = "PASS"

    add_step(
        "exchange",
        _build_step(
            step_key="websocket_health",
            status=ws_status,
            blocking=True,
            reason_code=ws_reason,
            message="Websocket sağlıklı" if ws_status == "PASS" else "Websocket sağlıksız",
            details={"age_sec": ws_age},
            data_source="exchange:heartbeat",
            started_at=time.perf_counter(),
        ),
    )

    market_source = data_sources.get("market_data") or {}
    market_payload = market_source.get("payload") or {}
    bid = _safe_float(market_payload.get("bid") or market_payload.get("best_bid"))
    ask = _safe_float(market_payload.get("ask") or market_payload.get("best_ask"))
    if not market_source.get("available"):
        orderbook_status = "UNKNOWN"
        orderbook_reason = "ORDERBOOK_MISSING"
    elif bid is None or ask is None or bid <= 0 or ask <= 0:
        orderbook_status = "FAIL"
        orderbook_reason = "ORDERBOOK_INVALID"
    else:
        orderbook_status = "PASS"
        orderbook_reason = "PASS"

    add_step(
        "exchange",
        _build_step(
            step_key="orderbook_sync",
            status=orderbook_status,
            blocking=True,
            reason_code=orderbook_reason,
            message="Orderbook sync ok" if orderbook_status == "PASS" else "Orderbook sync başarısız",
            details={"bid": bid, "ask": ask},
            data_source="market_data",
            started_at=time.perf_counter(),
        ),
    )

    rate_limit_status = str(exchange_metrics.get("rate_limit_status") or "unknown").lower()
    if rate_limit_status == "ok":
        rate_status = "PASS"
        rate_reason = "PASS"
    elif rate_limit_status == "critical":
        rate_status = "FAIL"
        rate_reason = "RATE_LIMIT_CRITICAL"
    elif rate_limit_status == "warning":
        rate_status = "WARN"
        rate_reason = "RATE_LIMIT_WARNING"
    else:
        rate_status = "UNKNOWN"
        rate_reason = "RATE_LIMIT_UNKNOWN"

    add_step(
        "exchange",
        _build_step(
            step_key="rate_limit_state",
            status=rate_status,
            blocking=True,
            reason_code=rate_reason,
            message="Rate limit sağlıklı" if rate_status == "PASS" else "Rate limit riski",
            details={"rate_limit_status": rate_limit_status},
            data_source="exchange_registry",
            started_at=time.perf_counter(),
        ),
    )

    # Execution checks
    precision = execution_tests.get("precision") or {}
    precision_ok = str(precision.get("status") or "").upper() == "PASS"
    precision_status = "PASS" if precision_ok else "FAIL" if precision else "UNKNOWN"
    add_step(
        "execution",
        _build_step(
            step_key="precision_validation",
            status=precision_status,
            blocking=True,
            reason_code="EXECUTION_PRECISION_FAIL" if not precision_ok else "PASS",
            message="Precision doğrulandı" if precision_ok else "Precision doğrulanamadı",
            details={"status": precision.get("status")},
            data_source="execution_adapter",
            started_at=time.perf_counter(),
        ),
    )

    submit = execution_tests.get("submit") or {}
    submit_mocked = bool(submit.get("mocked"))
    submit_status_raw = str(submit.get("status") or "").upper()
    submit_ok = submit_status_raw in {"SUBMITTED", "FILLED"} and not submit_mocked
    submit_status = "PASS" if submit_ok else "FAIL" if submit else "UNKNOWN"
    add_step(
        "execution",
        _build_step(
            step_key="dry_run_order",
            status=submit_status,
            blocking=True,
            reason_code="EXECUTION_TEST_MOCKED" if submit_mocked else "EXECUTION_SUBMIT_FAIL" if not submit_ok else "PASS",
            message="Dry run order ok" if submit_ok else "Dry run order başarısız",
            details={"status": submit.get("status"), "mocked": submit_mocked},
            data_source="execution_adapter",
            started_at=time.perf_counter(),
        ),
    )

    cancel = execution_tests.get("cancel") or {}
    cancel_mocked = bool(cancel.get("mocked"))
    cancel_status_raw = str(cancel.get("status") or "").upper()
    cancel_ok = cancel_status_raw == "CANCELLED" and not cancel_mocked
    cancel_status = "PASS" if cancel_ok else "FAIL" if cancel else "UNKNOWN"
    add_step(
        "execution",
        _build_step(
            step_key="cancel_test",
            status=cancel_status,
            blocking=True,
            reason_code="EXECUTION_CANCEL_MOCKED" if cancel_mocked else "EXECUTION_CANCEL_FAIL" if not cancel_ok else "PASS",
            message="Cancel test ok" if cancel_ok else "Cancel test başarısız",
            details={"status": cancel.get("status"), "mocked": cancel_mocked},
            data_source="execution_adapter",
            started_at=time.perf_counter(),
        ),
    )

    partial_fill_count = int(trading_state.get("partial_fill_count") or 0)
    if partial_fill_count > 0:
        partial_status = "PASS"
        partial_reason = "PASS"
    else:
        partial_status = "UNKNOWN"
        partial_reason = "PARTIAL_FILL_UNVERIFIED"
    add_step(
        "execution",
        _build_step(
            step_key="partial_fill_handling",
            status=partial_status,
            blocking=True,
            reason_code=partial_reason,
            message="Partial fill doğrulandı" if partial_status == "PASS" else "Partial fill doğrulanamadı",
            details={"partial_fill_count": partial_fill_count},
            data_source="execution_orders",
            started_at=time.perf_counter(),
        ),
    )

    if engine_positions_count == 0 and engine_orders_count == 0:
        reduce_status = "PASS"
        reduce_reason = "PASS"
    else:
        reduce_status = "UNKNOWN"
        reduce_reason = "REDUCE_ONLY_UNVERIFIED"

    add_step(
        "execution",
        _build_step(
            step_key="reduce_only_enforcement",
            status=reduce_status,
            blocking=True,
            reason_code=reduce_reason,
            message="Reduce-only doğrulandı" if reduce_status == "PASS" else "Reduce-only doğrulanamadı",
            details={"position_count": engine_positions_count, "order_count": engine_orders_count},
            data_source="execution_rules",
            started_at=time.perf_counter(),
        ),
    )

    # Risk checks
    risk_config_ok = bool(risk_config)
    add_step(
        "risk",
        _build_step(
            step_key="risk_config_loaded",
            status="PASS" if risk_config_ok else "FAIL",
            blocking=True,
            reason_code="PASS" if risk_config_ok else "RISK_CONFIG_MISSING",
            message="Risk config yüklendi" if risk_config_ok else "Risk config yok",
            details={"config_version": risk_config.get("config_version")},
            data_source="risk_engine_config",
            started_at=time.perf_counter(),
        ),
    )

    max_leverage = _safe_float(risk_config.get("max_leverage"))
    leverage_violation = False
    if max_leverage is not None:
        for row in trading_state.get("engine_positions") or []:
            try:
                if float(row.leverage or 0) > max_leverage:
                    leverage_violation = True
                    break
            except Exception:
                continue
    leverage_status = "PASS" if not leverage_violation else "FAIL"
    if max_leverage is None:
        leverage_status = "UNKNOWN"
    add_step(
        "risk",
        _build_step(
            step_key="leverage_validation",
            status=leverage_status,
            blocking=True,
            reason_code="LEVERAGE_MISMATCH" if leverage_status == "FAIL" else "RISK_CONFIG_MISSING" if leverage_status == "UNKNOWN" else "PASS",
            message="Leverage limit ok" if leverage_status == "PASS" else "Leverage mismatch",
            details={"max_leverage": max_leverage},
            data_source="risk_engine_config",
            started_at=time.perf_counter(),
        ),
    )

    if engine_positions_count == 0:
        margin_mode_status = "PASS"
        margin_mode_reason = "PASS"
    else:
        margin_mode_status = "UNKNOWN"
        margin_mode_reason = "MARGIN_MODE_UNKNOWN"

    add_step(
        "risk",
        _build_step(
            step_key="margin_mode_validation",
            status=margin_mode_status,
            blocking=True,
            reason_code=margin_mode_reason,
            message="Margin mode doğrulandı" if margin_mode_status == "PASS" else "Margin mode doğrulanamadı",
            details={"position_count": engine_positions_count},
            data_source="risk_engine_config",
            started_at=time.perf_counter(),
        ),
    )

    max_exposure_pct = _safe_float(risk_config.get("max_total_exposure_pct"))
    total_exposure = _safe_float(trading_state.get("total_exposure"), 0.0) or 0.0
    exposure_status = "UNKNOWN"
    exposure_reason = "EXPOSURE_DATA_MISSING"
    if wallet_balance is not None and wallet_balance > 0 and max_exposure_pct is not None:
        exposure_pct = (total_exposure / wallet_balance) * 100
        exposure_status = "FAIL" if exposure_pct > max_exposure_pct else "PASS"
        exposure_reason = "EXPOSURE_LIMIT_BREACH" if exposure_status == "FAIL" else "PASS"
    elif wallet_balance is not None and wallet_balance <= 0:
        exposure_status = "FAIL"
        exposure_reason = "EXPOSURE_NO_EQUITY"

    add_step(
        "risk",
        _build_step(
            step_key="position_size_limit",
            status=exposure_status,
            blocking=True,
            reason_code=exposure_reason,
            message="Exposure limiti ok" if exposure_status == "PASS" else "Exposure limiti aşıldı",
            details={"total_exposure": total_exposure, "wallet_balance": wallet_balance},
            data_source="risk_engine_config",
            started_at=time.perf_counter(),
        ),
    )

    add_step(
        "risk",
        _build_step(
            step_key="risk_engine_connectivity",
            status="PASS" if risk_orchestrator_enabled else "FAIL",
            blocking=True,
            reason_code="PASS" if risk_orchestrator_enabled else "RISK_ENGINE_UNAVAILABLE",
            message="Risk engine hazır" if risk_orchestrator_enabled else "Risk engine erişilemedi",
            details={"enabled": risk_orchestrator_enabled},
            data_source="risk_orchestrator",
            started_at=time.perf_counter(),
        ),
    )

    # Infra checks
    add_step(
        "infra",
        _build_step(
            step_key="db_check",
            status="PASS" if infra.get("db_ok") else "FAIL",
            blocking=True,
            reason_code="PASS" if infra.get("db_ok") else "DB_UNAVAILABLE",
            message="DB ok" if infra.get("db_ok") else "DB erişilemedi",
            details={},
            data_source="postgres",
            started_at=time.perf_counter(),
        ),
    )

    add_step(
        "infra",
        _build_step(
            step_key="redis_queue_check",
            status="PASS" if infra.get("redis_ok") else "FAIL",
            blocking=True,
            reason_code="PASS" if infra.get("redis_ok") else "REDIS_UNAVAILABLE",
            message="Redis ok" if infra.get("redis_ok") else "Redis erişilemedi",
            details={"queue_sizes": infra.get("queue_sizes")},
            data_source="redis",
            started_at=time.perf_counter(),
        ),
    )

    worker_events = int(infra.get("worker_events") or 0)
    worker_lag = _safe_float(infra.get("worker_lag_sec"))
    if worker_events == 0:
        worker_status = "UNKNOWN"
        worker_reason = "WORKER_STATE_UNKNOWN"
    elif worker_lag is not None and worker_lag > 120:
        worker_status = "FAIL"
        worker_reason = "WORKER_LAG_HIGH"
    else:
        worker_status = "PASS"
        worker_reason = "PASS"

    add_step(
        "infra",
        _build_step(
            step_key="worker_state",
            status=worker_status,
            blocking=True,
            reason_code=worker_reason,
            message="Worker sağlıklı" if worker_status == "PASS" else "Worker durumu belirsiz",
            details={"worker_events": worker_events, "worker_lag_sec": worker_lag},
            data_source="runtime:events:all",
            started_at=time.perf_counter(),
        ),
    )

    strategy_status_raw = str(infra.get("strategy_engine_status") or "unknown").lower()
    if strategy_status_raw in {"pass", "ok", "healthy"}:
        strategy_status = "PASS"
        strategy_reason = "PASS"
    elif strategy_status_raw in {"fail", "blocked", "down"}:
        strategy_status = "FAIL"
        strategy_reason = "STRATEGY_ENGINE_DOWN"
    else:
        strategy_status = "UNKNOWN"
        strategy_reason = "STRATEGY_ENGINE_UNKNOWN"

    add_step(
        "infra",
        _build_step(
            step_key="strategy_engine",
            status=strategy_status,
            blocking=True,
            reason_code=strategy_reason,
            message="Strategy engine sağlıklı" if strategy_status == "PASS" else "Strategy engine health yok",
            details={"status": strategy_status_raw},
            data_source="strategy_engine",
            started_at=time.perf_counter(),
        ),
    )

    reason_codes: list[str] = []
    blocking_total = 0
    blocking_passed = 0
    warning_total = 0
    warning_failed = 0
    unknown_total = 0

    blocking_failures: list[dict] = []
    warnings: list[dict] = []
    unknowns: list[dict] = []

    for step in steps:
        status = step["status"]
        if step["blocking"]:
            blocking_total += 1
            if status == "PASS":
                blocking_passed += 1
            else:
                blocking_failures.append({"step_key": step["step_key"], "layer": step.get("layer"), "reason_code": step["reason_code"], "status": status})
        if status == "WARN":
            warning_total += 1
            warning_failed += 1
            warnings.append({"step_key": step["step_key"], "layer": step.get("layer"), "reason_code": step["reason_code"]})
        if status == "UNKNOWN":
            unknown_total += 1
            unknowns.append({"step_key": step["step_key"], "layer": step.get("layer"), "reason_code": step["reason_code"]})
        if status != "PASS":
            reason_codes.append(step["reason_code"])

    readiness_state = "READY"
    if any(step["status"] == "FAIL" for step in steps if step["blocking"]):
        readiness_state = "BLOCKED"
    elif any(step["status"] == "UNKNOWN" for step in steps if step["blocking"]):
        readiness_state = "UNKNOWN"
    elif any(step["status"] == "WARN" for step in steps if step["blocking"]):
        readiness_state = "WARNING"

    score_payload = compute_readiness_score(
        position_sync_state="SYNCED" if (data_sources.get("positions") or {}).get("available") else "UNVERIFIED",
        order_reconciliation_state="RECONCILED" if (data_sources.get("open_orders") or {}).get("available") else "UNVERIFIED",
        balance_integrity_state="INTACT" if (data_sources.get("balances") or {}).get("available") else "UNVERIFIED",
        exchange_latency_state="NORMAL" if (data_sources.get("market_data") or {}).get("available") else "ALERT",
    )

    data_freshness = {}
    for key, source in data_sources.items():
        data_freshness[key] = {
            "available": bool(source.get("available")),
            "fallback_used": bool(source.get("fallback_used")),
            "timestamp": source.get("timestamp"),
            "data_source": source.get("data_source"),
            "stale_threshold_sec": stale_threshold_sec,
        }

    scores: dict[str, float] = {}
    for layer in LAYER_KEYS:
        layer_steps = by_layer.get(layer) or []
        if not layer_steps:
            scores[layer] = 0.0
            continue
        pass_count = sum(1 for step in layer_steps if step.get("status") == "PASS")
        scores[layer] = round((pass_count / len(layer_steps)) * 100, 2)

    return {
        "readiness_state": readiness_state,
        "go_live_allowed": readiness_state == "READY",
        "execution_allowed": readiness_state == "READY",
        "score": score_payload.get("readiness_confidence_score", 0.0),
        "scores": scores,
        "summary": {
            "blocking_total": blocking_total,
            "blocking_passed": blocking_passed,
            "warning_total": warning_total,
            "warning_failed": warning_failed,
            "unknown_total": unknown_total,
        },
        "steps": steps,
        "by_layer": by_layer,
        "blocking_failures": blocking_failures,
        "warnings": warnings,
        "unknowns": unknowns,
        "reason_codes": sorted(set(reason_codes)),
        "degraded": degraded or any(step["status"] == "UNKNOWN" for step in steps),
        "data_freshness": data_freshness,
        "generated_at": context.get("generated_at") or _utcnow().isoformat(),
        "legacy_score": score_payload,
        "execution_mode": execution_mode,
    }
def evaluate_go_live_readiness(
    db: Session,
    cache,
    *,
    user_id: str | None = None,
    refresh: bool = False,
    overrides: dict | None = None,
) -> dict:
    _ = refresh
    context = build_go_live_context(db, cache, user_id=user_id, overrides=overrides)
    try:
        return run_go_live_validator(context)
    except Exception:  # pragma: no cover - defensive fallback
        now = _utcnow().isoformat()
        return {
            "readiness_state": "UNKNOWN",
            "go_live_allowed": False,
            "execution_allowed": False,
            "score": 0.0,
            "scores": {layer: 0.0 for layer in LAYER_KEYS},
            "summary": {
                "blocking_total": 0,
                "blocking_passed": 0,
                "warning_total": 0,
                "warning_failed": 0,
                "unknown_total": 1,
            },
            "steps": [],
            "by_layer": {layer: [] for layer in LAYER_KEYS},
            "blocking_failures": [],
            "warnings": [],
            "unknowns": [],
            "reason_codes": ["validator_runtime_error"],
            "degraded": True,
            "data_freshness": {},
            "generated_at": now,
            "legacy_score": {},
            "execution_mode": str(context.get("execution_mode") or "SIM"),
        }
