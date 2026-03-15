from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.users.user_registry import (
    approve_user_account,
    list_user_accounts_for_approval,
    onboarding_status_by_email,
    register_user_account,
    reject_user_account,
    request_email_verification_code,
    verify_email_code,
    user_login_with_policy,
)
from db import get_db
from deps import get_current_user, require_admin
from models import User, UserRole
from schemas import (
    AuthOnboardingStatusResponse,
    AuthResponse,
    EmailVerificationRequest,
    EmailVerificationResponse,
    EmailVerificationVerifyRequest,
    RegisterRequest,
    UserResponse,
)
from services.audit_service import create_audit_log
from services.admin_profile_service import change_admin_password, update_admin_profile

router = APIRouter(prefix="/auth", tags=["auth"])


class AdminProfileUpdateRequest(BaseModel):
    email: str | None = None
    full_name: str | None = None


class AdminPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class LocalLoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register", response_model=UserResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    user = register_user_account(db, payload)

    create_audit_log(
        db,
        action="user_registration_requested",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        actor_role=user.role.value,
        severity="warning",
        details={"email": user.email, "approval_status": user.approval_status},
    )
    return user


@router.post("/email-verification/request", response_model=EmailVerificationResponse)
def request_email_verification(payload: EmailVerificationRequest, db: Session = Depends(get_db)):
    profile = request_email_verification_code(db, payload.email)
    return EmailVerificationResponse(
        status="code_sent",
        email=payload.email,
        email_verified=bool(profile.email_verified),
        expires_at=profile.verification_expires_at,
        verification_code=profile.verification_code,
        message="Doğrulama kodu oluşturuldu",
    )


@router.post("/email-verification/verify", response_model=EmailVerificationResponse)
def verify_email_verification(payload: EmailVerificationVerifyRequest, db: Session = Depends(get_db)):
    profile = verify_email_code(db, payload.email, payload.code)
    return EmailVerificationResponse(
        status="verified",
        email=payload.email,
        email_verified=bool(profile.email_verified),
        message="E-posta doğrulandı",
    )


@router.get("/onboarding-status", response_model=AuthOnboardingStatusResponse)
def get_auth_onboarding_status(email: str, db: Session = Depends(get_db)):
    payload = onboarding_status_by_email(db, email)
    return AuthOnboardingStatusResponse(**payload)


def _login_with_policy(
    payload: LocalLoginRequest,
    db: Session,
    target_role: UserRole | None = None,
    allowed_roles: set[UserRole] | None = None,
) -> AuthResponse:
    session = user_login_with_policy(db, payload, target_role=target_role, allowed_roles=allowed_roles)
    user = session.user
    create_audit_log(
        db,
        action="user_login",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        actor_role=user.role.value,
        details={"email": user.email},
    )
    return AuthResponse(access_token=session.access_token, token_type="bearer", user=user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LocalLoginRequest, db: Session = Depends(get_db)):
    return _login_with_policy(payload, db)


@router.post("/login/admin", response_model=AuthResponse)
def admin_login(payload: LocalLoginRequest, db: Session = Depends(get_db)):
    return _login_with_policy(payload, db, allowed_roles={UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS})


@router.post("/login/user", response_model=AuthResponse)
def user_login(payload: LocalLoginRequest, db: Session = Depends(get_db)):
    return _login_with_policy(payload, db, target_role=UserRole.USER)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/admin/profile", response_model=UserResponse)
def patch_admin_profile(
    payload: AdminProfileUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    updated = update_admin_profile(
        db,
        current_admin,
        email=payload.email,
        full_name=payload.full_name,
    )
    create_audit_log(
        db,
        action="admin_profile_updated",
        entity_type="user",
        entity_id=updated.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"email": updated.email},
    )
    return updated


@router.post("/admin/password/change", response_model=UserResponse)
def post_admin_password_change(
    payload: AdminPasswordChangeRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    updated = change_admin_password(
        db,
        current_admin,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    create_audit_log(
        db,
        action="admin_password_changed",
        entity_type="user",
        entity_id=updated.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
    )
    return updated


@router.get("/admin/user-approval-requests", response_model=list[UserResponse])
def list_user_approval_requests(
    status_filter: str = Query(default="pending", alias="status"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_user_accounts_for_approval(db, status_filter)


@router.post("/admin/user-approval-requests/{user_id}/approve", response_model=UserResponse)
def approve_user_request(
    user_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = approve_user_account(db, user_id)
    create_audit_log(
        db,
        action="user_approval_approved",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"email": user.email},
    )
    return user


@router.post("/admin/user-approval-requests/{user_id}/reject", response_model=UserResponse)
def reject_user_request(
    user_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = reject_user_account(db, user_id)
    create_audit_log(
        db,
        action="user_approval_rejected",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"email": user.email},
    )
    return user