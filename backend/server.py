import asyncio
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from core.config import settings
from core.observability.http_logging_middleware import RequestObservabilityMiddleware
from core.structured_logging import configure_structured_logging
from routers import (
    admin_action_center,
    admin_emergency,
    admin_control,
    admin_kill_switch,
    admin_futures_adl_status,
    admin_futures_correlation,
    admin_futures_capital,
    admin_futures_tail_risk,
    admin_futures_live_readiness,
    admin_futures_scaling_validation,
    admin_futures_strategy_analytics,
    admin_futures_decision_diagnostics,
    admin_futures_leverage_status,
    admin_futures_liquidation_status,
    admin_futures_microstructure_status,
    admin_futures_testnet_control,
    admin_futures_risk_status,
    admin_futures_strategy_status,
    admin_system_readiness,
    admin_phase3,
    admin_strategy_risk_capital,
    admin_strategy_observability,
    admin_phase9_meta,
    admin_positions_monitor,
    admin_canonical_strategies,
    admin_learning,
    admin_strategy_family_gates,
    admin_strategy_intelligence,
    admin_commercial,
    admin_universe_monitor,
    admin_live_trading_dashboard,
    admin_closure,
    admin_users,
    alerts,
    audit_logs,
    auth,
    backtest,
    bot_profiles,
    dashboard,
    exchange,
    market,
    paper_positions,
    phase4_live,
    pipeline,
    spot_strategy,
    ops_alerts,
    report_archive,
    reports_alias,
    risk_policies,
    symbol_selector,
    admin_execution,
    user_approvals,
    user_execution,
    user_trading,
    user_explainability,
    user_platform,
    user_reports,
    user_scanner_signals,
    user_scanner_symbol_selection,
    user_learning_simulator,
    user_live_dashboard_router,
    debug_effective_universe,
    user_scanner_router,
    screener,
    admin_dashboard_alias,
    mfa,
    branding,
    admin_brand_settings,
    admin_universe_router,
    admin_risk_router,
    user_indicator_screener,
    user_risk,
    strategy_templates,
    strategy_domain,
    venues,
    audit,
)
from services.bootstrap import seed_default_admin
from services.connection_reliability_service import load_connection_reliability_policy
from services.migration_service import run_alembic_upgrade
from services.pipeline.runtime import pipeline_runtime
from services.realtime.socket_gateway import create_socket_app
from services.state_rebuild_service import run_state_rebuild
from services.user_exchange_health_loop import run_exchange_connection_health_loop
from services.weekly_report_service import run_weekly_report_loop
from services.db_backup_scheduler_service import run_backup_scheduler_loop
from db import engine, get_db, redis_client, verify_database_connection
from core.db_determinism import enforce_postgresql_only
from services.observability_service import (
    QUEUE_SIZE_THRESHOLD,
    READY_QUEUE_CRITICAL_FACTOR,
    build_metrics_exposition,
    collect_observability_snapshot,
    current_ready_override,
    emit_threshold_alerts,
)

configure_structured_logging(logging.INFO)
logger = logging.getLogger(__name__)
weekly_report_task: asyncio.Task | None = None
exchange_health_task: asyncio.Task | None = None
backup_scheduler_task: asyncio.Task | None = None
PROCESS_STARTED_AT = datetime.now(timezone.utc)
# Contract-test compatibility: some tests monkeypatch `server.engine` directly.
ENGINE_COMPAT = engine

fastapi_app = FastAPI(title="Algorithmic Trading Platform API", version="0.2.0")
api_router = APIRouter(prefix="/api")


@api_router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "backend-api",
        "checks": {
            "process": {
                "status": "up",
                "uptime_seconds": int((datetime.now(timezone.utc) - PROCESS_STARTED_AT).total_seconds()),
            }
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@api_router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    checks: dict[str, dict] = {}
    ready = True

    try:
        verify_database_connection()
        checks["database"] = {"status": "ready"}
    except Exception as exc:  # pragma: no cover - runtime dependency failure branch
        ready = False
        checks["database"] = {"status": "not_ready", "reason": str(exc)[:200]}

    try:
        redis_client.ping()
        checks["redis"] = {"status": "ready"}
    except Exception as exc:  # pragma: no cover - runtime dependency failure branch
        ready = False
        checks["redis"] = {"status": "not_ready", "reason": str(exc)[:200]}

    snapshot = collect_observability_snapshot(db)
    queue_size = int(snapshot.get("queue_size", 0))
    queue_limit = int(QUEUE_SIZE_THRESHOLD * READY_QUEUE_CRITICAL_FACTOR)
    if queue_size > queue_limit:
        ready = False
        checks["execution_queue"] = {
            "status": "not_ready",
            "queue_size": queue_size,
            "critical_limit": queue_limit,
            "reason": "queue_pressure",
        }
    else:
        checks["execution_queue"] = {
            "status": "ready",
            "queue_size": queue_size,
            "critical_limit": queue_limit,
        }

    override = current_ready_override()
    if override.get("active"):
        ready = False
        checks["ready_override"] = {
            "status": "not_ready",
            "reason": override.get("reason"),
            "until": override.get("until"),
        }
    else:
        checks["ready_override"] = {"status": "ready"}

    status_code = 200 if ready else 503
    payload = {
        "status": "ready" if ready else "not_ready",
        "service": "backend-api",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(status_code=status_code, content=payload)


@api_router.get("/metrics", response_class=PlainTextResponse)
def metrics_export(db: Session = Depends(get_db)):
    snapshot = collect_observability_snapshot(db)
    emit_threshold_alerts(db, snapshot=snapshot)
    return PlainTextResponse(build_metrics_exposition(snapshot), media_type="text/plain; version=0.0.4")


@api_router.get("/")
def api_root():
    return {
        "message": "Algorithmic trading platform phase-3 hardening core is running",
        "phase": "3-iter1",
        "execution_mode": "paper",
    }


api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(bot_profiles.router)
api_router.include_router(risk_policies.router)
api_router.include_router(user_risk.router)
api_router.include_router(user_platform.router)
api_router.include_router(user_scanner_signals.router)
api_router.include_router(user_scanner_symbol_selection.router)
api_router.include_router(user_scanner_router.router)
api_router.include_router(screener.router)
api_router.include_router(admin_dashboard_alias.router)
api_router.include_router(mfa.router)
api_router.include_router(branding.router)
api_router.include_router(admin_brand_settings.router)
api_router.include_router(user_learning_simulator.router)
api_router.include_router(user_live_dashboard_router.router)
api_router.include_router(user_indicator_screener.router)
api_router.include_router(user_execution.router)
api_router.include_router(user_trading.router)
api_router.include_router(user_explainability.router)
api_router.include_router(user_reports.router)
api_router.include_router(debug_effective_universe.router)
api_router.include_router(strategy_templates.router)
api_router.include_router(strategy_domain.router)
api_router.include_router(audit_logs.router)
api_router.include_router(alerts.router)
api_router.include_router(report_archive.router)
api_router.include_router(reports_alias.router)
api_router.include_router(symbol_selector.router)
api_router.include_router(ops_alerts.router)
api_router.include_router(user_approvals.router)
api_router.include_router(admin_users.router)
api_router.include_router(admin_universe_monitor.router)
api_router.include_router(admin_live_trading_dashboard.router)
api_router.include_router(admin_universe_router.router)
api_router.include_router(admin_risk_router.router)
api_router.include_router(exchange.router)
api_router.include_router(venues.router)
api_router.include_router(audit.router)
api_router.include_router(market.router)
api_router.include_router(admin_control.router)
api_router.include_router(admin_kill_switch.router)
api_router.include_router(admin_futures_risk_status.router)
api_router.include_router(admin_futures_liquidation_status.router)
api_router.include_router(admin_futures_adl_status.router)
api_router.include_router(admin_futures_microstructure_status.router)
api_router.include_router(admin_futures_decision_diagnostics.router)
api_router.include_router(admin_futures_leverage_status.router)
api_router.include_router(admin_futures_testnet_control.router)
api_router.include_router(admin_futures_strategy_status.router)
api_router.include_router(admin_system_readiness.router)
api_router.include_router(admin_futures_strategy_analytics.router)
api_router.include_router(admin_futures_correlation.router)
api_router.include_router(admin_futures_capital.router)
api_router.include_router(admin_futures_tail_risk.router)
api_router.include_router(admin_futures_live_readiness.router)
api_router.include_router(admin_futures_scaling_validation.router)
api_router.include_router(admin_phase3.router)
api_router.include_router(admin_strategy_risk_capital.router)
api_router.include_router(admin_strategy_observability.router)
api_router.include_router(admin_execution.router)
api_router.include_router(admin_emergency.router)
api_router.include_router(admin_action_center.router)
api_router.include_router(admin_phase9_meta.router)
api_router.include_router(admin_positions_monitor.router)
api_router.include_router(admin_canonical_strategies.router)
api_router.include_router(admin_learning.router)
api_router.include_router(admin_strategy_family_gates.router)
api_router.include_router(admin_strategy_intelligence.router)
api_router.include_router(admin_commercial.router)
api_router.include_router(admin_closure.router)
api_router.include_router(pipeline.router)
api_router.include_router(spot_strategy.router)
api_router.include_router(paper_positions.router)
api_router.include_router(backtest.router)
api_router.include_router(phase4_live.router)

fastapi_app.include_router(api_router)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
fastapi_app.add_middleware(RequestObservabilityMiddleware)


@fastapi_app.on_event("startup")
async def startup_event():
    db_url = os.getenv("DATABASE_URL")
    enforce_postgresql_only(db_url, "startup")

    run_alembic_upgrade()
    verify_database_connection()

    from db import SessionLocal

    seed_default_admin()
    reliability_policy = load_connection_reliability_policy(force_refresh=True)

    db_session = SessionLocal()
    try:
        run_state_rebuild(db_session, trigger_source="startup")
    finally:
        db_session.close()
    await pipeline_runtime.start()
    global weekly_report_task, exchange_health_task, backup_scheduler_task
    weekly_report_task = asyncio.create_task(run_weekly_report_loop(SessionLocal))
    exchange_health_task = asyncio.create_task(run_exchange_connection_health_loop(SessionLocal))
    backup_scheduler_task = asyncio.create_task(run_backup_scheduler_loop())
    logger.info(
        "Platform startup complete with Phase-3 hardening runtime",
        extra={
            "event_type": "platform_startup",
            "policy_version": reliability_policy.get("policy_version"),
            "runtime_env": reliability_policy.get("runtime_env"),
        },
    )


@fastapi_app.on_event("shutdown")
async def shutdown_event():
    await pipeline_runtime.stop()
    global weekly_report_task, exchange_health_task, backup_scheduler_task
    if weekly_report_task:
        weekly_report_task.cancel()
    if exchange_health_task:
        exchange_health_task.cancel()
    if backup_scheduler_task:
        backup_scheduler_task.cancel()


app = create_socket_app(fastapi_app)