from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import get_current_user
from exchange.binance_mock import BinanceMockAdapter
from models import BotProfile, ExecutionEvent, User, UserRole
from schemas import (
    ExchangeLifecycleEvidenceResponse,
    ExchangeTestOrderResponse,
    ExchangeValidateResponse,
    ExecutionLifecycleEventResponse,
    ExecutionEventResponse,
    MockOrderRequest,
    UserReadinessChecklistResponse,
)
from services.audit_service import create_audit_log
from services.live_mode_service import (
    lifecycle_evidence_for_metric,
    latest_execution_metric,
    run_exchange_test_order_market,
    user_readiness_checklist,
    validate_exchange_credentials_for_user,
)

router = APIRouter(prefix="/exchange", tags=["exchange"])
adapter = BinanceMockAdapter(redis_client)


@router.get("/validate", response_model=ExchangeValidateResponse)
def validate_exchange(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload, response_code = validate_exchange_credentials_for_user(db, current_user.id)
    create_audit_log(
        db,
        action="exchange_validate_checked",
        entity_type="exchange_validate",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning" if response_code >= 400 else "info",
        details=payload,
    )
    if response_code >= 400:
        raise HTTPException(status_code=response_code, detail=payload)
    return payload


@router.post("/test-order", response_model=ExchangeTestOrderResponse)
def exchange_test_order(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    readiness = user_readiness_checklist(db, current_user.id)
    if readiness["readiness_status"] != "ready_for_test_order":
        reason_map = {
            "missing_credentials": "invalid_key",
            "missing_trade_permission": "permission_denied",
            "ip_restriction": "ip_restricted",
            "exchange_unreachable": "testnet_unreachable",
            "stale_validation_snapshot": "stale_validation",
            "release_gate_forced_block": "exchange_rejected",
            "exchange_health_degraded": "testnet_unreachable",
        }
        failure_code = reason_map.get(readiness.get("last_error_reason"), "stale_validation" if readiness.get("is_validation_stale") else "exchange_rejected")
        reason_message = {
            "awaiting_valid_key": "awaiting valid key",
            "blocked": readiness.get("last_error_reason") or "blocked",
        }.get(readiness["readiness_status"], readiness["readiness_status"])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": readiness["readiness_status"],
                "failure_code": failure_code,
                "message": f"Binance Testnet API key ve secret doğrulanmadan gerçek test-order çalıştırılamaz. ({reason_message})",
            },
        )

    try:
        metric = run_exchange_test_order_market(db, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="exchange_test_order_sent",
        entity_type="execution_metrics",
        entity_id=metric.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning",
        details={
            "symbol": metric.symbol,
            "status": metric.status,
            "slippage_pct": metric.slippage_pct,
            "execution_time_ms": metric.execution_time_ms,
            "state_machine_path": metric.state_machine_path,
        },
    )
    return ExchangeTestOrderResponse(
        order_id=metric.order_id,
        exchange_order_id=metric.exchange_order_id,
        client_order_id=metric.client_order_id,
        price_avg=metric.price_avg,
        executed_qty=metric.executed_qty,
        slippage_pct=metric.slippage_pct,
        execution_time_ms=metric.execution_time_ms,
        status=metric.status,
        final_status=metric.final_status,
        failure_code=metric.failure_code,
        submitted_at=metric.submitted_at,
        ack_at=metric.ack_at,
        final_at=metric.final_at,
        validation_snapshot_id=metric.validation_snapshot_id,
        raw_exchange_status=metric.raw_exchange_status,
        state_machine_path=metric.state_machine_path,
        strategy_type=metric.strategy_type,
        volatility_regime=metric.volatility_regime,
        volatility_pct=metric.volatility_pct,
    )


@router.get("/readiness-checklist", response_model=UserReadinessChecklistResponse)
def exchange_readiness_checklist(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return UserReadinessChecklistResponse(**user_readiness_checklist(db, current_user.id))


@router.get("/lifecycle-evidence/latest", response_model=ExchangeLifecycleEvidenceResponse)
def latest_lifecycle_evidence(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    metric = latest_execution_metric(db, current_user.id)
    if metric is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Henüz execution kanıtı yok")

    events = lifecycle_evidence_for_metric(db, metric.id)
    return ExchangeLifecycleEvidenceResponse(
        order_id=metric.order_id,
        exchange_order_id=metric.exchange_order_id,
        final_status=metric.final_status,
        submitted_at=metric.submitted_at,
        ack_at=metric.ack_at,
        final_at=metric.final_at,
        timeline=[
            ExecutionLifecycleEventResponse(
                event_name=item.event_name,
                event_timestamp=item.event_timestamp,
                payload=item.payload,
            )
            for item in events
        ],
    )


@router.get("/mock/state")
def get_exchange_mock_state(current_user: User = Depends(get_current_user)):
    return {
        "adapter": adapter.healthcheck(),
        "last_order": redis_client.get("exchange:binance:mock:last_order"),
        "viewer_role": current_user.role.value,
    }


@router.get("/mock/events", response_model=list[ExecutionEventResponse])
def list_mock_events(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(ExecutionEvent)
    if current_user.role != UserRole.ADMIN:
        bot_ids = db.query(BotProfile.id).filter(BotProfile.user_id == current_user.id)
        query = query.filter(ExecutionEvent.bot_profile_id.in_(bot_ids))
    return query.order_by(ExecutionEvent.created_at.desc()).limit(50).all()


@router.post("/mock/execute", response_model=ExecutionEventResponse)
def execute_mock_order(
    payload: MockOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot_query = db.query(BotProfile).filter(BotProfile.id == payload.bot_profile_id)
    if current_user.role != UserRole.ADMIN:
        bot_query = bot_query.filter(BotProfile.user_id == current_user.id)

    bot_profile = bot_query.first()
    if bot_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot profile not found")

    result = adapter.execute_mock_order(payload.symbol, payload.side, payload.quantity)
    event = ExecutionEvent(
        bot_profile_id=bot_profile.id,
        exchange=bot_profile.exchange,
        symbol=result["symbol"],
        side=result["side"],
        quantity=result["quantity"],
        mock_price=result["mock_price"],
        execution_status=result["status"],
        response_payload=result,
        note="MOCK execution only. No live order sent.",
    )

    db.add(event)
    db.commit()
    db.refresh(event)
    create_audit_log(
        db,
        action="mock_execution_sent",
        entity_type="execution_event",
        entity_id=event.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning",
        details={"exchange": bot_profile.exchange, "symbol": event.symbol, "side": event.side},
    )
    return event