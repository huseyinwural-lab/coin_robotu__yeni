import logging

import redis
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

from core.config import settings

logger = logging.getLogger(__name__)


class InMemoryRedis:
    def __init__(self):
        self._store: dict[str, str] = {}

    def set(self, key: str, value: str):
        self._store[key] = value

    def get(self, key: str):
        return self._store.get(key)

    def ping(self):
        return True

    def delete(self, key: str):
        if key in self._store:
            del self._store[key]

    def incr(self, key: str, amount: int = 1):
        current = int(self._store.get(key, "0"))
        current += amount
        self._store[key] = str(current)
        return current


def _build_engine():
    primary_engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with primary_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return primary_engine
    except OperationalError:
        logger.warning("PostgreSQL unavailable in this runtime, using local SQLite fallback.")
        return create_engine("sqlite:///./trading_platform_local.db", connect_args={"check_same_thread": False})


def _build_redis_client():
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        client.ping()
        return client
    except redis.exceptions.RedisError:
        logger.warning("Redis unavailable in this runtime, using in-memory state fallback.")
        return InMemoryRedis()


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
redis_client = _build_redis_client()


def _ensure_sqlite_phase4_columns():
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        try:
            user_exchange_columns = {
                row[1] for row in connection.execute(text("PRAGMA table_info(user_exchange_settings)"))
            }
            if "validation_snapshot_id" not in user_exchange_columns:
                connection.execute(text("ALTER TABLE user_exchange_settings ADD COLUMN validation_snapshot_id VARCHAR(120)"))

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS execution_lifecycle_events (
                        id VARCHAR PRIMARY KEY,
                        execution_metric_id VARCHAR NOT NULL,
                        user_id VARCHAR NOT NULL,
                        event_name VARCHAR(40) NOT NULL,
                        event_timestamp DATETIME NOT NULL,
                        payload JSON NOT NULL
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS user_risk_settings (
                        id VARCHAR PRIMARY KEY,
                        user_id VARCHAR NOT NULL UNIQUE,
                        allocation_pct FLOAT NOT NULL DEFAULT 20,
                        trade_risk_pct FLOAT NOT NULL DEFAULT 10,
                        daily_loss_limit_pct FLOAT NOT NULL DEFAULT 3,
                        compounding_enabled BOOLEAN NOT NULL DEFAULT 1,
                        base_capital FLOAT NOT NULL DEFAULT 10000,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS alert_policies (
                        id VARCHAR PRIMARY KEY,
                        admin_notification_enabled BOOLEAN NOT NULL DEFAULT 1,
                        ops_webhook_url TEXT NOT NULL DEFAULT '',
                        monitoring_alert_log_enabled BOOLEAN NOT NULL DEFAULT 1,
                        execution_quality_warning_threshold FLOAT NOT NULL DEFAULT 60,
                        execution_quality_critical_threshold FLOAT NOT NULL DEFAULT 40,
                        permission_drift_warning_per_day INTEGER NOT NULL DEFAULT 2,
                        permission_drift_critical_per_day INTEGER NOT NULL DEFAULT 5,
                        gate_override_warning_per_day INTEGER NOT NULL DEFAULT 2,
                        gate_override_critical_per_day INTEGER NOT NULL DEFAULT 5,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(text("INSERT OR IGNORE INTO alert_policies (id) VALUES ('global')"))
        except Exception:
            logger.exception("SQLite phase4 compatibility migration failed")


_ensure_sqlite_phase4_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_auto_migrations():
    with engine.begin() as connection:
        if engine.dialect.name == "sqlite":
            columns = connection.execute(text("PRAGMA table_info(bot_profiles)")).fetchall()
            existing_columns = {column[1] for column in columns}
            if "is_running" not in existing_columns:
                connection.execute(text("ALTER TABLE bot_profiles ADD COLUMN is_running BOOLEAN DEFAULT 0"))
        else:
            connection.execute(text("ALTER TABLE bot_profiles ADD COLUMN IF NOT EXISTS is_running BOOLEAN DEFAULT FALSE"))