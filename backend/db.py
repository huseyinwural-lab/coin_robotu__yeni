import logging
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import redis
from fastapi import HTTPException, status
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from core.config import settings
from core.db_determinism import enforce_postgresql_only

logger = logging.getLogger(__name__)


LOCALHOST_DATABASE_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


@dataclass
class DatabaseRuntimeState:
    configured: bool = False
    url_valid: bool = False
    initialized: bool = False
    reachable: bool = False
    last_error: str | None = None
    last_checked_at: str | None = None
    database_url: str | None = None


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

    def llen(self, key: str):
        if self._is_expired(key):
            return 0
        return len(self._lists.get(key, []))

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


_ENGINE_LOCK = threading.Lock()
_engine_instance: Engine | None = None
_session_factory: sessionmaker | None = None
_db_state = DatabaseRuntimeState()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mark_db_state(**kwargs) -> None:
    for key, value in kwargs.items():
        setattr(_db_state, key, value)
    _db_state.last_checked_at = _utc_now_iso()


def _sanitize_error(exc: Exception) -> str:
    return str(exc).strip()[:400] or exc.__class__.__name__


def _resolve_database_url() -> str:
    database_url = enforce_postgresql_only(settings.database_url, "db_engine")
    _mark_db_state(configured=bool(database_url), url_valid=False, database_url=database_url, last_error=None)
    parsed = make_url(database_url)

    if not parsed.host:
        raise RuntimeError("database_url_host_missing")
    host_is_local = str(parsed.host).strip().lower() in LOCALHOST_DATABASE_HOSTS
    allow_localhost = (
        str(os.getenv("ALLOW_LOCALHOST_DATABASE_URL", "") or "").strip().lower() in {"1", "true", "yes"}
        or str(os.getenv("CI", "") or "").strip().lower() in {"1", "true", "yes"}
        or bool(os.getenv("PYTEST_CURRENT_TEST"))
    )
    if host_is_local and not allow_localhost:
        raise RuntimeError("database_url_localhost_forbidden")
    if not parsed.database:
        raise RuntimeError("database_url_dbname_missing")

    normalized_url = database_url
    if host_is_local:
        try:
            normalized_url = parsed.update_query_dict({"sslmode": "disable"}).render_as_string(hide_password=False)
        except Exception:  # noqa: BLE001
            normalized_url = database_url

    _mark_db_state(url_valid=True, database_url=normalized_url, last_error=None)
    return normalized_url


def _create_and_verify_engine(database_url: str) -> Engine:
    connect_args = {"connect_timeout": 4} if database_url.startswith("postgresql") else {}
    parsed = make_url(database_url)
    host = str(parsed.host or "").strip().lower()
    use_null_pool = "pooler.supabase.com" in host
    if database_url.startswith("postgresql") and host not in LOCALHOST_DATABASE_HOSTS:
        connect_args["sslmode"] = "require"
        connect_args.setdefault("keepalives", 1)
        connect_args.setdefault("keepalives_idle", 30)
        connect_args.setdefault("keepalives_interval", 10)
        connect_args.setdefault("keepalives_count", 5)

    def _env_int(name: str, fallback: int) -> int:
        try:
            return int(str(os.environ.get(name, fallback)).strip())
        except Exception:
            return fallback

    base_pool_timeout = _env_int("DB_POOL_TIMEOUT", 30)
    base_pool_size = _env_int("DB_POOL_SIZE", 10)
    base_max_overflow = _env_int("DB_MAX_OVERFLOW", 20)
    base_pool_recycle = _env_int("DB_POOL_RECYCLE_SECONDS", 600)
    pooler_pool_timeout = _env_int("DB_POOLER_TIMEOUT", 20)
    pooler_pool_recycle = _env_int("DB_POOLER_RECYCLE_SECONDS", 180)

    engine_kwargs: dict = {
        "pool_pre_ping": True,
        "pool_recycle": base_pool_recycle,
        "connect_args": connect_args,
    }
    if use_null_pool:
        engine_kwargs.update(
            {
                "pool_timeout": pooler_pool_timeout,
                "pool_size": base_pool_size,
                "max_overflow": base_max_overflow,
                "pool_use_lifo": True,
                "pool_reset_on_return": "rollback",
                "pool_recycle": pooler_pool_recycle,
            }
        )
    else:
        engine_kwargs.update(
            {
                "pool_timeout": base_pool_timeout,
                "pool_size": base_pool_size,
                "max_overflow": base_max_overflow,
                "pool_use_lifo": True,
                "pool_reset_on_return": "rollback",
            }
        )

    last_error: Exception | None = None

    for attempt in range(3):
        candidate_engine = None
        try:
            candidate_engine = create_engine(
                database_url,
                **engine_kwargs,
            )
            with candidate_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return candidate_engine
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if candidate_engine is not None:
                try:
                    candidate_engine.dispose()
                except Exception:  # noqa: BLE001
                    pass
            if attempt < 2:
                time.sleep(0.6 * (attempt + 1))
                continue

    assert last_error is not None
    raise last_error


def init_db_engine(force: bool = False) -> Engine:
    global _engine_instance, _session_factory

    if _engine_instance is not None and not force:
        return _engine_instance

    with _ENGINE_LOCK:
        if _engine_instance is not None and not force:
            return _engine_instance

        try:
            database_url = _resolve_database_url()
            engine_obj = _create_and_verify_engine(database_url)
        except Exception as exc:
            _mark_db_state(initialized=False, reachable=False, last_error=_sanitize_error(exc))
            logger.error("DATABASE_INIT_FAILED", extra={"reason": _sanitize_error(exc)})
            raise RuntimeError(_sanitize_error(exc)) from exc

        _engine_instance = engine_obj
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=_engine_instance)
        _mark_db_state(initialized=True, reachable=True, last_error=None)
        logger.info("DATABASE_INIT_OK")
        return _engine_instance


def get_engine() -> Engine:
    return init_db_engine(force=False)


class EngineProxy:
    def __getattr__(self, item):
        return getattr(get_engine(), item)

    def __repr__(self):
        if _engine_instance is None:
            return "<EngineProxy state=uninitialized>"
        return repr(_engine_instance)


engine = EngineProxy()


def SessionLocal():
    global _session_factory
    if _session_factory is None:
        init_db_engine(force=False)
    assert _session_factory is not None
    return _session_factory()


def get_database_runtime_state() -> dict:
    return asdict(_db_state)


def is_database_ready() -> bool:
    return bool(_db_state.initialized and _db_state.reachable)


def verify_database_connection() -> None:
    try:
        db_engine = get_engine()
        with db_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        _mark_db_state(reachable=False, initialized=False, last_error=_sanitize_error(exc))
        raise
    _mark_db_state(reachable=True, initialized=True, last_error=None)


def reset_database_runtime_state_for_tests() -> None:
    global _engine_instance, _session_factory
    with _ENGINE_LOCK:
        _engine_instance = None
        _session_factory = None
    _mark_db_state(
        configured=False,
        url_valid=False,
        initialized=False,
        reachable=False,
        last_error=None,
        database_url=None,
    )


def _build_redis_client():
    ci_mode = str(os.getenv("CI", "") or "").strip().lower() in {"1", "true", "yes"}
    fail_fast_default = "false" if ci_mode else "true"
    redis_fail_fast = str(os.getenv("REDIS_FAIL_FAST", fail_fast_default) or fail_fast_default).strip().lower() in {
        "1",
        "true",
        "yes",
    }
    client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
        health_check_interval=30,
    )
    parsed = urlparse(settings.redis_url)
    redis_preview = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}/{str(parsed.path or '/').lstrip('/')}"
    try:
        client.ping()
        logger.warning("REDIS_CONNECT_OK", extra={"redis_url": redis_preview, "mode": "fail_fast"})
        return client
    except redis.exceptions.RedisError as exc:
        logger.error(
            "REDIS_CONNECT_FAIL",
            extra={
                "redis_url": redis_preview,
                "reason": _sanitize_error(exc),
                "mode": "fail_fast" if redis_fail_fast else "memory_fallback",
            },
        )
        if redis_fail_fast:
            raise RuntimeError("redis_init_failed_fail_fast") from exc
        logger.warning("REDIS_INMEMORY_FALLBACK_ENABLED", extra={"redis_url": redis_preview})
        return InMemoryRedis()


Base = declarative_base()
redis_client = _build_redis_client()

def get_db():
    if not is_database_ready() or _session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_not_ready",
        )
    try:
        db = SessionLocal()
    except Exception as exc:
        reason = _sanitize_error(exc)
        logger.error("DATABASE_SESSION_CREATE_FAILED", extra={"reason": reason})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"database_unavailable:{reason}",
        ) from exc
    try:
        yield db
    finally:
        db.close()


def run_auto_migrations():
    logger.warning("run_auto_migrations is disabled. Use Alembic migrations only.")