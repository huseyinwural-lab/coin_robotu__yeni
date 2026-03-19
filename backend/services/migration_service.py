import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from core.db_determinism import enforce_postgresql_only

logger = logging.getLogger(__name__)


def _resolve_migration_url() -> str:
    explicit_url = os.getenv("ALEMBIC_DATABASE_URL")
    if explicit_url:
        return enforce_postgresql_only(explicit_url, "alembic_explicit_url")

    env_url = os.getenv("DATABASE_URL")
    if not env_url:
        raise RuntimeError("Missing DATABASE_URL for Alembic migration")

    normalized_env_url = enforce_postgresql_only(env_url, "alembic_database_url")

    try:
        connect_args = {}
        if str(normalized_env_url).startswith("postgresql"):
            connect_args = {"connect_timeout": 3}
        engine = create_engine(normalized_env_url, pool_pre_ping=True, connect_args=connect_args, future=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return normalized_env_url
    except SQLAlchemyError:
        raise RuntimeError("Alembic DB URL unreachable")


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
