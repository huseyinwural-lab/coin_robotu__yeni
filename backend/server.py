import asyncio
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from core.config import settings
from core.observability.http_logging_middleware import RequestObservabilityMiddleware
from core.structured_logging import configure_structured_logging
from api import runtime_ws
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
    admin_futures_strategy_control,
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
    admin_anomaly_alerts,
    admin_canonical_strategies,
    admin_learning,
    admin_strategy_family_gates,
    admin_strategy_intelligence,
    admin_commercial,
    admin_commercial_p0,
    admin_revenue,
    export,
    snapshots,
    runtime_execution,
    admin_universe_monitor,
    admin_live_trading_dashboard,
    admin_closure,
    admin_users,
    identity_control,
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
    runtime_control,
    risk_policies,
    symbol_selector,
    admin_execution,
    execution_safety,
    execution_readiness_core,
    user_approvals,
    admin_onboarding,
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
    incident_intelligence,
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
from services.commercial_export_scheduler_service import run_commercial_export_scheduler_loop
from services.venue_sanity_scheduler_service import run_venue_sanity_scheduler_loop
from services.readiness_maintenance_scheduler_service import run_readiness_maintenance_scheduler_loop
from services.execution_microstructure_service import ExecutionMicrostructureRuntime
from services.commercial_preview_smoke_service import (
    run_commercial_preview_http_gate_once,
    run_commercial_preview_smoke_gate,
)
from db import (
    engine,
    get_database_runtime_state,
    get_db,
    init_db_engine,
    is_database_ready,
    redis_client,
    verify_database_connection,
)
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
commercial_export_scheduler_task: asyncio.Task | None = None
preview_smoke_gate_task: asyncio.Task | None = None
venue_sanity_scheduler_task: asyncio.Task | None = None
readiness_maintenance_scheduler_task: asyncio.Task | None = None
execution_microstructure_runtime: ExecutionMicrostructureRuntime | None = None
PROCESS_STARTED_AT = datetime.now(timezone.utc)
STARTUP_RUNTIME_STATE = {
    "database_url_valid": False,
    "migration_ok": False,
    "database_ready": False,
    "seed_admin_ok": False,
    "state_rebuild_ok": False,
    "pipeline_runtime_ok": False,
    "background_loops_started": False,
    "preview_smoke_gate": {"status": "pending"},
    "last_error": None,
}
# Contract-test compatibility: some tests monkeypatch `server.engine` directly.
ENGINE_COMPAT = engine

fastapi_app = FastAPI(title="Algorithmic Trading Platform API", version="0.2.0")
api_router = APIRouter(prefix="/api")


@api_router.get("/health")
def health_check():
    db_state = get_database_runtime_state()
    db_healthy = bool(db_state.get("reachable") and db_state.get("initialized"))
    process_status = "up" if db_healthy else "degraded"
    status_code = 200 if db_healthy else 503
    payload = {
        "status": "ok" if db_healthy else "degraded",
        "service": "backend-api",
        "checks": {
            "process": {
                "status": process_status,
                "uptime_seconds": int((datetime.now(timezone.utc) - PROCESS_STARTED_AT).total_seconds()),
            },
            "database": db_state,
            "startup": STARTUP_RUNTIME_STATE,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(status_code=status_code, content=payload)


@api_router.get("/health/live")
def live_health_check():
    payload = {
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
    return JSONResponse(status_code=200, content=payload)


def _ready_dependency_checks() -> tuple[bool, dict[str, dict]]:
    checks: dict[str, dict] = {}
    ready = True

    try:
        verify_database_connection()
        checks["database"] = {"status": "ready"}
    except Exception as exc:  # noqa: BLE001
        ready = False
        checks["database"] = {"status": "not_ready", "reason": str(exc)[:200]}

    try:
        redis_client.ping()
        checks["redis"] = {"status": "ready"}
    except Exception as exc:  # noqa: BLE001
        ready = False
        checks["redis"] = {"status": "not_ready", "reason": str(exc)[:200]}

    preview_gate_required = str(os.getenv("PREVIEW_SMOKE_GATE_REQUIRED", "true") or "true").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if preview_gate_required:
        preview_state = STARTUP_RUNTIME_STATE.get("preview_smoke_gate") or {}
        preview_status = str(preview_state.get("status") or "pending").strip().lower()
        preview_ready = preview_status == "pass"
        checks["preview_smoke_gate"] = {
            "status": "ready" if preview_ready else "not_ready",
            "gate_status": preview_status,
            "checked_at": preview_state.get("checked_at"),
            "reason": preview_state.get("reason") or preview_state.get("last_error"),
        }
        if not preview_ready:
            ready = False
    else:
        checks["preview_smoke_gate"] = {"status": "skipped", "reason": "disabled_by_flag"}

    return ready, checks


@api_router.get("/health/ready")
def simple_readiness_check():
    ready, checks = _ready_dependency_checks()
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "service": "backend-api",
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@api_router.get("/ready")
def readiness_check():
    ready, checks = _ready_dependency_checks()

    if is_database_ready():
        try:
            from db import SessionLocal

            db = SessionLocal()
            try:
                snapshot = collect_observability_snapshot(db)
            finally:
                db.close()

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
        except Exception as exc:
            ready = False
            checks["execution_queue"] = {"status": "not_ready", "reason": str(exc)[:200]}
    else:
        ready = False
        checks["execution_queue"] = {"status": "not_ready", "reason": "database_unavailable"}

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
        "startup": STARTUP_RUNTIME_STATE,
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
api_router.include_router(mfa.public_router)
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
api_router.include_router(incident_intelligence.router)
api_router.include_router(audit_logs.router)
api_router.include_router(alerts.router)
api_router.include_router(report_archive.router)
api_router.include_router(reports_alias.router)
api_router.include_router(symbol_selector.router)
api_router.include_router(ops_alerts.router)
api_router.include_router(user_approvals.router)
api_router.include_router(admin_onboarding.router)
api_router.include_router(admin_users.router)
api_router.include_router(identity_control.router)
api_router.include_router(admin_universe_monitor.router)
api_router.include_router(admin_live_trading_dashboard.router)
api_router.include_router(admin_universe_router.router)
api_router.include_router(admin_risk_router.router)
api_router.include_router(exchange.router)
api_router.include_router(venues.router)
api_router.include_router(audit.router)
api_router.include_router(admin_onboarding.audit_router)
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
api_router.include_router(admin_futures_strategy_control.router)
api_router.include_router(admin_futures_correlation.router)
api_router.include_router(admin_futures_capital.router)
api_router.include_router(admin_futures_tail_risk.router)
api_router.include_router(admin_futures_live_readiness.router)
api_router.include_router(admin_futures_scaling_validation.router)
api_router.include_router(admin_phase3.router)
api_router.include_router(admin_strategy_risk_capital.router)
api_router.include_router(admin_strategy_observability.router)
api_router.include_router(admin_execution.router)
api_router.include_router(execution_safety.router)
api_router.include_router(execution_readiness_core.router)
api_router.include_router(admin_emergency.router)
api_router.include_router(admin_action_center.router)
api_router.include_router(admin_phase9_meta.router)
api_router.include_router(admin_positions_monitor.router)
api_router.include_router(admin_anomaly_alerts.router)
api_router.include_router(admin_canonical_strategies.router)
api_router.include_router(admin_learning.router)
api_router.include_router(admin_strategy_family_gates.router)
api_router.include_router(admin_strategy_intelligence.router)
api_router.include_router(admin_commercial.router)
api_router.include_router(admin_commercial_p0.router)
api_router.include_router(admin_revenue.router)
api_router.include_router(export.router)
api_router.include_router(snapshots.router)
api_router.include_router(runtime_execution.router)
api_router.include_router(runtime_ws.router)
api_router.include_router(admin_closure.router)
api_router.include_router(pipeline.router)
api_router.include_router(spot_strategy.router)
api_router.include_router(paper_positions.router)
api_router.include_router(backtest.router)
api_router.include_router(phase4_live.router)
api_router.include_router(runtime_control.router)

fastapi_app.include_router(api_router)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
fastapi_app.add_middleware(RequestObservabilityMiddleware)


@fastapi_app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none';")
    return response


@fastapi_app.on_event("startup")
async def startup_event():
    async def _run_with_retry(
        task_name: str,
        func,
        retries: int = 5,
        base_delay: float = 1.5,
        timeout_seconds: float = 20.0,
    ) -> bool:
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                await asyncio.wait_for(asyncio.to_thread(func), timeout=timeout_seconds)
                logger.info("STARTUP_TASK_OK", extra={"task": task_name, "attempt": attempt})
                return True
            except Exception as exc:
                last_error = str(exc)[:300]
                logger.warning(
                    "STARTUP_TASK_RETRY",
                    extra={
                        "task": task_name,
                        "attempt": attempt,
                        "retries": retries,
                        "error": last_error,
                    },
                )
                await asyncio.sleep(base_delay * attempt)
        STARTUP_RUNTIME_STATE["last_error"] = last_error
        logger.error("STARTUP_TASK_FAILED", extra={"task": task_name, "error": last_error})
        return False

    async def _run_preview_smoke_gate_job() -> None:
        max_attempts = max(1, int(os.getenv("PREVIEW_SMOKE_GATE_ATTEMPTS", "12") or "12"))
        interval_seconds = max(2.0, float(os.getenv("PREVIEW_SMOKE_GATE_INTERVAL_SECONDS", "5") or "5"))
        timeout_seconds = max(15.0, float(os.getenv("PREVIEW_SMOKE_GATE_TIMEOUT_SECONDS", "75") or "75"))
        base_url = str(os.getenv("PREVIEW_SMOKE_BASE_URL") or "").strip()
        admin_email = str(os.getenv("PREVIEW_SMOKE_ADMIN_EMAIL") or os.getenv("ADMIN_BOOTSTRAP_EMAIL") or "").strip()
        admin_password = str(os.getenv("PREVIEW_SMOKE_ADMIN_PASSWORD") or os.getenv("ADMIN_BOOTSTRAP_PASSWORD") or "").strip()

        if not base_url:
            STARTUP_RUNTIME_STATE["preview_smoke_gate"] = {
                "status": "failed",
                "reason": "preview_smoke_base_url_missing",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            return

        if not admin_email or not admin_password:
            STARTUP_RUNTIME_STATE["preview_smoke_gate"] = {
                "status": "failed",
                "reason": "preview_smoke_admin_credentials_missing",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            return

        for attempt in range(1, max_attempts + 1):
            STARTUP_RUNTIME_STATE["preview_smoke_gate"] = {
                "status": "pending",
                "attempt": attempt,
                "max_attempts": max_attempts,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                result = await run_commercial_preview_http_gate_once(
                    base_url=base_url,
                    admin_email=admin_email,
                    admin_password=admin_password,
                    timeout_seconds=timeout_seconds,
                )
                result["attempt"] = attempt
                result["max_attempts"] = max_attempts
                STARTUP_RUNTIME_STATE["preview_smoke_gate"] = result
                logger.info("PREVIEW_SMOKE_GATE_PASSED", extra={"attempt": attempt})
                return
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)[:300]
                logger.warning(
                    "PREVIEW_SMOKE_GATE_RETRY",
                    extra={
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "error": last_error,
                    },
                )
                STARTUP_RUNTIME_STATE["preview_smoke_gate"] = {
                    "status": "failed",
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "last_error": last_error,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
                if attempt < max_attempts:
                    await asyncio.sleep(interval_seconds)

    db_url = os.getenv("DATABASE_URL")
    try:
        enforce_postgresql_only(db_url, "startup")
        STARTUP_RUNTIME_STATE["database_url_valid"] = True
        logger.info("DB_ENGINE=postgresql")
    except Exception as exc:
        STARTUP_RUNTIME_STATE["database_url_valid"] = False
        STARTUP_RUNTIME_STATE["last_error"] = str(exc)[:300]
        logger.error("DATABASE_URL_INVALID", extra={"error": str(exc)[:300]})

    STARTUP_RUNTIME_STATE["migration_ok"] = await _run_with_retry(
        "alembic_upgrade",
        run_alembic_upgrade,
        retries=2,
        timeout_seconds=25,
    )
    STARTUP_RUNTIME_STATE["database_ready"] = await _run_with_retry(
        "database_connectivity",
        verify_database_connection,
        retries=3,
        timeout_seconds=8,
    )
    if STARTUP_RUNTIME_STATE["database_ready"]:
        STARTUP_RUNTIME_STATE["database_ready"] = await _run_with_retry(
            "database_init",
            init_db_engine,
            retries=2,
            timeout_seconds=10,
        )

    reliability_policy = {"policy_version": "unknown", "runtime_env": "degraded"}
    if STARTUP_RUNTIME_STATE["database_ready"]:
        from db import SessionLocal

        STARTUP_RUNTIME_STATE["seed_admin_ok"] = await _run_with_retry(
            "seed_default_admin",
            seed_default_admin,
            retries=2,
            timeout_seconds=10,
        )
        try:
            reliability_policy = load_connection_reliability_policy(force_refresh=True)
        except Exception as exc:
            STARTUP_RUNTIME_STATE["last_error"] = str(exc)[:300]
            logger.warning("RELIABILITY_POLICY_LOAD_FAILED", extra={"error": str(exc)[:300]})

        def _state_rebuild_job():
            db_session = SessionLocal()
            try:
                run_state_rebuild(db_session, trigger_source="startup")
            finally:
                db_session.close()

        STARTUP_RUNTIME_STATE["state_rebuild_ok"] = await _run_with_retry(
            "state_rebuild",
            _state_rebuild_job,
            retries=2,
            timeout_seconds=12,
        )
        STARTUP_RUNTIME_STATE["preview_smoke_gate"] = {
            "status": "pending",
            "mode": "deploy_http_gate",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        logger.error("DATABASE_NOT_READY_STARTUP_DEGRADED")
        STARTUP_RUNTIME_STATE["preview_smoke_gate"] = {
            "status": "skipped",
            "reason": "database_not_ready",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    canary_mode = str(os.getenv("CANARY_MODE", "false") or "false").strip().lower() in {"1", "true", "yes"}
    runtime_flag_default = "0" if canary_mode else "1"
    pipeline_runtime_enabled = (
        str(os.getenv("PIPELINE_RUNTIME_ENABLED", runtime_flag_default) or runtime_flag_default).strip().lower()
        in {"1", "true", "yes"}
    )
    if STARTUP_RUNTIME_STATE["database_ready"] and pipeline_runtime_enabled:
        try:
            await pipeline_runtime.start()
            STARTUP_RUNTIME_STATE["pipeline_runtime_ok"] = True
        except Exception as exc:
            STARTUP_RUNTIME_STATE["pipeline_runtime_ok"] = False
            STARTUP_RUNTIME_STATE["last_error"] = str(exc)[:300]
            logger.error("PIPELINE_RUNTIME_START_FAILED", extra={"error": str(exc)[:300]})
    elif STARTUP_RUNTIME_STATE["database_ready"] and not pipeline_runtime_enabled:
        STARTUP_RUNTIME_STATE["pipeline_runtime_ok"] = False
        logger.warning("PIPELINE_RUNTIME_SKIPPED_BY_FLAG", extra={"canary_mode": canary_mode})
    else:
        STARTUP_RUNTIME_STATE["pipeline_runtime_ok"] = False
        logger.warning("PIPELINE_RUNTIME_SKIPPED_DATABASE_NOT_READY")

    global weekly_report_task, exchange_health_task, backup_scheduler_task, commercial_export_scheduler_task, preview_smoke_gate_task, venue_sanity_scheduler_task, readiness_maintenance_scheduler_task, execution_microstructure_runtime
    if STARTUP_RUNTIME_STATE["database_ready"]:
        from db import SessionLocal

        execution_microstructure_runtime = ExecutionMicrostructureRuntime(redis_client)
        await execution_microstructure_runtime.start()
        weekly_report_task = asyncio.create_task(run_weekly_report_loop(SessionLocal))
        exchange_health_task = asyncio.create_task(run_exchange_connection_health_loop(SessionLocal))
        backup_scheduler_task = asyncio.create_task(run_backup_scheduler_loop())
        commercial_export_scheduler_task = asyncio.create_task(run_commercial_export_scheduler_loop())
        preview_smoke_gate_task = asyncio.create_task(_run_preview_smoke_gate_job())
        venue_sanity_scheduler_task = asyncio.create_task(run_venue_sanity_scheduler_loop(SessionLocal))
        readiness_maintenance_scheduler_task = asyncio.create_task(run_readiness_maintenance_scheduler_loop(SessionLocal))
        STARTUP_RUNTIME_STATE["background_loops_started"] = True
    else:
        STARTUP_RUNTIME_STATE["background_loops_started"] = False

    logger.info(
        "Platform startup complete with runtime status",
        extra={
            "event_type": "platform_startup",
            "policy_version": reliability_policy.get("policy_version"),
            "runtime_env": reliability_policy.get("runtime_env"),
            "startup_state": STARTUP_RUNTIME_STATE,
        },
    )


@fastapi_app.on_event("shutdown")
async def shutdown_event():
    if STARTUP_RUNTIME_STATE.get("pipeline_runtime_ok"):
        await pipeline_runtime.stop()
    global weekly_report_task, exchange_health_task, backup_scheduler_task, commercial_export_scheduler_task, preview_smoke_gate_task, venue_sanity_scheduler_task, readiness_maintenance_scheduler_task, execution_microstructure_runtime
    if execution_microstructure_runtime:
        await execution_microstructure_runtime.stop()
    if weekly_report_task:
        weekly_report_task.cancel()
    if exchange_health_task:
        exchange_health_task.cancel()
    if backup_scheduler_task:
        backup_scheduler_task.cancel()
    if commercial_export_scheduler_task:
        commercial_export_scheduler_task.cancel()
    if preview_smoke_gate_task:
        preview_smoke_gate_task.cancel()
    if venue_sanity_scheduler_task:
        venue_sanity_scheduler_task.cancel()
    if readiness_maintenance_scheduler_task:
        readiness_maintenance_scheduler_task.cancel()


app = create_socket_app(fastapi_app)