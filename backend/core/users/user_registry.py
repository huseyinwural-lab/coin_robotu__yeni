from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.security import create_access_token, hash_password, verify_password
from models import User, UserRole
from schemas import LoginRequest, RegisterRequest
from services.risk_policy_defaults_service import ensure_user_safe_default_risk_policy


@dataclass
class UserLoginSession:
    user: User
    access_token: str


def _normalize_email(email: str) -> str:
    return email.strip()


def _ensure_user_can_login(user: User):
    if user.role == UserRole.USER and user.approval_status == "pending":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesabınız admin onayı bekliyor")
    if user.role == UserRole.USER and user.approval_status == "rejected":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Onay talebiniz reddedildi")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesap pasif durumda")


def register_user_account(db: Session, payload: RegisterRequest) -> User:
    normalized_email = _normalize_email(payload.email)
    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        email=normalized_email,
        password_hash=hash_password(payload.password),
        role=UserRole.USER,
        is_active=False,
        approval_status="pending",
        approval_requested_at=datetime.now(timezone.utc),
        approved_at=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def user_login_with_policy(
    db: Session,
    payload: LoginRequest,
    target_role: UserRole | None = None,
    allowed_roles: set[UserRole] | None = None,
) -> UserLoginSession:
    normalized_email = _normalize_email(payload.email)
    user = db.query(User).filter(User.email == normalized_email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if target_role and user.role != target_role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yanlış giriş paneli")
    if allowed_roles and user.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yanlış giriş paneli")

    _ensure_user_can_login(user)
    token = create_access_token(subject=user.id, role=user.role.value, email=user.email)
    return UserLoginSession(user=user, access_token=token)


def list_user_accounts_for_approval(db: Session, status_filter: str) -> list[User]:
    query = db.query(User).filter(User.role == UserRole.USER)
    if status_filter in {"pending", "approved", "rejected"}:
        query = query.filter(User.approval_status == status_filter)
    return query.order_by(User.approval_requested_at.asc()).all()


def approve_user_account(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.USER).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı")

    user.approval_status = "approved"
    user.is_active = True
    user.approved_at = datetime.now(timezone.utc)
    user.disabled_at = None
    ensure_user_safe_default_risk_policy(db, user.id, commit=False)
    db.commit()
    db.refresh(user)
    return user


def reject_user_account(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.USER).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı")

    user.approval_status = "rejected"
    user.is_active = False
    user.approved_at = None
    user.disabled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user