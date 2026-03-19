import hashlib
import os
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.orm import Session

from core.config import settings
from models import UserExchangeSetting

AES_PREFIX = "aesgcm:v1"


def _current_key_bytes() -> bytes:
    return hashlib.sha256(settings.exchange_credentials_encryption_key.encode()).digest()


def _legacy_key_candidates() -> list[bytes]:
    candidates: list[bytes] = []
    jwt_key = hashlib.sha256(settings.jwt_secret.encode()).digest()
    if jwt_key not in candidates:
        candidates.append(jwt_key)
    return candidates


def _fernet_from_bytes(key_bytes: bytes) -> Fernet:
    return Fernet(urlsafe_b64encode(key_bytes))


def _legacy_fernet() -> Fernet:
    return _fernet_from_bytes(_legacy_key_candidates()[0])


def _current_fernet() -> Fernet:
    return _fernet_from_bytes(_current_key_bytes())


def _aesgcm_from_bytes(key_bytes: bytes) -> AESGCM:
    return AESGCM(key_bytes)


def _aesgcm() -> AESGCM:
    return _aesgcm_from_bytes(_current_key_bytes())


def _b64encode(data: bytes) -> str:
    return urlsafe_b64encode(data).decode()


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return urlsafe_b64decode((data + padding).encode())


def encrypt_exchange_secret(raw: str) -> str:
    normalized = (raw or "").strip()
    if not normalized:
        return ""
    nonce = os.urandom(12)
    encrypted = _aesgcm().encrypt(nonce, normalized.encode(), None)
    return f"{AES_PREFIX}:{_b64encode(nonce)}:{_b64encode(encrypted)}"


def _decrypt_aes_payload(raw_encrypted: str) -> str:
    payload = raw_encrypted[len(f"{AES_PREFIX}:") :]
    nonce_encoded, encrypted_encoded = payload.split(":", 1)
    nonce = _b64decode(nonce_encoded)
    encrypted = _b64decode(encrypted_encoded)
    aes_keys = [_current_key_bytes(), *_legacy_key_candidates()]
    for key_bytes in aes_keys:
        try:
            return _aesgcm_from_bytes(key_bytes).decrypt(nonce, encrypted, None).decode()
        except Exception:
            continue
    raise ValueError("unable_to_decrypt_exchange_secret")


def decrypt_exchange_secret(raw_encrypted: str) -> str:
    cipher = (raw_encrypted or "").strip()
    if not cipher:
        return ""

    try:
        if cipher.startswith(f"{AES_PREFIX}:"):
            return _decrypt_aes_payload(cipher)
        fernet_candidates = [_current_fernet(), _legacy_fernet()]
        for fernet in fernet_candidates:
            try:
                return fernet.decrypt(cipher.encode()).decode()
            except Exception:
                continue
        return ""
    except Exception:
        return ""


def mask_secret(secret: str | None) -> str:
    value = (secret or "").strip()
    if not value:
        return "missing"
    if len(value) <= 7:
        return "***"
    return f"{value[:4]}***{value[-3:]}"


def credential_fingerprint(api_key: str | None, api_secret: str | None) -> str:
    key = (api_key or "").strip()
    secret = (api_secret or "").strip()
    if not key and not secret:
        return ""
    return hashlib.sha256(f"{key}:{secret}".encode()).hexdigest()[:12]


def get_or_create_user_exchange_setting(db: Session, user_id: str) -> UserExchangeSetting:
    settings_row = db.query(UserExchangeSetting).filter(UserExchangeSetting.user_id == user_id).first()
    if settings_row:
        return settings_row

    settings_row = UserExchangeSetting(
        id=str(uuid.uuid4()),
        user_id=user_id,
        exchange="binance",
        mode="testnet",
        api_key_encrypted="",
        api_secret_encrypted="",
        permissions_snapshot=[],
        can_trade_snapshot=None,
        last_validation_success=None,
        last_reason_codes=[],
    )
    db.add(settings_row)
    db.commit()
    db.refresh(settings_row)
    return settings_row


def upsert_user_exchange_connection(
    db: Session,
    *,
    user_id: str,
    exchange: str,
    mode: str,
    api_key: str,
    api_secret: str,
) -> UserExchangeSetting:
    settings_row = get_or_create_user_exchange_setting(db, user_id)
    settings_row.exchange = exchange.strip().lower()
    settings_row.mode = mode.strip().lower()
    settings_row.api_key_encrypted = encrypt_exchange_secret(api_key)
    settings_row.api_secret_encrypted = encrypt_exchange_secret(api_secret)
    settings_row.last_validation_success = None
    settings_row.last_reason_codes = []
    settings_row.validation_snapshot_id = None
    settings_row.validation_checked_at = None
    settings_row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings_row)
    return settings_row


def exchange_connection_view(settings_row: UserExchangeSetting) -> dict:
    api_key = decrypt_exchange_secret(settings_row.api_key_encrypted)
    api_secret = decrypt_exchange_secret(settings_row.api_secret_encrypted)
    return {
        "exchange": settings_row.exchange,
        "mode": settings_row.mode,
        "has_api_key": bool(settings_row.api_key_encrypted),
        "has_api_secret": bool(settings_row.api_secret_encrypted),
        "masked_api_key": mask_secret(api_key),
        "credential_fingerprint": credential_fingerprint(api_key, api_secret),
        "updated_at": settings_row.updated_at,
    }