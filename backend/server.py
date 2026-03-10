import logging

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from core.config import settings
from db import Base, engine
from routers import (
    audit_logs,
    auth,
    bot_profiles,
    dashboard,
    exchange,
    risk_policies,
    strategy_templates,
)
from services.bootstrap import seed_default_admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Algorithmic Trading Platform API", version="0.1.0")
api_router = APIRouter(prefix="/api")


@api_router.get("/")
def api_root():
    return {
        "message": "Algorithmic trading platform skeleton is running",
        "phase": "1-b",
        "execution_mode": "mock",
    }


api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(bot_profiles.router)
api_router.include_router(risk_policies.router)
api_router.include_router(strategy_templates.router)
api_router.include_router(audit_logs.router)
api_router.include_router(exchange.router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    seed_default_admin()
    logger.info("Platform startup complete with PostgreSQL + Redis config")