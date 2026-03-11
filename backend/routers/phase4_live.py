from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, require_admin
from models import AdminControl, User
from schemas import (
    ExchangeSettingsResponse,
    ExchangeSettingsUpdateRequest,
    ExecutionQualitySummaryResponse,
    LiveActivationConfigResponse,
    LiveReadinessScoreResponse,
    LiveActivationConfigUpdate,
    LiveReadinessResponse,
    PermissionCheckRequest,
    PermissionCheckResponse,
    PermissionStatusResponse,
    ReleaseGateStatusResponse,
    TestOrderResponse,
    TestnetConnectivityResponse,
)
from services.audit_service import create_audit_log
from services.live_mode_service import (
    adapter,
    apply_config_update,
    build_readiness_report,
    compute_live_readiness_score,
    admin_permission_overview,
    exchange_settings_view,
    get_or_create_exchange_settings,
    get_or_create_live_config,
    latest_execution_quality,
    list_execution_quality,
    permission_status_for_user,
    release_gate_view,
    resolve_runtime_credentials,
    run_controlled_test_order,
    save_exchange_settings,
    trigger_close_all_positions,
    trigger_stop_all_bots,
)

router = APIRouter(prefix="/phase4", tags=["phase4_live"])


@router.get("/live-config", response_model=LiveActivationConfigResponse)
def get_live_config(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_or_create_live_config(db)


@router.put("/live-config", response_model=LiveActivationConfigResponse)
def update_live_config(
    payload: LiveActivationConfigUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    config = get_or_create_live_config(db)
    updated = apply_config_update(db, config, payload.model_dump())
    create_audit_log(
        db,
        action="phase4_live_config_updated",
        entity_type="live_activation_config",
        entity_id=updated.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"symbol_whitelist": updated.symbol_whitelist, "max_position_pct": updated.max_position_pct},
    )
    return updated


@router.get("/readiness-check", response_model=LiveReadinessResponse)
def get_live_readiness(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    config = get_or_create_live_config(db)
    env_key, env_secret, _ = resolve_runtime_credentials(None, None)
    report = build_readiness_report(config, env_key, env_secret)
    return LiveReadinessResponse(
        mode=report["mode"],
        exchange=report["exchange"],
        market_type=report["market_type"],
        checks=report["checks"],
        safe_limits=report["safe_limits"],
        docs_references=report["docs_references"],
    )


@router.post("/permission-check", response_model=PermissionCheckResponse)
def permission_check(
    payload: PermissionCheckRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    key, secret, source = resolve_runtime_credentials(payload.api_key, payload.api_secret)
    result = adapter.permission_check(key, secret)
    create_audit_log(
        db,
        action="phase4_permission_check",
        entity_type="phase4_live",
        entity_id="permission_check",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"status": result["status"], "masked_key": result["masked_key"], "source": source},
    )
    return PermissionCheckResponse(**result)


@router.get("/exchange-settings", response_model=ExchangeSettingsResponse)
def get_exchange_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings_row = get_or_create_exchange_settings(db, current_user.id)
    return ExchangeSettingsResponse(**exchange_settings_view(settings_row))


@router.put("/exchange-settings", response_model=ExchangeSettingsResponse)
def update_exchange_settings(
    payload: ExchangeSettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings_row = save_exchange_settings(
        db,
        user_id=current_user.id,
        exchange=payload.exchange,
        mode=payload.mode,
        api_key=payload.api_key,
        api_secret=payload.api_secret,
    )
    create_audit_log(
        db,
        action="phase4_exchange_settings_updated",
        entity_type="user_exchange_settings",
        entity_id=settings_row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"exchange": settings_row.exchange, "mode": settings_row.mode},
    )
    return ExchangeSettingsResponse(**exchange_settings_view(settings_row))


@router.get("/permission-status", response_model=PermissionStatusResponse)
def user_permission_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    status_payload = permission_status_for_user(db, current_user.id)
    return PermissionStatusResponse(**status_payload)


@router.post("/test-order", response_model=TestOrderResponse)
def send_first_test_order(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role.value != "user":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Test emri sadece user hesabı ile tetiklenebilir")

    try:
        log = run_controlled_test_order(db, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="phase4_test_order_sent",
        entity_type="testnet_execution",
        entity_id=log.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": log.symbol,
            "expected_price": log.expected_price,
            "fill_price": log.fill_price,
            "slippage": log.slippage,
            "execution_latency": log.execution_latency,
            "state_machine_path": log.state_machine_path,
        },
    )
    return TestOrderResponse(
        execution_id=log.id,
        symbol=log.symbol,
        strategy_direction=log.strategy_direction,
        status=log.status,
        state_machine_path=log.state_machine_path,
        expected_price=log.expected_price,
        fill_price=log.fill_price,
        slippage=log.slippage,
        execution_latency=log.execution_latency,
        execution_quality_score=log.execution_quality_score,
        release_gate_status=log.release_gate_status,
        timestamp=log.created_at.isoformat(),
    )


@router.get("/execution-quality/latest", response_model=ExecutionQualitySummaryResponse)
def latest_user_execution_quality(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    latest = latest_execution_quality(db, current_user.id)
    if latest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Henüz test emri kaydı yok")
    return ExecutionQualitySummaryResponse(
        execution_id=latest.id,
        symbol=latest.symbol,
        status=latest.status,
        expected_price=latest.expected_price,
        fill_price=latest.fill_price,
        slippage=latest.slippage,
        execution_latency=latest.execution_latency,
        execution_quality_score=latest.execution_quality_score,
        timestamp=latest.created_at,
    )


@router.get("/admin/execution-quality", response_model=list[ExecutionQualitySummaryResponse])
def admin_execution_quality(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=5, le=100),
):
    rows = list_execution_quality(db, limit=limit)
    return [
        ExecutionQualitySummaryResponse(
            execution_id=item.id,
            symbol=item.symbol,
            status=item.status,
            expected_price=item.expected_price,
            fill_price=item.fill_price,
            slippage=item.slippage,
            execution_latency=item.execution_latency,
            execution_quality_score=item.execution_quality_score,
            timestamp=item.created_at,
        )
        for item in rows
    ]


@router.get("/admin/live-readiness-score", response_model=LiveReadinessScoreResponse)
def admin_live_readiness_score(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return LiveReadinessScoreResponse(**compute_live_readiness_score(db))


@router.get("/admin/permission-status", response_model=PermissionStatusResponse)
def admin_permission_status(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return PermissionStatusResponse(**admin_permission_overview(db))


@router.get("/admin/release-gate", response_model=ReleaseGateStatusResponse)
def admin_release_gate(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return ReleaseGateStatusResponse(**release_gate_view(db))


@router.get("/testnet-connectivity", response_model=TestnetConnectivityResponse)
def testnet_connectivity(_: User = Depends(require_admin)):
    return TestnetConnectivityResponse(**adapter.ping())


@router.post("/kill-switch/stop-all-bots")
def stop_all_bots(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    trigger_stop_all_bots(db)
    create_audit_log(
        db,
        action="phase4_kill_switch_stop_all_bots",
        entity_type="kill_switch",
        entity_id="stop_all_bots",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
    )
    return {"status": "ok", "action": "stop_all_bots"}


@router.post("/kill-switch/close-all-positions")
def close_all_positions(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    trigger_close_all_positions(db)
    create_audit_log(
        db,
        action="phase4_kill_switch_close_all_positions",
        entity_type="kill_switch",
        entity_id="close_all_positions",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
    )
    return {"status": "ok", "action": "close_all_positions"}


@router.post("/kill-switch/disable-futures")
def disable_futures(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    config = get_or_create_live_config(db)
    config.disable_futures = True

    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    if control:
        control.disable_futures = True

    db.commit()
    create_audit_log(
        db,
        action="phase4_kill_switch_disable_futures",
        entity_type="kill_switch",
        entity_id="disable_futures",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
    )
    return {"status": "ok", "action": "disable_futures"}
