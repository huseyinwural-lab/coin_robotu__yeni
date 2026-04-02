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
from core.readiness.exposure_policy import evaluate_exposure_policy, load_exposure_policy
from core.safety.kill_switch import get_kill_switch_state
from db import redis_client
from models import (
    CommercialTrade,
    ExecutionLifecycleEvent,
    ExecutionMetric,
    ExecutionStateTransition,
    LiveActivationConfig,
    Order,
    PaperPosition,
    PortfolioExposureSnapshot,
    PnlRecord,
    Position,
    TestnetExecutionLog,
    UserExchangeConnection,
    UserExecutionIntent,
)
from runtime_control.pipeline_controller import PIPELINE_QUEUE_KEYS
from services.execution_mode_control_service import get_execution_mode, normalize_execution_mode
from services.admin_exchange_credentials_service import execution_credentials_for_adapter, get_execution_credentials
from services.exchange_adapter.execution_adapter import ExchangeExecutionAdapter
from services.exchange_adapter.market_data_adapter import ExchangeMarketDataAdapter
from services.live_mode_service import (
    BinanceFuturesTestnetAdapter,
    _rate_limit_health,
    _risk_orchestrator_enabled,
    _worker_lag_seconds,
    get_market_ticker,
    get_or_create_live_config,
    release_gate_view,
    resolve_runtime_credentials,
)
from services.pipeline.cache_store import get_json
from services.risk_engine_service import evaluate_risk_decision, load_risk_config

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

LAYER_KEYS = ["core", "trading_state", "exchange", "execution", "risk", "infra", "latency", "safety"]

RISK_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "risk_engine_config.json"
RISK_CONFIG_BACKUP_PATH = Path(__file__).resolve().parents[2] / "config" / "risk_engine_config_backup.json"
LATENCY_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "latency_config.json"
TIMEOUT_POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "timeout_policy.json"
DATA_QUALITY_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "readiness_data_quality_config.json"

DEFAULT_LATENCY_CONFIG = {
    "round_trip": {"warn": 500, "block": 1500},
    "order_execution": {"warn": 1000, "block": 3000},
    "tick_to_trade": {"warn": 750, "block": 2000},
    "percentiles": {
        "p95_multiplier": 1.15,
        "p99_multiplier": 1.35,
    },
}

DEFAULT_TIMEOUT_POLICY = {
    "exchange_call": 3.0,
    "order_execution": 5.0,
    "market_data": 2.0,
    "strategy_heartbeat_stale_sec": 90,
    "strategy_restart_grace_period_sec": 45,
    "venue_overrides": {},
    "symbol_overrides": {},
    "strategy_overrides": {},
}

DEFAULT_DATA_QUALITY_CONFIG = {
    "funding_freshness_sec": 120,
    "liquidation": {
        "min_input_coverage_pct": 80,
        "require_maintenance_margin": True,
        "distance_warn_multiplier": 1.4,
    },
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_required_venues() -> list[str]:
    supported = {"binance", "bybit"}
    policy = str(os.environ.get("GO_LIVE_VENUE_POLICY") or "binance_only").strip().lower()
    raw = str(os.environ.get("GO_LIVE_REQUIRED_VENUES") or "").strip()

    if raw:
        requested = [item.strip().lower() for item in raw.split(",") if item.strip()]
    elif policy in {"multi_venue", "binance_bybit", "all"}:
        requested = ["binance", "bybit"]
    else:
        requested = ["binance"]

    normalized: list[str] = []
    for venue in requested:
        if venue in supported and venue not in normalized:
            normalized.append(venue)

    if not normalized:
        normalized = ["binance"]

    return normalized


def _load_risk_config() -> dict:
    for path in [RISK_CONFIG_PATH, RISK_CONFIG_BACKUP_PATH]:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


def _load_latency_config(cache=None, overrides: dict | None = None) -> dict:
    payload = dict(DEFAULT_LATENCY_CONFIG)
    file_payload = {}
    try:
        if LATENCY_CONFIG_PATH.exists():
            file_payload = json.loads(LATENCY_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        file_payload = {}

    cache_override = {}
    try:
        cache_override = get_json(cache, "readiness:latency:overrides") if cache else {}
    except Exception:
        cache_override = {}

    env_override = {}
    raw_env = os.environ.get("READINESS_LATENCY_CONFIG_JSON")
    if raw_env:
        try:
            env_override = json.loads(raw_env)
        except Exception:
            env_override = {}

    for candidate in [file_payload, cache_override, env_override, overrides or {}]:
        if not isinstance(candidate, dict):
            continue
        for key in ["round_trip", "order_execution", "tick_to_trade"]:
            current = payload.get(key) or {}
            incoming = candidate.get(key) or {}
            if isinstance(incoming, dict):
                current = {**current, **incoming}
            payload[key] = current
        current_pct = payload.get("percentiles") or {}
        incoming_pct = candidate.get("percentiles") or {}
        if isinstance(incoming_pct, dict):
            payload["percentiles"] = {**current_pct, **incoming_pct}
    return payload


def _load_timeout_policy(cache=None, overrides: dict | None = None) -> dict:
    payload = dict(DEFAULT_TIMEOUT_POLICY)
    file_payload = {}
    try:
        if TIMEOUT_POLICY_PATH.exists():
            file_payload = json.loads(TIMEOUT_POLICY_PATH.read_text(encoding="utf-8"))
    except Exception:
        file_payload = {}

    cache_override = {}
    try:
        cache_override = get_json(cache, "readiness:timeout:policy") if cache else {}
    except Exception:
        cache_override = {}

    env_override = {}
    raw_env = os.environ.get("READINESS_TIMEOUT_POLICY_JSON")
    if raw_env:
        try:
            env_override = json.loads(raw_env)
        except Exception:
            env_override = {}

    for candidate in [file_payload, cache_override, env_override, overrides or {}]:
        if not isinstance(candidate, dict):
            continue
        for key in payload.keys():
            if candidate.get(key) is not None:
                payload[key] = candidate.get(key)
    return payload


def _load_data_quality_config(cache=None, overrides: dict | None = None) -> dict:
    payload = dict(DEFAULT_DATA_QUALITY_CONFIG)
    payload["liquidation"] = dict(DEFAULT_DATA_QUALITY_CONFIG.get("liquidation") or {})

    file_payload = {}
    try:
        if DATA_QUALITY_CONFIG_PATH.exists():
            file_payload = json.loads(DATA_QUALITY_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        file_payload = {}

    cache_override = {}
    try:
        cache_override = get_json(cache, "readiness:data_quality:config") if cache else {}
    except Exception:
        cache_override = {}

    env_override = {}
    raw_env = os.environ.get("READINESS_DATA_QUALITY_CONFIG_JSON")
    if raw_env:
        try:
            env_override = json.loads(raw_env)
        except Exception:
            env_override = {}

    for candidate in [file_payload, cache_override, env_override, overrides or {}]:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("funding_freshness_sec") is not None:
            payload["funding_freshness_sec"] = candidate.get("funding_freshness_sec")
        liquidation = payload.get("liquidation") or {}
        incoming_liquidation = candidate.get("liquidation") or {}
        if isinstance(incoming_liquidation, dict):
            payload["liquidation"] = {**liquidation, **incoming_liquidation}
    return payload


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(float(v) for v in values)
    if len(sorted_values) == 1:
        return round(sorted_values[0], 2)
    rank = (len(sorted_values) - 1) * (pct / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return round(sorted_values[lower], 2)
    weight = rank - lower
    value = sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight
    return round(value, 2)


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

    risk_config = overrides.get("risk_config")
    if risk_config is None:
        try:
            risk_config = load_risk_config(cache)
        except Exception:
            risk_config = _load_risk_config()
    exposure_policy = load_exposure_policy(risk_config=risk_config, overrides=overrides.get("exposure_policy_overrides"))
    latency_config = overrides.get("latency_config") or _load_latency_config(cache, overrides.get("latency_config_overrides"))
    timeout_policy = overrides.get("timeout_policy") or _load_timeout_policy(cache, overrides.get("timeout_policy_overrides"))
    data_quality_config = overrides.get("data_quality_config") or _load_data_quality_config(cache, overrides.get("data_quality_config_overrides"))
    risk_orchestrator_enabled = _risk_orchestrator_enabled(db)

    positions_query = db.query(Position).filter(Position.status == "open")
    if user_id:
        positions_query = positions_query.filter(Position.user_id == user_id)
    engine_positions = positions_query.all()

    orders_query = db.query(Order).filter(Order.state.in_(["CREATED", "OPEN", "PARTIALLY_FILLED"]))
    if user_id:
        orders_query = orders_query.filter(Order.user_id == user_id)
    engine_orders = orders_query.all()

    strategy_ids = []
    strategy_metrics: dict[str, dict] = {}
    try:
        intent_query = db.query(UserExecutionIntent).order_by(UserExecutionIntent.created_at.desc()).limit(300)
        if user_id:
            intent_query = intent_query.filter(UserExecutionIntent.user_id == user_id)
        intent_rows = list(intent_query)
        strategy_ids = list({str(row.strategy_id) for row in intent_rows if row.strategy_id})
        for row in intent_rows:
            strategy_id = str(row.strategy_id or "default").strip()
            if not strategy_id:
                continue
            bucket = strategy_metrics.setdefault(strategy_id, {"total": 0, "success": 0, "rejected": 0, "errors": 0, "last_status": None})
            status = str(row.status or "").upper()
            bucket["total"] += 1
            bucket["last_status"] = status
            if status in {"FILLED", "EXECUTED", "APPROVED", "RELEASED"}:
                bucket["success"] += 1
            if status in {"REJECTED", "BLOCKED", "FAILED", "ERROR"}:
                bucket["rejected"] += 1
            if status in {"ERROR", "FAILED"}:
                bucket["errors"] += 1
    except Exception:
        strategy_ids = []
        strategy_metrics = {}

    symbols = list({str(row.symbol) for row in engine_positions if row.symbol})
    symbols += [str(row.symbol) for row in engine_orders if row.symbol]
    symbols = list({item for item in symbols if item})

    partial_fill_count = 0
    try:
        partial_query = db.query(Order).filter(Order.state == "PARTIALLY_FILLED")
        if user_id:
            partial_query = partial_query.filter(Order.user_id == user_id)
        partial_fill_count = partial_query.count()
    except Exception:
        partial_fill_count = 0

    lifecycle_states: list[str] = []
    lifecycle_events: list[str] = []
    lifecycle_sync_ok = False
    successful_lifecycle_count = 0
    mocked_metric_count = 0
    real_metric_count = 0
    try:
        metric_query = db.query(ExecutionMetric).order_by(ExecutionMetric.created_at.desc()).limit(200)
        if user_id:
            metric_query = metric_query.filter(ExecutionMetric.user_id == user_id)
        metric_rows = metric_query.all()
        metric_ids = {str(row.id) for row in metric_rows}

        for row in metric_rows:
            path = row.state_machine_path if isinstance(row.state_machine_path, list) else []
            norm_path = [str(item).upper() for item in path if str(item or "").strip()]
            lifecycle_states.extend(norm_path)
            exchange_response = row.exchange_response if isinstance(row.exchange_response, dict) else {}
            is_mocked = bool(exchange_response.get("mocked"))
            if is_mocked:
                mocked_metric_count += 1
            else:
                real_metric_count += 1
            if "CREATED" in norm_path and "FILLED" in norm_path:
                successful_lifecycle_count += 1

        lifecycle_event_query = db.query(ExecutionLifecycleEvent).order_by(ExecutionLifecycleEvent.event_timestamp.desc()).limit(400)
        if user_id:
            lifecycle_event_query = lifecycle_event_query.filter(ExecutionLifecycleEvent.user_id == user_id)
        if metric_ids:
            lifecycle_event_query = lifecycle_event_query.filter(ExecutionLifecycleEvent.execution_metric_id.in_(metric_ids))
        lifecycle_event_rows = lifecycle_event_query.all()
        lifecycle_events = [str(row.event_name or "").upper() for row in lifecycle_event_rows]

        transition_query = db.query(ExecutionStateTransition).order_by(ExecutionStateTransition.occurred_at.desc()).limit(400)
        transition_rows = transition_query.all()
        for row in transition_rows:
            lifecycle_states.extend(
                [
                    str(row.state or "").upper(),
                    str(row.from_state or "").upper(),
                    str(row.to_state or "").upper(),
                ]
            )

        non_empty_states = [state for state in lifecycle_states if state]
        lifecycle_sync_ok = bool(non_empty_states) and bool(lifecycle_events)
    except Exception:
        lifecycle_states = []
        lifecycle_events = []
        lifecycle_sync_ok = False
        successful_lifecycle_count = 0
        mocked_metric_count = 0
        real_metric_count = 0

    total_exposure = 0.0
    for row in engine_positions:
        price = float(row.current_price or row.entry_price or 0)
        total_exposure += abs(float(row.size or 0)) * price

    funding_available = False
    funding_error = None
    funding_count = 0
    funding_by_symbol: dict[str, dict] = {}
    funding_fresh = False
    configured_funding_freshness = _safe_float(data_quality_config.get("funding_freshness_sec"), None)
    funding_threshold_sec = int(configured_funding_freshness) if configured_funding_freshness else max(int((_safe_float(risk_config.get("stale_data_threshold_ms")) or 120000) / 1000), 30)
    market_adapter = ExchangeMarketDataAdapter(timeout_seconds=float(timeout_policy.get("market_data") or 2.0))
    try:
        threshold = _utcnow() - timedelta(days=1)
        funding_query = db.query(CommercialTrade).filter(CommercialTrade.ingested_at >= threshold)
        funding_query = funding_query.filter(CommercialTrade.funding_fee_usd != 0)
        if user_id:
            funding_query = funding_query.filter(CommercialTrade.user_id == user_id)
        funding_rows = funding_query.order_by(CommercialTrade.ingested_at.desc()).limit(500).all()
        funding_count = len(funding_rows)

        db_symbol_timestamps: dict[str, datetime] = {}
        for row in funding_rows:
            symbol_key = str(row.symbol or "").upper().strip()
            if not symbol_key:
                continue
            current_ts = db_symbol_timestamps.get(symbol_key)
            if current_ts is None or (row.ingested_at and row.ingested_at > current_ts):
                db_symbol_timestamps[symbol_key] = row.ingested_at

        for symbol in symbols:
            symbol_key = str(symbol or "").upper().strip()
            if not symbol_key:
                continue

            cache_data = {}
            if cache:
                try:
                    cache_data = get_json(cache, f"futures:funding:{symbol_key}") or {}
                except Exception:
                    cache_data = {}
            rate = _safe_float((cache_data or {}).get("funding_rate"))
            ts_raw = (cache_data or {}).get("timestamp") or (cache_data or {}).get("fetched_at")
            ts = _parse_timestamp(ts_raw)
            source = "cache" if cache_data else "none"

            if ts is None:
                try:
                    adapter_payload = market_adapter.fetch_funding_rate(exchange="bybit", symbol=symbol_key)
                    rate = _safe_float(adapter_payload.get("funding_rate"), rate)
                    ts = _parse_timestamp(adapter_payload.get("fetched_at") or adapter_payload.get("next_funding_time"))
                    source = "exchange_adapter"
                except Exception:
                    source = source if source != "none" else "adapter_error"

            db_ts = db_symbol_timestamps.get(symbol_key)
            if ts is None and db_ts is not None:
                ts = db_ts
                source = "commercial_trade"

            freshness_sec = None
            stale = True
            if ts is not None:
                freshness_sec = int((_utcnow() - ts).total_seconds())
                stale = freshness_sec > funding_threshold_sec

            if ts is None:
                state = "FAIL"
                reason = "FUNDING_DATA_MISSING"
            elif stale:
                state = "FAIL"
                reason = "FUNDING_DATA_STALE"
            else:
                state = "PASS"
                reason = "PASS"

            funding_by_symbol[symbol_key] = {
                "state": state,
                "reason_code": reason,
                "funding_rate": rate,
                "timestamp": ts.isoformat() if ts else None,
                "freshness_sec": freshness_sec,
                "source": source,
            }

        funding_available = any(item.get("state") == "PASS" for item in funding_by_symbol.values())
        funding_fresh = bool(funding_by_symbol) and all(item.get("state") == "PASS" for item in funding_by_symbol.values())
    except Exception as exc:
        funding_error = str(exc)

    adapter_credentials = {}
    adapter_credential_summary = {}
    try:
        adapter_credentials = execution_credentials_for_adapter(db)
        adapter_credential_summary = get_execution_credentials(db)
    except Exception:
        adapter_credentials = {}
        adapter_credential_summary = {}

    exec_adapter = ExchangeExecutionAdapter(credentials_override=adapter_credentials)
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

    api_key, api_secret, credential_source = resolve_runtime_credentials(None, None)
    adapter = BinanceFuturesTestnetAdapter()
    credentials_available = bool(api_key and api_secret)

    account_payload = None
    account_status = None
    account_error = None
    position_risk_payload = None
    position_risk_status = None
    position_risk_error = None
    reduce_only_payload = None
    reduce_only_status = None
    reduce_only_error = None

    if credentials_available:
        try:
            account_payload, account_status, _ = adapter.account_probe(api_key, api_secret)
        except Exception as exc:  # pragma: no cover - defensive
            account_error = str(exc)
        try:
            position_risk_payload, position_risk_status, _ = adapter.position_risk(api_key, api_secret)
        except Exception as exc:  # pragma: no cover - defensive
            position_risk_error = str(exc)
        try:
            reduce_only_payload, reduce_only_status, _ = adapter.reduce_only_test(api_key, api_secret)
        except Exception as exc:  # pragma: no cover - defensive
            reduce_only_error = str(exc)

    websocket_snapshot = get_json(cache, "exchange:heartbeat") if cache else {}
    rate_limit_status = _rate_limit_health(db)

    pnl_snapshot = None
    pnl_net_total = None
    pnl_error = None
    try:
        pnl_query = db.query(PnlRecord).order_by(PnlRecord.as_of.desc())
        if user_id:
            pnl_query = pnl_query.filter(PnlRecord.user_id == user_id)
        pnl_snapshot = pnl_query.first()
        if pnl_snapshot:
            pnl_net_total = float(pnl_snapshot.net_total_usd or 0.0)
    except Exception as exc:
        pnl_error = str(exc)

    metrics_query = db.query(ExecutionMetric)
    if user_id:
        metrics_query = metrics_query.filter(ExecutionMetric.user_id == user_id)
    metrics = metrics_query.order_by(ExecutionMetric.created_at.desc()).limit(50).all()
    ack_latencies = []
    execution_latencies = []
    tick_latencies = []
    for row in metrics:
        if row.submitted_at and row.ack_at:
            ack_latencies.append((row.ack_at - row.submitted_at).total_seconds() * 1000)
        if row.ack_at and row.final_at:
            execution_latencies.append((row.final_at - row.ack_at).total_seconds() * 1000)
        if row.submitted_at and row.mid_price_timestamp:
            stamp = _parse_timestamp(row.mid_price_timestamp)
            if stamp:
                tick_latencies.append((row.submitted_at - stamp).total_seconds() * 1000)

    def _avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    round_trip_avg = _avg(ack_latencies)
    order_exec_avg = _avg(execution_latencies)
    tick_to_trade_avg = _avg(tick_latencies)

    round_trip_p95 = _percentile(ack_latencies, 95)
    round_trip_p99 = _percentile(ack_latencies, 99)
    order_exec_p95 = _percentile(execution_latencies, 95)
    order_exec_p99 = _percentile(execution_latencies, 99)
    tick_to_trade_p95 = _percentile(tick_latencies, 95)
    tick_to_trade_p99 = _percentile(tick_latencies, 99)

    latency_metrics = {
        "round_trip_ms": round_trip_avg,
        "order_execution_ms": order_exec_avg,
        "tick_to_trade_ms": tick_to_trade_avg,
        "round_trip_p95_ms": round_trip_p95,
        "round_trip_p99_ms": round_trip_p99,
        "order_execution_p95_ms": order_exec_p95,
        "order_execution_p99_ms": order_exec_p99,
        "tick_to_trade_p95_ms": tick_to_trade_p95,
        "tick_to_trade_p99_ms": tick_to_trade_p99,
        "samples": {
            "round_trip": len(ack_latencies),
            "order_execution": len(execution_latencies),
            "tick_to_trade": len(tick_latencies),
        },
    }

    dry_run_count = 0
    try:
        dry_run_query = db.query(TestnetExecutionLog)
        if user_id:
            dry_run_query = dry_run_query.filter(TestnetExecutionLog.user_id == user_id)
        dry_run_count = dry_run_query.count()
    except Exception:
        dry_run_count = 0

    strategy_heartbeat = None
    strategy_last_execution = None
    strategy_error_state = None
    strategy_restart_at = None
    if redis_client is not None:
        try:
            strategy_heartbeat = redis_client.get("strategy:engine:heartbeat")
        except Exception:
            strategy_heartbeat = None
        try:
            strategy_last_execution = redis_client.get("strategy:engine:last_execution_at")
        except Exception:
            strategy_last_execution = None
        try:
            strategy_error_state = redis_client.get("strategy:engine:error_state")
        except Exception:
            strategy_error_state = None
        try:
            strategy_restart_at = redis_client.get("strategy:engine:restart_at")
        except Exception:
            strategy_restart_at = None

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

    portfolio_exposure = {
        "global_notional": 0.0,
        "by_symbol": {},
        "by_strategy": {},
        "sample_count": 0,
    }
    try:
        exposure_query = db.query(PortfolioExposureSnapshot).order_by(PortfolioExposureSnapshot.timestamp.desc()).limit(400)
        if user_id:
            exposure_query = exposure_query.filter(PortfolioExposureSnapshot.user_id == user_id)
        exposure_rows = exposure_query.all()
        portfolio_exposure["sample_count"] = len(exposure_rows)
        for row in exposure_rows:
            notional = abs(float(row.notional or 0.0))
            portfolio_exposure["global_notional"] += notional
            symbol_key = str(row.symbol or "").upper().strip()
            strategy_key = str(row.strategy_id or "default").strip() or "default"
            if symbol_key:
                portfolio_exposure["by_symbol"][symbol_key] = round(float(portfolio_exposure["by_symbol"].get(symbol_key) or 0.0) + notional, 6)
            portfolio_exposure["by_strategy"][strategy_key] = round(
                float(portfolio_exposure["by_strategy"].get(strategy_key) or 0.0) + notional,
                6,
            )
        portfolio_exposure["global_notional"] = round(float(portfolio_exposure["global_notional"]), 6)
    except Exception:
        portfolio_exposure = {
            "global_notional": 0.0,
            "by_symbol": {},
            "by_strategy": {},
            "sample_count": 0,
        }

    risk_engine_health = {
        "config_loaded": bool(risk_config),
        "policy_apply_ok": False,
        "sample_decision": None,
        "error": None,
    }
    try:
        sample_decision = evaluate_risk_decision(
            db,
            cache,
            user_id=user_id or "readiness-system",
            symbol=(symbols[0] if symbols else "BTCUSDT"),
            strategy_decision="LONG",
            market_type="futures",
            proposed_notional_usdt=25.0,
            strategy_code=(strategy_ids[0] if strategy_ids else "default"),
            requested_leverage=1,
            snapshot_age_ms=80.0,
            spread_bps=6.0,
            execution_latency_ms=120.0,
            slippage_pct=0.08,
            orderbook_depth_score=0.95,
            liquidation_distance_pct=10.0,
        )
        risk_engine_health["sample_decision"] = sample_decision
        risk_engine_health["policy_apply_ok"] = bool(sample_decision.get("risk_decision"))
    except Exception as exc:
        risk_engine_health["error"] = str(exc)

    sample_symbol = symbols[0] if symbols else test_symbol
    exchange_matrix: dict[str, dict] = {}
    venue_config_checklist: dict[str, dict] = {}
    runtime_environment = str(connection_payload.get("environment") or "testnet").lower()

    required_venues = _resolve_required_venues()
    venue_policy = str(os.environ.get("GO_LIVE_VENUE_POLICY") or "binance_only").strip().lower()

    for venue in required_venues:
        venue_payload = {
            "connectivity": "UNKNOWN",
            "latency_ms": None,
            "orderbook": "UNKNOWN",
            "rate_limit": "UNKNOWN",
            "websocket_age_sec": None,
            "source": "none",
            "reason_code": "UNKNOWN",
            "environment": runtime_environment,
        }
        checklist = {
            "has_testnet_credentials": False,
            "has_live_credentials": False,
            "environment_mapped": True,
            "policy_valid": True,
            "reason_code": "PASS",
        }
        if venue == "binance":
            venue_payload["connectivity"] = "PASS" if connection_payload.get("exists") and connection_payload.get("validation_success") else "FAIL"
            venue_payload["latency_ms"] = connection_payload.get("latency_ms")
            venue_payload["rate_limit"] = str(rate_limit_status or "unknown").upper()
            venue_payload["websocket_age_sec"] = (websocket_snapshot or {}).get("age_sec") or (websocket_snapshot or {}).get("heartbeat_age_sec")
            market_payload = market_source.get("payload") or {}
            bid = _safe_float(market_payload.get("bid") or market_payload.get("best_bid"))
            ask = _safe_float(market_payload.get("ask") or market_payload.get("best_ask"))
            venue_payload["orderbook"] = "PASS" if bid and ask and bid > 0 and ask > 0 else "FAIL"
            venue_payload["source"] = "connection_snapshot"
            venue_payload["reason_code"] = "PASS" if venue_payload["connectivity"] == "PASS" and venue_payload["orderbook"] == "PASS" else "BINANCE_PROBE_FAIL"
        else:
            bybit_creds = (adapter_credentials or {}).get("bybit") or {}
            checklist["has_testnet_credentials"] = bool(bybit_creds.get("testnet_api_key") and bybit_creds.get("testnet_api_secret"))
            checklist["has_live_credentials"] = bool(bybit_creds.get("live_api_key") and bybit_creds.get("live_api_secret"))

            if runtime_environment == "live" and not checklist["has_live_credentials"]:
                checklist["environment_mapped"] = False
                checklist["reason_code"] = "BYBIT_LIVE_CREDENTIALS_MISSING"
            elif runtime_environment != "live" and not checklist["has_testnet_credentials"]:
                checklist["environment_mapped"] = False
                checklist["reason_code"] = "BYBIT_TESTNET_CREDENTIALS_MISSING"

            started = time.perf_counter()
            try:
                auth_ok, auth_probe, _ = exec_adapter._bybit_auth_probe(environment=runtime_environment)  # noqa: SLF001
                ticker = market_adapter.fetch_ticker(exchange="bybit", symbol=sample_symbol)
                venue_payload["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
                bid = _safe_float(ticker.get("bid_price"))
                ask = _safe_float(ticker.get("ask_price"))
                venue_payload["connectivity"] = "PASS" if auth_ok else "FAIL"
                venue_payload["orderbook"] = "PASS" if bid and ask and bid > 0 and ask > 0 else "FAIL"
                venue_payload["rate_limit"] = "UNKNOWN"
                venue_payload["source"] = "market_adapter"
                venue_payload["provider"] = auth_probe
                if not auth_ok:
                    venue_payload["reason_code"] = "BYBIT_AUTH_PROBE_FAIL"
                elif venue_payload["orderbook"] != "PASS":
                    venue_payload["reason_code"] = "BYBIT_ORDERBOOK_INVALID"
                else:
                    venue_payload["reason_code"] = "PASS"
            except Exception:
                venue_payload["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
                venue_payload["connectivity"] = "FAIL"
                venue_payload["orderbook"] = "FAIL"
                venue_payload["source"] = "market_adapter_error"
                venue_payload["reason_code"] = "BYBIT_CONNECTIVITY_FAIL"

            if not checklist["environment_mapped"]:
                venue_payload["connectivity"] = "FAIL"
                venue_payload["reason_code"] = checklist["reason_code"]

        exchange_matrix[venue] = venue_payload
        venue_config_checklist[venue] = checklist

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
        "exposure_policy": exposure_policy,
        "latency_config": latency_config,
        "timeout_policy": timeout_policy,
        "data_quality_config": data_quality_config,
        "risk_orchestrator_enabled": risk_orchestrator_enabled,
        "risk_engine_health": risk_engine_health,
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
            "funding_fresh": funding_fresh,
            "funding_by_symbol": funding_by_symbol,
        },
        "strategy_ids": strategy_ids,
        "strategy_metrics": strategy_metrics,
        "symbols": symbols,
        "execution_lifecycle": {
            "states": sorted({state for state in lifecycle_states if state}),
            "events": sorted({event for event in lifecycle_events if event}),
            "sync_ok": lifecycle_sync_ok,
            "successful_lifecycle_count": successful_lifecycle_count,
            "mocked_metric_count": mocked_metric_count,
            "real_metric_count": real_metric_count,
        },
        "portfolio_exposure": portfolio_exposure,
        "exchange_matrix": exchange_matrix,
        "required_venues": required_venues,
        "venue_policy": venue_policy,
        "venue_config_checklist": venue_config_checklist,
        "adapter_credential_summary": adapter_credential_summary,
        "execution_tests": {
            "precision": precision_result,
            "submit": submit_result,
            "cancel": cancel_result,
        },
        "exchange_account": {
            "payload": account_payload,
            "status_code": account_status,
            "error": account_error,
            "credentials_available": credentials_available,
            "credential_source": credential_source,
        },
        "position_risk": {
            "payload": position_risk_payload,
            "status_code": position_risk_status,
            "error": position_risk_error,
        },
        "reduce_only_test": {
            "payload": reduce_only_payload,
            "status_code": reduce_only_status,
            "error": reduce_only_error,
        },
        "exchange_metrics": {
            "websocket": websocket_snapshot,
            "rate_limit_status": rate_limit_status,
        },
        "latency_metrics": latency_metrics,
        "pnl_snapshot": {
            "net_total_usd": pnl_net_total,
            "error": pnl_error,
            "as_of": pnl_snapshot.as_of.isoformat() if pnl_snapshot else None,
        },
        "dry_run_count": dry_run_count,
        "infra": {
            "db_ok": db_ok,
            "redis_ok": redis_ok,
            "queue_sizes": queue_sizes,
            "worker_events": worker_events,
            "worker_lag_sec": worker_lag_sec,
            "strategy_engine_status": "unknown",
            "strategy_heartbeat": strategy_heartbeat.decode() if isinstance(strategy_heartbeat, (bytes, bytearray)) else strategy_heartbeat,
            "strategy_last_execution": strategy_last_execution.decode() if isinstance(strategy_last_execution, (bytes, bytearray)) else strategy_last_execution,
            "strategy_error_state": strategy_error_state.decode() if isinstance(strategy_error_state, (bytes, bytearray)) else strategy_error_state,
            "strategy_restart_at": strategy_restart_at.decode() if isinstance(strategy_restart_at, (bytes, bytearray)) else strategy_restart_at,
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
    exchange_account = context.get("exchange_account") or {}
    position_risk = context.get("position_risk") or {}
    reduce_only_test = context.get("reduce_only_test") or {}
    infra = context.get("infra") or {}
    risk_config = context.get("risk_config") or {}
    exposure_policy = context.get("exposure_policy") or load_exposure_policy(risk_config=risk_config)
    latency_config = context.get("latency_config") or dict(DEFAULT_LATENCY_CONFIG)
    timeout_policy = context.get("timeout_policy") or dict(DEFAULT_TIMEOUT_POLICY)
    data_quality_config = context.get("data_quality_config") or dict(DEFAULT_DATA_QUALITY_CONFIG)
    risk_orchestrator_enabled = bool(context.get("risk_orchestrator_enabled"))
    risk_engine_health = context.get("risk_engine_health") or {}
    latency_metrics = context.get("latency_metrics") or {}
    pnl_snapshot = context.get("pnl_snapshot") or {}
    dry_run_count = int(context.get("dry_run_count") or 0)
    strategy_ids = context.get("strategy_ids") or []
    strategy_metrics = context.get("strategy_metrics") or {}
    symbols = context.get("symbols") or []
    exchange_matrix = context.get("exchange_matrix") or {}
    required_venues = context.get("required_venues") or _resolve_required_venues()
    venue_policy = str(context.get("venue_policy") or os.environ.get("GO_LIVE_VENUE_POLICY") or "binance_only").strip().lower()
    venue_config_checklist = context.get("venue_config_checklist") or {}
    execution_lifecycle = context.get("execution_lifecycle") or {}
    portfolio_exposure = context.get("portfolio_exposure") or {}

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
    funding_by_symbol = trading_state.get("funding_by_symbol") or {}
    funding_fresh = bool(trading_state.get("funding_fresh"))
    if engine_positions_count == 0:
        funding_status = "PASS"
        funding_reason = "PASS"
    elif funding_error:
        funding_status = "FAIL"
        funding_reason = "FUNDING_DATA_ERROR"
    elif not funding_by_symbol:
        funding_status = "FAIL"
        funding_reason = "FUNDING_DATA_MISSING"
    elif any(str(item.get("state") or "").upper() == "FAIL" for item in funding_by_symbol.values()):
        funding_status = "FAIL"
        funding_reason = "FUNDING_DATA_STALE"
    elif not funding_available or not funding_fresh:
        funding_status = "FAIL"
        funding_reason = "FUNDING_DATA_MISSING"
    else:
        funding_status = "PASS"
        funding_reason = "PASS"

    add_step(
        "trading_state",
        _build_step(
            step_key="funding_status",
            status=funding_status,
            blocking=True,
            reason_code=funding_reason,
            message="Funding readiness doğrulandı" if funding_status == "PASS" else "Funding readiness başarısız",
            details={
                "funding_count": trading_state.get("funding_count", 0),
                "funding_fresh": funding_fresh,
                "freshness_threshold_sec": data_quality_config.get("funding_freshness_sec"),
                "symbols": funding_by_symbol,
            },
            data_source="commercial_trades",
            started_at=time.perf_counter(),
        ),
    )

    liquidation_cfg = data_quality_config.get("liquidation") or {}
    liquidation_threshold = _safe_float(risk_config.get("min_liquidation_distance_pct")) or 5.0
    liquidation_warn_multiplier = _safe_float(liquidation_cfg.get("distance_warn_multiplier"), 1.4) or 1.4
    min_coverage_pct = _safe_float(liquidation_cfg.get("min_input_coverage_pct"), 80.0) or 80.0
    require_maint_margin = bool(liquidation_cfg.get("require_maintenance_margin", True))
    risk_payload = position_risk.get("payload")
    risk_positions = []
    if isinstance(risk_payload, list):
        risk_positions = risk_payload
    elif isinstance(risk_payload, dict) and risk_payload:
        risk_positions = [risk_payload]

    engine_positions = trading_state.get("engine_positions") or []
    engine_position_map: dict[str, Any] = {}
    for pos in engine_positions:
        symbol_key = str(getattr(pos, "symbol", "") or "").upper().strip()
        if symbol_key and symbol_key not in engine_position_map:
            engine_position_map[symbol_key] = pos

    liquidation_distances = []
    liquidation_by_symbol: dict[str, dict] = {}
    total_active_positions = 0
    covered_positions = 0
    missing_mark_symbols: list[str] = []
    missing_liq_symbols: list[str] = []
    missing_maint_symbols: list[str] = []
    for item in risk_positions:
        try:
            position_amt = float(item.get("positionAmt") or item.get("position_amt") or 0)
        except (TypeError, ValueError):
            position_amt = 0
        if position_amt == 0:
            continue
        total_active_positions += 1
        symbol_key = str(item.get("symbol") or item.get("s") or "").upper().strip()
        mark_price = _safe_float(item.get("markPrice") or item.get("mark_price"))
        liquidation_price = _safe_float(item.get("liquidationPrice") or item.get("liquidation_price"))
        leverage = _safe_float(item.get("leverage"))
        maint_margin = _safe_float(item.get("maintMargin") or item.get("maintenanceMargin") or item.get("maint_margin"))

        if liquidation_price is None and symbol_key and symbol_key in engine_position_map:
            pos = engine_position_map.get(symbol_key)
            entry_price = _safe_float(getattr(pos, "entry_price", None))
            leverage = _safe_float(getattr(pos, "leverage", leverage))
            size = _safe_float(getattr(pos, "size", position_amt), position_amt)
            if entry_price and leverage and leverage > 0:
                if (size or 0) >= 0:
                    liquidation_price = entry_price * max(0.01, 1 - (1 / leverage))
                else:
                    liquidation_price = entry_price * (1 + (1 / leverage))

        if require_maint_margin and maint_margin is None and symbol_key:
            missing_maint_symbols.append(symbol_key)

        if mark_price is None and symbol_key:
            missing_mark_symbols.append(symbol_key)
        if liquidation_price is None and symbol_key:
            missing_liq_symbols.append(symbol_key)

        if mark_price and liquidation_price:
            distance_pct = abs((mark_price - liquidation_price) / mark_price) * 100
            liquidation_distances.append(distance_pct)
            covered_positions += 1
            if symbol_key:
                liquidation_by_symbol[symbol_key] = {
                    "distance_pct": round(distance_pct, 4),
                    "mark_price": mark_price,
                    "liquidation_price": round(liquidation_price, 8),
                    "threshold_pct": liquidation_threshold,
                    "maintenance_margin": maint_margin,
                }

    coverage_pct = round((covered_positions / max(total_active_positions, 1)) * 100, 4) if total_active_positions > 0 else 100.0

    if engine_positions_count == 0:
        liquidation_status = "PASS"
        liquidation_reason = "PASS"
    elif require_maint_margin and missing_maint_symbols:
        liquidation_status = "FAIL"
        liquidation_reason = "LIQUIDATION_MAINT_MARGIN_MISSING"
    elif coverage_pct < min_coverage_pct:
        liquidation_status = "FAIL"
        liquidation_reason = "LIQUIDATION_INPUT_COVERAGE_LOW"
    elif missing_mark_symbols:
        liquidation_status = "UNKNOWN"
        liquidation_reason = "LIQUIDATION_MARK_PRICE_MISSING"
    elif missing_liq_symbols and not liquidation_distances:
        liquidation_status = "UNKNOWN"
        liquidation_reason = "LIQUIDATION_PRICE_UNAVAILABLE"
    elif not liquidation_distances:
        liquidation_status = "UNKNOWN"
        liquidation_reason = "LIQUIDATION_DATA_MISSING"
    else:
        min_distance = min(liquidation_distances)
        if min_distance < liquidation_threshold:
            liquidation_status = "FAIL"
            liquidation_reason = "LIQUIDATION_DISTANCE_LOW"
        elif min_distance < liquidation_threshold * liquidation_warn_multiplier:
            liquidation_status = "WARN"
            liquidation_reason = "LIQUIDATION_DISTANCE_NEAR"
        else:
            liquidation_status = "PASS"
            liquidation_reason = "PASS"

    add_step(
        "trading_state",
        _build_step(
            step_key="liquidation_risk",
            status=liquidation_status,
            blocking=True,
            reason_code=liquidation_reason,
            message="Liquidation risk uygun" if liquidation_status == "PASS" else "Liquidation riski yüksek",
            details={
                "distance_min_pct": min(liquidation_distances) if liquidation_distances else None,
                "threshold_pct": liquidation_threshold,
                "by_symbol": liquidation_by_symbol,
                "input_coverage": {
                    "total_active_positions": total_active_positions,
                    "covered_positions": covered_positions,
                    "coverage_pct": coverage_pct,
                    "min_required_pct": min_coverage_pct,
                },
                "missing_inputs": {
                    "mark_price_symbols": sorted(set(missing_mark_symbols)),
                    "liquidation_price_symbols": sorted(set(missing_liq_symbols)),
                    "maintenance_margin_symbols": sorted(set(missing_maint_symbols)),
                },
            },
            data_source="exchange_position_risk",
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

    for venue, payload in exchange_matrix.items():
        venue_key = str(venue or "").lower().strip() or "unknown"
        connectivity = str(payload.get("connectivity") or "UNKNOWN").upper()
        orderbook = str(payload.get("orderbook") or "UNKNOWN").upper()
        venue_rate = str(payload.get("rate_limit") or "UNKNOWN").upper()
        venue_latency = _safe_float(payload.get("latency_ms"))

        add_step(
            "exchange",
            _build_step(
                step_key=f"venue_connectivity_{venue_key}",
                status=connectivity,
                blocking=True,
                reason_code="PASS" if connectivity == "PASS" else str(payload.get("reason_code") or f"{venue_key.upper()}_CONNECTIVITY_{connectivity}"),
                message=f"{venue_key} connectivity ok" if connectivity == "PASS" else f"{venue_key} connectivity sorunlu",
                details=payload,
                data_source=f"exchange_matrix:{venue_key}",
                started_at=time.perf_counter(),
            ),
        )

        add_step(
            "exchange",
            _build_step(
                step_key=f"venue_orderbook_{venue_key}",
                status=orderbook,
                blocking=True,
                reason_code="PASS" if orderbook == "PASS" else str(payload.get("reason_code") or f"{venue_key.upper()}_ORDERBOOK_{orderbook}"),
                message=f"{venue_key} orderbook ok" if orderbook == "PASS" else f"{venue_key} orderbook sorunlu",
                details=payload,
                data_source=f"exchange_matrix:{venue_key}",
                started_at=time.perf_counter(),
            ),
        )

        latency_status = "UNKNOWN"
        latency_reason = f"{venue_key.upper()}_LATENCY_UNKNOWN"
        venue_timeout_overrides = (timeout_policy.get("venue_overrides") or {}).get(venue_key) or {}
        exchange_timeout_sec = _safe_float(venue_timeout_overrides.get("exchange_call"), _safe_float(timeout_policy.get("exchange_call"), 3.0) or 3.0) or 3.0
        exchange_timeout_ms = float(exchange_timeout_sec) * 1000
        if venue_latency is not None:
            if venue_latency > exchange_timeout_ms:
                latency_status = "FAIL"
                latency_reason = f"{venue_key.upper()}_LATENCY_TIMEOUT"
            else:
                latency_status = "PASS"
                latency_reason = "PASS"

        add_step(
            "exchange",
            _build_step(
                step_key=f"venue_latency_{venue_key}",
                status=latency_status,
                blocking=True,
                reason_code=latency_reason,
                message=f"{venue_key} latency ok" if latency_status == "PASS" else f"{venue_key} latency risk",
                details={"latency_ms": venue_latency, "timeout_ms": exchange_timeout_ms},
                data_source=f"exchange_matrix:{venue_key}",
                started_at=time.perf_counter(),
            ),
        )

        rate_status = "PASS" if venue_rate == "OK" else "UNKNOWN" if venue_rate == "UNKNOWN" else "WARN"
        add_step(
            "exchange",
            _build_step(
                step_key=f"venue_rate_limit_{venue_key}",
                status=rate_status,
                blocking=True,
                reason_code="PASS" if rate_status == "PASS" else f"{venue_key.upper()}_RATE_LIMIT_{venue_rate}",
                message=f"{venue_key} rate limit ok" if rate_status == "PASS" else f"{venue_key} rate limit risk",
                details={"rate_limit": venue_rate},
                data_source=f"exchange_matrix:{venue_key}",
                started_at=time.perf_counter(),
            ),
        )

        checklist = venue_config_checklist.get(venue_key) or {}
        checklist_ok = bool(checklist.get("environment_mapped", True)) and bool(checklist.get("policy_valid", True))
        add_step(
            "exchange",
            _build_step(
                step_key=f"venue_config_checklist_{venue_key}",
                status="PASS" if checklist_ok else "FAIL",
                blocking=True,
                reason_code="PASS" if checklist_ok else str(checklist.get("reason_code") or f"{venue_key.upper()}_CONFIG_INVALID"),
                message=f"{venue_key} config checklist ok" if checklist_ok else f"{venue_key} config checklist fail",
                details=checklist,
                data_source=f"venue_config:{venue_key}",
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
    submit_status = "WARN" if submit_mocked else "PASS" if submit_ok else "FAIL" if submit else "UNKNOWN"
    add_step(
        "execution",
        _build_step(
            step_key="dry_run_order",
            status=submit_status,
            blocking=False,
            reason_code="EXECUTION_TEST_MOCKED" if submit_mocked else "EXECUTION_SUBMIT_FAIL" if not submit_ok else "PASS",
            message="Dry run order ok" if submit_ok else "Dry run order başarısız",
            details={
                "status": submit.get("status"),
                "mocked": submit_mocked,
                "proof_class": "MOCKED" if submit_mocked else "REAL",
            },
            data_source="execution_adapter",
            started_at=time.perf_counter(),
        ),
    )

    cancel = execution_tests.get("cancel") or {}
    cancel_mocked = bool(cancel.get("mocked"))
    cancel_status_raw = str(cancel.get("status") or "").upper()
    cancel_ok = cancel_status_raw == "CANCELLED" and not cancel_mocked
    cancel_status = "WARN" if cancel_mocked else "PASS" if cancel_ok else "FAIL" if cancel else "UNKNOWN"
    add_step(
        "execution",
        _build_step(
            step_key="cancel_test",
            status=cancel_status,
            blocking=False,
            reason_code="EXECUTION_CANCEL_MOCKED" if cancel_mocked else "EXECUTION_CANCEL_FAIL" if not cancel_ok else "PASS",
            message="Cancel test ok" if cancel_ok else "Cancel test başarısız",
            details={
                "status": cancel.get("status"),
                "mocked": cancel_mocked,
                "proof_class": "MOCKED" if cancel_mocked else "REAL",
            },
            data_source="execution_adapter",
            started_at=time.perf_counter(),
        ),
    )

    lifecycle_states = {str(state or "").upper() for state in (execution_lifecycle.get("states") or []) if str(state or "").strip()}
    lifecycle_events = {str(state or "").upper() for state in (execution_lifecycle.get("events") or []) if str(state or "").strip()}
    lifecycle_sync_ok = bool(execution_lifecycle.get("sync_ok"))
    real_metric_count = int(execution_lifecycle.get("real_metric_count") or 0)
    mocked_metric_count = int(execution_lifecycle.get("mocked_metric_count") or 0)

    partial_ok = "PARTIALLY_FILLED" in lifecycle_states and "FILLED" in lifecycle_states
    fill_ok = "FILLED" in lifecycle_states
    cancel_ok = "CANCELLED" in lifecycle_states or "CANCELED" in lifecycle_states
    reject_ok = "REJECTED" in lifecycle_states or "EXPIRED" in lifecycle_states

    add_step(
        "execution",
        _build_step(
            step_key="partial_fill_handling",
            status="PASS" if partial_ok else "FAIL",
            blocking=True,
            reason_code="PASS" if partial_ok else "PARTIAL_FILL_INVALID",
            message="Partial fill lifecycle doğrulandı" if partial_ok else "Partial fill lifecycle eksik",
            details={"states": sorted(lifecycle_states)},
            data_source="execution_state_transitions",
            started_at=time.perf_counter(),
        ),
    )

    add_step(
        "execution",
        _build_step(
            step_key="fill_path",
            status="PASS" if fill_ok else "FAIL",
            blocking=True,
            reason_code="PASS" if fill_ok else "FILL_PATH_INVALID",
            message="Fill lifecycle doğrulandı" if fill_ok else "Fill lifecycle eksik",
            details={"states": sorted(lifecycle_states)},
            data_source="execution_state_transitions",
            started_at=time.perf_counter(),
        ),
    )

    add_step(
        "execution",
        _build_step(
            step_key="cancel_path",
            status="PASS" if cancel_ok else "FAIL",
            blocking=True,
            reason_code="PASS" if cancel_ok else "CANCEL_PATH_INVALID",
            message="Cancel lifecycle doğrulandı" if cancel_ok else "Cancel lifecycle eksik",
            details={"states": sorted(lifecycle_states)},
            data_source="execution_state_transitions",
            started_at=time.perf_counter(),
        ),
    )

    add_step(
        "execution",
        _build_step(
            step_key="reject_path",
            status="PASS" if reject_ok else "FAIL",
            blocking=True,
            reason_code="PASS" if reject_ok else "REJECT_PATH_INVALID",
            message="Reject lifecycle doğrulandı" if reject_ok else "Reject lifecycle eksik",
            details={"states": sorted(lifecycle_states)},
            data_source="execution_state_transitions",
            started_at=time.perf_counter(),
        ),
    )

    add_step(
        "execution",
        _build_step(
            step_key="lifecycle_db_event_sync",
            status="PASS" if lifecycle_sync_ok else "FAIL",
            blocking=True,
            reason_code="PASS" if lifecycle_sync_ok else "EXECUTION_LIFECYCLE_SYNC_FAIL",
            message="Execution lifecycle DB/event uyumlu" if lifecycle_sync_ok else "Execution lifecycle DB/event uyumsuz",
            details={"states": sorted(lifecycle_states), "events": sorted(lifecycle_events)},
            data_source="execution_lifecycle_events",
            started_at=time.perf_counter(),
        ),
    )

    proof_quality_ok = real_metric_count > 0
    add_step(
        "execution",
        _build_step(
            step_key="execution_proof_quality",
            status="PASS" if proof_quality_ok else "FAIL",
            blocking=True,
            reason_code="PASS" if proof_quality_ok else "EXECUTION_PROOF_ONLY_MOCKED",
            message="Execution proof gerçek testnet verisi içeriyor" if proof_quality_ok else "Execution proof sadece mocked",
            details={
                "real_metric_count": real_metric_count,
                "mocked_metric_count": mocked_metric_count,
                "submit_mocked": submit_mocked,
                "cancel_mocked": cancel_mocked,
            },
            data_source="execution_metrics",
            started_at=time.perf_counter(),
        ),
    )

    reduce_payload = reduce_only_test.get("payload") or {}
    reduce_status_code = reduce_only_test.get("status_code")
    reduce_ok = False
    reduce_reason = "REDUCE_ONLY_UNVERIFIED"
    if reduce_status_code is None:
        reduce_status = "UNKNOWN"
    elif reduce_status_code >= 400:
        reduce_status = "PASS"
        reduce_ok = True
        reduce_reason = "REDUCE_ONLY_REJECTED"
    else:
        order_status = str(reduce_payload.get("status") or "").upper()
        if order_status in {"NEW", "FILLED"}:
            reduce_status = "FAIL"
            reduce_reason = "REDUCE_ONLY_ACCEPTED"
        else:
            reduce_status = "UNKNOWN"
            reduce_reason = "REDUCE_ONLY_UNKNOWN"

    add_step(
        "execution",
        _build_step(
            step_key="reduce_only_enforcement",
            status=reduce_status,
            blocking=True,
            reason_code=reduce_reason,
            message="Reduce-only doğrulandı" if reduce_status == "PASS" else "Reduce-only doğrulanamadı",
            details={"status_code": reduce_status_code, "payload": reduce_payload},
            data_source="exchange_adapter",
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
    leverage_cap = _safe_float(getattr(config, "leverage_cap", None))
    expected_max_leverage = max_leverage
    if leverage_cap is not None:
        expected_max_leverage = min(expected_max_leverage, leverage_cap) if expected_max_leverage is not None else leverage_cap

    account_payload = exchange_account.get("payload") or {}
    account_positions = account_payload.get("positions") if isinstance(account_payload, dict) else None

    leverage_values = []
    margin_modes = []
    for item in (risk_positions if 'risk_positions' in locals() else []):
        try:
            position_amt = float(item.get("positionAmt") or 0)
        except (TypeError, ValueError):
            position_amt = 0
        if position_amt == 0:
            continue
        leverage_values.append(_safe_float(item.get("leverage")))
        margin_modes.append(str(item.get("marginType") or item.get("margin_type") or "").lower())

    if not leverage_values and isinstance(account_positions, list):
        for item in account_positions:
            try:
                position_amt = float(item.get("positionAmt") or item.get("position_amt") or 0)
            except (TypeError, ValueError):
                position_amt = 0
            if position_amt == 0:
                continue
            leverage_values.append(_safe_float(item.get("leverage")))
            margin_modes.append(str(item.get("marginType") or item.get("margin_type") or "").lower())

    leverage_status = "UNKNOWN"
    leverage_reason = "LEVERAGE_DATA_MISSING"
    if engine_positions_count == 0:
        leverage_status = "PASS"
        leverage_reason = "PASS"
    elif not leverage_values:
        leverage_status = "UNKNOWN"
        leverage_reason = "LEVERAGE_DATA_MISSING"
    elif expected_max_leverage is None:
        leverage_status = "UNKNOWN"
        leverage_reason = "LEVERAGE_EXPECTATION_MISSING"
    elif any(value is not None and value > expected_max_leverage for value in leverage_values):
        leverage_status = "FAIL"
        leverage_reason = "LEVERAGE_MISMATCH"
    else:
        leverage_status = "PASS"
        leverage_reason = "PASS"

    add_step(
        "risk",
        _build_step(
            step_key="leverage_validation",
            status=leverage_status,
            blocking=True,
            reason_code=leverage_reason,
            message="Leverage limit ok" if leverage_status == "PASS" else "Leverage mismatch",
            details={"max_leverage": expected_max_leverage, "observed": leverage_values},
            data_source="exchange_position_risk",
            started_at=time.perf_counter(),
        ),
    )

    expected_margin_mode = str(risk_config.get("margin_mode") or "").lower()
    margin_mode_status = "UNKNOWN"
    margin_mode_reason = "MARGIN_MODE_UNKNOWN"
    if engine_positions_count == 0:
        margin_mode_status = "PASS"
        margin_mode_reason = "PASS"
    elif not margin_modes:
        margin_mode_status = "UNKNOWN"
        margin_mode_reason = "MARGIN_MODE_DATA_MISSING"
    elif not expected_margin_mode:
        margin_mode_status = "UNKNOWN"
        margin_mode_reason = "MARGIN_MODE_EXPECTATION_MISSING"
    elif any(mode and mode != expected_margin_mode for mode in margin_modes):
        margin_mode_status = "FAIL"
        margin_mode_reason = "MARGIN_MODE_MISMATCH"
    else:
        margin_mode_status = "PASS"
        margin_mode_reason = "PASS"

    add_step(
        "risk",
        _build_step(
            step_key="margin_mode_validation",
            status=margin_mode_status,
            blocking=True,
            reason_code=margin_mode_reason,
            message="Margin mode doğrulandı" if margin_mode_status == "PASS" else "Margin mode doğrulanamadı",
            details={"expected": expected_margin_mode, "observed": margin_modes},
            data_source="exchange_position_risk",
            started_at=time.perf_counter(),
        ),
    )

    total_exposure = _safe_float(trading_state.get("total_exposure"), 0.0) or 0.0
    exposure_policy_result = evaluate_exposure_policy(
        wallet_balance=wallet_balance,
        total_exposure=total_exposure,
        portfolio_exposure=portfolio_exposure,
        risk_config=risk_config,
        policy_overrides=exposure_policy,
    )
    exposure_status = str(exposure_policy_result.get("state") or "UNKNOWN")
    exposure_reason = str(exposure_policy_result.get("reason_code") or "EXPOSURE_DATA_MISSING")

    add_step(
        "risk",
        _build_step(
            step_key="position_size_limit",
            status=exposure_status,
            blocking=True,
            reason_code=exposure_reason,
            message="Exposure limiti ok" if exposure_status == "PASS" else "Exposure limiti aşıldı",
            details={
                "total_exposure": total_exposure,
                "wallet_balance": wallet_balance,
                "policy": exposure_policy_result,
            },
            data_source="risk_engine_config",
            started_at=time.perf_counter(),
        ),
    )

    risk_engine_ok = bool(risk_orchestrator_enabled) and bool(risk_engine_health.get("config_loaded")) and bool(risk_engine_health.get("policy_apply_ok")) and not risk_engine_health.get("error")
    risk_engine_reason = "PASS"
    if not risk_orchestrator_enabled:
        risk_engine_reason = "RISK_ENGINE_DISABLED"
    elif not risk_engine_health.get("config_loaded"):
        risk_engine_reason = "RISK_ENGINE_CONFIG_FAIL"
    elif risk_engine_health.get("error"):
        risk_engine_reason = "RISK_ENGINE_RUNTIME_FAIL"
    elif not risk_engine_health.get("policy_apply_ok"):
        risk_engine_reason = "RISK_ENGINE_POLICY_APPLY_FAIL"

    add_step(
        "risk",
        _build_step(
            step_key="risk_engine_connectivity",
            status="PASS" if risk_engine_ok else "FAIL",
            blocking=True,
            reason_code=risk_engine_reason,
            message="Risk engine canlı doğrulama geçti" if risk_engine_ok else "Risk engine canlı doğrulama başarısız",
            details={
                "enabled": risk_orchestrator_enabled,
                "health": risk_engine_health,
            },
            data_source="risk_engine_service",
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

    heartbeat_raw = infra.get("strategy_heartbeat")
    last_execution_raw = infra.get("strategy_last_execution")
    restart_raw = infra.get("strategy_restart_at")
    strategy_error_state = str(infra.get("strategy_error_state") or "").strip()
    stale_threshold_sec = int(_safe_float(timeout_policy.get("strategy_heartbeat_stale_sec"), 90) or 90)
    grace_period_sec = int(_safe_float(timeout_policy.get("strategy_restart_grace_period_sec"), 45) or 45)

    heartbeat_payload = None
    producer_id = None
    heartbeat_ts = None
    if isinstance(heartbeat_raw, dict):
        heartbeat_payload = heartbeat_raw
    elif isinstance(heartbeat_raw, str) and heartbeat_raw.strip().startswith("{"):
        try:
            heartbeat_payload = json.loads(heartbeat_raw)
        except Exception:
            heartbeat_payload = None

    if isinstance(heartbeat_payload, dict):
        producer_id = str(heartbeat_payload.get("producer_id") or "").strip() or None
        heartbeat_ts = _parse_timestamp(heartbeat_payload.get("timestamp") or heartbeat_payload.get("generated_at") or heartbeat_payload.get("heartbeat_at"))

    if heartbeat_ts is None:
        heartbeat_ts = _parse_timestamp(heartbeat_raw)
    last_execution_ts = _parse_timestamp(last_execution_raw)
    restart_ts = _parse_timestamp(restart_raw)
    heartbeat_age_sec = int((_utcnow() - heartbeat_ts).total_seconds()) if heartbeat_ts else None
    last_execution_age_sec = int((_utcnow() - last_execution_ts).total_seconds()) if last_execution_ts else None
    restart_age_sec = int((_utcnow() - restart_ts).total_seconds()) if restart_ts else None
    within_restart_grace = restart_age_sec is not None and restart_age_sec <= grace_period_sec

    if not heartbeat_ts:
        strategy_status = "UNKNOWN"
        strategy_reason = "STRATEGY_ENGINE_UNKNOWN"
    elif within_restart_grace:
        strategy_status = "UNKNOWN"
        strategy_reason = "STRATEGY_ENGINE_GRACE_PERIOD"
    elif strategy_error_state:
        strategy_status = "FAIL"
        strategy_reason = "STRATEGY_ENGINE_ERROR"
    elif heartbeat_age_sec is not None and heartbeat_age_sec > stale_threshold_sec:
        strategy_status = "FAIL"
        strategy_reason = "STRATEGY_ENGINE_HEARTBEAT_STALE"
    elif producer_id is None:
        strategy_status = "FAIL"
        strategy_reason = "STRATEGY_HEARTBEAT_PRODUCER_MISSING"
    elif last_execution_age_sec is None:
        strategy_status = "FAIL"
        strategy_reason = "STRATEGY_ENGINE_IDLE_NO_OUTPUT"
    elif last_execution_age_sec > stale_threshold_sec * 3:
        strategy_status = "FAIL"
        strategy_reason = "STRATEGY_ENGINE_IDLE_NO_OUTPUT"
    else:
        strategy_status = "PASS"
        strategy_reason = "PASS"

    add_step(
        "infra",
        _build_step(
            step_key="strategy_engine",
            status=strategy_status,
            blocking=True,
            reason_code=strategy_reason,
            message="Strategy engine health doğrulandı" if strategy_status == "PASS" else "Strategy engine health başarısız",
            details={
                "heartbeat": heartbeat_raw,
                "heartbeat_payload": heartbeat_payload,
                "producer_id": producer_id,
                "last_execution": last_execution_raw,
                "restart_at": restart_raw,
                "heartbeat_age_sec": heartbeat_age_sec,
                "last_execution_age_sec": last_execution_age_sec,
                "restart_age_sec": restart_age_sec,
                "restart_grace_period_sec": grace_period_sec,
                "error_state": strategy_error_state,
                "stale_threshold_sec": stale_threshold_sec,
            },
            data_source="strategy:engine:heartbeat",
            started_at=time.perf_counter(),
        ),
    )

    # Latency checks
    round_trip_ms = _safe_float(latency_metrics.get("round_trip_ms"))
    order_exec_ms = _safe_float(latency_metrics.get("order_execution_ms"))
    tick_to_trade_ms = _safe_float(latency_metrics.get("tick_to_trade_ms"))

    def _latency_status(value: float | None, key: str):
        if value is None:
            return "UNKNOWN", f"{key.upper()}_MISSING"
        thresholds = latency_config.get(key) or {}
        warn = thresholds.get("warn")
        block = thresholds.get("block")
        if block is not None and value > block:
            return "FAIL", f"{key.upper()}_BLOCK"
        if warn is not None and value > warn:
            return "WARN", f"{key.upper()}_WARN"
        return "PASS", "PASS"

    percentile_cfg = latency_config.get("percentiles") or {}
    p95_multiplier = _safe_float(percentile_cfg.get("p95_multiplier"), 1.15) or 1.15
    p99_multiplier = _safe_float(percentile_cfg.get("p99_multiplier"), 1.35) or 1.35

    for key, value, step_key in [
        ("round_trip", round_trip_ms, "round_trip_latency"),
        ("order_execution", order_exec_ms, "order_execution_latency"),
        ("tick_to_trade", tick_to_trade_ms, "tick_to_trade_latency"),
    ]:
        status, reason = _latency_status(value, key)
        add_step(
            "latency",
            _build_step(
                step_key=step_key,
                status=status,
                blocking=True,
                reason_code=reason,
                message="Latency normal" if status == "PASS" else "Latency yüksek",
                details={"value_ms": value, "thresholds": latency_config.get(key)},
                data_source="execution_metrics",
                started_at=time.perf_counter(),
            ),
        )

    latency_percentile_steps = [
        ("round_trip", _safe_float(latency_metrics.get("round_trip_p95_ms")), _safe_float(latency_metrics.get("round_trip_p99_ms"))),
        ("order_execution", _safe_float(latency_metrics.get("order_execution_p95_ms")), _safe_float(latency_metrics.get("order_execution_p99_ms"))),
        ("tick_to_trade", _safe_float(latency_metrics.get("tick_to_trade_p95_ms")), _safe_float(latency_metrics.get("tick_to_trade_p99_ms"))),
    ]
    for key, p95, p99 in latency_percentile_steps:
        thresholds = latency_config.get(key) or {}
        warn = _safe_float(thresholds.get("warn"))
        block = _safe_float(thresholds.get("block"))
        if p95 is None or p99 is None or warn is None or block is None:
            status = "UNKNOWN"
            reason = f"{key.upper()}_PCTL_MISSING"
        elif p99 > (block * p99_multiplier):
            status = "FAIL"
            reason = f"{key.upper()}_P99_BLOCK"
        elif p95 > (warn * p95_multiplier):
            status = "WARN"
            reason = f"{key.upper()}_P95_WARN"
        else:
            status = "PASS"
            reason = "PASS"
        add_step(
            "latency",
            _build_step(
                step_key=f"{key}_percentiles",
                status=status,
                blocking=True,
                reason_code=reason,
                message="Latency percentile normal" if status == "PASS" else "Latency percentile risk",
                details={
                    "p95_ms": p95,
                    "p99_ms": p99,
                    "warn_threshold_ms": warn,
                    "block_threshold_ms": block,
                    "p95_multiplier": p95_multiplier,
                    "p99_multiplier": p99_multiplier,
                },
                data_source="execution_metrics",
                started_at=time.perf_counter(),
            ),
        )

    # Safety checks
    submit_result = execution_tests.get("submit") or {}
    submit_mocked = bool(submit_result.get("mocked"))
    successful_lifecycle_count = int(execution_lifecycle.get("successful_lifecycle_count") or 0)
    dry_run_ok = dry_run_count > 0 and successful_lifecycle_count > 0 and not submit_mocked
    add_step(
        "safety",
        _build_step(
            step_key="dry_run_required",
            status="PASS" if dry_run_ok else "FAIL",
            blocking=True,
            reason_code="PASS" if dry_run_ok else "DRY_RUN_REQUIRED",
            message="Dry-run tamam" if dry_run_ok else "Dry-run zorunlu",
            details={
                "dry_run_count": dry_run_count,
                "successful_lifecycle_count": successful_lifecycle_count,
                "mocked": submit_mocked,
            },
            data_source="testnet_execution_log",
            started_at=time.perf_counter(),
        ),
    )

    capital_guard_policy = (exposure_policy or {}).get("capital_guard") or {}
    max_drawdown_pct = _safe_float(capital_guard_policy.get("max_drawdown_pct") or risk_config.get("max_drawdown_pct") or risk_config.get("max_daily_loss_pct"))
    max_exposure_pct_safety = _safe_float((exposure_policy.get("global") or {}).get("max_total_exposure_pct"), _safe_float(risk_config.get("max_total_exposure_pct")))
    drawdown_pct = None
    net_total_usd = _safe_float(pnl_snapshot.get("net_total_usd"))
    portfolio_notional = _safe_float(portfolio_exposure.get("global_notional"), 0.0) or 0.0
    if net_total_usd is not None and wallet_balance is not None and wallet_balance > 0 and net_total_usd < 0:
        drawdown_pct = abs(net_total_usd) / wallet_balance * 100

    effective_exposure = max(float(total_exposure or 0.0), float(portfolio_notional or 0.0))
    effective_exposure_pct = None
    if wallet_balance is not None and wallet_balance > 0:
        effective_exposure_pct = (effective_exposure / wallet_balance) * 100

    if max_drawdown_pct is None:
        capital_status = "UNKNOWN"
        capital_reason = "DRAW_DOWN_CONFIG_MISSING"
    elif effective_exposure_pct is not None and max_exposure_pct_safety is not None and effective_exposure_pct > max_exposure_pct_safety * 1.25:
        capital_status = "FAIL"
        capital_reason = "CAPITAL_EXPOSURE_BREACH"
    elif drawdown_pct is None:
        capital_status = "UNKNOWN"
        capital_reason = "DRAW_DOWN_DATA_MISSING"
    elif drawdown_pct > max_drawdown_pct:
        capital_status = "FAIL"
        capital_reason = "DRAW_DOWN_LIMIT_BREACH"
    elif drawdown_pct > max_drawdown_pct * 0.8:
        capital_status = "WARN"
        capital_reason = "DRAW_DOWN_LIMIT_NEAR"
    else:
        capital_status = "PASS"
        capital_reason = "PASS"

    add_step(
        "safety",
        _build_step(
            step_key="capital_guard",
            status=capital_status,
            blocking=True,
            reason_code=capital_reason,
            message="Capital guard ok" if capital_status == "PASS" else "Capital guard risk",
            details={
                "drawdown_pct": drawdown_pct,
                "threshold_pct": max_drawdown_pct,
                "effective_exposure_pct": effective_exposure_pct,
                "portfolio_notional": portfolio_notional,
            },
            data_source="pnl_records",
            started_at=time.perf_counter(),
        ),
    )

    exposure_status = str(exposure_policy_result.get("state") or "UNKNOWN")
    exposure_reason = str(exposure_policy_result.get("reason_code") or "EXPOSURE_DATA_MISSING")
    exposure_pct = _safe_float(exposure_policy_result.get("global_exposure_pct"))

    add_step(
        "safety",
        _build_step(
            step_key="exposure_limit",
            status=exposure_status,
            blocking=True,
            reason_code=exposure_reason,
            message="Exposure limit ok" if exposure_status == "PASS" else "Exposure limit risk",
            details={
                "exposure_pct": exposure_pct,
                "threshold_pct": max_exposure_pct_safety,
                "effective_exposure": effective_exposure,
                "by_symbol": portfolio_exposure.get("by_symbol") or {},
                "by_strategy": portfolio_exposure.get("by_strategy") or {},
                "symbol_breakers": exposure_policy_result.get("symbol_breakers") or [],
                "strategy_breakers": exposure_policy_result.get("strategy_breakers") or [],
            },
            data_source="risk_engine_config",
            started_at=time.perf_counter(),
        ),
    )

    timeout_threshold_ms = {
        "exchange_call": float(_safe_float(timeout_policy.get("exchange_call"), 3.0) or 3.0) * 1000,
        "order_execution": float(_safe_float(timeout_policy.get("order_execution"), 5.0) or 5.0) * 1000,
        "market_data": float(_safe_float(timeout_policy.get("market_data"), 2.0) or 2.0) * 1000,
    }

    def _timeout_bucket(layer: str, step_key: str) -> str | None:
        key = str(step_key or "")
        if layer == "exchange" or key.startswith("venue_"):
            return "exchange_call"
        if layer == "execution" or key in {"dry_run_required", "reduce_only_enforcement"}:
            return "order_execution"
        if layer in {"trading_state", "latency"} and any(item in key for item in ["market", "funding", "liquidation", "latency"]):
            return "market_data"
        return None

    for step in steps:
        bucket = _timeout_bucket(str(step.get("layer") or ""), str(step.get("step_key") or ""))
        if not bucket:
            continue
        threshold_ms = timeout_threshold_ms.get(bucket)
        duration_ms = int(step.get("duration_ms") or 0)
        if threshold_ms is None or duration_ms <= threshold_ms:
            continue

        previous_status = str(step.get("status") or "UNKNOWN")
        step["status"] = "FAIL"
        step["reason_code"] = f"TIMEOUT_{bucket.upper()}"
        step["message"] = f"Step timeout: {bucket}"
        details = step.get("details") or {}
        details["timeout_bucket"] = bucket
        details["timeout_threshold_ms"] = threshold_ms
        details["duration_ms"] = duration_ms
        details["previous_status"] = previous_status
        step["details"] = details

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

    def _layer_state(layer: str) -> str:
        layer_steps = by_layer.get(layer) or []
        statuses = [step.get("status") for step in layer_steps]
        if any(status == "FAIL" for status in statuses):
            return "BLOCKED"
        if any(status == "UNKNOWN" for status in statuses):
            return "UNKNOWN"
        if any(status == "WARN" for status in statuses):
            return "WARNING"
        return "READY" if statuses else "UNKNOWN"

    exchange_readiness: dict[str, dict] = {}
    for venue, payload in exchange_matrix.items():
        venue_key = str(venue or "").lower().strip()
        if not venue_key:
            continue
        connectivity = str(payload.get("connectivity") or "UNKNOWN").upper()
        orderbook = str(payload.get("orderbook") or "UNKNOWN").upper()
        latency = _safe_float(payload.get("latency_ms"))
        exchange_timeout_ms = float(_safe_float(timeout_policy.get("exchange_call"), 3.0) or 3.0) * 1000

        if connectivity == "FAIL" or orderbook == "FAIL":
            state = "BLOCKED"
        elif connectivity == "UNKNOWN" or orderbook == "UNKNOWN":
            state = "UNKNOWN"
        elif latency is not None and latency > exchange_timeout_ms:
            state = "BLOCKED"
        else:
            state = "READY"

        exchange_readiness[venue_key] = {
            "state": state,
            "connectivity": connectivity,
            "orderbook": orderbook,
            "latency_ms": latency,
            "rate_limit": str(payload.get("rate_limit") or "UNKNOWN").upper(),
            "websocket_age_sec": payload.get("websocket_age_sec"),
            "source": payload.get("source"),
        }

    for fallback_exchange in required_venues:
        exchange_readiness.setdefault(fallback_exchange, {"state": "UNKNOWN"})

    liquidation_step = next((step for step in steps if step.get("step_key") == "liquidation_risk"), {})
    liquidation_by_symbol = (liquidation_step.get("details") or {}).get("by_symbol") or {}
    funding_by_symbol = trading_state.get("funding_by_symbol") or {}

    symbol_readiness: dict[str, str] = {}
    for symbol in symbols:
        symbol_key = str(symbol or "").upper().strip()
        if not symbol_key:
            continue
        funding_state = str((funding_by_symbol.get(symbol_key) or {}).get("state") or "UNKNOWN").upper()
        liquidation_distance = _safe_float((liquidation_by_symbol.get(symbol_key) or {}).get("distance_pct"))
        liquidation_threshold = _safe_float((liquidation_by_symbol.get(symbol_key) or {}).get("threshold_pct"), _safe_float(risk_config.get("min_liquidation_distance_pct"), 5.0) or 5.0) or 5.0

        state = "READY"
        if funding_state == "FAIL":
            state = "BLOCKED"
        elif funding_state == "UNKNOWN":
            state = "UNKNOWN"
        elif liquidation_distance is None:
            state = "UNKNOWN"
        elif liquidation_distance < liquidation_threshold:
            state = "BLOCKED"
        elif liquidation_distance < liquidation_threshold * 1.5:
            state = "WARNING"
        symbol_readiness[symbol_key] = state

    strategy_readiness: dict[str, str] = {}
    for strategy_id in strategy_ids:
        metric = strategy_metrics.get(strategy_id) or {}
        total = int(metric.get("total") or 0)
        success = int(metric.get("success") or 0)
        rejected = int(metric.get("rejected") or 0)
        errors = int(metric.get("errors") or 0)

        if total == 0:
            strategy_state = "UNKNOWN"
        else:
            success_rate = success / max(total, 1)
            reject_rate = rejected / max(total, 1)
            if errors > 0 or reject_rate >= 0.5:
                strategy_state = "BLOCKED"
            elif success_rate < 0.75:
                strategy_state = "WARNING"
            else:
                strategy_state = "READY"
        strategy_readiness[strategy_id] = strategy_state

    readiness_matrix = {
        "exchange": exchange_readiness,
        "symbol": symbol_readiness,
        "strategy": strategy_readiness,
    }

    execution_proof = {
        "real_metric_count": int(execution_lifecycle.get("real_metric_count") or 0),
        "mocked_metric_count": int(execution_lifecycle.get("mocked_metric_count") or 0),
        "submit_mocked": bool((execution_tests.get("submit") or {}).get("mocked")),
        "cancel_mocked": bool((execution_tests.get("cancel") or {}).get("mocked")),
    }
    execution_proof["has_mocked_paths"] = bool(execution_proof["submit_mocked"] or execution_proof["cancel_mocked"] or execution_proof["mocked_metric_count"] > 0)
    execution_proof["proof_status"] = "REAL" if execution_proof["real_metric_count"] > 0 else "MOCKED_ONLY"

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
        "required_venues": required_venues,
        "venue_policy": venue_policy,
        "exchange_readiness": exchange_readiness,
        "symbol_readiness": symbol_readiness,
        "strategy_readiness": strategy_readiness,
        "readiness_matrix": readiness_matrix,
        "execution_proof": execution_proof,
        "latency_config": latency_config,
        "timeout_policy": timeout_policy,
        "data_quality_config": data_quality_config,
        "venue_config_checklist": venue_config_checklist,
        "adapter_credential_summary": context.get("adapter_credential_summary") or {},
        "latency_metrics": latency_metrics,
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
            "required_venues": _resolve_required_venues(),
            "venue_policy": str(os.environ.get("GO_LIVE_VENUE_POLICY") or "binance_only").strip().lower(),
            "exchange_readiness": {},
            "symbol_readiness": {},
            "strategy_readiness": {},
            "readiness_matrix": {"exchange": {}, "symbol": {}, "strategy": {}},
            "execution_proof": {
                "real_metric_count": 0,
                "mocked_metric_count": 0,
                "submit_mocked": True,
                "cancel_mocked": True,
                "has_mocked_paths": True,
                "proof_status": "MOCKED_ONLY",
            },
            "latency_config": dict(DEFAULT_LATENCY_CONFIG),
            "timeout_policy": dict(DEFAULT_TIMEOUT_POLICY),
            "data_quality_config": dict(DEFAULT_DATA_QUALITY_CONFIG),
            "venue_config_checklist": {},
            "adapter_credential_summary": {},
            "latency_metrics": {},
        }
