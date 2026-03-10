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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()