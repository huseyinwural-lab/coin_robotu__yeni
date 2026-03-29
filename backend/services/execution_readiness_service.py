from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models import PaperPosition, UserExchangeConnection
from services.audit_service import create_guard_audit_event
from services.explainability_rules_service import build_trade_explain


def _latest_connection(db: Session, user_id: str | None) -> UserExchangeConnection | None:
    query = db.query(UserExchangeConnection)
    if user_id:
        query = query.filter(UserExchangeConnection.user_id == user_id)
    return query.order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc()).first()


def evaluate_execution_readiness(db: Session, *, user_id: str | None = None) -> dict:
    from services.live_mode_service import release_gate_view
    from services.pipeline.runtime import pipeline_runtime
    from core.readiness.go_live_validator import evaluate_go_live_readiness

    cache = pipeline_runtime.cache if pipeline_runtime else None
    validator = evaluate_go_live_readiness(db, cache, user_id=user_id)
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

    mode = "LIVE" if str(validator.get("execution_mode") or "").upper() == "LIVE" else "MOCKED"
    mocked_flag = mode != "LIVE"

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
    has_mocked_paths = bool(execution_proof.get("has_mocked_paths"))
    if has_mocked_paths and "EXECUTION_PROOF_MOCKED_PATHS" not in reason_codes:
        reason_codes.append("EXECUTION_PROOF_MOCKED_PATHS")

    return {
        "exchange_connection": exchange_connection_status,
        "permissions": permissions_status,
        "latency_ms": latency_ms,
        "order_test": "OK" if validator.get("execution_allowed") else "FAIL",
        "mode": mode,
        "final_status": final_status,
        "mocked_flag": mocked_flag,
        "override_active": override_active,
        "reason_codes": sorted(set(reason_codes)),
        "execution_proof": execution_proof,
        "mocked_paths": has_mocked_paths,
        "readiness_state": readiness_state,
        "execution_allowed": bool(validator.get("execution_allowed")),
        "go_live_allowed": bool(validator.get("go_live_allowed")),
    }


def enforce_execution_guard_or_raise(
    db: Session,
    *,
    user_id: str,
    actor_user_id: str,
    actor_role: str,
    source: str,
    symbol: str | None = None,
) -> dict:
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

    readiness = evaluate_execution_readiness(db, user_id=user_id)
    adjustments = {
        "adjusted_size": microstructure_guard.get("adjusted_size") if guard_state == "REDUCE_SIZE" else requested_size,
        "adjusted_notional": microstructure_guard.get("adjusted_notional") if guard_state == "REDUCE_SIZE" else notional,
        "recommended_order_type": microstructure_guard.get("recommended_order_type"),
    }
    result = {
        "valid": len(violations) == 0,
        "violations": violations,
        "execution_mode": str(readiness.get("mode") or "MOCKED").lower(),
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
