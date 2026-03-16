from __future__ import with_statement

import os
from pathlib import Path
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db import Base
import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _is_sqlite_url(url: str) -> bool:
    return str(url or "").strip().lower().startswith("sqlite")


def _is_neutral_placeholder(url: str) -> bool:
    candidate = str(url or "").strip().lower()
    if not candidate:
        return True
    return candidate in {
        "driver://user:pass@localhost/dbname",
        "postgresql+psycopg2://<set-via-env>",
        "postgresql+psycopg2://set-via-env",
    }


def get_url() -> str:
    explicit = os.getenv("ALEMBIC_DATABASE_URL")
    if explicit:
        return explicit

    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    configured = config.get_main_option("sqlalchemy.url")
    if configured and not _is_neutral_placeholder(configured):
        if _is_sqlite_url(configured):
            raise RuntimeError(
                "SQLite URL is not allowed for Alembic migrations. "
                "Provide ALEMBIC_DATABASE_URL or DATABASE_URL with PostgreSQL."
            )
        return configured

    raise RuntimeError(
        "No database URL found for Alembic. Set ALEMBIC_DATABASE_URL or DATABASE_URL."
    )


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()