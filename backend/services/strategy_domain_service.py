import hashlib
import json
import time
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models import StrategyDefinition, StrategyVersion


_CACHE_TTL_SECONDS = 30
_strategy_cache: dict[str, tuple[float, str]] = {}
_version_cache: dict[str, tuple[float, str]] = {}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def build_version_hash(*, config_json: dict, strategy_id: str, version_number: int, config_schema_version: str) -> str:
    canonical = canonical_json(config_json)
    raw = f"{canonical}|{strategy_id}|{version_number}|{config_schema_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_strategy(db: Session, strategy_id: str) -> StrategyDefinition | None:
    row = db.query(StrategyDefinition).filter(StrategyDefinition.strategy_id == strategy_id).first()
    if row is not None:
        _strategy_cache[strategy_id] = (time.time(), strategy_id)
    return row


def get_version(db: Session, version_id: str) -> StrategyVersion | None:
    row = db.query(StrategyVersion).filter(StrategyVersion.version_id == version_id).first()
    if row is not None:
        _version_cache[version_id] = (time.time(), version_id)
    return row


def get_active_strategy_set(db: Session) -> list[StrategyDefinition]:
    return (
        db.query(StrategyDefinition)
        .filter(StrategyDefinition.status == "active")
        .order_by(StrategyDefinition.updated_at.desc())
        .all()
    )


def get_active_version(db: Session, strategy_id: str) -> StrategyVersion | None:
    strategy = get_strategy(db, strategy_id)
    if strategy is None or strategy.active_version_id is None:
        return None
    return get_version(db, strategy.active_version_id)


def create_strategy_definition(
    db: Session,
    *,
    name: str,
    code: str,
    description: str,
    created_by: str,
) -> StrategyDefinition:
    normalized_code = code.strip().lower()
    existing = db.query(StrategyDefinition).filter(StrategyDefinition.code == normalized_code).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="strategy_code_exists")

    row = StrategyDefinition(
        strategy_id=str(uuid.uuid4()),
        name=name.strip(),
        code=normalized_code,
        description=description.strip(),
        owner_type="admin",
        created_by=created_by,
        status="draft",
        created_at=_now_utc(),
        updated_at=_now_utc(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    _strategy_cache[row.strategy_id] = (time.time(), row.strategy_id)
    return row


def create_strategy_version(
    db: Session,
    *,
    strategy_id: str,
    config_json: dict,
    config_schema_version: str,
    created_by: str,
) -> StrategyVersion:
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    latest = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_number.desc())
        .first()
    )
    next_version = (latest.version_number + 1) if latest else 1
    version_hash = build_version_hash(
        config_json=config_json,
        strategy_id=strategy_id,
        version_number=next_version,
        config_schema_version=config_schema_version,
    )

    existing_same_hash = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id, StrategyVersion.version_hash == version_hash)
        .first()
    )
    if existing_same_hash is not None:
        _version_cache[existing_same_hash.version_id] = (time.time(), existing_same_hash.version_id)
        return existing_same_hash

    row = StrategyVersion(
        version_id=str(uuid.uuid4()),
        strategy_id=strategy_id,
        version_number=next_version,
        config_json=config_json,
        config_schema_version=config_schema_version,
        created_by=created_by,
        created_at=_now_utc(),
        version_hash=version_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    _version_cache[row.version_id] = (time.time(), row.version_id)
    return row


def activate_strategy_version(db: Session, *, strategy_id: str, version_id: str) -> StrategyDefinition:
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    version = get_version(db, version_id)
    if version is None or version.strategy_id != strategy_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_version_not_found")

    strategy.active_version_id = version_id
    strategy.status = "active"
    strategy.updated_at = _now_utc()
    db.commit()
    db.refresh(strategy)
    _strategy_cache[strategy.strategy_id] = (time.time(), strategy.strategy_id)
    return strategy


def archive_strategy(db: Session, *, strategy_id: str) -> StrategyDefinition:
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    strategy.status = "archived"
    strategy.updated_at = _now_utc()
    db.commit()
    db.refresh(strategy)
    _strategy_cache[strategy.strategy_id] = (time.time(), strategy.strategy_id)
    return strategy
