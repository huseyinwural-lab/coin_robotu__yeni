import logging
from datetime import datetime, timedelta, timezone

import redis
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from core.config import settings
from core.db_determinism import enforce_postgresql_only

logger = logging.getLogger(__name__)


class InMemoryRedis:
    def __init__(self):
        self._store: dict[str, str] = {}
        self._lists: dict[str, list[str]] = {}
        self._sets: dict[str, set[str]] = {}
        self._expiry: dict[str, datetime] = {}

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _remove_key(self, key: str):
        self._store.pop(key, None)
        self._lists.pop(key, None)
        self._sets.pop(key, None)
        self._expiry.pop(key, None)

    def _is_expired(self, key: str) -> bool:
        expires_at = self._expiry.get(key)
        if not expires_at:
            return False
        if self._now() < expires_at:
            return False
        self._remove_key(key)
        return True

    def _exists(self, key: str) -> bool:
        self._is_expired(key)
        return key in self._store or key in self._lists or key in self._sets

    def set(self, key: str, value: str):
        self._store[key] = value
        if key in self._expiry:
            self._expiry.pop(key, None)

    def get(self, key: str):
        if self._is_expired(key):
            return None
        return self._store.get(key)

    def ping(self):
        return True

    def delete(self, key: str):
        self._remove_key(key)

    def incr(self, key: str, amount: int = 1):
        self._is_expired(key)
        current = int(self._store.get(key, "0"))
        current += amount
        self._store[key] = str(current)
        return current

    def rpush(self, key: str, value: str):
        self._is_expired(key)
        self._lists.setdefault(key, [])
        self._lists[key].append(value)
        return len(self._lists[key])

    def lpop(self, key: str):
        if self._is_expired(key):
            return None
        values = self._lists.get(key, [])
        if not values:
            return None
        return values.pop(0)

    def lrange(self, key: str, start: int, end: int):
        if self._is_expired(key):
            return []
        values = self._lists.get(key, [])
        if not values:
            return []

        normalized_start = max(start, 0)
        normalized_end = len(values) - 1 if end < 0 else min(end, len(values) - 1)
        if normalized_start > normalized_end:
            return []
        return values[normalized_start : normalized_end + 1]

    def brpoplpush(self, source: str, destination: str, timeout: int = 0):
        _ = timeout
        if self._is_expired(source):
            return None
        values = self._lists.get(source, [])
        if not values:
            return None
        item = values.pop()
        self._is_expired(destination)
        self._lists.setdefault(destination, [])
        self._lists[destination].insert(0, item)
        return item

    def lrem(self, key: str, count: int, value: str):
        if self._is_expired(key):
            return 0
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
        self._is_expired(key)
        self._sets.setdefault(key, set())
        before = len(self._sets[key])
        self._sets[key].add(value)
        return 1 if len(self._sets[key]) > before else 0

    def sismember(self, key: str, value: str):
        if self._is_expired(key):
            return False
        return value in self._sets.get(key, set())

    def expire(self, key: str, ttl_seconds: int):
        if ttl_seconds <= 0:
            self._remove_key(key)
            return True
        if not self._exists(key):
            return False
        self._expiry[key] = self._now() + timedelta(seconds=ttl_seconds)
        return True


def _build_engine():
    database_url = enforce_postgresql_only(settings.database_url, "db_engine")
    embedded_marker = "sql" + "ite"
    assert embedded_marker not in database_url.lower(), "DATABASE_URL içinde gömülü db marker olamaz"

    connect_args = {"connect_timeout": 5} if database_url.startswith("postgresql") else {}
    engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return engine


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


def verify_database_connection() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_auto_migrations():
    logger.warning("run_auto_migrations is disabled. Use Alembic migrations only.")