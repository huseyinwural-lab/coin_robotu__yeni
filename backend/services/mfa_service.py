from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.security import create_access_token
from models import AuthMfaChallenge, User, UserMfaBackupCode, UserMfaPreference, UserRole

MFA_ALLOWED_METHODS = {"totp"}
MFA_CHALLENGE_TTL_MINUTES = 10
MFA_BACKUP_CODES_DEFAULT_COUNT = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _normalize_methods(values: list[str] | None, *, include_backup: bool = False) -> list[str]:
    allowed_methods = set(MFA_ALLOWED_METHODS)
    if include_backup:
        allowed_methods.add("backup_code")
    normalized = []
    for value in values or []:
        method = str(value or "").strip().lower()
        if method in allowed_methods and method not in normalized:
            normalized.append(method)
    return normalized


def _ensure_mfa_tables(db: Session):
    for model in (UserMfaPreference, AuthMfaChallenge, UserMfaBackupCode):
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


def get_mfa_settings(db: Session, user_id: str) -> dict:
    pref = _get_or_create_preference(db, user_id)
    methods = _normalize_methods(pref.enabled_methods)
    return {
        "is_enabled": bool(pref.is_enabled),
        "enabled_methods": methods,
        "totp_configured": bool(pref.totp_secret),
        "totp_verified": bool(pref.totp_verified),
        "email_otp_verified": False,
        "backup_codes_remaining": _active_backup_codes_count(db, user_id),
        "updated_at": pref.updated_at,
    }


def regenerate_backup_codes(db: Session, *, user_id: str, count: int = MFA_BACKUP_CODES_DEFAULT_COUNT) -> dict:
    _ensure_mfa_tables(db)
    usable_count = max(4, min(int(count or MFA_BACKUP_CODES_DEFAULT_COUNT), 20))
    generated_codes = _generate_backup_codes(usable_count)

    db.query(UserMfaBackupCode).filter(UserMfaBackupCode.user_id == user_id).delete(synchronize_session=False)
    for item in generated_codes:
        db.add(
            UserMfaBackupCode(
                user_id=user_id,
                code_hash=_hash_token(_normalize_backup_code(item)),
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
    user = db.query(User).filter(User.id == user_id).first()
    methods = _normalize_methods(enabled_methods)

    if is_enabled and not methods:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mfa_method_required")

    if is_enabled and "totp" in methods:
        if not pref.totp_secret:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="totp_setup_required")
        if not pref.totp_verified:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="totp_verify_required")

    if user is not None and user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS}:
        if not is_enabled:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="admin_totp_mfa_required")
        if "totp" not in methods:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="admin_totp_mfa_required")

    pref.enabled_methods = methods
    pref.is_enabled = bool(is_enabled and len(methods) > 0)
    pref.updated_at = _now()
    db.commit()
    db.refresh(pref)
    return get_mfa_settings(db, user_id)


def begin_totp_setup(db: Session, *, user: User) -> dict:
    pref = _get_or_create_preference(db, user.id)
    secret = pyotp.random_base32()
    pref.totp_secret = secret
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
    if not pref.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="totp_not_initialized")

    valid = pyotp.TOTP(pref.totp_secret).verify(str(code or "").strip(), valid_window=1)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_totp_code")

    pref.totp_verified = True
    if "totp" not in _normalize_methods(pref.enabled_methods):
        pref.enabled_methods = [*_normalize_methods(pref.enabled_methods), "totp"]
    pref.updated_at = _now()
    db.commit()
    db.refresh(pref)
    return get_mfa_settings(db, user_id)


def start_mfa_challenge_if_required(db: Session, *, user: User) -> dict | None:
    pref = _get_or_create_preference(db, user.id)
    methods = _normalize_methods(pref.enabled_methods)
    if not pref.is_enabled or not methods:
        return None

    backup_codes_remaining = _active_backup_codes_count(db, user.id)
    challenge_methods = list(methods)
    if backup_codes_remaining > 0 and "backup_code" not in challenge_methods:
        challenge_methods.append("backup_code")

    challenge_token = secrets.token_urlsafe(32)
    now = _now()

    challenge = AuthMfaChallenge(
        user_id=user.id,
        challenge_token_hash=_hash_token(challenge_token),
        allowed_methods=challenge_methods,
        email_otp_hash=None,
        email_delivery_status="DISABLED",
        expires_at=now + timedelta(minutes=MFA_CHALLENGE_TTL_MINUTES),
    )
    db.add(challenge)
    db.commit()

    return {
        "mfa_required": True,
        "mfa_challenge_token": challenge_token,
        "mfa_methods": challenge_methods,
        "mfa_expires_at": challenge.expires_at,
        "email_delivery_status": "DISABLED",
        "email_code_preview": None,
    }


def verify_mfa_challenge(db: Session, *, challenge_token: str, method: str, code: str) -> dict:
    _ensure_mfa_tables(db)
    hashed = _hash_token(challenge_token)
    row = db.query(AuthMfaChallenge).filter(AuthMfaChallenge.challenge_token_hash == hashed).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_mfa_challenge")
    if row.consumed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mfa_challenge_already_used")

    now = _now()
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mfa_challenge_expired")

    normalized_method = str(method or "").strip().lower()
    allowed_methods = _normalize_methods(row.allowed_methods, include_backup=True)
    if normalized_method not in allowed_methods:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mfa_method_not_allowed")

    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")

    normalized_code = str(code or "").strip()
    if normalized_method == "totp":
        pref = _get_or_create_preference(db, user.id)
        if not pref.totp_secret or not pref.totp_verified:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="totp_not_ready")
        valid_totp = pyotp.TOTP(pref.totp_secret).verify(normalized_code, valid_window=1)
        if not valid_totp:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_totp_code")
    elif normalized_method == "backup_code":
        normalized_backup_code = _normalize_backup_code(normalized_code)
        backup_row = (
            db.query(UserMfaBackupCode)
            .filter(
                UserMfaBackupCode.user_id == user.id,
                UserMfaBackupCode.code_hash == _hash_token(normalized_backup_code),
                UserMfaBackupCode.used_at.is_(None),
            )
            .first()
        )
        if backup_row is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_backup_code")
        backup_row.used_at = now
    elif normalized_method == "email":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email_mfa_disabled_for_login")
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_mfa_method")

    row.consumed_at = now
    db.commit()

    token = create_access_token(subject=user.id, role=user.role.value, email=user.email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
        "mfa_required": False,
        "mfa_challenge_token": None,
        "mfa_methods": [],
    }
