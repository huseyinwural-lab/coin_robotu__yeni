import asyncio
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

import resend
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.security import hash_password
from models import User, UserOnboardingProfile

PASSWORD_RESET_TOKEN_TTL_MINUTES = 15


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _get_or_create_onboarding_profile(db: Session, user: User) -> UserOnboardingProfile:
    profile = db.query(UserOnboardingProfile).filter(UserOnboardingProfile.user_id == user.id).first()
    if profile is not None:
        return profile
    profile = UserOnboardingProfile(user_id=user.id, email_verified=False)
    db.add(profile)
    db.flush()
    return profile


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def validate_password_strength(new_password: str) -> None:
    password = str(new_password or "")
    if len(password) < 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password_min_length_10")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password_requires_uppercase")
    if not re.search(r"[a-z]", password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password_requires_lowercase")
    if not re.search(r"\d", password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password_requires_number")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password_requires_symbol")


def issue_password_reset_token(db: Session, email: str) -> dict:
    normalized_email = _normalize_email(email)
    if not normalized_email:
        return {"user": None, "token": None, "expires_at": None}

    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if user is None:
        return {"user": None, "token": None, "expires_at": None}

    profile = _get_or_create_onboarding_profile(db, user)
    now = datetime.now(timezone.utc)
    raw_token = secrets.token_urlsafe(42)
    profile.password_reset_token_hash = _token_hash(raw_token)
    profile.password_reset_requested_at = now
    profile.password_reset_expires_at = now + timedelta(minutes=PASSWORD_RESET_TOKEN_TTL_MINUTES)
    profile.updated_at = now
    db.commit()

    return {
        "user": user,
        "token": raw_token,
        "expires_at": profile.password_reset_expires_at,
    }


def consume_password_reset_token(db: Session, token: str, new_password: str) -> User:
    cleaned_token = str(token or "").strip()
    if not cleaned_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_or_expired_reset_token")

    validate_password_strength(new_password)

    profile = (
        db.query(UserOnboardingProfile)
        .filter(UserOnboardingProfile.password_reset_token_hash == _token_hash(cleaned_token))
        .first()
    )
    if profile is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_or_expired_reset_token")

    now = datetime.now(timezone.utc)
    expires_at = profile.password_reset_expires_at
    if expires_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_or_expired_reset_token")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_or_expired_reset_token")

    user = db.query(User).filter(User.id == profile.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_or_expired_reset_token")

    user.password_hash = hash_password(new_password)
    user.updated_at = now
    profile.password_reset_token_hash = None
    profile.password_reset_expires_at = None
    profile.password_reset_requested_at = None
    profile.updated_at = now
    db.commit()
    db.refresh(user)
    return user


def build_password_reset_link(token: str) -> str:
    redirect_url = os.environ.get("PASSWORD_RESET_REDIRECT_URL")
    if not redirect_url:
        raise RuntimeError("PASSWORD_RESET_REDIRECT_URL_missing")
    separator = "&" if "?" in redirect_url else "?"
    return f"{redirect_url}{separator}token={token}"


async def send_password_reset_email(recipient_email: str, reset_link: str) -> dict:
    resend_api_key = os.environ.get("RESEND_API_KEY")
    sender_email = os.environ.get("PASSWORD_RESET_FROM_EMAIL")
    to_override = os.environ.get("PASSWORD_RESET_TO_OVERRIDE")

    if not resend_api_key:
        raise RuntimeError("RESEND_API_KEY_missing")
    if not sender_email:
        raise RuntimeError("PASSWORD_RESET_FROM_EMAIL_missing")

    to_email = str(to_override or recipient_email).strip()
    if not to_email:
        raise RuntimeError("password_reset_recipient_missing")

    resend.api_key = resend_api_key
    params = {
        "from": sender_email,
        "to": [to_email],
        "subject": "Şifre Sıfırlama Talebi",
        "html": (
            "<div style='font-family:Arial,sans-serif;line-height:1.6'>"
            "<h2 style='margin:0 0 12px'>Şifre sıfırlama talebi</h2>"
            "<p>Şifrenizi sıfırlamak için aşağıdaki bağlantıya tıklayın. Bu bağlantı 15 dakika geçerlidir.</p>"
            f"<p><a href='{reset_link}' style='display:inline-block;padding:10px 16px;background:#f97316;color:#111827;text-decoration:none;border-radius:8px;font-weight:700'>"
            "Şifremi sıfırla</a></p>"
            f"<p style='word-break:break-all'><small>{reset_link}</small></p>"
            "<p>Eğer bu talebi siz yapmadıysanız bu e-postayı yok sayabilirsiniz.</p>"
            "</div>"
        ),
    }
    response = await asyncio.to_thread(resend.Emails.send, params)
    return {"id": response.get("id"), "to": to_email}
