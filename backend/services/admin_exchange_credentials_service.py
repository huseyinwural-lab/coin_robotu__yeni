import json
from datetime import datetime, timezone

from core.users.user_exchange_connector import mask_secret
from models import ExternalProviderCredential
from services.secret_provider_service import (
    decrypt_secret_value,
    encrypt_secret_value,
    revoke_secret_value,
    rotate_secret_value,
    secret_provider_name,
)


EXECUTION_CREDENTIALS_PROVIDER = "exchange_execution_credentials_v1"


DEFAULT_PAYLOAD = {
    "bybit_api_key": "",
    "bybit_secret": "",
    "bybit_live_api_key": "",
    "bybit_live_secret": "",
    "okx_api_key": "",
    "okx_secret": "",
    "okx_passphrase": "",
}


def _normalize(payload: dict | None) -> dict:
    normalized = {**DEFAULT_PAYLOAD, **(payload or {})}
    return {key: str(value or "").strip() for key, value in normalized.items()}


def _read_row_payload(row: ExternalProviderCredential | None) -> dict:
    if row is None or not row.api_key_encrypted:
        return dict(DEFAULT_PAYLOAD)
    decrypted = decrypt_secret_value(row.api_key_encrypted)
    if not decrypted:
        return dict(DEFAULT_PAYLOAD)
    try:
        parsed = json.loads(decrypted)
        if isinstance(parsed, dict):
            return _normalize(parsed)
    except Exception:
        return dict(DEFAULT_PAYLOAD)
    return dict(DEFAULT_PAYLOAD)


def _masked_view(payload: dict) -> dict:
    return {
        "bybit_api_key": mask_secret(payload.get("bybit_api_key")),
        "bybit_secret": mask_secret(payload.get("bybit_secret")),
        "bybit_live_api_key": mask_secret(payload.get("bybit_live_api_key")),
        "bybit_live_secret": mask_secret(payload.get("bybit_live_secret")),
        "okx_api_key": mask_secret(payload.get("okx_api_key")),
        "okx_secret": mask_secret(payload.get("okx_secret")),
        "okx_passphrase": mask_secret(payload.get("okx_passphrase")),
    }


def get_execution_credentials(db) -> dict:
    row = (
        db.query(ExternalProviderCredential)
        .filter(ExternalProviderCredential.provider == EXECUTION_CREDENTIALS_PROVIDER)
        .first()
    )
    payload = _read_row_payload(row)
    has_bybit_live = bool(payload.get("bybit_live_api_key") and payload.get("bybit_live_secret"))
    has_bybit_legacy = bool(payload.get("bybit_api_key") and payload.get("bybit_secret"))
    return {
        "provider": EXECUTION_CREDENTIALS_PROVIDER,
        "secret_provider": secret_provider_name(),
        "has_bybit_credentials": bool(has_bybit_live or has_bybit_legacy),
        "has_bybit_live_credentials": has_bybit_live,
        "has_okx_credentials": bool(payload.get("okx_api_key") and payload.get("okx_secret") and payload.get("okx_passphrase")),
        "masked": _masked_view(payload),
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


def upsert_execution_credentials(db, patch_payload: dict) -> dict:
    row = (
        db.query(ExternalProviderCredential)
        .filter(ExternalProviderCredential.provider == EXECUTION_CREDENTIALS_PROVIDER)
        .first()
    )
    if row is None:
        row = ExternalProviderCredential(provider=EXECUTION_CREDENTIALS_PROVIDER)
        db.add(row)
        db.flush()

    current = _read_row_payload(row)
    merged = _normalize({**current, **(patch_payload or {})})
    serialized = json.dumps(merged, ensure_ascii=False)

    old_reference = row.api_key_encrypted
    if old_reference:
        row.api_key_encrypted = rotate_secret_value(old_reference, serialized)
    else:
        row.api_key_encrypted = encrypt_secret_value(serialized)

    if decrypt_secret_value(row.api_key_encrypted) != serialized:
        raise ValueError("execution_credential_readback_verification_failed")

    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return get_execution_credentials(db)


def raw_execution_credentials(db) -> dict:
    row = (
        db.query(ExternalProviderCredential)
        .filter(ExternalProviderCredential.provider == EXECUTION_CREDENTIALS_PROVIDER)
        .first()
    )
    return _read_row_payload(row)


def execution_credentials_for_adapter(db) -> dict:
    payload = raw_execution_credentials(db)
    bybit_legacy_key = payload.get("bybit_api_key") or ""
    bybit_legacy_secret = payload.get("bybit_secret") or ""
    return {
        "bybit": {
            "api_key": bybit_legacy_key,
            "api_secret": bybit_legacy_secret,
            "live_api_key": payload.get("bybit_live_api_key") or bybit_legacy_key,
            "live_api_secret": payload.get("bybit_live_secret") or bybit_legacy_secret,
        },
        "okx": {
            "api_key": payload.get("okx_api_key") or "",
            "api_secret": payload.get("okx_secret") or "",
            "passphrase": payload.get("okx_passphrase") or "",
        },
    }


def revoke_execution_credentials(db) -> None:
    row = (
        db.query(ExternalProviderCredential)
        .filter(ExternalProviderCredential.provider == EXECUTION_CREDENTIALS_PROVIDER)
        .first()
    )
    if row and row.api_key_encrypted:
        try:
            revoke_secret_value(row.api_key_encrypted)
        except Exception:
            pass
        row.api_key_encrypted = None
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
