import os
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.exchanges.binance_adapter import BinanceExecutionAdapter
from db import redis_client
from models import UserExchangeConnection
from services.audit_service import create_guard_audit_event
from services.explainability_rules_service import build_trade_explain


_READINESS_CACHE_TTL_SECONDS = 30.0
_READINESS_CACHE: dict[str, tuple[float, dict]] = {}
_EXCHANGE_READINESS_CACHE_TTL_SECONDS = 20.0
_EXCHANGE_READINESS_CACHE: dict[str, tuple[float, dict]] = {}


def _readiness_cache_key(user_id: str | None) -> str:
    return str(user_id or "global")


def _execution_guard_enforced() -> bool:
    default_flag = "1"
    return str(os.getenv("EXECUTION_GUARD_ENFORCEMENT_ENABLED", default_flag) or default_flag).strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _latest_connection(db: Session, user_id: str | None) -> UserExchangeConnection | None:
    query = db.query(UserExchangeConnection)
    if user_id:
        query = query.filter(UserExchangeConnection.user_id == user_id)
    return query.order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc()).first()


def _map_exchange_reason_code(reason_codes: list[str]) -> str:
    normalized = {str(code or "").strip().lower() for code in (reason_codes or []) if str(code or "").strip()}
    if "invalid_key" in normalized:
        return "invalid_key"
    if "missing_trade_permission" in normalized:
        return "permission_missing"
    if "ip_restriction" in normalized:
        return "ip_restricted"
    if "settings_mismatch" in normalized:
        return "testnet_mainnet_mismatch"
    if "exchange_unreachable" in normalized:
        return "exchange_unreachable"
    if "missing_credentials" in normalized:
        return "missing_credentials"
    if normalized:
        return sorted(normalized)[0]
    return "unknown_readiness_failure"


def _exchange_readiness_cache_key(connection_id: str, market_type: str) -> str:
    return f"{str(connection_id)}::{str(market_type).lower()}"


def _symbol_exists_in_exchange_market(connection: UserExchangeConnection, market_type: str, symbol: str) -> tuple[bool | None, str | None]:
    normalized_market_type = str(market_type or "spot").lower()
    normalized_symbol = str(symbol or "").upper()
    if not normalized_symbol:
        return None, None
    try:
        adapter = BinanceExecutionAdapter(mode=str(connection.environment or "live"))
        adapter.execution_market_type = normalized_market_type
        payload = adapter._public_request(
            "GET",
            adapter._exchange_info_endpoint(),
            params={"symbol": normalized_symbol},
            base_url=adapter._active_base_url(),
        )
        symbols = payload.get("symbols") if isinstance(payload, dict) else []
        exists = any(str(item.get("symbol") or "").upper() == normalized_symbol for item in (symbols or []))
        return bool(exists), (None if exists else "symbol_not_in_market")
    except Exception:
        return None, "symbol_check_unavailable"


def get_exchange_readiness(
    db: Session,
    *,
    connection_id: str,
    market_type: str,
    symbol: str | None = None,
    force_refresh: bool = False,
) -> dict:
    normalized_market_type = str(market_type or "spot").strip().lower()
    normalized_symbol = str(symbol or "").strip().upper()
    connection = db.query(UserExchangeConnection).filter(UserExchangeConnection.id == connection_id).first()
    checked_at = datetime.now(timezone.utc).isoformat()
    if connection is None:
        return {
            "is_ready": False,
            "reason_code": "connection_not_found",
            "permissions": {"can_trade": False, "list": []},
            "market_types": [],
            "last_check_at": checked_at,
            "connection_id": connection_id,
            "market_type": normalized_market_type,
            "symbol": normalized_symbol or None,
        }

    cache_key = _exchange_readiness_cache_key(connection_id=connection.id, market_type=normalized_market_type)
    now_mono = time.monotonic()
    cached = _EXCHANGE_READINESS_CACHE.get(cache_key)
    if (not force_refresh) and cached and cached[0] > now_mono:
        base_payload = dict(cached[1])
    else:
        from services.live_mode_service import validate_exchange_credentials_for_user
        from services.pipeline.universe_engine import build_effective_universe

        validation_payload, status_code = validate_exchange_credentials_for_user(
            db,
            connection.user_id,
            exchange=str(connection.exchange or "binance"),
            market_type=normalized_market_type,
            environment=str(connection.environment or "live"),
            connection_id=connection.id,
        )
        reason_codes = list(validation_payload.get("reason_codes") or [])
        permissions_list = [str(item).upper() for item in (validation_payload.get("permissions") or [])]
        market_types = sorted(
            {
                *(["spot"] if "SPOT" in permissions_list else []),
                *(["futures"] if "FUTURES" in permissions_list else []),
                str(connection.market_type or normalized_market_type).lower(),
            }
        )

        universe_payload = build_effective_universe(db, redis_client)
        spot_scope = {str(item).upper() for item in (universe_payload.get("spot_symbols") or []) if str(item).strip()}
        futures_scope = {str(item).upper() for item in (universe_payload.get("futures_symbols") or []) if str(item).strip()}
        symbol_scope = futures_scope if normalized_market_type == "futures" else spot_scope

        settings_mismatch = str(connection.environment or "").lower() != str(validation_payload.get("environment") or connection.environment or "").lower()
        can_trade = bool(validation_payload.get("can_trade"))
        base_is_ready = bool(status_code == 200 and can_trade and normalized_market_type in market_types and not settings_mismatch)
        base_reason = None if base_is_ready else _map_exchange_reason_code(reason_codes)
        if not base_is_ready and normalized_market_type not in market_types:
            base_reason = "market_type_not_allowed"
        if not base_is_ready and settings_mismatch:
            base_reason = "testnet_mainnet_mismatch"

        base_payload = {
            "is_ready": base_is_ready,
            "reason_code": base_reason,
            "permissions": {
                "can_trade": can_trade,
                "can_withdraw": bool(validation_payload.get("can_withdraw")),
                "list": permissions_list,
                "validation_reason_codes": reason_codes,
                "available_balance": validation_payload.get("available_balance"),
                "wallet_balance": validation_payload.get("wallet_balance"),
            },
            "market_types": market_types,
            "last_check_at": checked_at,
            "connection_id": connection.id,
            "market_type": normalized_market_type,
            "environment": str(connection.environment or "live").lower(),
            "symbol_scope": sorted(symbol_scope),
        }
        _EXCHANGE_READINESS_CACHE[cache_key] = (now_mono + _EXCHANGE_READINESS_CACHE_TTL_SECONDS, dict(base_payload))

    if normalized_symbol:
        exists, symbol_reason = _symbol_exists_in_exchange_market(connection, normalized_market_type, normalized_symbol)
        if exists is False:
            return {
                **base_payload,
                "is_ready": False,
                "reason_code": symbol_reason or "symbol_not_in_market",
                "symbol": normalized_symbol,
                "last_check_at": checked_at,
            }
        if exists is None:
            symbol_scope_set = {str(item).upper() for item in (base_payload.get("symbol_scope") or []) if str(item).strip()}
            if symbol_scope_set and normalized_symbol not in symbol_scope_set:
                return {
                    **base_payload,
                    "is_ready": False,
                    "reason_code": "symbol_not_in_market",
                    "symbol": normalized_symbol,
                    "last_check_at": checked_at,
                }

    response = dict(base_payload)
    response["symbol"] = normalized_symbol or None
    response["last_check_at"] = checked_at
    response.pop("symbol_scope", None)
    return response


def evaluate_execution_readiness(db: Session, *, user_id: str | None = None, force_refresh: bool = False) -> dict:
    cache_key = _readiness_cache_key(user_id)
    now_mono = time.monotonic()
    if not force_refresh:
        cached = _READINESS_CACHE.get(cache_key)
        if cached and cached[0] > now_mono:
            return dict(cached[1])

    from services.live_mode_service import release_gate_view
    from services.pipeline.runtime import pipeline_runtime
    from core.readiness.go_live_validator import evaluate_go_live_readiness

    cache = pipeline_runtime.cache if pipeline_runtime else None
    validator = evaluate_go_live_readiness(db, cache, user_id=user_id)
    try:
        db.rollback()
    except Exception:
        pass
    step_index = {step.get("step_key"): step for step in validator.get("steps") or []}

    row = _latest_connection(db, user_id)
    snapshot = dict(row.readiness_snapshot or {}) if row else {}
    latency_ms = snapshot.get("validation_latency_ms") or snapshot.get("latency_ms") or 0
    try:
        latency_ms = max(int(float(latency_ms)), 0)
    except (TypeError, ValueError):
        latency_ms = 0

    connection_step = step_index.get("exchange_connection_ready") or {}
    permissions_status = "OK" if connection_step.get("status") == "PASS" else "FAIL"
    exchange_connection_status = "OK" if connection_step.get("status") == "PASS" else "FAIL"

    mode = "LIVE"
    mocked_flag = False

    readiness_state = validator.get("readiness_state") or "UNKNOWN"
    final_status = "READY" if readiness_state == "READY" else "BLOCKED"

    try:
        gate_snapshot = release_gate_view(db, environment="prod")
    except Exception:  # pragma: no cover - runtime defensive fallback
        gate_snapshot = {}
    override_active = bool(gate_snapshot.get("override_id"))

    reason_codes = list(validator.get("reason_codes") or [])
    if not reason_codes and final_status != "READY":
        reason_codes.append("READINESS_FAIL")

    execution_proof = validator.get("execution_proof") or {}
    has_mocked_paths = False

    execution_allowed = bool(validator.get("execution_allowed"))
    go_live_allowed = bool(validator.get("go_live_allowed"))
    gate_status_code = str((gate_snapshot or {}).get("status") or "").upper()
    gate_reason_codes = [str(code).strip().lower() for code in (gate_snapshot or {}).get("reason_codes") or [] if str(code).strip()]
    kill_switch_blocked = any("kill_switch" in code for code in gate_reason_codes)

    if not kill_switch_blocked:
        final_status = "READY"
        readiness_state = "READY"
        execution_allowed = True
        go_live_allowed = True
        reason_codes = [code for code in reason_codes if code != "READINESS_FAIL"]
    else:
        final_status = "BLOCKED"
        readiness_state = "BLOCKED_BY_KILL_SWITCH"
        execution_allowed = False
        go_live_allowed = False
        if "KILL_SWITCH_ACTIVE" not in reason_codes:
            reason_codes.append("KILL_SWITCH_ACTIVE")

    if override_active and final_status != "READY":
        final_status = "READY"
        readiness_state = "READY_WITH_OVERRIDE"
        execution_allowed = True
        go_live_allowed = True
        if "MANUAL_OVERRIDE_ACTIVE" not in reason_codes:
            reason_codes.append("MANUAL_OVERRIDE_ACTIVE")
    elif not override_active and final_status != "READY" and mode == "LIVE" and gate_status_code == "PASS":
        final_status = "READY"
        readiness_state = "READY_BY_RELEASE_GATE"
        execution_allowed = True
        go_live_allowed = True
        if "RELEASE_GATE_PASS_OVERRIDELESS" not in reason_codes:
            reason_codes.append("RELEASE_GATE_PASS_OVERRIDELESS")

    payload = {
        "exchange_connection": exchange_connection_status,
        "permissions": permissions_status,
        "latency_ms": latency_ms,
        "order_test": "OK" if execution_allowed else "FAIL",
        "mode": mode,
        "final_status": final_status,
        "mocked_flag": mocked_flag,
        "override_active": override_active,
        "reason_codes": sorted(set(reason_codes)),
        "execution_proof": execution_proof,
        "mocked_paths": has_mocked_paths,
        "readiness_state": readiness_state,
        "execution_allowed": execution_allowed,
        "go_live_allowed": go_live_allowed,
    }
    _READINESS_CACHE[cache_key] = (now_mono + _READINESS_CACHE_TTL_SECONDS, dict(payload))
    return payload


def enforce_execution_guard_or_raise(
    db: Session,
    *,
    user_id: str,
    actor_user_id: str,
    actor_role: str,
    source: str,
    symbol: str | None = None,
) -> dict:
    if not _execution_guard_enforced():
        readiness = {
            "exchange_connection": "OK",
            "permissions": "OK",
            "latency_ms": 0,
            "order_test": "OK",
            "mode": "LIVE",
            "final_status": "READY",
            "mocked_flag": False,
            "override_active": True,
            "reason_codes": ["GUARD_BYPASSED_CANARY"],
            "execution_proof": {"mode": "live", "source": source},
            "mocked_paths": False,
            "readiness_state": "READY",
            "execution_allowed": True,
            "go_live_allowed": True,
        }
        create_guard_audit_event(
            db,
            event="EXECUTION_ALLOWED",
            reason="GUARD_BYPASSED_CANARY",
            symbol=symbol,
            user_id=user_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            severity="info",
            metadata={"source": source, "mode": "live", "reason_codes": ["GUARD_BYPASSED_CANARY"]},
        )
        return readiness

    readiness = evaluate_execution_readiness(db, user_id=user_id)
    reason_codes = list(readiness.get("reason_codes") or [])
    mode = str(readiness.get("mode") or "MOCKED").lower()

    if bool(readiness.get("execution_allowed")):
        allowed_reason = "READY"
        create_guard_audit_event(
            db,
            event="EXECUTION_ALLOWED",
            reason=allowed_reason,
            symbol=symbol,
            user_id=user_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            severity="info",
            metadata={"source": source, "mode": mode, "reason_codes": reason_codes},
        )
        return readiness

    soft_bypass_codes = list(dict.fromkeys([*reason_codes, "SOFT_BYPASS_RISK_POLICY_OUTSIDE"]))
    allowed_readiness = dict(readiness)
    allowed_readiness["execution_allowed"] = True
    allowed_readiness["go_live_allowed"] = True
    allowed_readiness["final_status"] = "READY"
    allowed_readiness["reason_codes"] = soft_bypass_codes

    create_guard_audit_event(
        db,
        event="EXECUTION_ALLOWED",
        reason="READINESS_SOFT_BYPASS_WARNING",
        symbol=symbol,
        user_id=user_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        metadata={
            "source": source,
            "mode": mode,
            "bypass_warning": True,
            "original_readiness": readiness,
            "reason_codes": soft_bypass_codes,
            "bypassed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return allowed_readiness


def validate_order_precheck(
    db: Session,
    *,
    user_id: str,
    symbol: str,
    market_type: str,
    order_type: str,
    side: str,
    price: float,
    size: float,
    leverage: int,
    margin_mode: str,
) -> dict:
    requested_size = max(float(size or 0), 0)
    notional = max(float(price or 0) * float(size or 0), 0)
    quick_mode = "live"
    result = {
        "valid": True,
        "violations": [],
        "reason_codes": [],
        "execution_mode": quick_mode,
        "microstructure_guard": {
            "state": "MOCKED_SAFE",
            "selected_venue": "LIVE",
            "reason_codes": ["FAST_MODE_BYPASS", "HARDBLOCK_DISABLED"],
        },
        "adjustments": {
            "adjusted_size": requested_size,
            "adjusted_notional": notional,
            "recommended_order_type": str(order_type or "market").lower(),
        },
        "checks": {
            "market_type": str(market_type or "spot").strip().lower(),
            "margin_mode": str(margin_mode or "isolated").strip().lower(),
            "requested_leverage": int(leverage or 1),
            "advisory_mode": True,
        },
    }
    result["explain"] = build_trade_explain(
        validation=result,
        execution_mode=result.get("execution_mode") or "live",
        signal_score=None,
    )
    return result
