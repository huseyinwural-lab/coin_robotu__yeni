import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.users.user_exchange_connector import (
    credential_fingerprint,
    decrypt_exchange_secret,
    encrypt_exchange_secret,
    get_or_create_user_exchange_setting,
    mask_secret,
    upsert_user_exchange_connection,
)
from models import UserExchangeConnection
from services.venue_service import check_user_venue_access, seed_binance_venue_registry


def _now():
    return datetime.now(timezone.utc)


def _normalize_market_type(market_type: str | None) -> str:
    candidate = (market_type or "spot").strip().lower()
    return candidate if candidate in {"spot", "futures"} else "spot"


def _normalize_environment(environment: str | None) -> str:
    candidate = (environment or "testnet").strip().lower()
    return candidate if candidate in {"testnet", "live"} else "testnet"


def _default_readiness_snapshot(db: Session, user_id: str, exchange: str, market_type: str, environment: str) -> dict:
    seed_binance_venue_registry(db)
    allowed, venue_state, capability_match, reason_codes = check_user_venue_access(
        db,
        user_id,
        exchange,
        market_type,
        environment,
    )
    return {
        "allowed": allowed,
        "venue_state": venue_state,
        "capability_match": capability_match,
        "reason_codes": reason_codes,
        "snapshot_at": _now().isoformat(),
    }


def _serialize_connection(row: UserExchangeConnection) -> dict:
    api_key = decrypt_exchange_secret(row.api_key_encrypted)
    api_secret = decrypt_exchange_secret(row.api_secret_encrypted)
    return {
        "id": row.id,
        "user_id": row.user_id,
        "account_label": row.account_label,
        "exchange": row.exchange,
        "market_type": row.market_type,
        "environment": row.environment,
        "is_default": bool(row.is_default),
        "readiness_snapshot": row.readiness_snapshot or {},
        "permission_snapshot": row.permission_snapshot or [],
        "has_api_key": bool(row.api_key_encrypted),
        "has_api_secret": bool(row.api_secret_encrypted),
        "masked_api_key": mask_secret(api_key),
        "credential_fingerprint": credential_fingerprint(api_key, api_secret),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _bootstrap_from_legacy(db: Session, user_id: str) -> None:
    existing = db.query(UserExchangeConnection).filter(UserExchangeConnection.user_id == user_id).first()
    if existing is not None:
        return

    legacy = get_or_create_user_exchange_setting(db, user_id)
    row = UserExchangeConnection(
        id=str(uuid.uuid4()),
        user_id=user_id,
        account_label="default",
        exchange=(legacy.exchange or "binance").strip().lower(),
        market_type="spot",
        environment=(legacy.mode or "testnet").strip().lower(),
        is_default=True,
        readiness_snapshot={},
        permission_snapshot=legacy.permissions_snapshot or [],
        api_key_encrypted=legacy.api_key_encrypted or "",
        api_secret_encrypted=legacy.api_secret_encrypted or "",
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(row)
    db.commit()


def _sync_legacy_default(db: Session, row: UserExchangeConnection) -> None:
    api_key = decrypt_exchange_secret(row.api_key_encrypted)
    api_secret = decrypt_exchange_secret(row.api_secret_encrypted)
    upsert_user_exchange_connection(
        db,
        user_id=row.user_id,
        exchange=row.exchange,
        mode=row.environment,
        api_key=api_key,
        api_secret=api_secret,
    )


def list_user_exchange_connections(db: Session, user_id: str) -> list[dict]:
    _bootstrap_from_legacy(db, user_id)
    rows = (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.user_id == user_id)
        .order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc())
        .all()
    )
    return [_serialize_connection(row) for row in rows]


def create_user_exchange_connection(
    db: Session,
    *,
    user_id: str,
    account_label: str,
    exchange: str,
    market_type: str,
    environment: str,
    is_default: bool,
    api_key: str | None,
    api_secret: str | None,
    permission_snapshot: list[str] | None,
    readiness_snapshot: dict | None,
) -> dict:
    _bootstrap_from_legacy(db, user_id)
    clean_label = (account_label or "").strip()
    if not clean_label:
        raise ValueError("account_label_required")

    existing_label = (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.user_id == user_id, UserExchangeConnection.account_label == clean_label)
        .first()
    )
    if existing_label is not None:
        raise ValueError("account_label_already_exists")

    normalized_exchange = (exchange or "binance").strip().lower()
    normalized_market_type = _normalize_market_type(market_type)
    normalized_environment = _normalize_environment(environment)

    has_any = db.query(UserExchangeConnection).filter(UserExchangeConnection.user_id == user_id).count() > 0
    make_default = bool(is_default) or not has_any
    if make_default:
        (
            db.query(UserExchangeConnection)
            .filter(UserExchangeConnection.user_id == user_id, UserExchangeConnection.is_default.is_(True))
            .update({"is_default": False}, synchronize_session=False)
        )

    row = UserExchangeConnection(
        id=str(uuid.uuid4()),
        user_id=user_id,
        account_label=clean_label,
        exchange=normalized_exchange,
        market_type=normalized_market_type,
        environment=normalized_environment,
        is_default=make_default,
        readiness_snapshot=readiness_snapshot
        if isinstance(readiness_snapshot, dict)
        else _default_readiness_snapshot(db, user_id, normalized_exchange, normalized_market_type, normalized_environment),
        permission_snapshot=permission_snapshot or [],
        api_key_encrypted=encrypt_exchange_secret(api_key or ""),
        api_secret_encrypted=encrypt_exchange_secret(api_secret or ""),
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if row.is_default:
        _sync_legacy_default(db, row)

    return _serialize_connection(row)


def update_user_exchange_connection(
    db: Session,
    *,
    user_id: str,
    connection_id: str,
    account_label: str | None,
    exchange: str | None,
    market_type: str | None,
    environment: str | None,
    is_default: bool | None,
    api_key: str | None,
    api_secret: str | None,
    permission_snapshot: list[str] | None,
    readiness_snapshot: dict | None,
) -> dict:
    row = (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.id == connection_id, UserExchangeConnection.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("connection_not_found")

    if account_label is not None:
        clean_label = account_label.strip()
        if not clean_label:
            raise ValueError("account_label_required")
        label_taken = (
            db.query(UserExchangeConnection)
            .filter(
                UserExchangeConnection.user_id == user_id,
                UserExchangeConnection.account_label == clean_label,
                UserExchangeConnection.id != row.id,
            )
            .first()
        )
        if label_taken is not None:
            raise ValueError("account_label_already_exists")
        row.account_label = clean_label

    if exchange is not None:
        row.exchange = (exchange or row.exchange).strip().lower()
    if market_type is not None:
        row.market_type = _normalize_market_type(market_type)
    if environment is not None:
        row.environment = _normalize_environment(environment)
    if permission_snapshot is not None:
        row.permission_snapshot = permission_snapshot
    if readiness_snapshot is not None:
        row.readiness_snapshot = readiness_snapshot
    else:
        row.readiness_snapshot = _default_readiness_snapshot(db, user_id, row.exchange, row.market_type, row.environment)

    if api_key is not None:
        row.api_key_encrypted = encrypt_exchange_secret(api_key)
    if api_secret is not None:
        row.api_secret_encrypted = encrypt_exchange_secret(api_secret)

    if is_default is True and not row.is_default:
        (
            db.query(UserExchangeConnection)
            .filter(UserExchangeConnection.user_id == user_id, UserExchangeConnection.is_default.is_(True))
            .update({"is_default": False}, synchronize_session=False)
        )
        row.is_default = True

    row.updated_at = _now()
    db.commit()
    db.refresh(row)

    if row.is_default:
        _sync_legacy_default(db, row)

    return _serialize_connection(row)


def set_default_user_exchange_connection(db: Session, *, user_id: str, connection_id: str) -> dict:
    row = (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.id == connection_id, UserExchangeConnection.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("connection_not_found")

    (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.user_id == user_id, UserExchangeConnection.is_default.is_(True))
        .update({"is_default": False}, synchronize_session=False)
    )
    row.is_default = True
    row.updated_at = _now()
    db.commit()
    db.refresh(row)

    _sync_legacy_default(db, row)
    return _serialize_connection(row)


def delete_user_exchange_connection(db: Session, *, user_id: str, connection_id: str) -> dict:
    row = (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.id == connection_id, UserExchangeConnection.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("connection_not_found")

    was_default = bool(row.is_default)
    db.delete(row)
    db.commit()

    replacement = None
    if was_default:
        replacement = (
            db.query(UserExchangeConnection)
            .filter(UserExchangeConnection.user_id == user_id)
            .order_by(UserExchangeConnection.updated_at.desc())
            .first()
        )
        if replacement is not None:
            replacement.is_default = True
            replacement.updated_at = _now()
            db.commit()
            db.refresh(replacement)
            _sync_legacy_default(db, replacement)

    return {
        "deleted": True,
        "connection_id": connection_id,
        "replacement_default_id": replacement.id if replacement is not None else None,
    }
