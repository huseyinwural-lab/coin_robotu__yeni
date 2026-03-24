from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.security import create_access_token, hash_password, verify_password
from models import User, UserOnboardingProfile, UserRole
from schemas import LoginRequest, RegisterRequest
from services.identity_control_service import get_or_create_identity_profile
from services.password_policy_service import validate_password_policy
from services.risk_policy_defaults_service import ensure_user_safe_default_risk_policy
from services.venue_service import ensure_user_venue_assignment


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
    validate_password_policy(payload.password, minimum_length=10)
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
    db.flush()
    first_name = (payload.first_name or "").strip()
    last_name = (payload.last_name or "").strip()
    full_name_from_parts = " ".join(part for part in [first_name, last_name] if part).strip()
    resolved_full_name = full_name_from_parts or (payload.full_name or "").strip() or None

    onboarding = UserOnboardingProfile(
        user_id=user.id,
        full_name=resolved_full_name,
        phone=(payload.phone or "").strip() or None,
        email_verified=False,
    )
    db.add(onboarding)
    db.commit()
    db.refresh(user)
    profile = get_or_create_identity_profile(db, user.id)
    profile.password_changed_at = datetime.now(timezone.utc)
    profile.password_expires_at = datetime.now(timezone.utc) + timedelta(days=90)
    db.commit()
    return user


def _onboarding_profile_for_user(db: Session, user: User) -> UserOnboardingProfile:
    row = db.query(UserOnboardingProfile).filter(UserOnboardingProfile.user_id == user.id).first()
    if row:
        return row
    row = UserOnboardingProfile(user_id=user.id, email_verified=False)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def request_email_verification_code(db: Session, email: str) -> UserOnboardingProfile:
    normalized_email = _normalize_email(email)
    user = db.query(User).filter(User.email == normalized_email, User.role == UserRole.USER).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı")

    profile = _onboarding_profile_for_user(db, user)
    now = datetime.now(timezone.utc)
    code = f"{secrets.randbelow(900000) + 100000}"
    profile.verification_code = code
    profile.verification_requested_at = now
    profile.verification_expires_at = now.replace(microsecond=0) + timedelta(minutes=15)
    profile.updated_at = now
    db.commit()
    db.refresh(profile)
    return profile


def verify_email_code(db: Session, email: str, code: str) -> UserOnboardingProfile:
    normalized_email = _normalize_email(email)
    user = db.query(User).filter(User.email == normalized_email, User.role == UserRole.USER).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı")

    profile = _onboarding_profile_for_user(db, user)
    now = datetime.now(timezone.utc)
    normalized_code = str(code or "").strip()

    if not profile.verification_code or normalized_code != profile.verification_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doğrulama kodu geçersiz")

    expires_at = profile.verification_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and now > expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doğrulama kodunun süresi doldu")

    profile.email_verified = True
    profile.verification_code = None
    profile.verification_expires_at = None
    profile.updated_at = now
    db.commit()
    db.refresh(profile)
    return profile


def onboarding_status_by_email(db: Session, email: str) -> dict:
    normalized_email = _normalize_email(email)
    user = db.query(User).filter(User.email == normalized_email, User.role == UserRole.USER).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı")

    profile = _onboarding_profile_for_user(db, user)
    verified = bool(profile.email_verified)
    approval = str(user.approval_status)
    active = bool(user.is_active)
    steps = [
        {"key": "account_created", "label": "Hesap oluşturuldu", "done": True},
        {"key": "email_verified", "label": "E-posta doğrulandı", "done": verified},
        {"key": "admin_approved", "label": "Admin onayı", "done": approval == "approved"},
        {"key": "login_ready", "label": "Girişe hazır", "done": verified and approval == "approved" and active},
    ]
    return {
        "email": user.email,
        "email_verified": verified,
        "approval_status": approval,
        "is_active": active,
        "full_name": profile.full_name,
        "phone": profile.phone,
        "steps": steps,
    }


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
    ensure_user_venue_assignment(
        db,
        user_id=user.id,
        exchange_code="binance",
        market_type="futures",
        environment="testnet",
        commit=False,
    )
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