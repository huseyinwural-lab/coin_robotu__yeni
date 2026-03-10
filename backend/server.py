import logging

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from core.config import settings
from db import Base, engine, run_auto_migrations
from routers import (
    admin_control,
    audit_logs,
    auth,
    bot_profiles,
    dashboard,
    exchange,
    paper_positions,
    pipeline,
    risk_policies,
    strategy_templates,
)
from services.bootstrap import seed_default_admin
from services.pipeline.runtime import pipeline_runtime
from services.realtime.socket_gateway import create_socket_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

fastapi_app = FastAPI(title="Algorithmic Trading Platform API", version="0.2.0")
api_router = APIRouter(prefix="/api")


@api_router.get("/")
def api_root():
    return {
        "message": "Algorithmic trading platform phase-2 pipeline is running",
        "phase": "2-b",
        "execution_mode": "paper",
    }


api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(bot_profiles.router)
api_router.include_router(risk_policies.router)
api_router.include_router(strategy_templates.router)
api_router.include_router(audit_logs.router)
api_router.include_router(exchange.router)
api_router.include_router(admin_control.router)
api_router.include_router(pipeline.router)
api_router.include_router(paper_positions.router)

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
    Base.metadata.create_all(bind=engine)
    run_auto_migrations()
    seed_default_admin()
    await pipeline_runtime.start()
    logger.info("Platform startup complete with Phase-2 pipeline runtime")


@fastapi_app.on_event("shutdown")
async def shutdown_event():
    await pipeline_runtime.stop()


app = create_socket_app(fastapi_app)