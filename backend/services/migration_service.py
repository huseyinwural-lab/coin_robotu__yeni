import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def _resolve_migration_url() -> str:
    env_url = os.getenv("DATABASE_URL")
    fallback_url = "sqlite:///./trading_platform_local.db"
    if not env_url:
        return fallback_url

    try:
        engine = create_engine(env_url, pool_pre_ping=True, connect_args={}, future=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return env_url
    except SQLAlchemyError:
        logger.warning("Alembic DB URL unreachable, using SQLite fallback for migrations")
        return fallback_url


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
