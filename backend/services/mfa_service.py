from __future__ import annotations

import hashlib
import os
import secrets
from base64 import b32decode, urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone

import pyotp
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from core.config import settings
from core.security import create_access_token
from db import redis_client
from models import AuthMfaChallenge, User, UserMfaBackupCode, UserMfaPreference, UserMfaSecurityState
from services.mfa_email_otp_service import send_mfa_email_otp

MFA_ALLOWED_METHODS = {"totp", "email_otp"}
MFA_CHALLENGE_TTL_MINUTES = 10
EMAIL_OTP_TTL_MINUTES = 5
MFA_GRACE_PERIOD_HOURS = 24
MFA_STEP_UP_TTL_MINUTES = 10
PRIVILEGED_MFA_ROLES = {"super_admin", "admin", "ops", "trader"}
BACKUP_CODE_HASHER = CryptContext(schemes=["bcrypt"], deprecated="auto")
MFA_SECRET_PREFIX = "mfa_aes:v1"
EMAIL_OTP_RESEND_LIMIT = 3
EMAIL_OTP_RATE_LIMIT_PER_MINUTE = 5


def _runtime_environment() -> str:
    return str(
        os.environ.get("APP_ENV")
        or os.environ.get("ENVIRONMENT")
        or os.environ.get("RUNTIME_ENV")
        or ""
    ).strip().lower()


def get_mfa_enforcement_context(*, user_email: str, endpoint_scope: str) -> dict:
    mode = str(os.environ.get("MFA_ENFORCEMENT_MODE") or "auto").strip().lower()
    runtime_env = _runtime_environment()
    is_production = runtime_env in {"prod", "production"}

    if mode == "enforce":
        base_required = True
    elif mode == "optional":
        base_required = False
    else:
        base_required = is_production

    enforcement_required = bool(base_required)
    return {
        "enforcement_required": bool(enforcement_required),
        "bypass_active": False,
        "bypass_reason": None,
        "environment": runtime_env or "unknown",
        "mode": mode,
        "endpoint_scope": endpoint_scope,
    }


def is_mfa_enforcement_required(*, user_email: str, endpoint_scope: str) -> bool:
    return bool(
        get_mfa_enforcement_context(
            user_email=user_email,
            endpoint_scope=endpoint_scope,
        ).get("enforcement_required")
    )


MFA_BACKUP_CODES_DEFAULT_COUNT = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _allow_email_code_preview() -> bool:
    runtime = _runtime_environment()
    return runtime not in {"prod", "production"}


def _generate_email_otp_code() -> str:
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(6))


def _check_email_otp_rate_limit(user_id: str, ip_address: str) -> None:
    key = f"mfa:email_otp:rate:{user_id}:{str(ip_address or 'unknown').strip().lower()}"
    count = int(redis_client.incr(key) or 1)
    redis_client.expire(key, 60)
    if count > EMAIL_OTP_RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="email_otp_rate_limited")


def _check_email_otp_resend_limit(challenge_hash: str, ttl_seconds: int) -> None:
    key = f"mfa:email_otp:resend:{challenge_hash}"
    count = int(redis_client.incr(key) or 1)
    redis_client.expire(key, max(int(ttl_seconds), 60))
    if count > EMAIL_OTP_RESEND_LIMIT:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="email_otp_resend_limit_exceeded")


def _is_privileged_role(user: User) -> bool:
    role_value = str(getattr(user.role, "value", user.role) or "").strip().lower()
    return role_value in PRIVILEGED_MFA_ROLES


def _looks_like_base32(raw: str) -> bool:
    candidate = str(raw or "").strip().upper().replace(" ", "")
    if len(candidate) < 16:
        return False
    try:
        b32decode(candidate, casefold=True)
        return True
    except Exception:
        return False


def _decrypt_totp_secret(raw_secret: str | None) -> str:
    stored = str(raw_secret or "").strip()
    if not stored:
        return ""
    if stored.startswith(f"{MFA_SECRET_PREFIX}:"):
        try:
            payload = stored[len(f"{MFA_SECRET_PREFIX}:") :]
            nonce_encoded, encrypted_encoded = payload.split(":", 1)
            nonce = _urlsafe_b64decode(nonce_encoded)
            encrypted = _urlsafe_b64decode(encrypted_encoded)
            return AESGCM(_mfa_secret_key()).decrypt(nonce, encrypted, None).decode()
        except Exception:
            return ""
    if _looks_like_base32(stored):
        return stored
    return ""


def _encrypt_totp_secret(secret: str) -> str:
    normalized = str(secret or "").strip()
    if not normalized:
        return ""
    nonce = os.urandom(12)
    encrypted = AESGCM(_mfa_secret_key()).encrypt(nonce, normalized.encode(), None)
    return f"{MFA_SECRET_PREFIX}:{_urlsafe_b64encode(nonce)}:{_urlsafe_b64encode(encrypted)}"


def _mfa_secret_key() -> bytes:
    return hashlib.sha256(str(settings.exchange_credentials_encryption_key or "").encode()).digest()


def _urlsafe_b64encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode()


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return urlsafe_b64decode((value + padding).encode())


def _normalize_methods(
    values: list[str] | None,
    *,
    include_backup: bool = False,
    include_grace_ack: bool = False,
) -> list[str]:
    allowed_methods = set(MFA_ALLOWED_METHODS)
    if include_backup:
        allowed_methods.add("backup_code")
    if include_grace_ack:
        allowed_methods.add("grace_ack")
    normalized = []
    for value in values or []:
        method = str(value or "").strip().lower()
        if method in allowed_methods and method not in normalized:
            normalized.append(method)
    return normalized


def _ensure_mfa_tables(db: Session):
    for model in (UserMfaPreference, AuthMfaChallenge, UserMfaBackupCode, UserMfaSecurityState):
        try:
            model.__table__.create(bind=db.bind, checkfirst=True)
        except Exception:
            continue


def _normalize_backup_code(raw_code: str) -> str:
    return "".join(ch for ch in str(raw_code or "").upper() if ch.isalnum())


def _generate_backup_codes(count: int) -> list[str]:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    rows: list[str] = []
    for _ in range(max(1, count)):
        block_a = "".join(secrets.choice(alphabet) for _ in range(4))
        block_b = "".join(secrets.choice(alphabet) for _ in range(4))
        rows.append(f"{block_a}-{block_b}")
    return rows


def _active_backup_codes_count(db: Session, user_id: str) -> int:
    _ensure_mfa_tables(db)
    return (
        db.query(UserMfaBackupCode)
        .filter(UserMfaBackupCode.user_id == user_id, UserMfaBackupCode.used_at.is_(None))
        .count()
    )


def _get_or_create_preference(db: Session, user_id: str) -> UserMfaPreference:
    _ensure_mfa_tables(db)
    row = db.query(UserMfaPreference).filter(UserMfaPreference.user_id == user_id).first()
    if row is not None:
        return row
    row = UserMfaPreference(user_id=user_id, is_enabled=False, enabled_methods=[])
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _get_or_create_security_state(db: Session, user_id: str) -> UserMfaSecurityState:
    _ensure_mfa_tables(db)
    row = db.query(UserMfaSecurityState).filter(UserMfaSecurityState.user_id == user_id).first()
    if row is not None:
        return row
    row = UserMfaSecurityState(user_id=user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _totp_ready(pref: UserMfaPreference) -> bool:
    return bool(pref.totp_verified and _decrypt_totp_secret(pref.totp_secret))


def _resolve_totp_timecode(secret: str, code: str, now: datetime, drift_windows: int = 1) -> int | None:
    normalized_code = "".join(ch for ch in str(code or "").strip() if ch.isdigit())
    if len(normalized_code) < 6:
        return None

    totp = pyotp.TOTP(secret)
    for offset in range(-drift_windows, drift_windows + 1):
        probe_time = now + timedelta(seconds=offset * 30)
        if totp.verify(normalized_code, for_time=probe_time, valid_window=0):
            return int(totp.timecode(probe_time))
    return None


def _verify_totp_and_apply_anti_replay(db: Session, *, user_id: str, secret: str, code: str, now: datetime) -> None:
    security_state = _get_or_create_security_state(db, user_id)
    matched_timecode = _resolve_totp_timecode(secret, code, now)
    if matched_timecode is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_totp_code")

    replay_hash = _hash_token(f"{str(code or '').strip()}::{matched_timecode}")
    if security_state.last_totp_code_hash and secrets.compare_digest(security_state.last_totp_code_hash, replay_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="totp_replay_detected")

    security_state.last_totp_code_hash = replay_hash
    security_state.last_totp_verified_at = now
    security_state.last_mfa_verified_at = now


def _backup_code_matches(stored_hash: str, normalized_code: str) -> bool:
    value = str(stored_hash or "")
    if value.startswith("$2"):
        try:
            return bool(BACKUP_CODE_HASHER.verify(normalized_code, value))
        except Exception:
            return False
    return secrets.compare_digest(value, _hash_token(normalized_code))


def _consume_backup_code_or_raise(db: Session, *, user_id: str, code: str, now: datetime) -> None:
    normalized_backup_code = _normalize_backup_code(code)
    if not normalized_backup_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_backup_code")

    candidates = (
        db.query(UserMfaBackupCode)
        .filter(UserMfaBackupCode.user_id == user_id, UserMfaBackupCode.used_at.is_(None))
        .all()
    )
    for row in candidates:
        if _backup_code_matches(row.code_hash, normalized_backup_code):
            row.used_at = now
            return

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_backup_code")


def _create_challenge(
    db: Session,
    *,
    user: User,
    challenge_methods: list[str],
    now: datetime,
    request_ip: str | None = None,
    challenge_reason: str | None = None,
) -> dict:
    challenge_token = secrets.token_urlsafe(32)
    ttl_minutes = EMAIL_OTP_TTL_MINUTES if "email_otp" in challenge_methods else MFA_CHALLENGE_TTL_MINUTES
    email_code_preview = None
    email_delivery_status = "DISABLED"
    email_otp_hash = None

    if "email_otp" in challenge_methods:
        _check_email_otp_rate_limit(user.id, str(request_ip or "unknown"))
        raw_email_code = _generate_email_otp_code()
        email_otp_hash = _hash_token(raw_email_code)
        try:
            send_mfa_email_otp(user.email, code=raw_email_code, ttl_minutes=ttl_minutes)
            email_delivery_status = "SENT"
        except Exception:
            email_delivery_status = "FAILED"
        if _allow_email_code_preview():
            email_code_preview = raw_email_code

    challenge = AuthMfaChallenge(
        user_id=user.id,
        challenge_token_hash=_hash_token(challenge_token),
        allowed_methods=challenge_methods,
        email_otp_hash=email_otp_hash,
        email_delivery_status=email_delivery_status,
        expires_at=now + timedelta(minutes=ttl_minutes),
    )
    db.add(challenge)
    db.commit()

    return {
        "mfa_required": True,
        "mfa_challenge_token": challenge_token,
        "mfa_methods": challenge_methods,
        "mfa_expires_at": challenge.expires_at,
        "email_delivery_status": email_delivery_status,
        "email_code_preview": email_code_preview,
        "mfa_grace_active": False,
        "mfa_grace_expires_at": None,
        "mfa_setup_required": False,
        "challenge_reason": challenge_reason,
    }


def _is_grace_expired(security_state: UserMfaSecurityState, now: datetime) -> bool:
    grace_expires_at = _to_utc(security_state.mfa_grace_expires_at)
    if grace_expires_at is None:
        return False
    return now > grace_expires_at


def get_mfa_settings(db: Session, user_id: str) -> dict:
    pref = _get_or_create_preference(db, user_id)
    methods = _normalize_methods(pref.enabled_methods)
    decrypted_secret = _decrypt_totp_secret(pref.totp_secret)
    return {
        "is_enabled": bool(pref.is_enabled),
        "enabled_methods": methods,
        "totp_configured": bool(decrypted_secret),
        "totp_verified": bool(pref.totp_verified),
        "email_otp_verified": False,
        "backup_codes_remaining": _active_backup_codes_count(db, user_id),
        "mfa_enabled_not_verified": bool(pref.is_enabled and not pref.totp_verified),
        "backup_download_required": bool(pref.totp_verified and _active_backup_codes_count(db, user_id) == 0),
        "updated_at": pref.updated_at,
    }


def regenerate_backup_codes(db: Session, *, user_id: str, count: int = MFA_BACKUP_CODES_DEFAULT_COUNT) -> dict:
    _ensure_mfa_tables(db)
    usable_count = max(4, min(int(count or MFA_BACKUP_CODES_DEFAULT_COUNT), 20))
    generated_codes = _generate_backup_codes(usable_count)

    db.query(UserMfaBackupCode).filter(UserMfaBackupCode.user_id == user_id).delete(synchronize_session=False)
    for item in generated_codes:
        normalized = _normalize_backup_code(item)
        db.add(
            UserMfaBackupCode(
                user_id=user_id,
                code_hash=BACKUP_CODE_HASHER.hash(normalized),
            )
        )
    db.commit()

    return {
        "generated_codes": generated_codes,
        "backup_codes_remaining": usable_count,
        "generated_at": _now(),
    }


def update_mfa_settings(db: Session, user_id: str, *, is_enabled: bool, enabled_methods: list[str]) -> dict:
    pref = _get_or_create_preference(db, user_id)
    methods = _normalize_methods(enabled_methods)

    if is_enabled and not methods:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mfa_method_required")

    if is_enabled and "totp" in methods:
        if not _decrypt_totp_secret(pref.totp_secret):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="totp_setup_required")
        if not pref.totp_verified:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="totp_verify_required")

    pref.enabled_methods = methods
    pref.is_enabled = bool(is_enabled and len(methods) > 0)
    pref.updated_at = _now()
    db.commit()
    db.refresh(pref)
    return get_mfa_settings(db, user_id)


def begin_totp_setup(db: Session, *, user: User) -> dict:
    pref = _get_or_create_preference(db, user.id)
    secret = _decrypt_totp_secret(pref.totp_secret)
    if pref.totp_verified or not secret:
        secret = pyotp.random_base32()
        pref.totp_secret = _encrypt_totp_secret(secret)
        pref.totp_verified = False
        pref.updated_at = _now()
        db.commit()
        db.refresh(pref)

    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="XILO")
    return {
        "secret": secret,
        "otpauth_uri": uri,
        "issuer": "XILO",
        "account_name": user.email,
    }


def verify_totp_setup(db: Session, *, user_id: str, code: str) -> dict:
    pref = _get_or_create_preference(db, user_id)
    secret = _decrypt_totp_secret(pref.totp_secret)
    if not secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="totp_not_initialized")

    now = _now()
    if _resolve_totp_timecode(secret, code, now) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_totp_code")

    security_state = _get_or_create_security_state(db, user_id)
    pref.totp_verified = True
    if "totp" not in _normalize_methods(pref.enabled_methods):
        pref.enabled_methods = [*_normalize_methods(pref.enabled_methods), "totp"]
    pref.is_enabled = True
    pref.updated_at = _now()
    security_state.mfa_grace_started_at = None
    security_state.mfa_grace_expires_at = None
    security_state.last_mfa_verified_at = now
    db.commit()
    db.refresh(pref)
    return get_mfa_settings(db, user_id)


def start_mfa_challenge_if_required(
    db: Session,
    *,
    user: User,
    force_challenge: bool = False,
    challenge_reason: str | None = None,
    request_ip: str | None = None,
) -> dict | None:
    pref = _get_or_create_preference(db, user.id)
    now = _now()
    role_is_privileged = _is_privileged_role(user)
    methods = _normalize_methods(pref.enabled_methods)
    backup_codes_remaining = _active_backup_codes_count(db, user.id)
    totp_ready = _totp_ready(pref)

    if force_challenge:
        challenge_methods: list[str] = []
        if totp_ready:
            challenge_methods = ["totp"]
            if backup_codes_remaining > 0:
                challenge_methods.append("backup_code")
            challenge_methods.append("email_otp")
        else:
            challenge_methods = ["email_otp"]

        payload = _create_challenge(
            db,
            user=user,
            challenge_methods=challenge_methods,
            now=now,
            request_ip=request_ip,
            challenge_reason=challenge_reason or "new_device",
        )
        if payload.get("email_delivery_status") == "FAILED" and challenge_methods == ["email_otp"]:
            return {
                "mfa_required": True,
                "login_blocked": True,
                "block_reason": "email_otp_delivery_failed",
                "email_delivery_status": "FAILED",
            }
        return payload

    if totp_ready:
        challenge_methods = ["totp"]
        if backup_codes_remaining > 0:
            challenge_methods.append("backup_code")
        payload = _create_challenge(
            db,
            user=user,
            challenge_methods=challenge_methods,
            now=now,
            request_ip=request_ip,
            challenge_reason=challenge_reason,
        )
        payload["mfa_setup_required"] = False
        return payload

    if role_is_privileged:
        security_state = _get_or_create_security_state(db, user.id)
        if security_state.mfa_grace_started_at is None or security_state.mfa_grace_expires_at is None:
            security_state.mfa_grace_started_at = now
            security_state.mfa_grace_expires_at = now + timedelta(hours=MFA_GRACE_PERIOD_HOURS)
            db.commit()
            db.refresh(security_state)

        grace_expires_at = _to_utc(security_state.mfa_grace_expires_at)
        if _is_grace_expired(security_state, now):
            return {
                "mfa_required": True,
                "login_blocked": True,
                "block_reason": "mfa_setup_required_after_grace",
                "mfa_setup_required": True,
                "mfa_grace_active": False,
                "mfa_grace_expires_at": grace_expires_at,
            }

        challenge_payload = _create_challenge(
            db,
            user=user,
            challenge_methods=["grace_ack"],
            now=now,
            request_ip=request_ip,
            challenge_reason="privileged_grace",
        )
        challenge_payload["mfa_grace_active"] = True
        challenge_payload["mfa_grace_expires_at"] = grace_expires_at
        challenge_payload["mfa_setup_required"] = True
        return challenge_payload

    if pref.is_enabled and methods:
        challenge_methods = list(methods)
        if "email_otp" not in challenge_methods:
            challenge_methods.append("email_otp")
        if backup_codes_remaining > 0 and "backup_code" not in challenge_methods:
            challenge_methods.append("backup_code")
        return _create_challenge(
            db,
            user=user,
            challenge_methods=challenge_methods,
            now=now,
            request_ip=request_ip,
            challenge_reason=challenge_reason,
        )

    return None


def _resolve_challenge_row(db: Session, challenge_token: str) -> AuthMfaChallenge:
    hashed = _hash_token(challenge_token)
    row = db.query(AuthMfaChallenge).filter(AuthMfaChallenge.challenge_token_hash == hashed).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_mfa_challenge")
    return row


def resolve_challenge_user(db: Session, *, challenge_token: str) -> User | None:
    try:
        row = _resolve_challenge_row(db, challenge_token)
    except HTTPException:
        return None
    return db.query(User).filter(User.id == row.user_id).first()


def resend_email_otp_for_challenge(
    db: Session,
    *,
    challenge_token: str,
    request_ip: str | None,
) -> dict:
    row = _resolve_challenge_row(db, challenge_token)
    if row.consumed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mfa_challenge_already_used")

    now = _now()
    expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mfa_challenge_expired")

    methods = _normalize_methods(row.allowed_methods, include_backup=True, include_grace_ack=True)
    if "email_otp" not in methods:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email_otp_not_enabled_for_challenge")

    ttl_seconds = int((expires_at - now).total_seconds())
    _check_email_otp_resend_limit(row.challenge_token_hash, ttl_seconds)

    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")

    _check_email_otp_rate_limit(user.id, str(request_ip or "unknown"))
    new_code = _generate_email_otp_code()
    row.email_otp_hash = _hash_token(new_code)

    try:
        send_mfa_email_otp(user.email, code=new_code, ttl_minutes=EMAIL_OTP_TTL_MINUTES)
        row.email_delivery_status = "SENT"
    except Exception:
        row.email_delivery_status = "FAILED"

    db.commit()

    return {
        "mfa_challenge_token": challenge_token,
        "email_delivery_status": row.email_delivery_status,
        "email_code_preview": new_code if _allow_email_code_preview() else None,
        "mfa_expires_at": row.expires_at,
    }


def _perform_mfa_method_verification(
    db: Session,
    *,
    user: User,
    method: str,
    code: str,
    now: datetime,
    challenge_context: AuthMfaChallenge | None = None,
) -> dict:
    normalized_method = str(method or "").strip().lower()
    pref = _get_or_create_preference(db, user.id)
    role_is_privileged = _is_privileged_role(user)

    if normalized_method == "totp":
        secret = _decrypt_totp_secret(pref.totp_secret)
        if not secret or not pref.totp_verified:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="totp_not_ready")
        _verify_totp_and_apply_anti_replay(db, user_id=user.id, secret=secret, code=code, now=now)
        return {"mfa_verified": True}

    if normalized_method == "backup_code":
        _consume_backup_code_or_raise(db, user_id=user.id, code=code, now=now)
        security_state = _get_or_create_security_state(db, user.id)
        security_state.last_mfa_verified_at = now
        return {"mfa_verified": True}

    if normalized_method == "email_otp":
        if challenge_context is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email_otp_not_available")
        expected_hash = str(challenge_context.email_otp_hash or "").strip()
        if not expected_hash:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email_otp_not_available")
        normalized_code = "".join(ch for ch in str(code or "") if ch.isdigit())
        if len(normalized_code) != 6:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_email_otp_code")
        if not secrets.compare_digest(expected_hash, _hash_token(normalized_code)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_email_otp_code")
        challenge_context.email_otp_hash = None
        security_state = _get_or_create_security_state(db, user.id)
        security_state.last_mfa_verified_at = now
        return {"mfa_verified": True}

    if normalized_method == "grace_ack":
        if challenge_context is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="grace_ack_not_allowed")
        if not role_is_privileged:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="grace_ack_not_allowed")
        security_state = _get_or_create_security_state(db, user.id)
        if _is_grace_expired(security_state, now):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="mfa_setup_required_after_grace")
        if _totp_ready(pref):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="grace_ack_not_allowed")
        return {
            "mfa_verified": False,
            "mfa_grace_active": True,
            "mfa_grace_expires_at": _to_utc(security_state.mfa_grace_expires_at),
            "mfa_setup_required": True,
        }

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_mfa_method")


def verify_mfa_challenge(
    db: Session,
    *,
    challenge_token: str,
    method: str,
    code: str,
    device_id: str,
    session_context: dict | None = None,
) -> dict:
    _ensure_mfa_tables(db)
    row = _resolve_challenge_row(db, challenge_token)
    if row.consumed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mfa_challenge_already_used")

    now = _now()
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mfa_challenge_expired")

    normalized_method = str(method or "").strip().lower()
    allowed_methods = _normalize_methods(row.allowed_methods, include_backup=True, include_grace_ack=True)
    if normalized_method not in allowed_methods:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mfa_method_not_allowed")

    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")

    verification_context = _perform_mfa_method_verification(
        db,
        user=user,
        method=normalized_method,
        code=code,
        now=now,
        challenge_context=row,
    )
    mfa_verified = bool(verification_context.get("mfa_verified"))

    row.consumed_at = now
    db.commit()

    token = create_access_token(
        subject=user.id,
        role=user.role.value,
        email=user.email,
        mfa_verified=mfa_verified,
        mfa_verified_at=now if mfa_verified else None,
        device_id=device_id,
        ip_hash=(session_context or {}).get("ip_hash"),
        device_fingerprint=(session_context or {}).get("device_fingerprint"),
    )
    step_up_valid_until = now + timedelta(minutes=MFA_STEP_UP_TTL_MINUTES) if mfa_verified else None

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
        "mfa_required": False,
        "mfa_challenge_token": None,
        "mfa_methods": [],
        "mfa_verified": mfa_verified,
        "mfa_grace_active": bool(verification_context.get("mfa_grace_active")),
        "mfa_grace_expires_at": verification_context.get("mfa_grace_expires_at"),
        "mfa_setup_required": bool(verification_context.get("mfa_setup_required")),
        "step_up_required": not mfa_verified,
        "step_up_valid_until": step_up_valid_until,
    }


def verify_step_up_code(
    db: Session,
    *,
    user: User,
    method: str,
    code: str,
    device_id: str,
    session_context: dict | None = None,
) -> dict:
    now = _now()
    pref = _get_or_create_preference(db, user.id)
    if not _totp_ready(pref):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="step_up_mfa_not_configured")

    allowed_methods = ["totp"]
    if _active_backup_codes_count(db, user.id) > 0:
        allowed_methods.append("backup_code")

    normalized_method = str(method or "").strip().lower()
    if normalized_method not in allowed_methods:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="step_up_method_not_allowed")

    _perform_mfa_method_verification(db, user=user, method=normalized_method, code=code, now=now)
    db.commit()

    token = create_access_token(
        subject=user.id,
        role=user.role.value,
        email=user.email,
        mfa_verified=True,
        mfa_verified_at=now,
        device_id=device_id,
        ip_hash=(session_context or {}).get("ip_hash"),
        device_fingerprint=(session_context or {}).get("device_fingerprint"),
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
        "mfa_required": False,
        "mfa_verified": True,
        "step_up_required": False,
        "step_up_valid_until": now + timedelta(minutes=MFA_STEP_UP_TTL_MINUTES),
        "mfa_methods": [],
    }


def disable_user_mfa(db: Session, *, user_id: str) -> dict:
    pref = _get_or_create_preference(db, user_id)
    pref.is_enabled = False
    pref.enabled_methods = []
    pref.totp_secret = None
    pref.totp_verified = False
    pref.updated_at = _now()
    db.query(UserMfaBackupCode).filter(UserMfaBackupCode.user_id == user_id).delete(synchronize_session=False)
    db.query(AuthMfaChallenge).filter(AuthMfaChallenge.user_id == user_id, AuthMfaChallenge.consumed_at.is_(None)).update(
        {AuthMfaChallenge.consumed_at: _now()},
        synchronize_session=False,
    )
    db.commit()
    return get_mfa_settings(db, user_id)


def admin_reset_user_mfa(db: Session, *, user_id: str) -> dict:
    state = _get_or_create_security_state(db, user_id)
    settings_payload = disable_user_mfa(db, user_id=user_id)
    state.mfa_grace_started_at = _now()
    state.mfa_grace_expires_at = _now() + timedelta(hours=MFA_GRACE_PERIOD_HOURS)
    state.last_mfa_verified_at = None
    state.last_totp_code_hash = None
    state.last_totp_verified_at = None
    db.commit()
    settings_payload["mfa_grace_active"] = True
    settings_payload["mfa_grace_expires_at"] = _to_utc(state.mfa_grace_expires_at)
    return settings_payload


def create_authenticated_mfa_challenge(
    db: Session,
    *,
    user: User,
    request_ip: str | None,
    challenge_reason: str = "manual_challenge",
) -> dict:
    payload = start_mfa_challenge_if_required(
        db,
        user=user,
        force_challenge=True,
        challenge_reason=challenge_reason,
        request_ip=request_ip,
    )
    if payload is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mfa_challenge_not_available")
    if payload.get("login_blocked"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(payload.get("block_reason") or "mfa_challenge_blocked"))
    return payload
