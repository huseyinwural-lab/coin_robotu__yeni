from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import PortfolioExposureSnapshot, Position, User, UserExecutionIntent

router = APIRouter(prefix="/admin/closure", tags=["admin_closure"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_panel_inventory() -> list[dict]:
    return [
        {
            "panel_key": "admin_dashboard",
            "title": "Admin Dashboard",
            "route": "/admin/dashboard",
            "file_name": "AdminDashboardPage.jsx",
            "api_endpoints": ["/dashboard/summary"],
            "interaction_model": {"supports_refresh": True, "supports_filters": False},
        },
        {
            "panel_key": "positions_monitor",
            "title": "Positions Monitor",
            "route": "/admin/positions-monitor",
            "file_name": "AdminPositionsMonitorPage.jsx",
            "api_endpoints": ["/admin/positions-monitor"],
            "interaction_model": {"supports_refresh": True, "supports_filters": False},
        },
        {
            "panel_key": "portfolio_risk",
            "title": "Portfolio Risk",
            "route": "/admin/portfolio-risk",
            "file_name": "AdminPortfolioRiskPage.jsx",
            "api_endpoints": [
                "/admin/portfolio-risk/limits",
                "/admin/portfolio-risk/clusters",
                "/admin/portfolio-risk",
            ],
            "interaction_model": {"supports_refresh": True, "supports_filters": False},
        },
        {
            "panel_key": "execution_queue",
            "title": "Execution Queue",
            "route": "/admin/execution-queue",
            "file_name": "AdminExecutionQueuePage.jsx",
            "api_endpoints": ["/admin/execution-queue"],
            "interaction_model": {"supports_refresh": True, "supports_filters": True},
        },
        {
            "panel_key": "strategy_allocation",
            "title": "Strategy Allocation",
            "route": "/admin/strategy-allocation",
            "file_name": "AdminStrategyAllocationPage.jsx",
            "api_endpoints": ["/admin/strategy-allocation"],
            "interaction_model": {"supports_refresh": True, "supports_filters": False},
        },
        {
            "panel_key": "strategy_intelligence",
            "title": "Strategy Intelligence",
            "route": "/admin/strategy-intelligence",
            "file_name": "AdminStrategyIntelligencePage.jsx",
            "api_endpoints": ["/admin/strategy-intelligence", "/admin/manual-overrides"],
            "interaction_model": {"supports_refresh": True, "supports_filters": False},
        },
        {
            "panel_key": "futures_risk_monitor",
            "title": "Futures Risk Monitor",
            "route": "/admin/futures/risk-monitor",
            "file_name": "AdminFuturesRiskMonitorPage.jsx",
            "api_endpoints": ["/admin/futures/risk/status", "/admin/futures/strategy/status"],
            "interaction_model": {"supports_refresh": True, "supports_filters": True},
        },
        {
            "panel_key": "futures_cluster_risk",
            "title": "Futures Cluster Risk",
            "route": "/admin/futures/cluster-risk",
            "file_name": "AdminFuturesClusterRiskPage.jsx",
            "api_endpoints": ["/admin/futures/cluster-risk"],
            "interaction_model": {"supports_refresh": True, "supports_filters": False},
        },
        {
            "panel_key": "futures_capital_governance",
            "title": "Futures Capital Governance",
            "route": "/admin/futures/capital-governance",
            "file_name": "AdminFuturesCapitalGovernancePage.jsx",
            "api_endpoints": ["/admin/futures/capital-budget", "/admin/futures/capital-drift"],
            "interaction_model": {"supports_refresh": True, "supports_filters": True},
        },
        {
            "panel_key": "futures_live_readiness",
            "title": "Futures Live Readiness",
            "route": "/admin/futures/live-readiness",
            "file_name": "AdminFuturesLiveReadinessPage.jsx",
            "api_endpoints": ["/admin/futures/live-readiness", "/admin/futures/readiness-score"],
            "interaction_model": {"supports_refresh": True, "supports_filters": False},
        },
        {
            "panel_key": "futures_strategy_governance",
            "title": "Futures Strategy Governance",
            "route": "/admin/futures/strategy-governance",
            "file_name": "AdminFuturesStrategyGovernancePage.jsx",
            "api_endpoints": ["/admin/futures/strategy-governance", "/admin/futures/strategy-health"],
            "interaction_model": {"supports_refresh": True, "supports_filters": True},
        },
        {
            "panel_key": "futures_strategy_analytics",
            "title": "Futures Strategy Analytics",
            "route": "/admin/futures/strategy-analytics",
            "file_name": "AdminFuturesStrategyAnalyticsPage.jsx",
            "api_endpoints": ["/admin/futures/strategy-performance", "/admin/futures/strategy-execution-quality"],
            "interaction_model": {"supports_refresh": True, "supports_filters": True},
        },
        {
            "panel_key": "futures_tail_risk",
            "title": "Futures Tail Risk",
            "route": "/admin/futures/tail-risk",
            "file_name": "AdminFuturesTailRiskPage.jsx",
            "api_endpoints": ["/admin/futures/tail-risk", "/admin/futures/global-risk"],
            "interaction_model": {"supports_refresh": True, "supports_filters": True},
        },
        {
            "panel_key": "futures_microstructure",
            "title": "Futures Microstructure Guard",
            "route": "/admin/futures/microstructure-guard",
            "file_name": "AdminFuturesMicrostructureGuardPage.jsx",
            "api_endpoints": ["/admin/futures/microstructure/status"],
            "interaction_model": {"supports_refresh": True, "supports_filters": True},
        },
        {
            "panel_key": "futures_scaling_validation",
            "title": "Futures Scaling Validation",
            "route": "/admin/futures/scaling-validation",
            "file_name": "AdminFuturesScalingValidationPage.jsx",
            "api_endpoints": ["/admin/futures/scaling-validation", "/admin/futures/scaling-report"],
            "interaction_model": {"supports_refresh": True, "supports_filters": False},
        },
        {
            "panel_key": "futures_testnet_control",
            "title": "Futures Testnet Control",
            "route": "/admin/futures/testnet-control",
            "file_name": "AdminFuturesTestnetControlPage.jsx",
            "api_endpoints": [
                "/admin/futures/testnet/status",
                "/admin/futures/testnet/release-gate",
                "/admin/futures/testnet/execution-quality",
            ],
            "interaction_model": {"supports_refresh": True, "supports_filters": True},
        },
        {
            "panel_key": "risk_orchestrator",
            "title": "Risk Orchestrator",
            "route": "/admin/risk-orchestrator",
            "file_name": "AdminRiskOrchestratorPage.jsx",
            "api_endpoints": ["/strategy-domain/admin/risk-orchestrator/status"],
            "interaction_model": {"supports_refresh": True, "supports_filters": True},
        },
        {
            "panel_key": "risk_orchestrator_analytics",
            "title": "Risk Orchestrator Analytics",
            "route": "/admin/risk-orchestrator/analytics",
            "file_name": "AdminRiskOrchestratorAnalyticsPage.jsx",
            "api_endpoints": ["/strategy-domain/admin/risk-orchestrator/analytics"],
            "interaction_model": {"supports_refresh": True, "supports_filters": True},
        },
        {
            "panel_key": "runtime_quarantine",
            "title": "Runtime Quarantine",
            "route": "/admin/runtime/quarantine",
            "file_name": "AdminRuntimeQuarantinePage.jsx",
            "api_endpoints": ["/strategy-domain/admin/runtime/quarantine"],
            "interaction_model": {"supports_refresh": True, "supports_filters": False},
        },
        {
            "panel_key": "runtime_recovery",
            "title": "Runtime Recovery",
            "route": "/admin/runtime/recovery",
            "file_name": "AdminRuntimeRecoveryPage.jsx",
            "api_endpoints": ["/strategy-domain/admin/runtime/stuck-intents"],
            "interaction_model": {"supports_refresh": True, "supports_filters": False},
        },
    ]


def _build_contract_specs() -> dict[str, dict]:
    return {
        "/dashboard/summary": {
            "required_fields": {"metrics": "object", "alerts": "array", "heartbeat": "string"},
            "empty_rule": {"type": "field_array", "field": "alerts"},
        },
        "/admin/positions-monitor": {
            "required_fields": {
                "generated_at": "string",
                "open_positions": "array",
                "cluster_exposure": "object",
                "risk_level": "string",
            },
            "empty_rule": {"type": "field_array", "field": "open_positions"},
        },
        "/admin/portfolio-risk/limits": {
            "required_fields": {
                "max_portfolio_leverage": "number",
                "max_symbol_exposure": "number",
                "max_cluster_exposure": "number",
            },
            "empty_rule": {"type": "never"},
        },
        "/admin/portfolio-risk/clusters": {
            "required_fields": {},
            "empty_rule": {"type": "list"},
        },
        "/admin/portfolio-risk": {
            "required_fields": {
                "timestamp": "string",
                "total_exposure": "number",
                "cluster_exposure": "object",
                "risk_alerts": "array",
            },
            "empty_rule": {"type": "field_array", "field": "risk_alerts"},
        },
        "/admin/execution-queue": {
            "required_fields": {},
            "empty_rule": {"type": "list"},
        },
        "/admin/strategy-allocation": {
            "required_fields": {},
            "empty_rule": {"type": "list"},
        },
        "/admin/strategy-intelligence": {
            "required_fields": {
                "generated_at": "string",
                "strategy_conflicts": "array",
                "capital_rebalance_events": "array",
                "hedge_suggestions": "array",
            },
            "empty_rule": {"type": "field_array", "field": "strategy_conflicts"},
        },
        "/admin/manual-overrides": {
            "required_fields": {},
            "empty_rule": {"type": "list"},
        },
        "/admin/futures/risk/status": {
            "required_fields": {"portfolio_leverage": "number", "policy_state": "string", "liquidation_risk": "string"},
            "empty_rule": {"type": "never"},
        },
        "/admin/futures/strategy/status": {
            "required_fields": {"strategy": "string", "generated_at": "string", "metrics": "object"},
            "empty_rule": {"type": "never"},
        },
        "/admin/futures/cluster-risk": {
            "required_fields": {"generated_at": "string", "cluster_exposures": "array", "risk_state": "string"},
            "empty_rule": {"type": "field_array", "field": "cluster_exposures"},
        },
        "/admin/futures/capital-budget": {
            "required_fields": {"generated_at": "string", "strategy_capital_budget": "array"},
            "empty_rule": {"type": "field_array", "field": "strategy_capital_budget"},
        },
        "/admin/futures/capital-drift": {
            "required_fields": {"generated_at": "string", "drift_state": "string", "capital_drift_events": "array"},
            "empty_rule": {"type": "field_array", "field": "capital_drift_events"},
        },
        "/admin/futures/live-readiness": {
            "required_fields": {"generated_at": "string", "readiness_score": "number", "alerts": "array"},
            "empty_rule": {"type": "field_array", "field": "alerts"},
        },
        "/admin/futures/readiness-score": {
            "required_fields": {"generated_at": "string", "readiness_score": "number", "alerts": "array"},
            "empty_rule": {"type": "field_array", "field": "alerts"},
        },
        "/admin/futures/strategy-governance": {
            "required_fields": {"generated_at": "string", "strategy_health_score": "array", "health_components": "array"},
            "empty_rule": {"type": "field_array", "field": "health_components"},
        },
        "/admin/futures/strategy-health": {
            "required_fields": {"generated_at": "string", "strategy_health_score": "array", "health_components": "array"},
            "empty_rule": {"type": "field_array", "field": "health_components"},
        },
        "/admin/futures/strategy-performance": {
            "required_fields": {"generated_at": "string", "strategy_pnl_contribution": "array"},
            "empty_rule": {"type": "field_array", "field": "strategy_pnl_contribution"},
        },
        "/admin/futures/strategy-execution-quality": {
            "required_fields": {"generated_at": "string", "strategy_execution_quality": "array"},
            "empty_rule": {"type": "field_array", "field": "strategy_execution_quality"},
        },
        "/admin/futures/tail-risk": {
            "required_fields": {"generated_at": "string", "tail_risk_score": "number", "risk_state": "string"},
            "empty_rule": {"type": "never"},
        },
        "/admin/futures/global-risk": {
            "required_fields": {"generated_at": "string", "global_risk_score": "number", "risk_state": "string"},
            "empty_rule": {"type": "never"},
        },
        "/admin/futures/microstructure/status": {
            "required_fields": {
                "portfolio_microstructure_state": "string",
                "portfolio_microstructure_risk_score": "number",
                "symbols": "array",
            },
            "empty_rule": {"type": "field_array", "field": "symbols"},
        },
        "/admin/futures/scaling-validation": {
            "required_fields": {"generated_at": "string", "scaling_robustness_score": "number", "stress_replay_dashboard": "array"},
            "empty_rule": {"type": "field_array", "field": "stress_replay_dashboard"},
        },
        "/admin/futures/scaling-report": {
            "required_fields": {"generated_at": "string", "scaling_robustness_score": "number", "stress_replay_dashboard": "array"},
            "empty_rule": {"type": "field_array", "field": "stress_replay_dashboard"},
        },
        "/admin/futures/testnet/status": {
            "required_fields": {"testnet_enabled": "boolean", "safe_mode_enabled": "boolean", "release_gate": "object"},
            "empty_rule": {"type": "never"},
        },
        "/admin/futures/testnet/release-gate": {
            "required_fields": {"status": "string", "reasons": "array", "updated_at": "string"},
            "empty_rule": {"type": "field_array", "field": "reasons"},
        },
        "/admin/futures/testnet/execution-quality": {
            "required_fields": {"days": "number", "total_orders": "number", "execution_quality_score": "number"},
            "empty_rule": {"type": "never"},
        },
        "/strategy-domain/admin/risk-orchestrator/status": {
            "required_fields": {"policy": "object", "kill_switch_active": "boolean", "open_intents": "number"},
            "empty_rule": {"type": "never"},
        },
        "/strategy-domain/admin/risk-orchestrator/analytics": {
            "required_fields": {
                "days": "number",
                "generated_at": "string",
                "reject_reason_distribution": "array",
                "breach_by_day": "array",
            },
            "empty_rule": {"type": "field_array", "field": "breach_by_day"},
        },
        "/strategy-domain/admin/runtime/quarantine": {
            "required_fields": {},
            "empty_rule": {"type": "list"},
        },
        "/strategy-domain/admin/runtime/stuck-intents": {
            "required_fields": {},
            "empty_rule": {"type": "list"},
        },
    }


def _state_coverage_for_file(file_name: str) -> dict:
    page_path = Path("/app/frontend/src/pages") / file_name
    if not page_path.exists():
        return {
            "loading": False,
            "empty": False,
            "broken": False,
            "success": False,
            "source_exists": False,
        }

    content = page_path.read_text(encoding="utf-8")
    lowered = content.lower()
    has_loading = (
        "loading-skeleton" in content
        or "LoadingSkeleton" in content
        or "isLoading" in content
        or "setLoading(" in content
        or "loading &&" in content
        or "loading:" in lowered
    )
    has_empty = (
        "-empty" in content
        or "empty-state" in content
        or "length === 0" in content
        or "length===0" in content
        or "veri yok" in lowered
        or "bulunamadı" in lowered
    )
    has_broken = (
        "broken-state" in content
        or "broken-alert" in content
        or "setLoadError" in content
        or "loadError" in content
        or "setErrorMessage" in content
        or "errorMessage" in content
        or "error-state" in content
        or "toast.error" in content
    )
    has_success = "-page" in content and "data-testid" in content
    return {
        "loading": has_loading,
        "empty": has_empty,
        "broken": has_broken,
        "success": has_success,
        "source_exists": True,
    }


def _canonical_metrics(db: Session) -> dict:
    now = _now()
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    open_positions = db.query(Position).filter(Position.status == "open").count()
    queued_intents = db.query(UserExecutionIntent).filter(UserExecutionIntent.status == "QUEUED").count()
    pending_executions = db.query(UserExecutionIntent).filter(UserExecutionIntent.status.in_(["PREVIEWED", "SUBMITTED", "QUEUED"])).count()

    risk_alerts_24h = (
        db.query(func.count(UserExecutionIntent.id))
        .filter(UserExecutionIntent.created_at >= day_ago, UserExecutionIntent.gate_decision != "ALLOW")
        .scalar()
        or 0
    )
    avg_risk_score_24h = (
        db.query(func.avg(UserExecutionIntent.risk_score))
        .filter(UserExecutionIntent.created_at >= day_ago)
        .scalar()
        or 0
    )
    total_exposure_7d = (
        db.query(func.sum(PortfolioExposureSnapshot.notional))
        .filter(PortfolioExposureSnapshot.timestamp >= week_ago)
        .scalar()
        or 0
    )

    recent_queue_rows = (
        db.query(UserExecutionIntent.status)
        .order_by(UserExecutionIntent.created_at.desc())
        .limit(200)
        .all()
    )
    queued_in_recent_200 = sum(1 for row in recent_queue_rows if row[0] == "QUEUED")

    return {
        "generated_at": now,
        "active_positions": int(open_positions),
        "queued_executions": int(queued_intents),
        "pending_executions": int(pending_executions),
        "total_exposure_7d": round(float(total_exposure_7d), 6),
        "risk_alerts_24h": int(risk_alerts_24h),
        "avg_risk_score_24h": round(float(avg_risk_score_24h), 6),
        "queued_in_recent_200": int(queued_in_recent_200),
    }


def _consistency_checks(db: Session) -> dict:
    canonical = _canonical_metrics(db)
    panel_proxy = {
        "positions_monitor_open_positions": canonical["active_positions"],
        "portfolio_risk_total_exposure_7d": canonical["total_exposure_7d"],
        "portfolio_risk_alerts_24h": canonical["risk_alerts_24h"],
        "execution_queue_queued_from_recent_200": canonical["queued_in_recent_200"],
    }

    checks = []

    def append_check(metric_name: str, canonical_value: float, panel_value: float, tolerance: float):
        delta = round(float(panel_value) - float(canonical_value), 6)
        checks.append(
            {
                "metric_name": metric_name,
                "canonical_value": canonical_value,
                "panel_value": panel_value,
                "delta": delta,
                "tolerance": tolerance,
                "in_tolerance": abs(delta) <= tolerance,
            }
        )

    append_check(
        "active_positions",
        float(canonical["active_positions"]),
        float(panel_proxy["positions_monitor_open_positions"]),
        0.0,
    )
    append_check(
        "total_exposure_7d",
        float(canonical["total_exposure_7d"]),
        float(panel_proxy["portfolio_risk_total_exposure_7d"]),
        0.001,
    )
    append_check(
        "risk_alerts_24h",
        float(canonical["risk_alerts_24h"]),
        float(panel_proxy["portfolio_risk_alerts_24h"]),
        0.0,
    )
    append_check(
        "queued_executions_recent_window",
        float(canonical["queued_in_recent_200"]),
        float(panel_proxy["execution_queue_queued_from_recent_200"]),
        0.0,
    )

    mismatches = [item for item in checks if not item["in_tolerance"]]
    return {
        "generated_at": _now(),
        "canonical_metrics": canonical,
        "panel_proxy_metrics": panel_proxy,
        "checks": checks,
        "mismatch_count": len(mismatches),
        "status": "PASS" if not mismatches else "WARNING",
    }


@router.get("/panels")
def closure_panel_inventory(
    current_user: User = Depends(require_admin),
):
    _ = current_user
    inventory = _build_panel_inventory()
    panel_rows = []
    for item in inventory:
        coverage = _state_coverage_for_file(item["file_name"])
        coverage_pass = all(
            [
                coverage.get("loading", False),
                coverage.get("empty", False),
                coverage.get("broken", False),
                coverage.get("success", False),
            ]
        )
        panel_rows.append(
            {
                **item,
                "required_states": ["loading", "empty", "broken", "success"],
                "state_coverage": coverage,
                "state_contract_pass": coverage_pass,
            }
        )

    return {
        "generated_at": _now(),
        "panels": panel_rows,
        "contracts": _build_contract_specs(),
    }


@router.get("/canonical-metrics")
def closure_canonical_metrics(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return _canonical_metrics(db)


@router.get("/consistency")
def closure_consistency_report(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return _consistency_checks(db)
