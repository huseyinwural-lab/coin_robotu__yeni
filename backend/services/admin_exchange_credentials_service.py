import json
from datetime import datetime, timezone

from core.users.user_exchange_connector import decrypt_exchange_secret, encrypt_exchange_secret, mask_secret
from models import ExternalProviderCredential


EXECUTION_CREDENTIALS_PROVIDER = "exchange_execution_credentials_v1"


DEFAULT_PAYLOAD = {
    "bybit_api_key": "",
    "bybit_secret": "",
    "bybit_testnet_api_key": "",
    "bybit_testnet_secret": "",
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
    decrypted = decrypt_exchange_secret(row.api_key_encrypted)
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
        "bybit_testnet_api_key": mask_secret(payload.get("bybit_testnet_api_key")),
        "bybit_testnet_secret": mask_secret(payload.get("bybit_testnet_secret")),
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
    has_bybit_testnet = bool(payload.get("bybit_testnet_api_key") and payload.get("bybit_testnet_secret"))
    has_bybit_live = bool(payload.get("bybit_live_api_key") and payload.get("bybit_live_secret"))
    has_bybit_legacy = bool(payload.get("bybit_api_key") and payload.get("bybit_secret"))
    return {
        "provider": EXECUTION_CREDENTIALS_PROVIDER,
        "has_bybit_credentials": bool(has_bybit_testnet or has_bybit_live or has_bybit_legacy),
        "has_bybit_testnet_credentials": has_bybit_testnet,
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
    row.api_key_encrypted = encrypt_exchange_secret(json.dumps(merged, ensure_ascii=False))
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
            "testnet_api_key": payload.get("bybit_testnet_api_key") or bybit_legacy_key,
            "testnet_api_secret": payload.get("bybit_testnet_secret") or bybit_legacy_secret,
            "live_api_key": payload.get("bybit_live_api_key") or "",
            "live_api_secret": payload.get("bybit_live_secret") or "",
        },
        "okx": {
            "api_key": payload.get("okx_api_key") or "",
            "api_secret": payload.get("okx_secret") or "",
            "passphrase": payload.get("okx_passphrase") or "",
        },
    }
