import csv
import io
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin, require_super_admin
from models import (
    DecisionTraceCold,
    DecisionTraceHot,
    ExecutionIntent,
    ExecutionIntentEvent,
    FailedEvent,
    StrategyPromotionRequest,
    StrategyVersionLifecycle,
    StrategyVersion,
    User,
)
from schemas import (
    DecisionContextInput,
    DecisionResultResponse,
    ExecutionIntentEventResponse,
    ExecutionIntentResponse,
    RegimeEvaluationResponse,
    RegimeSnapshotResponse,
    RiskOrchestratorAlertResponse,
    RiskOrchestratorApprovalAssignRequest,
    RiskOrchestratorApprovalDecisionRequest,
    RiskOrchestratorApprovalQueueItemResponse,
    RiskOrchestratorApprovalRequestResponse,
    RiskOrchestratorAnalyticsResponse,
    RiskOrchestratorDecisionTraceResponse,
    RiskOrchestratorDecisionIntelligenceResponse,
    RiskOrchestratorForceApplyRequest,
    RiskOrchestratorOperationalDashboardResponse,
    RiskOrchestratorRejectInsightsResponse,
    RiskOrchestratorPolicyApplyResponse,
    RiskOrchestratorRevertSimulationResponse,
    RiskOrchestratorAuditTimelineItemResponse,
    RiskOrchestratorAutoTriggerLogResponse,
    RiskOrchestratorControlActionRequest,
    RiskOrchestratorControlActionResponse,
    RiskOrchestratorInterventionRequest,
    RiskOrchestratorInterventionResponse,
    RiskOrchestratorManualOverrideCreateRequest,
    RiskOrchestratorManualOverrideDeactivateRequest,
    RiskOrchestratorManualOverrideResponse,
    RiskOrchestratorOpenPositionResponse,
    RiskOrchestratorPolicyApplyRequest,
    RiskOrchestratorPolicyChangeRequestResponse,
    RiskOrchestratorPolicyHistoryResponse,
    RiskOrchestratorPolicyResponse,
    RiskOrchestratorPolicyRevertRequest,
    RiskOrchestratorPolicySimulationRequest,
    RiskOrchestratorPolicySimulationResponse,
    RiskOrchestratorPolicyUpdate,
    RiskOrchestratorPolicyVersionResponse,
    RiskOrchestratorRejectDetailResponse,
    RiskOrchestratorRejectResponse,
    RiskOrchestratorStatusResponse,
    RiskOrchestratorSupervisorResponse,
    RuntimeDispatchRequest,
    RuntimeDispatchResponse,
    RuntimeEventEnvelopeResponse,
    RuntimeQuarantineEventResponse,
    RuntimeStuckIntentResponse,
    StrategyDefinitionCreate,
    StrategyDefinitionResponse,
    StrategyDetailResponse,
    StrategyRegimeBindingCreate,
    StrategyRegimeBindingResponse,
    StrategyRegimeOverviewResponse,
    StrategyVersionCreate,
    StrategyVersionResponse,
)
from services.audit_service import create_audit_log
from services.decision_kernel_service import build_context_hash, build_decision_hash, evaluate_decision_context
from services.regime_classifier_service import classify_regime, is_regime_allowed, persist_regime_snapshot
from services.risk_orchestrator_service import (
    assign_policy_approval_request,
    build_decision_intelligence,
    build_operational_dashboard,
    build_reject_insights,
    force_apply_approval_request,
    apply_revert_from_simulation,
    approve_policy_approval_request,
    apply_policy_from_simulation,
    build_audit_timeline,
    list_decision_traces,
    list_policy_queue,
    process_approval_escalations,
    list_policy_approval_requests,
    build_status_snapshot,
    create_manual_override,
    deactivate_manual_override,
    evaluate_pre_trade,
    export_decision_traces,
    execute_control_action,
    execute_position_intervention,
    get_or_create_policy,
    get_reject_detail,
    list_auto_trigger_logs,
    list_manual_overrides,
    list_open_positions,
    list_policy_history,
    list_risk_alerts,
    list_risk_rejects,
    reject_policy_approval_request,
    run_in_trade_supervisor,
    simulate_revert_to_version,
    simulate_policy_change,
)
from services.runtime_execution_service import dispatch_decision_result, process_submission_event_once
from services.runtime_ops_service import (
    dismiss_quarantined_event,
    list_quarantined_events,
    list_stuck_intents,
    mark_quarantined_failed,
    perform_recovery_action,
    replay_quarantined_event,
)
from services.risk_orchestrator_analytics_service import compute_risk_analytics
from services.strategy_domain_service import (
    activate_strategy_version,
    approve_strategy_promotion_request,
    archive_strategy,
    bulk_archive_strategies,
    bulk_export_audit_snapshot,
    bulk_tag_strategies,
    bulk_validate_strategies,
    compare_strategy_versions,
    create_strategy_definition,
    create_strategy_promotion_request,
    create_strategy_regime_binding,
    create_strategy_version,
    evaluate_strategy_context_standard,
    export_strategy_audit_history,
    generate_strategy_execution_preview,
    get_active_strategy_set,
    get_latest_regime_binding,
    get_strategy_promotion_readiness,
    get_strategy,
    get_strategy_filter_options,
    get_strategy_regime_bindings,
    get_strategy_regime_overview,
    get_strategy_timeline,
    get_strategy_version_drift_alerts,
    get_strategy_version_diff,
    get_strategy_version_false_signal_report,
    get_strategy_version_metrics,
    get_strategy_version_metrics_timeseries,
    get_strategy_rollback_chain,
    get_version,
    list_strategy_definitions_filtered,
    list_strategy_promotion_requests,
    list_strategy_version_lifecycles,
    reject_strategy_promotion_request,
    replay_strategy_context,
    resolve_strategy_binding_preview,
    rollback_strategy_version,
    set_strategy_rollout_stage,
    validate_strategy_version_config,
)
from services.unified_risk_core_service import (
    benchmark_compare,
    benchmark_report,
    calibrate_thresholds,
    drift_status,
    export_replay_timeline,
    get_calibrated_thresholds,
    get_scenario_pack_library,
    jira_epic_breakdown,
    list_risk_snapshot_manifest,
    list_rulesets,
    run_replay_timeline,
    run_policy_benchmark,
    run_unified_risk_orchestrator,
    simulate_pre_trade_risk,
    policy_decay,
    policy_leaderboard,
    policy_portfolio,
    policy_trends,
    get_policy_history,
    upsert_scenario_pack,
)



def _block_admin_risk_orchestrator_writes(request: Request) -> None:
    path = str(request.url.path or "")
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    if "/strategy-domain/admin/risk-orchestrator" not in path:
        if "/strategy-domain/admin/runtime/dispatch" in path or "/strategy-domain/admin/runtime/worker/run-once" in path:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={
                    "code": "PURE_LIVE_410",
                    "message": "Admin runtime tetikleme aksiyonları user tarafına taşındı.",
                },
            )
        return
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "PURE_LIVE_410",
            "message": "Admin risk orchestrator yazma aksiyonları user tarafına taşındı.",
        },
    )


router = APIRouter(
    prefix="/strategy-domain",
    tags=["strategy_domain"],
    dependencies=[Depends(_block_admin_risk_orchestrator_writes)],
)


def _build_reject_payload(context_payload: dict, *, strategy_version_id: str, reason_codes: list[str]) -> dict:
    payload = {
        "action": "REJECT",
        "order_intent": {"intent_type": "REJECT", "symbol": context_payload.get("symbol")},
        "size": 0.0,
        "price_reference": {
            "source": "market_snapshot",
            "value": context_payload.get("market_snapshot", {}).get("last_price"),
        },
        "confidence": 0.0,
        "risk_score": 1.0,
        "reason_codes": reason_codes,
        "strategy_version_id": strategy_version_id,
        "context_hash": build_context_hash(context_payload),
    }
    payload["decision_hash"] = build_decision_hash(payload)
    return payload


def _evaluate_regime_gate(
    *,
    db: Session,
    context_payload: dict,
    strategy_id: str,
    strategy_version_id: str,
    actor: User,
) -> tuple[RegimeSnapshotResponse, bool, str | None, str | None]:
    snapshot_payload = classify_regime(context_payload)
    snapshot_row = persist_regime_snapshot(strategy_version_id=strategy_version_id, snapshot_payload=snapshot_payload)
    db.add(snapshot_row)
    db.commit()
    db.refresh(snapshot_row)

    binding = get_latest_regime_binding(db, strategy_version_id)
    allowed = is_regime_allowed(binding, snapshot_payload["regime_label"])
    reason_code = None
    if not allowed:
        reason_code = "regime_not_allowed"
        create_audit_log(
            db,
            action="strategy_regime_gated_reject",
            entity_type="strategy_definition",
            entity_id=strategy_id,
            actor_user_id=actor.id,
            actor_role=actor.role.value,
            severity="warning",
            details={
                "strategy_id": strategy_id,
                "strategy_version_id": strategy_version_id,
                "regime_snapshot_id": snapshot_row.regime_snapshot_id,
                "regime_label": snapshot_row.regime_label,
                "reason_code": reason_code,
            },
        )

    return RegimeSnapshotResponse.model_validate(snapshot_row), allowed, reason_code, binding.binding_id if binding else None


def _policy_response(policy) -> RiskOrchestratorPolicyResponse:
    return RiskOrchestratorPolicyResponse(
        reference_equity_usd=policy.reference_equity_usd,
        account_max_notional_pct=policy.account_max_notional_pct,
        symbol_max_notional_pct=policy.symbol_max_notional_pct,
        strategy_max_concurrent_positions=policy.strategy_max_concurrent_positions,
        strategy_cooldown_seconds=policy.strategy_cooldown_seconds,
        max_order_frequency_per_min=policy.max_order_frequency_per_min,
        max_order_burst_per_10s=policy.max_order_burst_per_10s,
        daily_loss_limit_pct=policy.daily_loss_limit_pct,
        duplicate_suppression_window_seconds=policy.duplicate_suppression_window_seconds,
        policy_version=int(getattr(policy, "policy_version", 1) or 1),
        updated_at=policy.updated_at,
    )


def _sla_snapshot(item) -> tuple[int, str]:
    now_ts = datetime.now(timezone.utc)
    remaining = int((item.expires_at - now_ts).total_seconds())
    if remaining <= 0:
        return 0, "expired"
    if remaining <= 2 * 60:
        return remaining, "critical"
    if remaining <= 5 * 60:
        return remaining, "approaching"
    return remaining, "safe"


def _approval_queue_item_response(item) -> RiskOrchestratorApprovalQueueItemResponse:
    remaining, stage = _sla_snapshot(item)
    return RiskOrchestratorApprovalQueueItemResponse(
        **RiskOrchestratorApprovalRequestResponse.model_validate(item).model_dump(),
        sla_remaining_seconds=remaining,
        sla_stage=stage,
    )


class StrategyVersionValidationRequest(BaseModel):
    force: bool = Field(default=False)


class StrategyVersionDryRunRequest(BaseModel):
    context_snapshot: dict | None = None


class StrategyVersionDiffRequest(BaseModel):
    from_version_id: str
    to_version_id: str


class StrategyRollbackRequest(BaseModel):
    target_version_id: str
    reason: str = "manual_rollback"


class StrategyReplayRequest(BaseModel):
    strategy_version_id: str
    context_snapshot: dict


class StrategyCompareRequest(BaseModel):
    version_a_id: str
    version_b_id: str
    context_snapshot: dict


class StrategyPromoteRequest(BaseModel):
    strategy_version_id: str
    request_note: str = ""
    require_validation: bool = True
    require_dry_run: bool = True
    requested_stage: str | None = None


class StrategyPromotionDecisionRequest(BaseModel):
    note: str = ""


class StrategyRolloutStageRequest(BaseModel):
    rollout_stage: str | None = None


class StrategyExecutionPreviewRequest(BaseModel):
    context_snapshot: dict


class StrategyBulkArchiveRequest(BaseModel):
    strategy_ids: list[str]


class StrategyBulkValidateRequest(BaseModel):
    strategy_ids: list[str]


class StrategyBulkDryRunRequest(BaseModel):
    strategy_ids: list[str]
    context_snapshot: dict | None = None


class StrategyBulkTagRequest(BaseModel):
    strategy_ids: list[str]
    category: str | None = None
    tags: list[str] | None = None
    owner_name: str | None = None


class StrategyBulkAuditExportRequest(BaseModel):
    strategy_ids: list[str]
    format_type: str = "json"
    limit_per_strategy: int = 1000


def _lifecycle_response(item: StrategyVersionLifecycle) -> dict:
    return {
        "lifecycle_id": item.lifecycle_id,
        "strategy_id": item.strategy_id,
        "strategy_version_id": item.strategy_version_id,
        "is_active": bool(item.is_active),
        "is_production": bool(item.is_production),
        "lifecycle_state": item.lifecycle_state,
        "validation_status": item.validation_status,
        "validation_errors": item.validation_errors_json or [],
        "compatibility_status": item.compatibility_status,
        "compatibility_report": item.compatibility_report_json or {},
        "dry_run_status": item.dry_run_status,
        "dry_run_report": item.dry_run_report_json or {},
        "rollout_stage": item.rollout_stage,
        "promoted_at": item.promoted_at,
        "rolled_back_from_version_id": item.rolled_back_from_version_id,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _promotion_request_response(item: StrategyPromotionRequest) -> dict:
    return {
        "request_id": item.request_id,
        "strategy_id": item.strategy_id,
        "strategy_version_id": item.strategy_version_id,
        "requested_by": item.requested_by,
        "requested_role": item.requested_role,
        "status": item.status,
        "request_note": item.request_note,
        "approval_note": item.approval_note,
        "require_validation": bool(item.require_validation),
        "require_dry_run": bool(item.require_dry_run),
        "requested_stage": item.requested_stage,
        "approved_by": item.approved_by,
        "rejected_by": item.rejected_by,
        "created_at": item.created_at,
        "expires_at": item.expires_at,
        "reviewed_at": item.reviewed_at,
    }


@router.get("/admin/strategies", response_model=list[StrategyDefinitionResponse])
def admin_list_strategies(
    search: str | None = None,
    status_filter: str | None = None,
    lifecycle_state: str | None = None,
    active_only: bool = False,
    production_only: bool = False,
    validation_status: str | None = None,
    owner_user_id: str | None = None,
    owner_name: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 50,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows, _ = list_strategy_definitions_filtered(
        db,
        search=search,
        status_filter=status_filter,
        lifecycle_state=lifecycle_state,
        active_only=active_only,
        production_only=production_only,
        validation_status=validation_status,
        owner_user_id=owner_user_id,
        owner_name=owner_name,
        category=category,
        tag=tag,
        sort_by=sort_by,
        sort_order=sort_order,
        page=max(1, page),
        page_size=max(1, min(page_size, 200)),
    )
    return rows


@router.get("/admin/strategies/ops")
def admin_list_strategies_ops(
    search: str | None = None,
    status_filter: str | None = None,
    lifecycle_state: str | None = None,
    active_only: bool = False,
    production_only: bool = False,
    validation_status: str | None = None,
    owner_user_id: str | None = None,
    owner_name: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 50,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows, total = list_strategy_definitions_filtered(
        db,
        search=search,
        status_filter=status_filter,
        lifecycle_state=lifecycle_state,
        active_only=active_only,
        production_only=production_only,
        validation_status=validation_status,
        owner_user_id=owner_user_id,
        owner_name=owner_name,
        category=category,
        tag=tag,
        sort_by=sort_by,
        sort_order=sort_order,
        page=max(1, page),
        page_size=max(1, min(page_size, 200)),
    )
    return {
        "items": [StrategyDefinitionResponse.model_validate(item).model_dump() for item in rows],
        "pagination": {
            "page": max(1, page),
            "page_size": max(1, min(page_size, 200)),
            "total": total,
            "has_next": max(1, page) * max(1, min(page_size, 200)) < total,
        },
    }


@router.get("/admin/strategies/filter-options")
def admin_strategy_filter_options(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    return get_strategy_filter_options(db)


@router.post("/admin/strategies", response_model=StrategyDefinitionResponse, status_code=status.HTTP_201_CREATED)
def admin_create_strategy(
    payload: StrategyDefinitionCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = create_strategy_definition(
        db,
        name=payload.name,
        code=payload.code,
        description=payload.description,
        created_by=current_admin.id,
        owner_user_id=payload.owner_user_id,
        owner_name=payload.owner_name,
        category=payload.category,
        tags=payload.tags,
    )
    create_audit_log(
        db,
        action="strategy_definition_created",
        entity_type="strategy_definition",
        entity_id=row.strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"name": row.name, "code": row.code},
    )
    return row


@router.get("/admin/strategies/{strategy_id}", response_model=StrategyDetailResponse)
def admin_get_strategy_detail(strategy_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    versions = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_number.desc())
        .all()
    )
    return StrategyDetailResponse(
        strategy=StrategyDefinitionResponse.model_validate(strategy),
        versions=[StrategyVersionResponse.model_validate(item) for item in versions],
    )


@router.get("/admin/strategies/{strategy_id}/control-plane")
def admin_strategy_control_plane(strategy_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    versions = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_number.desc())
        .all()
    )
    lifecycles = list_strategy_version_lifecycles(db, strategy_id)
    lifecycle_map = {item.strategy_version_id: item for item in lifecycles}
    active_lifecycle = next((item for item in lifecycles if bool(item.is_active)), None)
    production_lifecycle = next((item for item in lifecycles if bool(item.is_production)), None)
    pending_requests = list_strategy_promotion_requests(
        db,
        strategy_id=strategy_id,
        status_filter="pending",
        requester_user_id=current_admin.id,
        is_super_admin=current_admin.role.value == "super_admin",
        limit=20,
    )

    return {
        "strategy": StrategyDefinitionResponse.model_validate(strategy),
        "versions": [StrategyVersionResponse.model_validate(item).model_dump() for item in versions],
        "lifecycles": [_lifecycle_response(item) for item in lifecycles],
        "active_version_id": strategy.active_version_id,
        "active_lifecycle": _lifecycle_response(active_lifecycle) if active_lifecycle else None,
        "production_lifecycle": _lifecycle_response(production_lifecycle) if production_lifecycle else None,
        "pending_promotion_requests": [_promotion_request_response(item) for item in pending_requests],
        "version_lifecycle_map": {
            item.version_id: _lifecycle_response(lifecycle_map[item.version_id])
            for item in versions
            if item.version_id in lifecycle_map
        },
    }


@router.get("/admin/strategies/{strategy_id}/lifecycle")
def admin_strategy_lifecycle(strategy_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")
    lifecycles = list_strategy_version_lifecycles(db, strategy_id)
    return {
        "strategy_id": strategy_id,
        "items": [_lifecycle_response(item) for item in lifecycles],
        "active_version_id": strategy.active_version_id,
    }


@router.post("/admin/strategies/{strategy_id}/versions", response_model=StrategyVersionResponse, status_code=status.HTTP_201_CREATED)
def admin_create_strategy_version(
    strategy_id: str,
    payload: StrategyVersionCreate,
    response: Response,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row, created_new = create_strategy_version(
        db,
        strategy_id=strategy_id,
        config_json=payload.config_json,
        config_schema_version=payload.config_schema_version,
        created_by=current_admin.id,
    )
    response.headers["x-strategy-version-created"] = "true" if created_new else "false"
    create_audit_log(
        db,
        action="strategy_version_created" if created_new else "strategy_version_reused",
        entity_type="strategy_version",
        entity_id=row.version_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "strategy_id": strategy_id,
            "version_number": row.version_number,
            "version_hash": row.version_hash,
            "created_new": created_new,
        },
    )
    return row


@router.post("/admin/strategies/{strategy_id}/versions/{version_id}/validate")
def admin_validate_strategy_version(
    strategy_id: str,
    version_id: str,
    payload: StrategyVersionValidationRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = payload
    result = validate_strategy_version_config(
        db,
        strategy_id=strategy_id,
        version_id=version_id,
        actor_user_id=current_admin.id,
    )
    create_audit_log(
        db,
        action="strategy_version_validated",
        entity_type="strategy_version",
        entity_id=version_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "strategy_id": strategy_id,
            "validation_status": result.get("validation_status"),
            "compatibility_status": result.get("compatibility_status"),
            "issues": result.get("issues"),
        },
    )
    return result


@router.post("/admin/strategies/{strategy_id}/versions/{version_id}/dry-run")
def admin_dry_run_strategy_version(
    strategy_id: str,
    version_id: str,
    payload: StrategyVersionDryRunRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "PURE_LIVE_410", "message": "strategy dry-run kaldırıldı"})


@router.post("/admin/strategies/{strategy_id}/versions/{version_id}/stage")
def admin_set_strategy_rollout_stage(
    strategy_id: str,
    version_id: str,
    payload: StrategyRolloutStageRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    lifecycle = set_strategy_rollout_stage(
        db,
        strategy_id=strategy_id,
        strategy_version_id=version_id,
        rollout_stage=payload.rollout_stage,
    )
    create_audit_log(
        db,
        action="strategy_rollout_stage_set",
        entity_type="strategy_version",
        entity_id=version_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "strategy_id": strategy_id,
            "rollout_stage": lifecycle.rollout_stage,
            "lifecycle_state": lifecycle.lifecycle_state,
        },
    )
    return _lifecycle_response(lifecycle)


@router.post("/admin/strategies/{strategy_id}/versions/diff")
def admin_strategy_version_diff(
    strategy_id: str,
    payload: StrategyVersionDiffRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_strategy_version_diff(
        db,
        strategy_id=strategy_id,
        from_version_id=payload.from_version_id,
        to_version_id=payload.to_version_id,
    )


@router.get("/admin/strategies/{strategy_id}/versions/timeline")
def admin_strategy_version_timeline(
    strategy_id: str,
    limit: int = 200,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return {
        "strategy_id": strategy_id,
        "items": get_strategy_timeline(db, strategy_id=strategy_id, limit=max(20, min(limit, 500))),
    }


@router.get("/admin/strategies/{strategy_id}/audit-history")
def admin_strategy_audit_history(
    strategy_id: str,
    limit: int = 200,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return {
        "strategy_id": strategy_id,
        "items": get_strategy_timeline(db, strategy_id=strategy_id, limit=max(20, min(limit, 500))),
    }


@router.post("/admin/strategies/{strategy_id}/rollback")
def admin_strategy_rollback(
    strategy_id: str,
    payload: StrategyRollbackRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = rollback_strategy_version(
        db,
        strategy_id=strategy_id,
        target_version_id=payload.target_version_id,
        actor_user_id=current_admin.id,
        reason=payload.reason,
    )
    create_audit_log(
        db,
        action="strategy_version_rolled_back",
        entity_type="strategy_definition",
        entity_id=strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={
            "strategy_id": strategy_id,
            "from_version_id": result.get("previous_active_version_id"),
            "to_version_id": result.get("current_active_version_id"),
            "reason": payload.reason,
        },
    )
    strategy = result.get("strategy")
    return {
        "strategy": StrategyDefinitionResponse.model_validate(strategy).model_dump() if strategy else None,
        "previous_active_version_id": result.get("previous_active_version_id"),
        "current_active_version_id": result.get("current_active_version_id"),
        "reason": result.get("reason"),
    }


@router.post("/admin/strategies/{strategy_id}/versions/{version_id}/execution-preview")
def admin_strategy_execution_preview(
    strategy_id: str,
    version_id: str,
    payload: StrategyExecutionPreviewRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = generate_strategy_execution_preview(
        db,
        strategy_id=strategy_id,
        version_id=version_id,
        context_payload=payload.context_snapshot,
    )
    create_audit_log(
        db,
        action="strategy_execution_preview_generated",
        entity_type="strategy_version",
        entity_id=version_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "strategy_id": strategy_id,
            "blocked_reasons": result.get("blocked_reasons"),
            "decision_hash": ((result.get("decision") or {}).get("decision_hash")),
        },
    )
    return result


@router.get("/admin/strategies/{strategy_id}/versions/{version_id}/metrics")
def admin_strategy_version_metrics(
    strategy_id: str,
    version_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_strategy_version_metrics(db, strategy_id=strategy_id, version_id=version_id)


@router.get("/admin/strategies/{strategy_id}/versions/{version_id}/metrics-trend")
def admin_strategy_version_metrics_trend(
    strategy_id: str,
    version_id: str,
    points: int = 60,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_strategy_version_metrics_timeseries(
        db,
        strategy_id=strategy_id,
        version_id=version_id,
        points=max(10, min(points, 500)),
    )


@router.get("/admin/strategies/{strategy_id}/versions/{version_id}/drift-alerts")
def admin_strategy_version_drift_alerts(
    strategy_id: str,
    version_id: str,
    limit: int = 100,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_strategy_version_drift_alerts(db, strategy_id=strategy_id, version_id=version_id, limit=max(1, min(limit, 500)))


@router.get("/admin/strategies/{strategy_id}/versions/{version_id}/false-signal-report")
def admin_strategy_version_false_signal_report(
    strategy_id: str,
    version_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_strategy_version_false_signal_report(db, strategy_id=strategy_id, version_id=version_id)


@router.get("/admin/strategies/{strategy_id}/versions/{version_id}/promotion-readiness")
def admin_strategy_promotion_readiness(
    strategy_id: str,
    version_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_strategy_promotion_readiness(db, strategy_id=strategy_id, version_id=version_id)


@router.post("/admin/strategies/bulk/archive")
def admin_bulk_archive_strategies(
    payload: StrategyBulkArchiveRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = bulk_archive_strategies(db, strategy_ids=payload.strategy_ids)
    create_audit_log(
        db,
        action="strategy_bulk_archive",
        entity_type="strategy_definition",
        entity_id="bulk",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details=result,
    )
    return result


@router.post("/admin/strategies/bulk/validate")
def admin_bulk_validate_strategies(
    payload: StrategyBulkValidateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = bulk_validate_strategies(db, strategy_ids=payload.strategy_ids, actor_user_id=current_admin.id)
    create_audit_log(
        db,
        action="strategy_bulk_validate",
        entity_type="strategy_definition",
        entity_id="bulk",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"success_count": result.get("success_count"), "failed_count": result.get("failed_count")},
    )
    return result


@router.post("/admin/strategies/bulk/dry-run")
def admin_bulk_dry_run_strategies(
    payload: StrategyBulkDryRunRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "PURE_LIVE_410", "message": "strategy bulk dry-run kaldırıldı"})


@router.post("/admin/strategies/bulk/tag")
def admin_bulk_tag_strategies(
    payload: StrategyBulkTagRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = bulk_tag_strategies(
        db,
        strategy_ids=payload.strategy_ids,
        category=payload.category,
        tags=payload.tags,
        owner_name=payload.owner_name,
    )
    create_audit_log(
        db,
        action="strategy_bulk_tag",
        entity_type="strategy_definition",
        entity_id="bulk",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details=result,
    )
    return result


@router.post("/admin/strategies/bulk/audit-snapshot")
def admin_bulk_audit_snapshot(
    payload: StrategyBulkAuditExportRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = bulk_export_audit_snapshot(
        db,
        strategy_ids=payload.strategy_ids,
        format_type=str(payload.format_type or "json").lower(),
        limit_per_strategy=max(1, min(payload.limit_per_strategy, 5000)),
    )
    create_audit_log(
        db,
        action="strategy_bulk_audit_snapshot",
        entity_type="strategy_definition",
        entity_id="bulk",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy_count": result.get("strategy_count"), "format": result.get("format")},
    )
    return result


@router.get("/admin/strategies/{strategy_id}/audit-history/export")
def admin_strategy_audit_export(
    strategy_id: str,
    format_type: str = "json",
    limit: int = 1000,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return export_strategy_audit_history(
        db,
        strategy_id=strategy_id,
        format_type=format_type,
        limit=max(1, min(limit, 5000)),
    )


@router.get("/admin/strategies/{strategy_id}/rollback-chain")
def admin_strategy_rollback_chain(
    strategy_id: str,
    limit: int = 100,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_strategy_rollback_chain(db, strategy_id=strategy_id, limit=max(1, min(limit, 500)))


@router.post("/admin/strategies/{strategy_id}/activate/{version_id}", response_model=StrategyDefinitionResponse)
def admin_activate_strategy_version(
    strategy_id: str,
    version_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    strategy = activate_strategy_version(db, strategy_id=strategy_id, version_id=version_id)
    create_audit_log(
        db,
        action="strategy_version_activated",
        entity_type="strategy_definition",
        entity_id=strategy.strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"active_version_id": strategy.active_version_id},
    )
    return strategy


@router.post("/admin/strategies/{strategy_id}/promote-request")
def admin_create_strategy_promote_request(
    strategy_id: str,
    payload: StrategyPromoteRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    request = create_strategy_promotion_request(
        db,
        strategy_id=strategy_id,
        strategy_version_id=payload.strategy_version_id,
        requested_by=current_admin.id,
        requested_role=current_admin.role.value,
        request_note=payload.request_note,
        require_validation=payload.require_validation,
        require_dry_run=payload.require_dry_run,
        requested_stage=payload.requested_stage,
    )
    create_audit_log(
        db,
        action="strategy_promote_requested",
        entity_type="strategy_promotion_request",
        entity_id=request.request_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "strategy_id": strategy_id,
            "strategy_version_id": request.strategy_version_id,
            "requested_stage": request.requested_stage,
            "require_validation": bool(request.require_validation),
            "require_dry_run": bool(request.require_dry_run),
        },
    )
    return _promotion_request_response(request)


@router.get("/admin/strategies/{strategy_id}/promotion-requests")
def admin_list_strategy_promote_requests(
    strategy_id: str,
    status_filter: str | None = None,
    limit: int = 100,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = list_strategy_promotion_requests(
        db,
        strategy_id=strategy_id,
        status_filter=status_filter,
        requester_user_id=current_admin.id,
        is_super_admin=current_admin.role.value == "super_admin",
        limit=max(1, min(limit, 300)),
    )
    return {
        "strategy_id": strategy_id,
        "items": [_promotion_request_response(item) for item in rows],
    }


@router.post("/admin/promotion-requests/{request_id}/approve")
def admin_approve_strategy_promote_request(
    request_id: str,
    payload: StrategyPromotionDecisionRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    request = approve_strategy_promotion_request(
        db,
        request_id=request_id,
        approved_by_user_id=current_super_admin.id,
        approval_note=payload.note,
    )
    create_audit_log(
        db,
        action="strategy_promoted",
        entity_type="strategy_promotion_request",
        entity_id=request_id,
        actor_user_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        severity="warning",
        details={
            "strategy_id": request.strategy_id,
            "strategy_version_id": request.strategy_version_id,
            "status": request.status,
        },
    )
    return _promotion_request_response(request)


@router.post("/admin/promotion-requests/{request_id}/reject")
def admin_reject_strategy_promote_request(
    request_id: str,
    payload: StrategyPromotionDecisionRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    request = reject_strategy_promotion_request(
        db,
        request_id=request_id,
        rejected_by_user_id=current_super_admin.id,
        rejection_note=payload.note,
    )
    create_audit_log(
        db,
        action="strategy_promotion_rejected",
        entity_type="strategy_promotion_request",
        entity_id=request_id,
        actor_user_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        severity="warning",
        details={
            "strategy_id": request.strategy_id,
            "strategy_version_id": request.strategy_version_id,
            "status": request.status,
        },
    )
    return _promotion_request_response(request)


@router.post("/admin/strategies/{strategy_id}/archive", response_model=StrategyDefinitionResponse)
def admin_archive_strategy(strategy_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    strategy = archive_strategy(db, strategy_id=strategy_id)
    create_audit_log(
        db,
        action="strategy_archived",
        entity_type="strategy_definition",
        entity_id=strategy.strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"status": strategy.status},
    )
    return strategy


@router.get("/admin/registry/active", response_model=list[StrategyDefinitionResponse])
def admin_active_strategy_set(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    return get_active_strategy_set(db)


@router.post("/admin/kernel/evaluate", response_model=DecisionResultResponse)
def admin_evaluate_kernel(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    try:
        context = DecisionContextInput.model_validate(payload)
    except ValidationError:
        reject_payload = {
            "action": "REJECT",
            "order_intent": {"intent_type": "REJECT", "symbol": payload.get("symbol")},
            "size": 0.0,
            "price_reference": {"source": "market_snapshot", "value": None},
            "confidence": 0.0,
            "risk_score": 1.0,
            "reason_codes": ["validation_error"],
            "strategy_version_id": payload.get("strategy_version_id"),
            "context_hash": build_context_hash(payload),
        }
        reject_payload["decision_hash"] = build_decision_hash(reject_payload)
        return DecisionResultResponse(decision_id=str(uuid.uuid4()), **reject_payload)

    version = get_version(db, context.strategy_version_id)

    context_payload = context.model_dump()
    context_hash = build_context_hash(context_payload)

    if version is None:
        result_payload = {
            "action": "REJECT",
            "order_intent": {"intent_type": "REJECT", "symbol": context.symbol},
            "size": 0.0,
            "price_reference": {"source": "market_snapshot", "value": context.market_snapshot.get("last_price")},
            "confidence": 0.0,
            "risk_score": 1.0,
            "reason_codes": ["strategy_version_not_found"],
            "strategy_version_id": context.strategy_version_id,
            "context_hash": context_hash,
        }
        result_payload["decision_hash"] = build_decision_hash(result_payload)
        return DecisionResultResponse(decision_id=str(uuid.uuid4()), **result_payload)

    if version.version_hash != context.strategy_version_hash:
        result_payload = {
            "action": "REJECT",
            "order_intent": {"intent_type": "REJECT", "symbol": context.symbol},
            "size": 0.0,
            "price_reference": {"source": "market_snapshot", "value": context.market_snapshot.get("last_price")},
            "confidence": 0.0,
            "risk_score": 1.0,
            "reason_codes": ["strategy_version_hash_mismatch"],
            "strategy_version_id": context.strategy_version_id,
            "context_hash": context_hash,
        }
        result_payload["decision_hash"] = build_decision_hash(result_payload)
        return DecisionResultResponse(decision_id=str(uuid.uuid4()), **result_payload)

    decision = evaluate_decision_context(context_payload)
    return DecisionResultResponse(decision_id=str(uuid.uuid4()), **decision)


@router.post("/admin/kernel/evaluate-standard")
def admin_evaluate_kernel_standard(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    try:
        context = DecisionContextInput.model_validate(payload)
    except ValidationError as exc:
        return {
            "result": "BLOCK",
            "PASS_BLOCK": "BLOCK",
            "score": 0.0,
            "SCORE": 0.0,
            "reason_codes": ["validation_error"],
            "REASON_CODES": ["validation_error"],
            "decision_hash": build_decision_hash({"validation_error": True, "payload": payload}),
            "DECISION_HASH": build_decision_hash({"validation_error": True, "payload": payload}),
            "validation_issues": [{"message": str(exc)}],
        }

    version = get_version(db, context.strategy_version_id)
    context_payload = context.model_dump()
    if version is None:
        result = {
            "result": "BLOCK",
            "score": 0.0,
            "reason_codes": ["strategy_version_not_found"],
            "decision_hash": build_decision_hash({"strategy_version_not_found": context.strategy_version_id}),
            "decision_trace": {"strategy_version_id": context.strategy_version_id},
        }
        return {**result, "PASS_BLOCK": result["result"], "SCORE": result["score"], "REASON_CODES": result["reason_codes"], "DECISION_HASH": result["decision_hash"]}

    if version.version_hash != context.strategy_version_hash:
        result = {
            "result": "BLOCK",
            "score": 0.0,
            "reason_codes": ["strategy_version_hash_mismatch"],
            "decision_hash": build_decision_hash(
                {
                    "strategy_version_id": context.strategy_version_id,
                    "received_hash": context.strategy_version_hash,
                    "actual_hash": version.version_hash,
                }
            ),
            "decision_trace": {
                "strategy_version_id": context.strategy_version_id,
                "received_hash": context.strategy_version_hash,
                "actual_hash": version.version_hash,
            },
        }
        return {**result, "PASS_BLOCK": result["result"], "SCORE": result["score"], "REASON_CODES": result["reason_codes"], "DECISION_HASH": result["decision_hash"]}

    result = evaluate_strategy_context_standard(strategy_version=version, context_payload=context_payload)
    create_audit_log(
        db,
        action="strategy_kernel_evaluate_standard",
        entity_type="strategy_version",
        entity_id=version.version_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "strategy_id": version.strategy_id,
            "strategy_version_id": version.version_id,
            "result": result.get("result"),
            "score": result.get("score"),
            "decision_hash": result.get("decision_hash"),
        },
    )
    return {
        **result,
        "PASS_BLOCK": result.get("result"),
        "SCORE": result.get("score"),
        "REASON_CODES": result.get("reason_codes"),
        "DECISION_HASH": result.get("decision_hash"),
    }


@router.post("/admin/kernel/replay")
def admin_replay_strategy_context(
    payload: StrategyReplayRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = replay_strategy_context(
        db,
        strategy_version_id=payload.strategy_version_id,
        context_snapshot=payload.context_snapshot,
    )
    create_audit_log(
        db,
        action="strategy_replay_executed",
        entity_type="strategy_version",
        entity_id=payload.strategy_version_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "strategy_version_id": payload.strategy_version_id,
            "deterministic": bool(result.get("deterministic")),
            "decision_hash": ((result.get("output") or {}).get("decision_hash")),
        },
    )
    return result


@router.post("/admin/kernel/compare")
def admin_compare_strategy_versions(
    payload: StrategyCompareRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = compare_strategy_versions(
        db,
        version_a_id=payload.version_a_id,
        version_b_id=payload.version_b_id,
        context_snapshot=payload.context_snapshot,
    )
    create_audit_log(
        db,
        action="strategy_compare_executed",
        entity_type="strategy_definition",
        entity_id=result.get("strategy_id") or payload.version_a_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "version_a_id": payload.version_a_id,
            "version_b_id": payload.version_b_id,
            "output_diff": result.get("output_diff"),
        },
    )
    return result


@router.get("/admin/regime/overview/{strategy_id}", response_model=StrategyRegimeOverviewResponse)
def admin_regime_overview(strategy_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    overview = get_strategy_regime_overview(db, strategy_id)
    return StrategyRegimeOverviewResponse(
        bindings=[StrategyRegimeBindingResponse.model_validate(item) for item in overview.get("bindings", [])],
        snapshots=[RegimeSnapshotResponse.model_validate(item) for item in overview.get("snapshots", [])],
        reject_distribution=overview.get("reject_distribution", {}),
    )


@router.get("/admin/regime/bindings/{strategy_version_id}", response_model=list[StrategyRegimeBindingResponse])
def admin_regime_bindings(
    strategy_version_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return [
        StrategyRegimeBindingResponse.model_validate(item)
        for item in get_strategy_regime_bindings(db, strategy_version_id)
    ]


@router.post("/admin/regime/bindings", response_model=StrategyRegimeBindingResponse, status_code=status.HTTP_201_CREATED)
def admin_create_regime_binding(
    payload: StrategyRegimeBindingCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = create_strategy_regime_binding(
        db,
        strategy_version_id=payload.strategy_version_id,
        allowed_regimes=payload.allowed_regimes,
        blocked_regimes=payload.blocked_regimes,
        priority=payload.priority,
        gating_policy_version=payload.gating_policy_version,
        created_by=current_admin.id,
    )
    create_audit_log(
        db,
        action="strategy_regime_binding_created",
        entity_type="strategy_regime_binding",
        entity_id=row.binding_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "strategy_version_id": row.strategy_version_id,
            "allowed_regimes": row.allowed_regimes,
            "blocked_regimes": row.blocked_regimes,
        },
    )
    return StrategyRegimeBindingResponse.model_validate(row)


@router.get("/admin/regime/resolved-binding-preview")
def admin_resolved_binding_preview(
    strategy_id: str | None = None,
    strategy_version_id: str | None = None,
    regime_label: str = "neutral",
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return resolve_strategy_binding_preview(
        db,
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        regime_label=regime_label,
    )


@router.post("/admin/regime/evaluate", response_model=RegimeEvaluationResponse)
def admin_regime_evaluate(
    payload: DecisionContextInput,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    version = get_version(db, payload.strategy_version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_version_not_found")
    if version.version_hash != payload.strategy_version_hash:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="strategy_version_hash_mismatch")

    snapshot, allowed, reason_code, binding_id = _evaluate_regime_gate(
        db=db,
        context_payload=payload.model_dump(),
        strategy_id=version.strategy_id,
        strategy_version_id=payload.strategy_version_id,
        actor=current_admin,
    )
    return RegimeEvaluationResponse(allowed=allowed, reason_code=reason_code, snapshot=snapshot, binding_id=binding_id)


@router.get("/admin/risk-orchestrator/policy", response_model=RiskOrchestratorPolicyResponse)
def admin_risk_policy(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    policy = get_or_create_policy(db)
    return _policy_response(policy)


@router.put("/admin/risk-orchestrator/policy", response_model=RiskOrchestratorPolicyResponse)
def admin_update_risk_policy(
    payload: RiskOrchestratorPolicyUpdate,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    _ = payload
    _ = current_super_admin
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="simulation_required_use_policy_simulate_and_apply",
    )


@router.post(
    "/admin/risk-orchestrator/policy/simulate",
    response_model=RiskOrchestratorPolicySimulationResponse,
)
def admin_risk_policy_simulate(
    payload: RiskOrchestratorPolicySimulationRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = simulate_policy_change(
        db,
        actor_id=current_admin.id,
        actor_role=current_admin.role.value,
        candidate_payload=payload.candidate_policy.model_dump(),
    )
    return RiskOrchestratorPolicySimulationResponse(**result)


@router.post(
    "/admin/risk-orchestrator/policy/apply",
    response_model=RiskOrchestratorPolicyApplyResponse,
)
def admin_risk_policy_apply(
    payload: RiskOrchestratorPolicyApplyRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = apply_policy_from_simulation(
        db,
        simulation_id=payload.simulation_id,
        actor_id=current_admin.id,
        actor_role=current_admin.role.value,
        reason_note=payload.reason_note,
        double_confirmed=payload.double_confirmed,
        apply_with_override=payload.apply_with_override,
        approval_note=payload.approval_note,
        request_key=payload.request_key,
        expected_policy_version=payload.expected_policy_version,
    )
    response_payload = {
        **result,
        "policy": _policy_response(result["policy"]) if result.get("policy") is not None else None,
    }
    return RiskOrchestratorPolicyApplyResponse(**response_payload)


@router.get(
    "/admin/risk-orchestrator/policy/history",
    response_model=RiskOrchestratorPolicyHistoryResponse,
)
def admin_risk_policy_history(
    limit: int = 25,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    history = list_policy_history(db, limit=limit)
    return RiskOrchestratorPolicyHistoryResponse(
        versions=[RiskOrchestratorPolicyVersionResponse.model_validate(item) for item in history["versions"]],
        change_requests=[RiskOrchestratorPolicyChangeRequestResponse.model_validate(item) for item in history["change_requests"]],
    )


@router.get(
    "/admin/risk-orchestrator/policy/approvals",
    response_model=list[RiskOrchestratorApprovalRequestResponse],
)
def admin_risk_policy_approvals(
    state: str | None = None,
    limit: int = 50,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = list_policy_approval_requests(db, state=state, limit=limit)
    return [RiskOrchestratorApprovalRequestResponse.model_validate(row) for row in rows]


@router.get(
    "/admin/risk-orchestrator/policy/queue",
    response_model=list[RiskOrchestratorApprovalQueueItemResponse],
)
def admin_risk_policy_queue(
    scope: str = "all",
    state: str | None = None,
    critical_first: bool = True,
    limit: int = 100,
    page: int = 1,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = list_policy_queue(
        db,
        actor_id=current_admin.id,
        scope=scope,
        state=state,
        critical_first=critical_first,
        limit=limit,
        page=page,
    )
    return [_approval_queue_item_response(item) for item in rows]


@router.post("/admin/risk-orchestrator/policy/queue/sweep")
def admin_risk_policy_queue_sweep(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return process_approval_escalations(db)


@router.post(
    "/admin/risk-orchestrator/policy/queue/{approval_id}/assign",
    response_model=RiskOrchestratorApprovalQueueItemResponse,
)
def admin_risk_policy_queue_assign(
    approval_id: str,
    payload: RiskOrchestratorApprovalAssignRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = assign_policy_approval_request(
        db,
        approval_id=approval_id,
        actor_id=current_admin.id,
        assignee_id=payload.assignee_id,
        auto_assign=payload.auto_assign,
    )
    return _approval_queue_item_response(row)


@router.post(
    "/admin/risk-orchestrator/policy/queue/{approval_id}/force-apply",
    response_model=RiskOrchestratorPolicyApplyResponse,
)
def admin_risk_policy_queue_force_apply(
    approval_id: str,
    payload: RiskOrchestratorForceApplyRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    result = force_apply_approval_request(
        db,
        approval_id=approval_id,
        actor_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        reason_note=payload.reason_note,
    )
    response_payload = {
        **result,
        "policy": _policy_response(result["policy"]) if result.get("policy") is not None else None,
    }
    return RiskOrchestratorPolicyApplyResponse(**response_payload)


@router.post(
    "/admin/risk-orchestrator/policy/approvals/{approval_id}/approve",
    response_model=RiskOrchestratorPolicyApplyResponse,
)
def admin_risk_policy_approval_approve(
    approval_id: str,
    payload: RiskOrchestratorApprovalDecisionRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = approve_policy_approval_request(
        db,
        approval_id=approval_id,
        actor_id=current_admin.id,
        actor_role=current_admin.role.value,
        decision_note=payload.decision_note,
    )
    apply_result = result["apply_result"]
    response_payload = {
        **apply_result,
        "policy": _policy_response(apply_result["policy"]) if apply_result.get("policy") is not None else None,
    }
    return RiskOrchestratorPolicyApplyResponse(**response_payload)


@router.post(
    "/admin/risk-orchestrator/policy/approvals/{approval_id}/reject",
    response_model=RiskOrchestratorApprovalRequestResponse,
)
def admin_risk_policy_approval_reject(
    approval_id: str,
    payload: RiskOrchestratorApprovalDecisionRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = reject_policy_approval_request(
        db,
        approval_id=approval_id,
        actor_id=current_admin.id,
        actor_role=current_admin.role.value,
        decision_note=payload.decision_note,
    )
    return RiskOrchestratorApprovalRequestResponse.model_validate(row)


@router.get(
    "/admin/risk-orchestrator/policy/decision-traces",
    response_model=list[RiskOrchestratorDecisionTraceResponse],
)
def admin_risk_policy_decision_traces(
    limit: int = 100,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = list_decision_traces(db, limit=limit)
    return [RiskOrchestratorDecisionTraceResponse.model_validate(row) for row in rows]


@router.get("/admin/risk-orchestrator/policy/decision-traces/export")
def admin_risk_policy_decision_traces_export(
    export_format: str = "json",
    limit: int = 500,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = export_decision_traces(db, limit=limit)

    if export_format.lower() == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "trace_id",
                "flow_type",
                "simulation_id",
                "classification",
                "risk_score",
                "rule_path",
                "decision_state",
                "requested_by",
                "approver_id",
                "request_key",
                "reason_note",
                "approval_note",
                "payload",
                "created_at",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "payload": json.dumps(row.get("payload") or {}, ensure_ascii=False)})
        csv_bytes = buffer.getvalue().encode("utf-8")
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=risk_orchestrator_decision_traces.csv",
            },
        )

    return Response(
        content=json.dumps({"items": rows}, ensure_ascii=False),
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=risk_orchestrator_decision_traces.json",
        },
    )


@router.get(
    "/admin/risk-orchestrator/policy/decision-intelligence/{trace_id}",
    response_model=RiskOrchestratorDecisionIntelligenceResponse,
)
def admin_risk_policy_decision_intelligence(
    trace_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    data = build_decision_intelligence(db, trace_id=trace_id)
    return RiskOrchestratorDecisionIntelligenceResponse(
        trace=RiskOrchestratorDecisionTraceResponse.model_validate(data["trace"]),
        before_after_diff=data["before_after_diff"],
        risk_breakdown=data["risk_breakdown"],
        why_decision=data["why_decision"],
        similar_patterns=data["similar_patterns"],
    )


@router.get(
    "/admin/risk-orchestrator/rejects/insights",
    response_model=RiskOrchestratorRejectInsightsResponse,
)
def admin_risk_rejects_insights(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    data = build_reject_insights(db)
    return RiskOrchestratorRejectInsightsResponse(**data)


@router.get(
    "/admin/risk-orchestrator/operations/dashboard",
    response_model=RiskOrchestratorOperationalDashboardResponse,
)
def admin_risk_operational_dashboard(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    data = build_operational_dashboard(db, actor_id=current_admin.id)
    return RiskOrchestratorOperationalDashboardResponse(**data)


@router.post(
    "/admin/risk-orchestrator/policy/revert/{version_id}/simulate",
    response_model=RiskOrchestratorRevertSimulationResponse,
)
def admin_risk_policy_revert_simulate(
    version_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = simulate_revert_to_version(
        db,
        version_id=version_id,
        actor_id=current_admin.id,
        actor_role=current_admin.role.value,
    )
    return RiskOrchestratorRevertSimulationResponse(
        version_id=result["version_id"],
        simulation=RiskOrchestratorPolicySimulationResponse(**result["simulation"]),
    )


@router.post(
    "/admin/risk-orchestrator/policy/revert/{version_id}/apply",
    response_model=RiskOrchestratorPolicyApplyResponse,
)
def admin_risk_policy_revert_apply(
    version_id: str,
    payload: RiskOrchestratorPolicyRevertRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    if not payload.simulation_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="revert_simulation_required")

    result = apply_revert_from_simulation(
        db,
        version_id=version_id,
        simulation_id=payload.simulation_id,
        actor_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        reason_note=payload.reason_note,
        double_confirmed=payload.double_confirmed,
        apply_with_override=payload.apply_with_override,
        request_key=payload.request_key,
        expected_policy_version=payload.expected_policy_version,
    )
    response_payload = {
        **result,
        "policy": _policy_response(result["policy"]) if result.get("policy") is not None else None,
    }
    return RiskOrchestratorPolicyApplyResponse(**response_payload)


@router.get("/admin/risk-orchestrator/status", response_model=RiskOrchestratorStatusResponse)
def admin_risk_status(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    snapshot = build_status_snapshot(db)
    policy = snapshot["policy"]
    return RiskOrchestratorStatusResponse(
        policy=_policy_response(policy),
        kill_switch_active=snapshot["kill_switch_active"],
        kill_switch_reasons=snapshot["kill_switch_reasons"],
        trading_enabled=snapshot.get("trading_enabled", True),
        open_intents=snapshot["open_intents"],
        open_intents_by_symbol=snapshot["open_intents_by_symbol"],
        open_intents_by_strategy=snapshot["open_intents_by_strategy"],
    )


@router.get("/admin/risk-orchestrator/rejects", response_model=list[RiskOrchestratorRejectResponse])
def admin_risk_rejects(
    reason_code: str | None = None,
    symbol: str | None = None,
    strategy_id: str | None = None,
    limit: int = 50,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = list_risk_rejects(
        db,
        reason_code=reason_code,
        symbol=symbol,
        strategy_id=strategy_id,
        limit=limit,
    )
    results: list[RiskOrchestratorRejectResponse] = []
    for row in rows:
        details = row.details or {}
        results.append(
            RiskOrchestratorRejectResponse(
                id=row.id,
                created_at=row.created_at,
                strategy_id=details.get("strategy_id"),
                strategy_version_id=details.get("strategy_version_id"),
                symbol=details.get("symbol"),
                reason_codes=details.get("reason_codes", []),
                details=details,
            )
        )
    return results


@router.get("/admin/risk-orchestrator/rejects/{reject_id}", response_model=RiskOrchestratorRejectDetailResponse)
def admin_risk_reject_detail(
    reject_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    row = get_reject_detail(db, audit_log_id=reject_id)
    details = row.details or {}
    reason_codes = details.get("reason_codes", [])
    return RiskOrchestratorRejectDetailResponse(
        id=row.id,
        created_at=row.created_at,
        strategy_id=details.get("strategy_id"),
        strategy_version_id=details.get("strategy_version_id"),
        symbol=details.get("symbol"),
        reason_codes=reason_codes,
        root_cause=(reason_codes[0] if reason_codes else None),
        details=details,
    )


@router.post("/admin/risk-orchestrator/supervisor/run", response_model=RiskOrchestratorSupervisorResponse)
def admin_risk_supervisor_run(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    result = run_in_trade_supervisor(
        db,
        persist=True,
        actor_id=current_admin.id,
        actor_role=current_admin.role.value,
    )
    return RiskOrchestratorSupervisorResponse(**result)


@router.get(
    "/admin/risk-orchestrator/supervisor/positions",
    response_model=list[RiskOrchestratorOpenPositionResponse],
)
def admin_risk_supervisor_positions(
    limit: int = 100,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = list_open_positions(db, limit=limit)
    return [
        RiskOrchestratorOpenPositionResponse(
            position_id=row.position_id,
            user_id=row.user_id,
            strategy_id=row.strategy_id,
            symbol=row.symbol,
            size=row.size,
            entry_price=row.entry_price,
            current_price=row.current_price,
            unrealized_pnl=row.unrealized_pnl,
            leverage=row.leverage,
            cluster_id=row.cluster_id,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post(
    "/admin/risk-orchestrator/supervisor/intervene",
    response_model=RiskOrchestratorInterventionResponse,
)
def admin_risk_supervisor_intervene(
    payload: RiskOrchestratorInterventionRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    effective_payload = dict(payload.payload or {})
    if payload.target_symbol and not effective_payload.get("target_symbol"):
        effective_payload["target_symbol"] = payload.target_symbol
    if payload.target_key and not effective_payload.get("target_key"):
        effective_payload["target_key"] = payload.target_key

    result = execute_position_intervention(
        db,
        position_id=payload.position_id,
        action_type=payload.action_type,
        reason_note=payload.reason_note,
        actor_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        payload=effective_payload,
    )
    intervention = result["intervention"]
    return RiskOrchestratorInterventionResponse(
        intervention_id=intervention.intervention_id,
        action_type=intervention.action_type,
        status=intervention.status,
        reason_note=intervention.reason_note,
        intent_id=intervention.intent_id,
        result_summary=intervention.result_summary,
        created_at=intervention.created_at,
    )


@router.post(
    "/admin/risk-orchestrator/actions/execute",
    response_model=RiskOrchestratorControlActionResponse,
)
def admin_risk_control_action(
    payload: RiskOrchestratorControlActionRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    result = execute_control_action(
        db,
        action_type=payload.action_type,
        reason_note=payload.reason_note,
        actor_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        context=payload.context,
    )
    intervention = result["intervention"]
    return RiskOrchestratorControlActionResponse(
        intervention_id=intervention.intervention_id,
        action_type=payload.action_type,
        status=intervention.status,
        reason_note=intervention.reason_note,
        effective_state=result["effective_state"],
        created_at=intervention.created_at,
    )


@router.post(
    "/admin/risk-orchestrator/actions/kill-switch",
    response_model=RiskOrchestratorControlActionResponse,
)
def admin_risk_kill_switch_action(
    payload: RiskOrchestratorControlActionRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    result = execute_control_action(
        db,
        action_type="kill_switch",
        reason_note=payload.reason_note,
        actor_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        context=payload.context,
    )
    intervention = result["intervention"]
    return RiskOrchestratorControlActionResponse(
        intervention_id=intervention.intervention_id,
        action_type="kill_switch",
        status=intervention.status,
        reason_note=intervention.reason_note,
        effective_state=result["effective_state"],
        created_at=intervention.created_at,
    )


@router.post(
    "/admin/risk-orchestrator/actions/global-pause",
    response_model=RiskOrchestratorControlActionResponse,
)
def admin_risk_global_pause_action(
    payload: RiskOrchestratorControlActionRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    result = execute_control_action(
        db,
        action_type="global_trading_pause",
        reason_note=payload.reason_note,
        actor_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        context=payload.context,
    )
    intervention = result["intervention"]
    return RiskOrchestratorControlActionResponse(
        intervention_id=intervention.intervention_id,
        action_type="global_trading_pause",
        status=intervention.status,
        reason_note=intervention.reason_note,
        effective_state=result["effective_state"],
        created_at=intervention.created_at,
    )


@router.post(
    "/admin/risk-orchestrator/actions/force-risk-check",
    response_model=RiskOrchestratorControlActionResponse,
)
def admin_risk_force_check_action(
    payload: RiskOrchestratorControlActionRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    result = execute_control_action(
        db,
        action_type="force_risk_check",
        reason_note=payload.reason_note,
        actor_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        context=payload.context,
    )
    intervention = result["intervention"]
    return RiskOrchestratorControlActionResponse(
        intervention_id=intervention.intervention_id,
        action_type="force_risk_check",
        status=intervention.status,
        reason_note=intervention.reason_note,
        effective_state=result["effective_state"],
        created_at=intervention.created_at,
    )


@router.post(
    "/admin/risk-orchestrator/exposure/overrides",
    response_model=RiskOrchestratorManualOverrideResponse,
)
def admin_risk_exposure_override_create(
    payload: RiskOrchestratorManualOverrideCreateRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    override_value = {
        "max_notional_pct": payload.max_notional_pct,
        "max_open_count": payload.max_open_count,
        "block_new_adds": payload.block_new_adds,
    }
    row = create_manual_override(
        db,
        actor_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        override_type=payload.override_type,
        target_key=payload.target_key,
        reason_note=payload.reason_note,
        override_value=override_value,
        expires_in_minutes=payload.expires_in_minutes,
    )
    return RiskOrchestratorManualOverrideResponse.model_validate(row)


@router.get(
    "/admin/risk-orchestrator/exposure/overrides",
    response_model=list[RiskOrchestratorManualOverrideResponse],
)
def admin_risk_exposure_override_list(
    active_only: bool = True,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = list_manual_overrides(db, active_only=active_only)
    return [RiskOrchestratorManualOverrideResponse.model_validate(row) for row in rows]


@router.post(
    "/admin/risk-orchestrator/exposure/overrides/{override_id}/deactivate",
    response_model=RiskOrchestratorManualOverrideResponse,
)
def admin_risk_exposure_override_deactivate(
    override_id: str,
    payload: RiskOrchestratorManualOverrideDeactivateRequest,
    current_super_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    row = deactivate_manual_override(
        db,
        override_id=override_id,
        actor_id=current_super_admin.id,
        actor_role=current_super_admin.role.value,
        reason_note=payload.reason_note,
    )
    return RiskOrchestratorManualOverrideResponse.model_validate(row)


@router.get(
    "/admin/risk-orchestrator/auto-trigger-logs",
    response_model=list[RiskOrchestratorAutoTriggerLogResponse],
)
def admin_risk_auto_trigger_logs(
    limit: int = 50,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = list_auto_trigger_logs(db, limit=limit)
    return [RiskOrchestratorAutoTriggerLogResponse.model_validate(row) for row in rows]


@router.get(
    "/admin/risk-orchestrator/audit/timeline",
    response_model=list[RiskOrchestratorAuditTimelineItemResponse],
)
def admin_risk_audit_timeline(
    limit: int = 100,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = build_audit_timeline(db, limit=limit)
    return [RiskOrchestratorAuditTimelineItemResponse(**row) for row in rows]


@router.get(
    "/admin/risk-orchestrator/alerts",
    response_model=list[RiskOrchestratorAlertResponse],
)
def admin_risk_alerts(
    severity: str | None = None,
    limit: int = 50,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = list_risk_alerts(db, severity=severity, limit=limit)
    return [
        RiskOrchestratorAlertResponse(
            id=row.id,
            alert_type=row.alert_type,
            severity=row.severity,
            status=row.status,
            message=row.message,
            details=row.details,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/admin/runtime/dispatch", response_model=RuntimeDispatchResponse)
def admin_dispatch_runtime(
    payload: RuntimeDispatchRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    context = payload.decision_context.model_dump()
    decision = admin_evaluate_kernel(context, current_admin=current_admin, db=db)

    decision_dict = decision.model_dump()
    if decision_dict.get("action") not in {"REJECT", "HOLD"}:
        _, allowed, reason_code, _ = _evaluate_regime_gate(
            db=db,
            context_payload=context,
            strategy_id=payload.strategy_id,
            strategy_version_id=context.get("strategy_version_id"),
            actor=current_admin,
        )
        if not allowed:
            decision_dict = _build_reject_payload(
                context,
                strategy_version_id=context.get("strategy_version_id"),
                reason_codes=[reason_code or "regime_not_allowed"],
            )

    if decision_dict.get("action") not in {"REJECT", "HOLD"}:
        risk_result = evaluate_pre_trade(
            db,
            strategy_id=payload.strategy_id,
            decision_result=decision_dict,
            context_payload=context,
        )
        if not risk_result.get("approved", True):
            decision_dict = _build_reject_payload(
                context,
                strategy_version_id=context.get("strategy_version_id"),
                reason_codes=risk_result.get("reason_codes", ["risk_orchestrator_reject"]),
            )
            create_audit_log(
                db,
                action="risk_orchestrator_reject",
                entity_type="strategy_definition",
                entity_id=payload.strategy_id,
                actor_user_id=current_admin.id,
                actor_role=current_admin.role.value,
                severity="warning",
                details={
                    "strategy_id": payload.strategy_id,
                    "strategy_version_id": context.get("strategy_version_id"),
                    "symbol": context.get("symbol"),
                    "reason_codes": risk_result.get("reason_codes", []),
                    "metrics": risk_result.get("metrics", {}),
                },
            )

    correlation_id = payload.decision_context.correlation_id
    decision_result, execution_intent, emitted = dispatch_decision_result(
        db,
        strategy_id=payload.strategy_id,
        correlation_id=correlation_id,
        decision_result=decision_dict,
        context_payload=context,
    )
    return RuntimeDispatchResponse(
        decision_result=DecisionResultResponse(**decision_result),
        execution_intent=execution_intent,
        emitted_events=[RuntimeEventEnvelopeResponse(**item) for item in emitted],
    )


@router.post("/admin/runtime/worker/run-once")
def admin_run_worker_once(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    result = process_submission_event_once(db)
    return result or {"status": "no_event"}


@router.get("/admin/runtime/intents", response_model=list[ExecutionIntentResponse])
def admin_list_execution_intents(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    return db.query(ExecutionIntent).order_by(ExecutionIntent.created_at.desc()).limit(100).all()


@router.get("/admin/runtime/intents/{intent_id}/events", response_model=list[ExecutionIntentEventResponse])
def admin_intent_events(intent_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    return (
        db.query(ExecutionIntentEvent)
        .filter(ExecutionIntentEvent.intent_id == intent_id)
        .order_by(ExecutionIntentEvent.created_at.asc())
        .all()
    )


@router.get("/admin/runtime/hot-traces")
def admin_hot_traces(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    rows = db.query(DecisionTraceHot).order_by(DecisionTraceHot.created_at.desc()).limit(100).all()
    return [{"trace_id": row.trace_id, "correlation_id": row.correlation_id, "context_hash": row.context_hash, "decision_hash": row.decision_hash, "intent_hash": row.intent_hash, "expires_at": row.expires_at, "created_at": row.created_at} for row in rows]


@router.get("/admin/runtime/cold-traces")
def admin_cold_traces(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    rows = db.query(DecisionTraceCold).order_by(DecisionTraceCold.created_at.desc()).limit(100).all()
    return [{"archive_id": row.archive_id, "correlation_id": row.correlation_id, "context_hash": row.context_hash, "decision_hash": row.decision_hash, "intent_hash": row.intent_hash, "terminal_state": row.terminal_state, "created_at": row.created_at} for row in rows]


@router.get("/admin/runtime/quarantine", response_model=list[RuntimeQuarantineEventResponse])
def admin_runtime_quarantine(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    rows = list_quarantined_events(db)
    response: list[RuntimeQuarantineEventResponse] = []
    for row in rows:
        payload = row.payload or {}
        response.append(
            RuntimeQuarantineEventResponse(
                id=row.id,
                event_id=row.entity_id,
                event_type=row.event_type,
                status=row.status,
                retry_count=row.retry_count,
                max_retry=row.max_retry,
                reason_code=payload.get("reason_code"),
                error_message=row.error_message,
                payload=payload,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return response


@router.post("/admin/runtime/quarantine/{event_id}/{action}", response_model=RuntimeQuarantineEventResponse)
def admin_runtime_quarantine_action(
    event_id: str,
    action: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    failed_event = (
        db.query(FailedEvent)
        .filter(FailedEvent.entity_type == "runtime_event", FailedEvent.entity_id == event_id)
        .first()
    )
    if failed_event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="quarantine_event_not_found")

    if action == "replay":
        failed_event = replay_quarantined_event(db, failed_event)
        action_label = "runtime_quarantine_replay"
    elif action == "dismiss":
        failed_event = dismiss_quarantined_event(db, failed_event)
        action_label = "runtime_quarantine_dismiss"
    elif action == "mark_failed":
        failed_event = mark_quarantined_failed(db, failed_event)
        action_label = "runtime_quarantine_mark_failed"
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_action")

    create_audit_log(
        db,
        action=action_label,
        entity_type="failed_event",
        entity_id=failed_event.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"event_id": event_id, "action": action},
    )

    payload = failed_event.payload or {}
    return RuntimeQuarantineEventResponse(
        id=failed_event.id,
        event_id=failed_event.entity_id,
        event_type=failed_event.event_type,
        status=failed_event.status,
        retry_count=failed_event.retry_count,
        max_retry=failed_event.max_retry,
        reason_code=payload.get("reason_code"),
        error_message=failed_event.error_message,
        payload=payload,
        created_at=failed_event.created_at,
        updated_at=failed_event.updated_at,
    )


@router.get("/admin/runtime/stuck-intents", response_model=list[RuntimeStuckIntentResponse])
def admin_stuck_intents(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    pending_threshold: int = 60,
    submitted_threshold: int = 120,
    partial_threshold: int = 300,
):
    _ = current_admin
    rows = list_stuck_intents(
        db,
        pending_threshold=pending_threshold,
        submitted_threshold=submitted_threshold,
        partial_threshold=partial_threshold,
    )
    return [RuntimeStuckIntentResponse(**row) for row in rows]


@router.post("/admin/runtime/stuck-intents/{intent_id}/{action}")
def admin_stuck_intent_action(
    intent_id: str,
    action: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return perform_recovery_action(
            db,
            intent_id=intent_id,
            action=action,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/admin/risk-orchestrator/unified-core/rulesets")
def admin_unified_risk_rulesets(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return list_rulesets()


@router.post("/admin/risk-orchestrator/unified-core/evaluate")
def admin_unified_risk_evaluate(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # Hard rule: execution kararı yalnız risk_orchestrator entrypoint'inden çıkar.
    target_user_id = str(payload.get("user_id") or current_admin.id)
    return run_unified_risk_orchestrator(
        db=db,
        cache=redis_client,
        user_id=target_user_id,
        ruleset=str(payload.get("ruleset") or "binance"),
        input_state=payload.get("input_state") if isinstance(payload.get("input_state"), dict) else None,
        snapshot_type=str(payload.get("snapshot_type") or "portfolio-level"),
        stage=str(payload.get("stage") or "pre-trade"),
        actor_id=current_admin.id,
        persist_artifact=bool(payload.get("persist_artifact", True)),
        scenario_id=str(payload.get("scenario_id")) if payload.get("scenario_id") else None,
        previous_state=str(payload.get("previous_state")) if payload.get("previous_state") else None,
        thresholds_override=payload.get("thresholds_override") if isinstance(payload.get("thresholds_override"), dict) else None,
        use_calibrated_thresholds=bool(payload.get("use_calibrated_thresholds", True)),
    )


@router.post("/admin/risk-orchestrator/unified-core/pre-trade-simulate")
def admin_unified_risk_pre_trade_simulation(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    proposed_order = payload.get("proposed_order") if isinstance(payload.get("proposed_order"), dict) else None
    if not proposed_order:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="proposed_order_required")
    target_user_id = str(payload.get("user_id") or current_admin.id)
    return simulate_pre_trade_risk(
        db=db,
        cache=redis_client,
        user_id=target_user_id,
        proposed_order=proposed_order,
        ruleset=str(payload.get("ruleset") or "binance"),
        actor_id=current_admin.id,
        scenario_id=str(payload.get("scenario_id")) if payload.get("scenario_id") else None,
        thresholds_override=payload.get("thresholds_override") if isinstance(payload.get("thresholds_override"), dict) else None,
        use_calibrated_thresholds=bool(payload.get("use_calibrated_thresholds", True)),
    )


@router.get("/admin/risk-orchestrator/unified-core/snapshots")
def admin_unified_risk_snapshots(
    limit: int = 100,
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    return list_risk_snapshot_manifest(limit=limit)


@router.get("/admin/risk-orchestrator/unified-core/jira-breakdown")
def admin_unified_risk_jira_breakdown(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return jira_epic_breakdown()


@router.get("/admin/risk-orchestrator/unified-core/scenarios")
def admin_unified_risk_scenarios(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return get_scenario_pack_library()


@router.post("/admin/risk-orchestrator/unified-core/scenarios")
def admin_unified_risk_upsert_scenario(
    payload: dict,
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    try:
        return upsert_scenario_pack(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/admin/risk-orchestrator/unified-core/thresholds")
def admin_unified_risk_thresholds(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return {"calibrated_thresholds": get_calibrated_thresholds()}


@router.post("/admin/risk-orchestrator/unified-core/calibrate")
def admin_unified_risk_calibrate(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target_user_id = str(payload.get("user_id") or current_admin.id)
    return calibrate_thresholds(
        db=db,
        cache=redis_client,
        user_id=target_user_id,
        ruleset=str(payload.get("ruleset") or "binance"),
        actor_id=current_admin.id,
    )


@router.post("/admin/risk-orchestrator/unified-core/replay")
def admin_unified_risk_replay(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    if not steps:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="steps_required")
    target_user_id = str(payload.get("user_id") or current_admin.id)
    timeline_payload = run_replay_timeline(
        db=db,
        cache=redis_client,
        user_id=target_user_id,
        steps=steps,
        ruleset=str(payload.get("ruleset") or "binance"),
        actor_id=current_admin.id,
        thresholds_override=payload.get("thresholds_override") if isinstance(payload.get("thresholds_override"), dict) else None,
        use_calibrated_thresholds=bool(payload.get("use_calibrated_thresholds", True)),
    )
    export_meta = export_replay_timeline(timeline_payload)
    return {**timeline_payload, "export": export_meta}


@router.post("/admin/risk-orchestrator/unified-core/benchmark/run")
def admin_unified_risk_benchmark_run(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target_user_id = str(payload.get("user_id") or current_admin.id)
    try:
        return run_policy_benchmark(
            db=db,
            cache=redis_client,
            user_id=target_user_id,
            scenario_ids=payload.get("scenario_ids") if isinstance(payload.get("scenario_ids"), list) else None,
            policy_sets=payload.get("policy_sets") if isinstance(payload.get("policy_sets"), list) else None,
            strategy_class=str(payload.get("strategy_class") or "default"),
            ruleset=str(payload.get("ruleset") or "binance"),
            base_input_state=payload.get("base_input_state") if isinstance(payload.get("base_input_state"), dict) else None,
            actor_id=current_admin.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/admin/risk-orchestrator/unified-core/benchmark/report")
def admin_unified_risk_benchmark_report(
    run_id: str | None = None,
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    try:
        return benchmark_report(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/admin/risk-orchestrator/unified-core/benchmark/compare")
def admin_unified_risk_benchmark_compare(
    payload: dict,
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    run_id = str(payload.get("run_id") or "").strip()
    if not run_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="run_id_required")
    try:
        return benchmark_compare(
            run_id=run_id,
            left_policy_id=str(payload.get("left_policy_id")) if payload.get("left_policy_id") else None,
            right_policy_id=str(payload.get("right_policy_id")) if payload.get("right_policy_id") else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/admin/risk-orchestrator/unified-core/drift/status")
def admin_unified_risk_drift_status(
    tolerance_pct: float = 10.0,
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    return drift_status(tolerance_pct=tolerance_pct)


@router.get("/admin/risk-orchestrator/unified-core/policy/leaderboard")
def admin_unified_risk_policy_leaderboard(
    limit: int = 20,
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    return policy_leaderboard(limit=limit)


@router.get("/admin/risk-orchestrator/unified-core/policy/history")
def admin_unified_risk_policy_history(
    policy_id: str | None = None,
    regime: str | None = None,
    limit: int = 1000,
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    return get_policy_history(policy_id=policy_id, regime=regime, limit=limit)


@router.get("/admin/risk-orchestrator/unified-core/policy/decay")
def admin_unified_risk_policy_decay(
    window: int = 20,
    drop_threshold: float = 0.15,
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    return policy_decay(window=window, drop_threshold=drop_threshold)


@router.get("/admin/risk-orchestrator/unified-core/policy/portfolio")
def admin_unified_risk_policy_portfolio(
    top_k: int = 2,
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    return policy_portfolio(top_k=top_k)


@router.get("/admin/risk-orchestrator/unified-core/policy/trends")
def admin_unified_risk_policy_trends(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return policy_trends()


@router.get("/admin/risk-orchestrator/analytics", response_model=RiskOrchestratorAnalyticsResponse)
def admin_risk_orchestrator_analytics(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    days: int = 14,
):
    _ = current_admin
    data = compute_risk_analytics(db, days=days)
    return RiskOrchestratorAnalyticsResponse(**data)
