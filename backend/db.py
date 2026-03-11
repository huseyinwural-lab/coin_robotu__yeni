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
            execution_metric_columns = {
                row[1] for row in connection.execute(text("PRAGMA table_info(execution_metrics)"))
            }
            if "exchange" not in execution_metric_columns:
                connection.execute(text("ALTER TABLE execution_metrics ADD COLUMN exchange VARCHAR(30) DEFAULT 'binance'"))
            if "market_type" not in execution_metric_columns:
                connection.execute(text("ALTER TABLE execution_metrics ADD COLUMN market_type VARCHAR(20) DEFAULT 'futures'"))
            if "environment" not in execution_metric_columns:
                connection.execute(text("ALTER TABLE execution_metrics ADD COLUMN environment VARCHAR(20) DEFAULT 'testnet'"))

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
                    CREATE TABLE IF NOT EXISTS execution_correction_events (
                        id VARCHAR PRIMARY KEY,
                        execution_metric_id VARCHAR NOT NULL,
                        user_id VARCHAR NOT NULL,
                        correction_type VARCHAR(40) NOT NULL DEFAULT 'annotation',
                        reason_code VARCHAR(40) NOT NULL DEFAULT 'manual_correction',
                        note TEXT NOT NULL DEFAULT '',
                        patch_payload JSON NOT NULL DEFAULT '{}',
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
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

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS exchange_registry (
                        id VARCHAR PRIMARY KEY,
                        exchange_code VARCHAR(40) UNIQUE NOT NULL,
                        exchange_name VARCHAR(120) NOT NULL,
                        status VARCHAR(20) NOT NULL DEFAULT 'active',
                        supported_market_types JSON NOT NULL DEFAULT '[]',
                        supports_testnet BOOLEAN NOT NULL DEFAULT 1,
                        supports_live BOOLEAN NOT NULL DEFAULT 0,
                        health_status VARCHAR(20) NOT NULL DEFAULT 'healthy',
                        rate_limit_status VARCHAR(20) NOT NULL DEFAULT 'ok',
                        adapter_version VARCHAR(40) NOT NULL DEFAULT 'v1',
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS exchange_capabilities (
                        id VARCHAR PRIMARY KEY,
                        exchange_code VARCHAR(40) NOT NULL,
                        market_type VARCHAR(20) NOT NULL,
                        supports_spot BOOLEAN NOT NULL DEFAULT 0,
                        supports_futures BOOLEAN NOT NULL DEFAULT 0,
                        supports_test_order BOOLEAN NOT NULL DEFAULT 1,
                        supports_quote_qty BOOLEAN NOT NULL DEFAULT 0,
                        supports_reduce_only BOOLEAN NOT NULL DEFAULT 0,
                        supports_leverage BOOLEAN NOT NULL DEFAULT 0,
                        supports_margin_mode BOOLEAN NOT NULL DEFAULT 0,
                        supports_hedge_mode BOOLEAN NOT NULL DEFAULT 0,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS allowed_markets (
                        id VARCHAR PRIMARY KEY,
                        exchange_code VARCHAR(40) NOT NULL,
                        market_type VARCHAR(20) NOT NULL,
                        environment VARCHAR(20) NOT NULL,
                        enabled BOOLEAN NOT NULL DEFAULT 1,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS user_venue_assignments (
                        id VARCHAR PRIMARY KEY,
                        user_id VARCHAR NOT NULL,
                        exchange_code VARCHAR(40) NOT NULL,
                        spot_allowed BOOLEAN NOT NULL DEFAULT 0,
                        futures_allowed BOOLEAN NOT NULL DEFAULT 0,
                        testnet_allowed BOOLEAN NOT NULL DEFAULT 1,
                        live_allowed BOOLEAN NOT NULL DEFAULT 0,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS replay_runs (
                        id VARCHAR PRIMARY KEY,
                        user_id VARCHAR NOT NULL,
                        exchange VARCHAR(30) NOT NULL DEFAULT 'binance',
                        market_type VARCHAR(20) NOT NULL DEFAULT 'futures',
                        environment VARCHAR(20) NOT NULL DEFAULT 'testnet',
                        symbol VARCHAR(20) NOT NULL DEFAULT 'BTCUSDT',
                        timeframe VARCHAR(10) NOT NULL DEFAULT '15m',
                        strategy_type VARCHAR(50) NOT NULL DEFAULT 'trend_following',
                        candles_processed INTEGER NOT NULL DEFAULT 0,
                        executions_count INTEGER NOT NULL DEFAULT 0,
                        filled_count INTEGER NOT NULL DEFAULT 0,
                        canceled_count INTEGER NOT NULL DEFAULT 0,
                        avg_simulated_latency_ms FLOAT NOT NULL DEFAULT 0,
                        avg_simulated_slippage_pct FLOAT NOT NULL DEFAULT 0,
                        metrics JSON NOT NULL DEFAULT '{}',
                        status VARCHAR(20) NOT NULL DEFAULT 'completed',
                        started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        completed_at DATETIME
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS replay_executions (
                        id VARCHAR PRIMARY KEY,
                        replay_run_id VARCHAR NOT NULL,
                        user_id VARCHAR NOT NULL,
                        symbol VARCHAR(20) NOT NULL DEFAULT 'BTCUSDT',
                        timeframe VARCHAR(10) NOT NULL DEFAULT '15m',
                        signal VARCHAR(20) NOT NULL DEFAULT 'none',
                        direction VARCHAR(10) NOT NULL DEFAULT 'none',
                        market_price FLOAT NOT NULL,
                        simulated_fill_price FLOAT,
                        simulated_latency_ms FLOAT,
                        simulated_slippage_pct FLOAT,
                        lifecycle JSON NOT NULL DEFAULT '[]',
                        status VARCHAR(20) NOT NULL DEFAULT 'SIM_CANCELED',
                        risk_tags JSON NOT NULL DEFAULT '[]',
                        candle_timestamp VARCHAR(40) NOT NULL DEFAULT '',
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS replay_equity_points (
                        id VARCHAR PRIMARY KEY,
                        replay_run_id VARCHAR NOT NULL,
                        user_id VARCHAR NOT NULL,
                        point_timestamp VARCHAR(40) NOT NULL DEFAULT '',
                        equity FLOAT NOT NULL DEFAULT 0,
                        pnl_delta FLOAT NOT NULL DEFAULT 0,
                        drawdown_pct FLOAT NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS risk_policy_audit_events (
                        id VARCHAR PRIMARY KEY,
                        replay_run_id VARCHAR NOT NULL,
                        user_id VARCHAR NOT NULL,
                        strategy_version VARCHAR(120) NOT NULL DEFAULT 'unknown-v1',
                        regime_bucket VARCHAR(40) NOT NULL DEFAULT 'normal',
                        drawdown FLOAT NOT NULL DEFAULT 0,
                        exposure_breach INTEGER NOT NULL DEFAULT 0,
                        reject_count INTEGER NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
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