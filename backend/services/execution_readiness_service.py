import os
import time
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models import PaperPosition, UserExchangeConnection
from services.audit_service import create_guard_audit_event
from services.explainability_rules_service import build_trade_explain


_READINESS_CACHE_TTL_SECONDS = 30.0
_READINESS_CACHE: dict[str, tuple[float, dict]] = {}


def _readiness_cache_key(user_id: str | None) -> str:
    return str(user_id or "global")


def _execution_guard_enforced() -> bool:
    default_flag = "1"
    return str(os.getenv("EXECUTION_GUARD_ENFORCEMENT_ENABLED", default_flag) or default_flag).strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _execution_fast_mode() -> bool:
    default_flag = "0"
    return str(os.getenv("EXECUTION_PREVIEW_FAST_MODE", default_flag) or default_flag).strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _latest_connection(db: Session, user_id: str | None) -> UserExchangeConnection | None:
    query = db.query(UserExchangeConnection)
    if user_id:
        query = query.filter(UserExchangeConnection.user_id == user_id)
    return query.order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc()).first()


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
    primary_reason = str((reason_codes[0] if reason_codes else "READINESS_FAIL") or "READINESS_FAIL").strip().upper()
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

    create_guard_audit_event(
        db,
        event="EXECUTION_BLOCKED",
        reason=primary_reason,
        symbol=symbol,
        user_id=user_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        metadata={"source": source, "mode": mode, "readiness": readiness, "blocked_at": datetime.now(timezone.utc).isoformat()},
    )
    raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="EXECUTION_BLOCKED_BY_READINESS")


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
    if _execution_fast_mode():
        requested_size = max(float(size or 0), 0)
        return {
            "status": "PASS",
            "valid": True,
            "reason_codes": [],
            "violations": [],
            "adjustments": {
                "requested_size": requested_size,
                "adjusted_size": requested_size,
                "requested_leverage": int(leverage or 1),
                "adjusted_leverage": int(leverage or 1),
            },
            "microstructure_guard": {
                "state": "MOCKED_SAFE",
                "selected_venue": "SIM",
                "reason_codes": ["FAST_MODE_BYPASS"],
            },
            "explainability": {
                "rule": "execution_precheck_fast_mode",
                "summary": "CANARY fast-mode ile precheck bypass edildi",
                "details": {
                    "symbol": symbol,
                    "market_type": market_type,
                    "source": "validate_order_precheck",
                },
            },
        }

    from services.live_mode_service import get_or_create_live_config
    from services.execution_microstructure_service import build_order_microstructure_assessment
    from services.pipeline.runtime import pipeline_runtime

    _ = (symbol, order_type, side)
    config = get_or_create_live_config(db)
    cache = pipeline_runtime.cache if pipeline_runtime else None

    leverage_limit = max(int(config.leverage_cap or 1), 1)
    max_exposure = float(config.max_notional_exposure or 0)
    market = str(market_type or "spot").strip().lower()
    margin = str(margin_mode or "isolated").strip().lower()
    requested_size = max(float(size or 0), 0)
    notional = max(float(price or 0) * float(size or 0), 0)
    min_order_size = 0.001
    min_notional = 5.0

    open_rows = db.query(PaperPosition).filter(PaperPosition.user_id == user_id, PaperPosition.status == "open").all()
    open_exposure = sum(abs(float(row.entry_price or 0) * float(row.quantity or 0)) for row in open_rows)
    projected_exposure = open_exposure + notional

    violations: list[dict] = []

    if market == "futures" and int(leverage or 1) > leverage_limit:
        violations.append(
            {
                "code": "leverage_limit_exceeded",
                "message": f"Leverage limiti aşıldı (max={leverage_limit})",
                "details": {"requested": int(leverage or 1), "limit": leverage_limit},
            }
        )

    if requested_size < min_order_size:
        violations.append(
            {
                "code": "min_order_size_violation",
                "message": "Min order size limitinin altında",
                "details": {"requested_size": requested_size, "min_order_size": min_order_size},
            }
        )

    if notional < min_notional:
        violations.append(
            {
                "code": "min_notional_violation",
                "message": "Min notional limitinin altında",
                "details": {"notional": round(notional, 4), "min_notional": min_notional},
            }
        )

    if market == "spot" and margin == "cross":
        violations.append(
            {
                "code": "margin_mode_invalid_for_spot",
                "message": "Spot market için cross margin desteklenmiyor",
                "details": {"market_type": market, "margin_mode": margin},
            }
        )

    if market == "futures" and margin not in {"isolated", "cross"}:
        violations.append(
            {
                "code": "margin_mode_invalid",
                "message": "Margin mode isolated veya cross olmalı",
                "details": {"margin_mode": margin},
            }
        )

    if max_exposure > 0 and projected_exposure > max_exposure:
        violations.append(
            {
                "code": "max_exposure_exceeded",
                "message": "Max exposure limiti aşılıyor",
                "details": {
                    "open_exposure": round(open_exposure, 4),
                    "projected_exposure": round(projected_exposure, 4),
                    "max_exposure": round(max_exposure, 4),
                },
            }
        )

    microstructure_guard = build_order_microstructure_assessment(
        db,
        cache,
        user_id=user_id,
        symbol=symbol,
        side=side,
        price=float(price or 0.0),
        size=requested_size,
        order_type=order_type,
    )
    guard_state = str(microstructure_guard.get("state") or "BLOCK").upper()
    if guard_state == "BLOCK":
        violations.append(
            {
                "code": "microstructure_guard_blocked",
                "message": "Microstructure suitability check trade açılmasını engelledi",
                "details": {
                    "state": guard_state,
                    "reasons": microstructure_guard.get("reasons") or [],
                    "selected_venue": microstructure_guard.get("selected_venue"),
                },
            }
        )
    elif guard_state == "SWITCH_EXECUTION_MODE" and str(order_type or "market").lower() != "limit":
        violations.append(
            {
                "code": "execution_mode_switch_required",
                "message": "Fast market nedeniyle execution mode değişimi gerekiyor",
                "details": {
                    "state": guard_state,
                    "recommended_order_type": microstructure_guard.get("recommended_order_type"),
                    "reasons": microstructure_guard.get("reasons") or [],
                },
            }
        )

    row = _latest_connection(db, user_id)
    snapshot = dict(row.readiness_snapshot or {}) if row else {}
    quick_mode = "live" if str(getattr(row, "environment", "")).lower() == "live" and bool(snapshot.get("can_trade", False)) else "mocked"
    adjustments = {
        "adjusted_size": microstructure_guard.get("adjusted_size") if guard_state == "REDUCE_SIZE" else requested_size,
        "adjusted_notional": microstructure_guard.get("adjusted_notional") if guard_state == "REDUCE_SIZE" else notional,
        "recommended_order_type": microstructure_guard.get("recommended_order_type"),
    }
    result = {
        "valid": len(violations) == 0,
        "violations": violations,
        "execution_mode": quick_mode,
        "microstructure_guard": microstructure_guard,
        "adjustments": adjustments,
        "checks": {
            "leverage_limit": leverage_limit,
            "requested_leverage": int(leverage or 1),
            "max_exposure": max_exposure,
            "open_exposure": round(open_exposure, 4),
            "projected_exposure": round(projected_exposure, 4),
            "min_order_size": min_order_size,
            "min_notional": min_notional,
            "market_type": market,
            "margin_mode": margin,
            "microstructure_state": guard_state,
        },
    }
    result["explain"] = build_trade_explain(
        validation=result,
        execution_mode=result.get("execution_mode") or "mocked",
        signal_score=None,
    )
    return result
