import asyncio
import logging

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from core.config import settings
from db import Base, engine
from routers import (
    admin_control,
    admin_futures_adl_status,
    admin_futures_liquidation_status,
    admin_futures_microstructure_status,
    admin_futures_risk_status,
    admin_futures_strategy_status,
    admin_phase3,
    admin_strategy_risk_capital,
    admin_strategy_observability,
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
    risk_policies,
    user_approvals,
    user_risk,
    strategy_templates,
    strategy_domain,
    venues,
    audit,
)
from services.bootstrap import seed_default_admin
from services.migration_service import run_alembic_upgrade
from services.pipeline.runtime import pipeline_runtime
from services.realtime.socket_gateway import create_socket_app
from services.state_rebuild_service import run_state_rebuild
from services.weekly_report_service import run_weekly_report_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
weekly_report_task: asyncio.Task | None = None

fastapi_app = FastAPI(title="Algorithmic Trading Platform API", version="0.2.0")
api_router = APIRouter(prefix="/api")


@api_router.get("/health")
def health_check():
    return {"status": "ok"}


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
api_router.include_router(strategy_templates.router)
api_router.include_router(strategy_domain.router)
api_router.include_router(audit_logs.router)
api_router.include_router(alerts.router)
api_router.include_router(report_archive.router)
api_router.include_router(ops_alerts.router)
api_router.include_router(user_approvals.router)
api_router.include_router(admin_users.router)
api_router.include_router(exchange.router)
api_router.include_router(venues.router)
api_router.include_router(audit.router)
api_router.include_router(market.router)
api_router.include_router(admin_control.router)
api_router.include_router(admin_futures_risk_status.router)
api_router.include_router(admin_futures_liquidation_status.router)
api_router.include_router(admin_futures_adl_status.router)
api_router.include_router(admin_futures_microstructure_status.router)
api_router.include_router(admin_futures_strategy_status.router)
api_router.include_router(admin_phase3.router)
api_router.include_router(admin_strategy_risk_capital.router)
api_router.include_router(admin_strategy_observability.router)
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


@fastapi_app.on_event("startup")
async def startup_event():
    run_alembic_upgrade()
    Base.metadata.create_all(bind=engine)
    seed_default_admin()
    from db import SessionLocal

    db_session = SessionLocal()
    try:
        run_state_rebuild(db_session, trigger_source="startup")
    finally:
        db_session.close()
    await pipeline_runtime.start()
    global weekly_report_task
    weekly_report_task = asyncio.create_task(run_weekly_report_loop(SessionLocal))
    logger.info("Platform startup complete with Phase-3 hardening runtime")


@fastapi_app.on_event("shutdown")
async def shutdown_event():
    await pipeline_runtime.stop()
    global weekly_report_task
    if weekly_report_task:
        weekly_report_task.cancel()


app = create_socket_app(fastapi_app)