from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.users.user_exchange_connector import credential_fingerprint, mask_secret
from db import get_db, redis_client
from deps import get_current_user, require_admin, require_super_admin
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
    ProductionGateChecklistUpdateRequest,
    ProductionGateCheckCompareResponse,
    ProductionGateCheckHistoryResponse,
    ProductionGateApiKeyTestRunRequest,
    ProductionGateExportResponse,
    ProductionGateModeTransitionRequest,
    ProductionGateOpsOverviewResponse,
    ProductionGateOrderScenarioRunRequest,
    ProductionGateOverrideAnalyticsResponse,
    ProductionGateOverrideCreateRequest,
    ProductionGateStateUpdateRequest,
    ProductionGateStatusResponse,
    ProductionGateTimelineResponse,
)
from services.audit_service import create_audit_log
from services.execution_mode_control_service import get_execution_mode, normalize_execution_mode, switch_execution_mode
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
    resolve_runtime_credentials,
    run_controlled_test_order,
    save_exchange_settings,
    update_alert_policy,
    trigger_close_all_positions,
    trigger_stop_all_bots,
)
from services.production_gate_service import (
    build_production_gate_export,
    create_production_gate_override,
    enforce_production_gate_or_raise,
    get_production_gate_checks_compare,
    get_production_gate_checks_history,
    get_production_gate_status,
    get_production_gate_timeline,
    get_production_gate_ops_overview,
    get_production_gate_override_analytics,
    rerun_production_gate_checks,
    revoke_production_gate_override,
    run_history_cleanup_job,
    run_order_scenario_matrix,
    run_production_gate_api_key_tests,
    set_production_gate_state,
    update_production_gate_hardening_config,
    update_production_gate_checklist_item,
    validate_production_gate_analytics_cross_check,
)
from services.faz56_live_expansion_service import (
    advance_expansion_step,
    apply_auto_rollback_if_needed,
    build_closure_proof_bundle,
    build_operator_cheat_sheet,
    compute_live_session_metrics,
    finalize_closure_artifact,
    generate_daily_live_report_artifact,
    get_or_create_expansion_state,
    latest_daily_live_report,
)

router = APIRouter(prefix="/phase4", tags=["phase4_live"])
logger = logging.getLogger(__name__)
MODE_TRANSITION_PHRASES = {
    "LIVE": "SWITCH TO LIVE",
    "TESTNET": "SWITCH TO TESTNET",
    "SIM": "SWITCH TO SIM",
    "PAPER": "SWITCH TO PAPER",
    "MOCK": "SWITCH TO MOCK",
}


class Faz56ActionRequest(BaseModel):
    reason: str = Field(default="faz56_progress", min_length=3, max_length=240)
    timezone: str = Field(default="Europe/Istanbul", min_length=3, max_length=64)


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
    if bool(payload.live_mode_enabled) or bool(payload.trading_enabled):
        enforce_production_gate_or_raise(
            db,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            action_type="phase4_live_config_enable",
            reason_text="phase4_live_config_enable",
        )

    config = get_or_create_live_config(db)
    updated = apply_config_update(db, config, payload.model_dump())
    create_audit_log(
        db,
        action="phase4_live_config_updated",
        entity_type="live_activation_config",
        entity_id=updated.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "symbol_whitelist": updated.symbol_whitelist,
            "max_position_pct": updated.max_position_pct,
            "canary_enabled": bool(updated.canary_enabled),
            "canary_symbols": list(updated.canary_symbols or []),
            "canary_max_capital_usdt": float(updated.canary_max_capital_usdt or 0),
            "canary_max_positions": int(updated.canary_max_positions or 0),
        },
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
    try:
        enforce_release_gate(db)
        return LiveReadinessScoreResponse(**compute_live_readiness_score(db))
    except Exception as exc:  # pragma: no cover - runtime defensive guard
        db.rollback()
        logger.exception("live_readiness_score_runtime_error", extra={"error": str(exc)[:300]})
        payload = compute_live_readiness_score(db)
        blockers = list(dict.fromkeys([*(payload.get("critical_blockers") or []), "release_gate_runtime_error"]))
        payload["critical_blockers"] = blockers
        payload["release_gate_status"] = "BLOCKED"
        payload["live_activation"] = "disabled"
        payload["readiness_score"] = min(float(payload.get("readiness_score") or 0), 80.0)
        return LiveReadinessScoreResponse(**payload)


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
            "reason_codes": ["release_gate_runtime_error"],
            "blocking_metrics": {"runtime_error": True},
            "live_activation": "disabled",
            "environment": env,
            "reason_code": "release_gate_runtime_error",
            "deploy_enable_flag": False,
            "override_active": False,
            "override_expires_at": None,
            "override_id": None,
        }
    if str(payload.get("status") or "") == "BLOCKED":
        reason_codes = list(payload.get("reason_codes") or [])
        if not reason_codes:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="INVALID_RELEASE_GATE_CONTRACT")
        payload["blocking_metrics"] = payload.get("blocking_metrics") or payload.get("metrics") or {}

    return ReleaseGateStatusResponse(**payload)


@router.post("/admin/release-gate/override", response_model=ReleaseGateOverrideResponse)
def create_gate_override(
    payload: ReleaseGateOverrideRequest,
    current_admin: User = Depends(require_super_admin),
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
    current_admin: User = Depends(require_super_admin),
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


@router.get("/admin/production-gate", response_model=ProductionGateStatusResponse)
def admin_production_gate_status(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    refresh_checks: bool = Query(default=False),
):
    return ProductionGateStatusResponse(**get_production_gate_status(db, refresh_checks=bool(refresh_checks), audit_limit=40))


@router.get("/admin/production-gate/ops-overview", response_model=ProductionGateOpsOverviewResponse)
def admin_production_gate_ops_overview(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ProductionGateOpsOverviewResponse(**get_production_gate_ops_overview(db, mode_history_limit=60))


@router.post("/admin/production-gate/api-key-tests/run", response_model=ProductionGateOpsOverviewResponse)
def admin_production_gate_run_api_key_tests(
    request: ProductionGateApiKeyTestRunRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    run_production_gate_api_key_tests(
        db,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        connection_id=request.connection_id,
        exchange=request.exchange,
    )
    return ProductionGateOpsOverviewResponse(**get_production_gate_ops_overview(db, mode_history_limit=60))


@router.post("/admin/production-gate/order-scenarios/rerun", response_model=ProductionGateOpsOverviewResponse)
def admin_production_gate_run_order_scenarios(
    request: ProductionGateOrderScenarioRunRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        run_order_scenario_matrix(
            db,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            scenario_key=request.scenario_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProductionGateOpsOverviewResponse(**get_production_gate_ops_overview(db, mode_history_limit=60))


@router.get("/admin/production-gate/mode-history")
def admin_production_gate_mode_history(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=40, ge=5, le=200),
):
    payload = get_production_gate_ops_overview(db, mode_history_limit=limit)
    return payload.get("mode_history") or []


@router.get("/admin/production-gate/checks/history", response_model=ProductionGateCheckHistoryResponse)
def admin_production_gate_checks_history(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    check_key: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    status_filter: str | None = Query(default=None),
    limit: int = Query(default=200, ge=10, le=1000),
):
    try:
        from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
        to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_date_range") from exc

    payload = get_production_gate_checks_history(
        db,
        check_key=check_key,
        date_from=from_dt,
        date_to=to_dt,
        status_filter=status_filter,
        limit=limit,
    )
    return ProductionGateCheckHistoryResponse(**payload)


@router.get("/admin/production-gate/checks/compare", response_model=ProductionGateCheckCompareResponse)
def admin_production_gate_checks_compare(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    check_key: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=200, ge=10, le=1000),
):
    try:
        from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
        to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_date_range") from exc

    payload = get_production_gate_checks_compare(
        db,
        check_key=check_key,
        date_from=from_dt,
        date_to=to_dt,
        limit=limit,
    )
    return ProductionGateCheckCompareResponse(**payload)


@router.get("/admin/production-gate/override-analytics", response_model=ProductionGateOverrideAnalyticsResponse)
def admin_production_gate_override_analytics(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = get_production_gate_override_analytics(db, limit_timeline=200)
    return ProductionGateOverrideAnalyticsResponse(**payload)


@router.get("/admin/production-gate/timeline", response_model=ProductionGateTimelineResponse)
def admin_production_gate_timeline(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    categories: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=300, ge=20, le=2000),
):
    try:
        from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
        to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_date_range") from exc

    category_list = [item.strip().lower() for item in str(categories or "").split(",") if item.strip()]
    payload = get_production_gate_timeline(
        db,
        categories=category_list,
        date_from=from_dt,
        date_to=to_dt,
        limit=limit,
    )
    return ProductionGateTimelineResponse(**payload)


@router.patch("/admin/production-gate/hardening-config")
def admin_production_gate_update_hardening_config(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    config = update_production_gate_hardening_config(
        db,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        payload=payload,
    )
    return {"status": "ok", "hardening_config": config}


@router.post("/admin/production-gate/history/cleanup")
def admin_production_gate_history_cleanup(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    force: bool = Query(default=False),
):
    payload = run_history_cleanup_job(db, force=bool(force))
    create_audit_log(
        db,
        action="PRODUCTION_GATE_HISTORY_CLEANUP",
        entity_type="production_gate",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "previous_state": "N/A",
            "next_state": "N/A",
            "reason_code": "HISTORY_CLEANUP",
            "reason_text": "manual_cleanup_trigger",
            "expiry": None,
            "cleanup_payload": payload,
        },
    )
    return payload


@router.get("/admin/production-gate/analytics/cross-check")
def admin_production_gate_analytics_cross_check(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = validate_production_gate_analytics_cross_check(db)
    if not bool(payload.get("is_consistent")):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=payload)
    return payload


@router.get("/admin/production-gate/system/cross-check")
def admin_production_gate_system_cross_check(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = validate_production_gate_analytics_cross_check(db)
    if not bool(payload.get("is_consistent")):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=payload)
    return payload


@router.post("/admin/production-gate/checks/rerun", response_model=ProductionGateStatusResponse)
def admin_production_gate_rerun_all(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = rerun_production_gate_checks(
        db,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        check_key=None,
    )
    return ProductionGateStatusResponse(**payload)


@router.post("/admin/production-gate/checks/{check_key}/rerun", response_model=ProductionGateStatusResponse)
def admin_production_gate_rerun_single(
    check_key: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        payload = rerun_production_gate_checks(
            db,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            check_key=check_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProductionGateStatusResponse(**payload)


@router.patch("/admin/production-gate/checklist/{item_key}", response_model=ProductionGateStatusResponse)
def admin_production_gate_update_checklist(
    item_key: str,
    request: ProductionGateChecklistUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        payload = update_production_gate_checklist_item(
            db,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            item_key=item_key,
            checked=bool(request.checked),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProductionGateStatusResponse(**payload)


@router.post("/admin/production-gate/state", response_model=ProductionGateStatusResponse)
def admin_production_gate_set_state(
    request: ProductionGateStateUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        payload = set_production_gate_state(
            db,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            target_state=request.target_state,
            reason_code=request.reason_code,
            reason_text=request.reason_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProductionGateStatusResponse(**payload)


@router.post("/admin/production-gate/override", response_model=ProductionGateStatusResponse)
def admin_production_gate_create_override(
    request: ProductionGateOverrideCreateRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        payload = create_production_gate_override(
            db,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            reason_code=request.reason_code,
            reason_text=request.reason_text,
            ttl_minutes=int(request.ttl_minutes),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProductionGateStatusResponse(**payload)


@router.post("/admin/production-gate/override/{override_id}/revoke", response_model=ProductionGateStatusResponse)
def admin_production_gate_revoke_override(
    override_id: str,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        payload = revoke_production_gate_override(
            db,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            override_id=override_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProductionGateStatusResponse(**payload)


@router.post("/admin/production-gate/mode-transition")
def admin_production_gate_mode_transition(
    request: ProductionGateModeTransitionRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    requested_mode = str(request.target_mode or "").strip().upper()
    target_mode = normalize_execution_mode(requested_mode)
    if target_mode is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_mode")

    expected_phrase = MODE_TRANSITION_PHRASES[requested_mode]
    if str(request.confirmation_phrase or "").strip().upper() != expected_phrase:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_confirmation_phrase", "expected_phrase": expected_phrase},
        )

    previous_mode = get_execution_mode(db, redis_client)
    if target_mode == "LIVE":
        enforce_production_gate_or_raise(
            db,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            action_type="production_gate_mode_transition",
            reason_text=request.reason_text,
        )

    try:
        switch_payload = switch_execution_mode(
            db,
            redis_client,
            mode=target_mode,
            reason=request.reason_text,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="PRODUCTION_GATE_MODE_TRANSITION",
        entity_type="production_gate",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if target_mode == "LIVE" else "info",
        details={
            "previous_state": previous_mode,
            "next_state": target_mode,
            "requested_mode": requested_mode,
            "reason_code": "MODE_TRANSITION",
            "reason_text": request.reason_text,
            "expiry": None,
        },
    )
    gate_payload = get_production_gate_status(db, refresh_checks=False, audit_limit=40)
    return {
        "status": "ok",
        "transition": switch_payload,
        "gate": gate_payload,
    }


@router.get("/admin/production-gate/export", response_model=ProductionGateExportResponse)
def admin_production_gate_export(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    scope: str = Query(default="full"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    try:
        from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
        to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_export_date_format") from exc

    payload = build_production_gate_export(db, date_from=from_dt, date_to=to_dt, scope=scope)
    return ProductionGateExportResponse(exported_at=payload["exported_at"], gate=payload["gate"])


@router.get("/admin/production-gate/export/raw")
def admin_production_gate_export_raw(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    scope: str = Query(default="full"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    try:
        from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
        to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_export_date_format") from exc

    payload = build_production_gate_export(db, date_from=from_dt, date_to=to_dt, scope=scope)
    return payload


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


@router.get("/faz56/expansion/state")
def faz56_expansion_state(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    timezone_name: str = Query(default="Europe/Istanbul"),
):
    _ = db
    return get_or_create_expansion_state(redis_client, timezone_name=timezone_name)


@router.post("/faz56/expansion/advance")
def faz56_expansion_advance(
    payload: Faz56ActionRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return advance_expansion_step(
        db,
        redis_client,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        reason=payload.reason,
        timezone_name=payload.timezone,
    )


@router.get("/faz56/live-session-metrics")
def faz56_live_session_metrics(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    window_minutes: int = Query(default=120, ge=30, le=1440),
):
    return compute_live_session_metrics(db, window_minutes=window_minutes)


@router.post("/faz56/auto-rollback/evaluate")
def faz56_auto_rollback_evaluate(
    payload: Faz56ActionRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    metrics = compute_live_session_metrics(db, window_minutes=120)
    rollback = apply_auto_rollback_if_needed(
        db,
        redis_client,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        reason=payload.reason,
        metrics=metrics,
    )
    return {"metrics": metrics, "rollback": rollback}


@router.post("/faz56/daily-report/generate")
def faz56_generate_daily_report(
    payload: Faz56ActionRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return generate_daily_live_report_artifact(db, redis_client, timezone_name=payload.timezone)


@router.get("/faz56/daily-report/latest")
def faz56_daily_report_latest(_: User = Depends(require_admin)):
    return latest_daily_live_report(redis_client)


@router.get("/faz56/closure/proofs")
def faz56_closure_proofs(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    timezone_name: str = Query(default="Europe/Istanbul"),
):
    return build_closure_proof_bundle(db, redis_client, timezone_name=timezone_name)


@router.post("/faz56/closure/finalize")
def faz56_closure_finalize(
    payload: Faz56ActionRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return finalize_closure_artifact(db, redis_client, timezone_name=payload.timezone)


@router.get("/faz56/operator-cheat-sheet")
def faz56_operator_cheat_sheet(_: User = Depends(require_admin)):
    return build_operator_cheat_sheet()
