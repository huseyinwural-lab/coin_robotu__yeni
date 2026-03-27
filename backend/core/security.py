from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: str,
    role: str,
    email: str,
    *,
    mfa_verified: bool = False,
    device_id: str,
    mfa_verified_at: datetime | None = None,
    ip_hash: str | None = None,
    device_fingerprint: str | None = None,
    step_up_at: datetime | None = None,
    step_up_scope: list[str] | None = None,
) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    verified_at = mfa_verified_at or (datetime.now(timezone.utc) if mfa_verified else None)
    payload = {
        "sub": subject,
        "role": role,
        "email": email,
        "exp": expire_at,
        "mfa_verified": bool(mfa_verified),
        "device_id": str(device_id or "").strip(),
        "mfa_verified_at": int(verified_at.timestamp()) if verified_at else None,
        "ip_hash": str(ip_hash or "").strip() or None,
        "device_fingerprint": str(device_fingerprint or "").strip() or None,
        "step_up_at": int((step_up_at or verified_at).timestamp()) if (step_up_at or verified_at) else None,
        "step_up_scope": [str(scope).strip() for scope in (step_up_scope or []) if str(scope).strip()],
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc