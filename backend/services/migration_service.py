import logging
import os
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
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
    parsed_env_url = make_url(normalized_env_url)
    parsed_host = str(parsed_env_url.host or "").strip().lower()
    if parsed_host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        raise RuntimeError("DATABASE_URL localhost host is not allowed")
    if not parsed_env_url.database:
        raise RuntimeError("DATABASE_URL database name is missing")

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
    timeout_seconds = int(os.getenv("ALEMBIC_UPGRADE_TIMEOUT_SECONDS", "25"))
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(backend_root))
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(alembic_ini), "upgrade", "head"],
        cwd=str(backend_root),
        env=env,
        check=True,
        timeout=timeout_seconds,
    )
    logger.info("Alembic migrations applied to head")
