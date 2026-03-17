import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.audit.audit_events import AuditEvent
from db import get_db, redis_client
from deps import get_current_user, is_admin_role
from exchange.binance_mock import BinanceMockAdapter
from models import BotProfile, ExecutionCorrectionEvent, ExecutionEvent, ExecutionMetric, User
from schemas import (
    ExecutionCorrectionCreate,
    ExecutionCorrectionResponse,
    ExchangeLifecycleEvidenceResponse,
    LifecycleProofResponse,
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
from services.quote_asset_policy import normalize_quote_symbol
from services.replay_service import get_replay_run_detail, run_replay_pipeline
from services.artifact_service import write_signed_artifact
from services.symbol_selector_service import resolve_symbol_universe

router = APIRouter(prefix="/exchange", tags=["exchange"])
adapter = BinanceMockAdapter(redis_client)


@router.get("/validate", response_model=ExchangeValidateResponse)
def validate_exchange(
    exchange: str = Query(...),
    market_type: str = Query(...),
    environment: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payload, response_code = validate_exchange_credentials_for_user(
        db,
        current_user.id,
        exchange=exchange,
        market_type=market_type,
        environment=environment,
    )
    create_audit_log(
        db,
        action="exchange_validate_checked",
        entity_type="exchange_validate",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning" if response_code >= 400 else "info",
        details={**payload, "requested_exchange": exchange, "requested_market_type": market_type, "requested_environment": environment},
    )
    if response_code >= 400:
        raise HTTPException(status_code=response_code, detail=payload)
    return payload


@router.post("/test-order", response_model=ExchangeTestOrderResponse)
def exchange_test_order(
    exchange: str | None = Query(default=None),
    market_type: str = Query(default="futures"),
    environment: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    leverage: int = Query(default=1),
    margin_mode: str = Query(default="cross"),
    position_side: str = Query(default="BOTH"),
    quantity: float | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    readiness = user_readiness_checklist(
        db,
        current_user.id,
        exchange=exchange,
        market_type=market_type,
        environment=environment,
    )
    if readiness["readiness_status"] != "ready_for_test_order":
        reason_map = {
            "missing_credentials": "invalid_key",
            "exchange_error_451": "invalid_key",
            "missing_trade_permission": "permission_denied",
            "ip_restriction": "ip_restricted",
            "insufficient_balance": "insufficient_balance",
            "exchange_unreachable": "testnet_unreachable",
            "stale_validation_snapshot": "stale_validation",
            "release_gate_forced_block": "exchange_rejected",
            "exchange_health_degraded": "testnet_unreachable",
            "settings_mismatch": "stale_validation",
        }
        failure_code = reason_map.get(
            readiness.get("last_error_reason"),
            "stale_validation" if readiness.get("is_validation_stale") else "unknown_exchange_error",
        )
        reason_message = {
            "awaiting_valid_key": "awaiting valid key",
            "blocked": readiness.get("last_error_reason") or "blocked",
        }.get(readiness["readiness_status"], readiness["readiness_status"])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": readiness["readiness_status"],
                "failure_code": failure_code,
                "exchange": readiness.get("exchange"),
                "market_type": readiness.get("market_type"),
                "environment": readiness.get("environment"),
                "symbol": symbol,
                "message": f"Binance Testnet API key ve secret doğrulanmadan gerçek test-order çalıştırılamaz. ({reason_message})",
            },
        )

    try:
        metric = run_exchange_test_order_market(
            db,
            current_user,
            exchange=readiness.get("exchange") or "binance",
            market_type=readiness.get("market_type") or "futures",
            environment=readiness.get("environment") or "testnet",
            symbol=symbol,
            leverage=leverage,
            margin_mode=margin_mode,
            position_side=position_side,
            quantity_override=quantity,
        )
    except ValueError as exc:
        known_codes = {
            "invalid_key",
            "permission_denied",
            "ip_restricted",
            "insufficient_balance",
            "exchange_rejected",
            "testnet_unreachable",
            "stale_validation",
            "unknown_exchange_error",
            "invalid_test_order_quantity",
            "quantity_below_min_qty",
            "quantity_rounds_to_zero",
            "quantity_below_min_notional",
        }
        message = str(exc)
        failure_code = next((code for code in known_codes if code in message), "unknown_exchange_error")
        create_audit_log(
            db,
            action="exchange_test_order_rejected",
            entity_type="exchange_test_order",
            entity_id=current_user.id,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            severity="warning",
            details={
                "failure_code": failure_code,
                "message": message,
                "exchange": readiness.get("exchange"),
                "market_type": readiness.get("market_type"),
                "environment": readiness.get("environment"),
                "symbol": symbol,
                "quantity": quantity,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "blocked",
                "failure_code": failure_code,
                "message": message,
                "exchange": readiness.get("exchange"),
                "market_type": readiness.get("market_type"),
                "environment": readiness.get("environment"),
                "symbol": symbol,
            },
        ) from exc

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
            "leverage_policy": (metric.raw_exchange_status or {}).get("leverage_policy", {}),
        },
    )
    leverage_policy = (metric.raw_exchange_status or {}).get("leverage_policy") or {}
    return ExchangeTestOrderResponse(
        order_id=metric.order_id,
        exchange_order_id=metric.exchange_order_id,
        client_order_id=metric.client_order_id,
        symbol=metric.symbol,
        exchange=metric.exchange,
        market_type=metric.market_type,
        environment=metric.environment,
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
        requested_leverage=leverage_policy.get("requested_leverage"),
        recommended_leverage=leverage_policy.get("recommended_leverage"),
        applied_leverage=leverage_policy.get("applied_leverage"),
        leverage_policy_mode=leverage_policy.get("leverage_policy_mode"),
        leverage_clamp_reasons=leverage_policy.get("leverage_clamp_reasons") or [],
    )


@router.post("/execution/order", response_model=ExchangeTestOrderResponse)
def exchange_execution_order(
    exchange: str | None = Query(default=None),
    market_type: str = Query(default="futures"),
    environment: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    leverage: int = Query(default=1),
    margin_mode: str = Query(default="cross"),
    position_side: str = Query(default="BOTH"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return exchange_test_order(
        exchange=exchange,
        market_type=market_type,
        environment=environment,
        symbol=symbol,
        leverage=leverage,
        margin_mode=margin_mode,
        position_side=position_side,
        current_user=current_user,
        db=db,
    )


@router.get("/readiness-checklist", response_model=UserReadinessChecklistResponse)
def exchange_readiness_checklist(
    exchange: str | None = Query(default=None),
    market_type: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return UserReadinessChecklistResponse(
        **user_readiness_checklist(
            db,
            current_user.id,
            exchange=exchange,
            market_type=market_type,
            environment=environment,
        )
    )


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


@router.post("/execution/{execution_id}/corrections", response_model=ExecutionCorrectionResponse, status_code=status.HTTP_201_CREATED)
def append_execution_correction(
    execution_id: str,
    payload: ExecutionCorrectionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    metric = db.query(ExecutionMetric).filter(ExecutionMetric.id == execution_id, ExecutionMetric.user_id == current_user.id).first()
    if metric is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution_not_found")

    row = ExecutionCorrectionEvent(
        id=str(uuid.uuid4()),
        execution_metric_id=execution_id,
        user_id=current_user.id,
        correction_type=payload.correction_type,
        reason_code=payload.reason_code,
        note=payload.note,
        patch_payload=payload.patch_payload,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/execution/{execution_id}/corrections", response_model=list[ExecutionCorrectionResponse])
def list_execution_corrections(
    execution_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(ExecutionCorrectionEvent)
        .filter(ExecutionCorrectionEvent.execution_metric_id == execution_id, ExecutionCorrectionEvent.user_id == current_user.id)
        .order_by(ExecutionCorrectionEvent.created_at.asc())
        .all()
    )


@router.post("/lifecycle-proof", response_model=LifecycleProofResponse)
def run_lifecycle_proof_pipeline(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exchange = "binance"
    market_type = "futures"
    environment = "testnet"
    timestamp = datetime.now(timezone.utc)
    proof_id = f"{current_user.id}_{timestamp.strftime('%Y%m%d%H%M%S')}"

    readiness = user_readiness_checklist(
        db,
        current_user.id,
        exchange=exchange,
        market_type=market_type,
        environment=environment,
    )

    if readiness.get("readiness_status") == "ready_for_test_order":
        try:
            metric = run_exchange_test_order_market(
                db,
                current_user,
                exchange=exchange,
                market_type=market_type,
                environment=environment,
                leverage=3,
                margin_mode="cross",
                position_side="BOTH",
                quantity_override=None,
            )
        except ValueError as exc:
            reason_codes = [str(exc)]
            blocker_payload = {
                "evidence_type": "blocked",
                "lifecycle_proof_status": "blocked",
                "proof_id": proof_id,
                "exchange": exchange,
                "market_type": market_type,
                "environment": environment,
                "reason_codes": reason_codes,
                "generated_at": timestamp.isoformat(),
            }
            exchange_artifact = write_signed_artifact(
                blocker_payload,
                artifact_type="exchange_evidence",
                filename_prefix=f"exchange_evidence_{proof_id}",
            )
            return LifecycleProofResponse(
                lifecycle_proof_status="blocked",
                evidence_type="blocked",
                exchange=exchange,
                market_type=market_type,
                environment=environment,
                reason_codes=reason_codes,
                exchange_artifact_id=exchange_artifact["artifact_id"],
                fallback_artifact_id=None,
                exchange_evidence_file=str(exchange_artifact["path"]),
                fallback_replay_evidence_file=None,
                replay_run_id=None,
                message="Live lifecycle proof denemesi başarısız",
                generated_at=timestamp,
            )
        timeline = lifecycle_evidence_for_metric(db, metric.id)
        payload = {
            "evidence_type": "live_exchange",
            "lifecycle_proof_status": "completed",
            "proof_id": proof_id,
            "exchange": exchange,
            "market_type": market_type,
            "environment": environment,
            "execution": {
                "execution_id": metric.id,
                "exchange_order_id": metric.exchange_order_id,
                "client_order_id": metric.client_order_id,
                "submitted_at": metric.submitted_at.isoformat() if metric.submitted_at else None,
                "ack_at": metric.ack_at.isoformat() if metric.ack_at else None,
                "final_at": metric.final_at.isoformat() if metric.final_at else None,
                "avg_fill_price": metric.price_avg,
                "executed_qty": metric.executed_qty,
                "execution_time_ms": metric.execution_time_ms,
                "slippage_pct": metric.slippage_pct,
                "validation_snapshot_id": metric.validation_snapshot_id,
                "state_machine_path": metric.state_machine_path,
            },
            "timeline": [
                {
                    "event_name": item.event_name,
                    "event_timestamp": item.event_timestamp.isoformat(),
                    "payload": item.payload,
                }
                for item in timeline
            ],
            "generated_at": timestamp.isoformat(),
        }
        exchange_artifact = write_signed_artifact(
            payload,
            artifact_type="exchange_evidence",
            filename_prefix=f"exchange_evidence_{proof_id}",
        )

        return LifecycleProofResponse(
            lifecycle_proof_status="completed",
            evidence_type="live_exchange",
            exchange=exchange,
            market_type=market_type,
            environment=environment,
            reason_codes=[],
            exchange_artifact_id=exchange_artifact["artifact_id"],
            fallback_artifact_id=None,
            exchange_evidence_file=str(exchange_artifact["path"]),
            fallback_replay_evidence_file=None,
            replay_run_id=None,
            message="Gerçek Binance Futures Testnet lifecycle proof tamamlandı",
            generated_at=timestamp,
        )

    reason_codes = [readiness.get("last_error_reason") or "awaiting_valid_key"]
    blocker_payload = {
        "evidence_type": "blocked",
        "lifecycle_proof_status": "blocked",
        "proof_id": proof_id,
        "exchange": exchange,
        "market_type": market_type,
        "environment": environment,
        "reason_codes": reason_codes,
        "readiness": readiness,
        "generated_at": timestamp.isoformat(),
    }
    exchange_artifact = write_signed_artifact(
        blocker_payload,
        artifact_type="exchange_evidence",
        filename_prefix=f"exchange_evidence_{proof_id}",
    )

    try:
        replay_universe = resolve_symbol_universe(
            db,
            source="crypto",
            exchange=exchange,
            market_type=market_type,
            mode="top_volume",
            selected_symbols=[],
            query="",
            quote_asset_filter="ALL",
        )
        replay_candidates = replay_universe.get("selected_symbols") or replay_universe.get("rows") or []
        replay_symbol_raw = replay_candidates[0] if replay_candidates else None
        if isinstance(replay_symbol_raw, dict):
            replay_symbol_raw = replay_symbol_raw.get("symbol")
        replay_symbol = normalize_quote_symbol(
            replay_symbol_raw,
            missing_error_code="no_allowed_quote_symbol_for_replay",
            invalid_error_code="invalid_quote_asset",
        )

        replay_run = run_replay_pipeline(
            db,
            current_user.id,
            exchange=exchange,
            market_type=market_type,
            environment=environment,
            symbol=replay_symbol,
            timeframe="15m",
            strategy_type="trend_following",
            limit=180,
        )
        run, executions = get_replay_run_detail(db, current_user.id, replay_run.id)
    except ValueError as exc:
        return LifecycleProofResponse(
            lifecycle_proof_status="blocked",
            evidence_type="blocked",
            exchange=exchange,
            market_type=market_type,
            environment=environment,
            reason_codes=reason_codes + [str(exc)],
            exchange_artifact_id=exchange_artifact["artifact_id"],
            fallback_artifact_id=None,
            exchange_evidence_file=str(exchange_artifact["path"]),
            fallback_replay_evidence_file=None,
            replay_run_id=None,
            message="Live proof bloklu; fallback replay üretimi de başarısız",
            generated_at=timestamp,
        )
    fallback_payload = {
        "evidence_type": "fallback_replay",
        "non_live_evidence": True,
        "lifecycle_proof_status": "fallback_generated",
        "proof_id": proof_id,
        "exchange": exchange,
        "market_type": market_type,
        "environment": environment,
        "replay_run": {
            "run_id": run.id,
            "candles_processed": run.candles_processed,
            "executions_count": run.executions_count,
            "filled_count": run.filled_count,
            "canceled_count": run.canceled_count,
            "avg_simulated_latency_ms": run.avg_simulated_latency_ms,
            "avg_simulated_slippage_pct": run.avg_simulated_slippage_pct,
            "status": run.status,
        },
        "lifecycle_distribution": {
            "SIM_NEW": len(executions),
            "SIM_FILLED": sum(1 for item in executions if item.status == "SIM_FILLED"),
            "SIM_CANCELED": sum(1 for item in executions if item.status == "SIM_CANCELED"),
        },
        "generated_at": timestamp.isoformat(),
    }
    fallback_artifact = write_signed_artifact(
        fallback_payload,
        artifact_type="fallback_replay_evidence",
        filename_prefix=f"fallback_replay_evidence_{proof_id}",
    )

    return LifecycleProofResponse(
        lifecycle_proof_status="fallback_generated",
        evidence_type="blocked",
        exchange=exchange,
        market_type=market_type,
        environment=environment,
        reason_codes=reason_codes,
        exchange_artifact_id=exchange_artifact["artifact_id"],
        fallback_artifact_id=fallback_artifact["artifact_id"],
        exchange_evidence_file=str(exchange_artifact["path"]),
        fallback_replay_evidence_file=str(fallback_artifact["path"]),
        replay_run_id=run.id,
        message="Live proof bloklu; fallback replay evidence üretildi",
        generated_at=timestamp,
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
    if not is_admin_role(current_user.role):
        bot_ids = db.query(BotProfile.id).filter(BotProfile.user_id == current_user.id)
        query = query.filter(ExecutionEvent.bot_profile_id.in_(bot_ids))
    return query.order_by(ExecutionEvent.created_at.desc()).limit(50).all()


@router.post("/mock/execute", response_model=ExecutionEventResponse)
def execute_mock_order(
    payload: MockOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot_query = db.query(BotProfile).filter(BotProfile.id == payload.bot_profile_id, BotProfile.is_deleted.is_(False))
    if not is_admin_role(current_user.role):
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
        action=AuditEvent.EXECUTION_SUBMIT_SUCCESS,
        entity_type="execution_event",
        entity_id=event.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning",
        details={"exchange": bot_profile.exchange, "symbol": event.symbol, "side": event.side, "MOCKED": True},
    )
    return event