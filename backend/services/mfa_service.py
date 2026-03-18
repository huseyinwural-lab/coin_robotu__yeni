from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
import resend
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.security import create_access_token
from models import AuthMfaChallenge, User, UserMfaPreference

MFA_ALLOWED_METHODS = {"totp", "email"}
MFA_CHALLENGE_TTL_MINUTES = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _normalize_methods(values: list[str] | None) -> list[str]:
    normalized = []
    for value in values or []:
        method = str(value or "").strip().lower()
        if method in MFA_ALLOWED_METHODS and method not in normalized:
            normalized.append(method)
    return normalized


def _ensure_mfa_tables(db: Session):
    for model in (UserMfaPreference, AuthMfaChallenge):
        try:
            model.__table__.create(bind=db.bind, checkfirst=True)
        except Exception:
            continue


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
        "email_otp_verified": bool(pref.email_otp_verified),
        "updated_at": pref.updated_at,
    }


def update_mfa_settings(db: Session, user_id: str, *, is_enabled: bool, enabled_methods: list[str]) -> dict:
    pref = _get_or_create_preference(db, user_id)
    methods = _normalize_methods(enabled_methods)

    if is_enabled and not methods:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mfa_method_required")

    if is_enabled and "totp" in methods:
        if not pref.totp_secret:
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


def _send_email_otp(email: str, code: str) -> str:
    resend_api_key = os.environ.get("RESEND_API_KEY")
    sender_email = os.environ.get("PASSWORD_RESET_FROM_EMAIL")
    to_override = os.environ.get("PASSWORD_RESET_TO_OVERRIDE")
    to_email = str(to_override or email).strip()

    if not resend_api_key or not sender_email or not to_email:
        return "PREVIEW"

    resend.api_key = resend_api_key
    params = {
        "from": sender_email,
        "to": [to_email],
        "subject": "XILO MFA Doğrulama Kodu",
        "html": (
            "<div style='font-family:Arial,sans-serif;line-height:1.5'>"
            "<h3>MFA doğrulama kodu</h3>"
            f"<p><b>{code}</b></p>"
            "<p>Kod 10 dakika geçerlidir.</p>"
            "</div>"
        ),
    }
    try:
        resend.Emails.send(params)
    except Exception:
        return "FAILED"
    return "SENT"


def start_mfa_challenge_if_required(db: Session, *, user: User) -> dict | None:
    pref = _get_or_create_preference(db, user.id)
    methods = _normalize_methods(pref.enabled_methods)
    if not pref.is_enabled or not methods:
        return None

    challenge_token = secrets.token_urlsafe(32)
    now = _now()
    email_code = f"{secrets.randbelow(900000) + 100000}"
    email_delivery_status = "NOT_REQUIRED"

    if "email" in methods:
        email_delivery_status = _send_email_otp(user.email, email_code)

    challenge = AuthMfaChallenge(
        user_id=user.id,
        challenge_token_hash=_hash_token(challenge_token),
        allowed_methods=methods,
        email_otp_hash=_hash_token(email_code) if "email" in methods else None,
        email_delivery_status=email_delivery_status,
        expires_at=now + timedelta(minutes=MFA_CHALLENGE_TTL_MINUTES),
    )
    db.add(challenge)
    db.commit()

    return {
        "mfa_required": True,
        "mfa_challenge_token": challenge_token,
        "mfa_methods": methods,
        "mfa_expires_at": challenge.expires_at,
        "email_delivery_status": email_delivery_status,
        "email_code_preview": email_code if email_delivery_status != "SENT" and "email" in methods else None,
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
    allowed_methods = _normalize_methods(row.allowed_methods)
    if normalized_method not in allowed_methods:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mfa_method_not_allowed")

    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")

    normalized_code = str(code or "").strip()
    if normalized_method == "email":
        if _hash_token(normalized_code) != str(row.email_otp_hash or ""):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_email_otp")
    elif normalized_method == "totp":
        pref = _get_or_create_preference(db, user.id)
        if not pref.totp_secret or not pref.totp_verified:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="totp_not_ready")
        valid_totp = pyotp.TOTP(pref.totp_secret).verify(normalized_code, valid_window=1)
        if not valid_totp:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_totp_code")

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
