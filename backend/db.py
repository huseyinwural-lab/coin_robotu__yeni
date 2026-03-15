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
        self._lists: dict[str, list[str]] = {}
        self._sets: dict[str, set[str]] = {}

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

    def rpush(self, key: str, value: str):
        self._lists.setdefault(key, [])
        self._lists[key].append(value)
        return len(self._lists[key])

    def lpop(self, key: str):
        values = self._lists.get(key, [])
        if not values:
            return None
        return values.pop(0)

    def brpoplpush(self, source: str, destination: str, timeout: int = 0):
        values = self._lists.get(source, [])
        if not values:
            return None
        item = values.pop()
        self._lists.setdefault(destination, [])
        self._lists[destination].insert(0, item)
        return item

    def lrem(self, key: str, count: int, value: str):
        values = self._lists.get(key, [])
        removed = 0
        if count >= 0:
            indices = [idx for idx, item in enumerate(values) if item == value]
            for idx in indices[:count if count > 0 else len(indices)]:
                values[idx] = None
                removed += 1
            self._lists[key] = [item for item in values if item is not None]
        return removed

    def sadd(self, key: str, value: str):
        self._sets.setdefault(key, set())
        before = len(self._sets[key])
        self._sets[key].add(value)
        return 1 if len(self._sets[key]) > before else 0

    def sismember(self, key: str, value: str):
        return value in self._sets.get(key, set())

    def expire(self, key: str, ttl_seconds: int):
        _ = (key, ttl_seconds)
        return True


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
    if engine.dialect.name == "sqlite":
        logger.info("Legacy runtime SQLite DDL patcher disabled; Alembic is the only migration source.")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_auto_migrations():
    logger.warning("run_auto_migrations is disabled. Use Alembic migrations only.")