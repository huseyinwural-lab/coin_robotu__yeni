from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.users.user_exchange_connector import credential_fingerprint, mask_secret
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
    PermissionDriftTrendResponse,
    PermissionStatusResponse,
    ReleaseGateOverrideRequest,
    ReleaseGateOverrideResponse,
    ReleaseGateStatusResponse,
    OverrideAnalyticsResponse,
    AlertHistoryItemResponse,
    AlertPolicyResponse,
    AlertPolicyUpdate,
    ActiveAlertResponse,
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
    enforce_release_gate,
    exchange_settings_view,
    get_or_create_exchange_settings,
    get_or_create_live_config,
    get_or_create_alert_policy,
    list_release_gate_overrides,
    latest_execution_quality,
    list_execution_quality,
    override_alert_analytics,
    active_alerts,
    permission_drift_trend,
    create_release_gate_override,
    revoke_release_gate_override,
    alert_history,
    permission_status_for_user,
    release_gate_view,
    resolve_runtime_credentials,
    run_controlled_test_order,
    save_exchange_settings,
    update_alert_policy,
    trigger_close_all_positions,
    trigger_stop_all_bots,
)

router = APIRouter(prefix="/phase4", tags=["phase4_live"])
logger = logging.getLogger(__name__)


def _quality_response(item) -> ExecutionQualitySummaryResponse:
    if hasattr(item, "mid_price"):
        return ExecutionQualitySummaryResponse(
            execution_id=item.id,
            symbol=item.symbol,
            status=item.status,
            strategy_type=item.strategy_type,
            volatility_regime=item.volatility_regime,
            volatility_pct=float(item.volatility_pct or 0),
            expected_price=item.mid_price,
            fill_price=item.price_avg,
            slippage=item.slippage_pct,
            execution_latency=item.execution_time_ms,
            execution_quality_score=item.execution_quality_score,
            timestamp=item.created_at,
        )

    return ExecutionQualitySummaryResponse(
        execution_id=item.id,
        symbol=item.symbol,
        status=item.status,
        strategy_type=item.details.get("strategy_type", "unknown"),
        volatility_regime=item.details.get("volatility_regime", "low"),
        volatility_pct=float(item.details.get("volatility_pct", 0) or 0),
        expected_price=item.expected_price,
        fill_price=item.fill_price,
        slippage=item.slippage,
        execution_latency=item.execution_latency,
        execution_quality_score=item.execution_quality_score,
        timestamp=item.created_at,
    )


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
        details={
            "exchange": settings_row.exchange,
            "mode": settings_row.mode,
            "masked_api_key": mask_secret(payload.api_key),
            "credential_fingerprint": credential_fingerprint(payload.api_key, payload.api_secret),
        },
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
    enforce_release_gate(db)
    return TestOrderResponse(
        execution_id=log.id,
        symbol=log.symbol,
        strategy_direction=log.strategy_direction,
        strategy_type=log.details.get("strategy_type", "unknown"),
        volatility_regime=log.details.get("volatility_regime", "low"),
        volatility_pct=float(log.details.get("volatility_pct", 0) or 0),
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
        return ExecutionQualitySummaryResponse(
            execution_id="awaiting_execution_evidence",
            symbol="BTCUSDT",
            status="awaiting_valid_key",
            strategy_type="-",
            volatility_regime="-",
            volatility_pct=0,
            expected_price=0,
            fill_price=None,
            slippage=None,
            execution_latency=None,
            execution_quality_score=0,
            timestamp=datetime.now(timezone.utc),
        )
    return _quality_response(latest)


@router.get("/admin/execution-quality", response_model=list[ExecutionQualitySummaryResponse])
def admin_execution_quality(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=5, le=100),
):
    rows = list_execution_quality(db, limit=limit)
    return [_quality_response(item) for item in rows]


@router.get("/admin/permission-drift-trend", response_model=PermissionDriftTrendResponse)
def admin_permission_drift_trend(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    days: int = Query(default=7, ge=7, le=30),
):
    trend = permission_drift_trend(db, days=days)
    return PermissionDriftTrendResponse(**trend)


@router.get("/admin/live-readiness-score", response_model=LiveReadinessScoreResponse)
def admin_live_readiness_score(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    enforce_release_gate(db)
    return LiveReadinessScoreResponse(**compute_live_readiness_score(db))


@router.get("/admin/permission-status", response_model=PermissionStatusResponse)
def admin_permission_status(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return PermissionStatusResponse(**admin_permission_overview(db))


@router.get("/admin/release-gate", response_model=ReleaseGateStatusResponse)
def admin_release_gate(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    environment: str = Query(default="prod"),
):
    env = str(environment or "prod").strip().lower()
    if env not in {"prod", "stage"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="environment must be stage or prod")

    try:
        payload = enforce_release_gate(db, environment=env)
    except Exception as exc:  # pragma: no cover - runtime defensive guard
        db.rollback()
        logger.exception("release_gate_evaluation_failed", extra={"environment": env, "error": str(exc)[:300]})
        payload = {
            "status": "BLOCKED",
            "reasons": ["release_gate_runtime_error"],
            "fail_reasons": ["release_gate_runtime_error"],
            "warning_reasons": [],
            "live_activation": "disabled",
            "environment": env,
            "reason_code": "release_gate_runtime_error",
            "override_active": False,
            "override_expires_at": None,
            "override_id": None,
        }
    return ReleaseGateStatusResponse(**payload)


@router.post("/admin/release-gate/override", response_model=ReleaseGateOverrideResponse)
def create_gate_override(
    payload: ReleaseGateOverrideRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = create_release_gate_override(
            db,
            admin_user_id=current_admin.id,
            reason_code=payload.reason_code,
            reason_note=payload.reason_note,
            ttl_minutes=payload.ttl_minutes,
            deploy_context=payload.deploy_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="release_gate_override_created",
        entity_type="release_gate_override",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"reason_code": row.reason_code, "expires_at": row.expires_at.isoformat()},
    )
    return ReleaseGateOverrideResponse(
        override_id=row.id,
        admin_user_id=row.admin_user_id,
        reason_code=row.reason_code,
        reason_note=row.reason_note,
        release_gate_snapshot=row.release_gate_snapshot,
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        deploy_context=row.deploy_context,
        used_deploy_count=row.used_deploy_count,
    )


@router.post("/admin/release-gate/override/{override_id}/revoke", response_model=ReleaseGateOverrideResponse)
def revoke_gate_override(
    override_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = revoke_release_gate_override(db, override_id=override_id, admin_user_id=current_admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="release_gate_override_revoked",
        entity_type="release_gate_override",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"revoked_at": row.revoked_at.isoformat() if row.revoked_at else None},
    )
    return ReleaseGateOverrideResponse(
        override_id=row.id,
        admin_user_id=row.admin_user_id,
        reason_code=row.reason_code,
        reason_note=row.reason_note,
        release_gate_snapshot=row.release_gate_snapshot,
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        deploy_context=row.deploy_context,
        used_deploy_count=row.used_deploy_count,
    )


@router.get("/admin/release-gate/overrides", response_model=list[ReleaseGateOverrideResponse])
def gate_override_history(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=30, ge=5, le=100),
):
    rows = list_release_gate_overrides(db, limit=limit)
    return [
        ReleaseGateOverrideResponse(
            override_id=row.id,
            admin_user_id=row.admin_user_id,
            reason_code=row.reason_code,
            reason_note=row.reason_note,
            release_gate_snapshot=row.release_gate_snapshot,
            created_at=row.created_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            deploy_context=row.deploy_context,
            used_deploy_count=row.used_deploy_count,
        )
        for row in rows
    ]


@router.get("/admin/override-analytics", response_model=OverrideAnalyticsResponse)
def gate_override_analytics(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    days: int = Query(default=7, ge=7, le=30),
):
    return OverrideAnalyticsResponse(**override_alert_analytics(db, days=days))


@router.get("/admin/alert-history", response_model=list[AlertHistoryItemResponse])
def gate_alert_history(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=30, ge=10, le=100),
):
    return [AlertHistoryItemResponse(**item) for item in alert_history(db, limit=limit)]


@router.get("/admin/alert-policy", response_model=AlertPolicyResponse)
def gate_alert_policy(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    policy = get_or_create_alert_policy(db)
    return AlertPolicyResponse(
        admin_notification_enabled=policy.admin_notification_enabled,
        ops_webhook_url=policy.ops_webhook_url,
        monitoring_alert_log_enabled=policy.monitoring_alert_log_enabled,
        execution_quality_warning_threshold=policy.execution_quality_warning_threshold,
        execution_quality_critical_threshold=policy.execution_quality_critical_threshold,
        permission_drift_warning_per_day=policy.permission_drift_warning_per_day,
        permission_drift_critical_per_day=policy.permission_drift_critical_per_day,
        gate_override_warning_per_day=policy.gate_override_warning_per_day,
        gate_override_critical_per_day=policy.gate_override_critical_per_day,
    )


@router.put("/admin/alert-policy", response_model=AlertPolicyResponse)
def gate_alert_policy_update(
    payload: AlertPolicyUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    policy = update_alert_policy(db, payload.model_dump())
    return AlertPolicyResponse(
        admin_notification_enabled=policy.admin_notification_enabled,
        ops_webhook_url=policy.ops_webhook_url,
        monitoring_alert_log_enabled=policy.monitoring_alert_log_enabled,
        execution_quality_warning_threshold=policy.execution_quality_warning_threshold,
        execution_quality_critical_threshold=policy.execution_quality_critical_threshold,
        permission_drift_warning_per_day=policy.permission_drift_warning_per_day,
        permission_drift_critical_per_day=policy.permission_drift_critical_per_day,
        gate_override_warning_per_day=policy.gate_override_warning_per_day,
        gate_override_critical_per_day=policy.gate_override_critical_per_day,
    )


@router.get("/admin/active-alerts", response_model=list[ActiveAlertResponse])
def gate_active_alerts(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [ActiveAlertResponse(**item) for item in active_alerts(db)]


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
