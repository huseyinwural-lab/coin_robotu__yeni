from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models import PaperPosition, UserExchangeConnection
from services.audit_service import create_audit_log
from services.exchange_adapter.execution_adapter import ExchangeExecutionAdapter


def _latest_connection(db: Session, user_id: str | None) -> UserExchangeConnection | None:
    query = db.query(UserExchangeConnection)
    if user_id:
        query = query.filter(UserExchangeConnection.user_id == user_id)
    return query.order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc()).first()


def evaluate_execution_readiness(db: Session, *, user_id: str | None = None) -> dict:
    from services.live_mode_service import release_gate_view

    row = _latest_connection(db, user_id)
    snapshot = dict(row.readiness_snapshot or {}) if row else {}

    has_connection = row is not None
    connection_health = str(snapshot.get("connection_health") or "").lower()
    exchange_connection_ok = has_connection and connection_health in {"online", "degraded"}
    permissions_ok = has_connection and bool(snapshot.get("can_trade"))

    mode = "MOCKED"
    order_test_ok = False
    probe: dict = {}

    if row and str(row.exchange or "").strip().lower() == "binance" and user_id:
        validation_success = bool(snapshot.get("validation_success") or snapshot.get("is_valid"))
        can_trade_snapshot = bool(snapshot.get("can_trade"))
        last_error_reason = str(snapshot.get("last_error_reason") or "").strip().lower()

        order_test_ok = validation_success and can_trade_snapshot
        mode = "LIVE" if order_test_ok else "MOCKED"
        probe = {
            "status": "SUBMITTED" if order_test_ok else "MOCKED",
            "mocked": not order_test_ok,
            "source": "exchange_connection_snapshot",
            "last_error_reason": last_error_reason,
            "exchange": row.exchange,
            "market_type": row.market_type,
            "environment": row.environment,
            "validation_success": validation_success,
            "can_trade": can_trade_snapshot,
        }
    else:
        adapter = ExchangeExecutionAdapter()
        probe = adapter.submit_order(
            exchange=(row.exchange if row else "bybit"),
            symbol="BTCUSDT",
            side="buy",
            price=50000,
            qty=0.001,
            leverage=1,
            environment=(row.environment if row else "testnet"),
        )
        order_test_ok = str(probe.get("status") or "").upper() in {"MOCKED", "SUBMITTED"}
        mode = "MOCKED" if bool(probe.get("mocked")) else "LIVE"

    latency_ms = snapshot.get("validation_latency_ms") or snapshot.get("latency_ms") or 0
    try:
        latency_ms = max(int(float(latency_ms)), 0)
    except (TypeError, ValueError):
        latency_ms = 0

    reason_codes: list[str] = []
    if not has_connection:
        reason_codes.append("no_exchange_connection")
    if not exchange_connection_ok and has_connection:
        reason_codes.append("exchange_connection_unhealthy")
    if not permissions_ok and has_connection:
        reason_codes.append("missing_trade_permission")
    if not order_test_ok:
        reason_codes.append("order_test_failed")
        if str(probe.get("last_error_reason") or "").strip():
            reason_codes.append(str(probe.get("last_error_reason")).strip())

    if mode == "MOCKED":
        mocked_source = str(probe.get("source") or "")
        if mocked_source == "exchange_connection_snapshot":
            final_status = "READY" if (exchange_connection_ok and permissions_ok) else "BLOCKED"
        else:
            final_status = "READY" if has_connection else "BLOCKED"
        if final_status == "READY":
            reason_codes.append("mocked_mode_active")
    else:
        final_status = "READY" if (exchange_connection_ok and permissions_ok and order_test_ok) else "BLOCKED"

    try:
        gate_snapshot = release_gate_view(db, environment="prod")
    except Exception:  # pragma: no cover - runtime defensive fallback
        gate_snapshot = {}
    override_active = bool(gate_snapshot.get("override_id"))
    if final_status == "BLOCKED" and override_active:
        final_status = "READY"
        reason_codes.append("execution_guard_override_active")

    exchange_connection_status = "OK" if exchange_connection_ok else "FAIL"
    permissions_status = "OK" if permissions_ok else "FAIL"

    return {
        "exchange_connection": exchange_connection_status,
        "permissions": permissions_status,
        "latency_ms": latency_ms,
        "order_test": "OK" if order_test_ok else "FAIL",
        "mode": mode,
        "final_status": final_status,
        "mocked_flag": mode == "MOCKED",
        "override_active": override_active,
        "reason_codes": sorted(set(reason_codes)),
    }


def enforce_execution_guard_or_raise(
    db: Session,
    *,
    user_id: str,
    actor_user_id: str,
    actor_role: str,
    source: str,
) -> dict:
    readiness = evaluate_execution_readiness(db, user_id=user_id)
    if str(readiness.get("final_status") or "") == "READY":
        return readiness

    create_audit_log(
        db,
        action="EXECUTION_BLOCKED",
        entity_type="execution_guard",
        entity_id=user_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        details={
            "source": source,
            "readiness": readiness,
            "blocked_at": datetime.now(timezone.utc).isoformat(),
        },
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

    _ = (symbol, order_type, side)
    config = get_or_create_live_config(db)

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

    readiness = evaluate_execution_readiness(db, user_id=user_id)
    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "execution_mode": str(readiness.get("mode") or "MOCKED").lower(),
        "checks": {
            "leverage_limit": leverage_limit,
            "max_exposure": max_exposure,
            "open_exposure": round(open_exposure, 4),
            "projected_exposure": round(projected_exposure, 4),
            "min_order_size": min_order_size,
            "min_notional": min_notional,
            "market_type": market,
            "margin_mode": margin,
        },
    }
