import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def _resolve_migration_url() -> str:
    explicit_url = os.getenv("ALEMBIC_DATABASE_URL")
    if explicit_url:
        return explicit_url

    sqlite_fallback_enabled = str(os.getenv("ALEMBIC_ALLOW_SQLITE_FALLBACK", "0")).strip() == "1"
    sqlite_url = "sqlite:///./trading_platform_local.db"

    env_url = os.getenv("DATABASE_URL")
    if not env_url:
        if sqlite_fallback_enabled:
            logger.warning("DATABASE_URL missing; using SQLite fallback because ALEMBIC_ALLOW_SQLITE_FALLBACK=1")
            return sqlite_url
        raise RuntimeError("Missing DATABASE_URL for Alembic migration")

    try:
        connect_args = {}
        if str(env_url).startswith("postgresql"):
            connect_args = {"connect_timeout": 3}
        engine = create_engine(env_url, pool_pre_ping=True, connect_args=connect_args, future=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return env_url
    except SQLAlchemyError:
        if sqlite_fallback_enabled:
            logger.warning("Alembic DB URL unreachable; using SQLite fallback because ALEMBIC_ALLOW_SQLITE_FALLBACK=1")
            return sqlite_url
        raise RuntimeError("Alembic DB URL unreachable; SQLite fallback is disabled")


def run_alembic_upgrade():
    backend_root = Path(__file__).resolve().parent.parent
    alembic_ini = backend_root / "alembic.ini"
    if not alembic_ini.exists():
        logger.warning("alembic.ini not found; skipping versioned migration")
        return

    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    migration_url = _resolve_migration_url()
    config.set_main_option("sqlalchemy.url", migration_url)
    os.environ["ALEMBIC_DATABASE_URL"] = migration_url
    command.upgrade(config, "head")
    logger.info("Alembic migrations applied to head")
