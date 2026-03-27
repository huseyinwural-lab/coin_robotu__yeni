from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from core.live.readiness_score_engine import compute_readiness_score
from core.safety.kill_switch import get_kill_switch_state
from models import ExecutionMetric, LiveActivationConfig, PaperPosition, UserExchangeConnection
from services.execution_mode_control_service import get_execution_mode, normalize_execution_mode
from services.live_mode_service import get_market_ticker, get_or_create_live_config, release_gate_view
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    }


def run_go_live_validator(context: dict) -> dict:
    steps: list[dict] = []

    execution_mode = str(context.get("execution_mode") or "SIM").upper()
    env_mode = context.get("env_mode")
    config: LiveActivationConfig | None = context.get("config")
    release_gate = context.get("release_gate") or {}
    connection = context.get("connection") or {}
    data_sources = context.get("data_sources") or {}

    degraded = False

    mode_start = time.perf_counter()
    mode_ok = execution_mode == "LIVE"
    if env_mode and env_mode != execution_mode:
        mode_ok = False
    steps.append(
        _build_step(
            step_key="mode_integrity",
            status="PASS" if mode_ok else "FAIL",
            blocking=True,
            reason_code="MODE_MISMATCH" if not mode_ok else "PASS",
            message="Execution mode LIVE olmalı" if not mode_ok else "Mode LIVE",
            details={"execution_mode": execution_mode, "env_mode": env_mode},
            data_source="execution_mode_control",
            started_at=mode_start,
        )
    )

    live_start = time.perf_counter()
    explicit_live = bool(config.live_mode_enabled) if config else False
    safe_mode = bool(config.safe_mode_enabled) if config else False
    explicit_ok = explicit_live and not safe_mode
    steps.append(
        _build_step(
            step_key="explicit_live_enabled",
            status="PASS" if explicit_ok else "FAIL",
            blocking=True,
            reason_code="EXPLICIT_LIVE_DISABLED" if not explicit_ok else "PASS",
            message="Live enable flag zorunlu" if not explicit_ok else "Live flag açık",
            details={"live_mode_enabled": explicit_live, "safe_mode_enabled": safe_mode},
            data_source="live_activation_config",
            started_at=live_start,
        )
    )

    kill_start = time.perf_counter()
    kill_switch_active = bool(context.get("kill_switch_active"))
    config_kill_switch = bool(config.kill_switch_enabled) if config else False
    kill_ok = not kill_switch_active and not config_kill_switch
    steps.append(
        _build_step(
            step_key="kill_switch_clear",
            status="PASS" if kill_ok else "FAIL",
            blocking=True,
            reason_code="KILL_SWITCH_ACTIVE" if not kill_ok else "PASS",
            message="Kill switch aktif" if not kill_ok else "Kill switch pasif",
            details={"kill_switch_active": kill_switch_active, "config_kill_switch": config_kill_switch},
            data_source="redis:execution:kill_switch:state",
            started_at=kill_start,
        )
    )

    gate_start = time.perf_counter()
    gate_status = str(release_gate.get("status") or "UNKNOWN").upper()
    gate_ok = gate_status == "PASS"
    steps.append(
        _build_step(
            step_key="release_gate_pass",
            status="PASS" if gate_ok else "FAIL" if gate_status != "UNKNOWN" else "UNKNOWN",
            blocking=True,
            reason_code="PASS" if gate_ok else str(release_gate.get("reason_code") or "RELEASE_GATE_BLOCKED"),
            message="Release gate PASS değil" if not gate_ok else "Release gate PASS",
            details={"status": gate_status, "reason_codes": release_gate.get("reason_codes")},
            data_source="release_gate_view",
            started_at=gate_start,
        )
    )

    conn_start = time.perf_counter()
    connection_exists = bool(connection.get("exists"))
    connection_health = str(connection.get("connection_health") or "unknown").lower()
    can_trade = bool(connection.get("can_trade"))
    validation_success = bool(connection.get("validation_success"))
    connection_ok = connection_exists and connection_health in {"online", "degraded"} and can_trade and validation_success
    conn_status = "PASS" if connection_ok else "UNKNOWN" if not connection_exists else "FAIL"
    steps.append(
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
        )
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
    steps.append(
        _build_step(
            step_key="credentials_env_match",
            status=env_status,
            blocking=True,
            reason_code="CREDENTIAL_ENV_MISMATCH" if not env_ok else "PASS",
            message="Credential environment uyuşmuyor" if not env_ok else "Credential environment uyumlu",
            details={"connection_environment": connection_env, "execution_mode": execution_mode},
            data_source="connection_environment",
            started_at=env_start,
        )
    )

    def _data_step(name: str, reason_code: str, message: str):
        nonlocal degraded
        data = data_sources.get(name) or {}
        available = bool(data.get("available"))
        fallback_used = bool(data.get("fallback_used"))
        status = "PASS" if available and not fallback_used else "UNKNOWN"
        if not available:
            degraded = True
        if fallback_used:
            degraded = True
        step = _build_step(
            step_key=f"{name}_present",
            status=status,
            blocking=True,
            reason_code=reason_code,
            message=message if status != "PASS" else f"{name} mevcut",
            details={"fallback_used": fallback_used, "source": data.get("data_source")},
            data_source=str(data.get("data_source") or "cache"),
            started_at=time.perf_counter(),
        )
        return step

    for key, reason, message in [
        ("balances", "BALANCE_DATA_MISSING", "Balance verisi eksik"),
        ("positions", "POSITION_DATA_MISSING", "Position verisi eksik"),
        ("open_orders", "OPEN_ORDERS_DATA_MISSING", "Open orders verisi eksik"),
        ("market_data", "MARKET_DATA_MISSING", "Market data verisi eksik"),
    ]:
        step = _data_step(key, reason, message)
        steps.append(step)

    reason_codes: list[str] = []
    blocking_total = 0
    blocking_passed = 0
    warning_total = 0
    warning_failed = 0
    unknown_total = 0

    for step in steps:
        status = step["status"]
        if step["blocking"]:
            blocking_total += 1
            if status == "PASS":
                blocking_passed += 1
        if status == "WARN":
            warning_total += 1
            warning_failed += 1
        if status == "UNKNOWN":
            unknown_total += 1
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
            "stale_threshold_sec": 300,
        }

    return {
        "readiness_state": readiness_state,
        "go_live_allowed": readiness_state == "READY",
        "execution_allowed": readiness_state == "READY",
        "score": score_payload.get("readiness_confidence_score", 0.0),
        "summary": {
            "blocking_total": blocking_total,
            "blocking_passed": blocking_passed,
            "warning_total": warning_total,
            "warning_failed": warning_failed,
            "unknown_total": unknown_total,
        },
        "steps": steps,
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
            "summary": {
                "blocking_total": 0,
                "blocking_passed": 0,
                "warning_total": 0,
                "warning_failed": 0,
                "unknown_total": 1,
            },
            "steps": [],
            "reason_codes": ["validator_runtime_error"],
            "degraded": True,
            "data_freshness": {},
            "generated_at": now,
            "legacy_score": {},
            "execution_mode": str(context.get("execution_mode") or "SIM"),
        }
