from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
import logging

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
    PasswordResetRequestPayload,
    PasswordResetRequestResponse,
    PasswordResetConfirmPayload,
    PasswordResetConfirmResponse,
    OnboardingDecisionRequest,
)
from services.audit_service import create_audit_log
from services.admin_profile_service import change_admin_password, update_admin_profile
from services.mfa_service import get_mfa_enforcement_context, get_mfa_settings, start_mfa_challenge_if_required
from services.identity_control_service import (
    enforce_login_protection,
    get_or_create_identity_profile,
    list_active_sessions,
    record_login_failure,
    register_auth_session,
    revoke_session,
)
from services.password_reset_service import (
    build_password_reset_link,
    consume_password_reset_token,
    issue_password_reset_token,
    send_password_reset_email,
)
from services.onboarding_approval_service import execute_onboarding_decision
router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


class AdminProfileUpdateRequest(BaseModel):
    email: str | None = None
    full_name: str | None = None


class AdminPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class LocalLoginRequest(BaseModel):
    email: str
    password: str


GENERIC_PASSWORD_RESET_MESSAGE = (
    "Eğer e-posta kayıtlıysa şifre sıfırlama bağlantısı gönderildi. Lütfen gelen kutunuzu kontrol edin."
)


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
    request: Request,
    endpoint_scope: str,
    db: Session,
    target_role: UserRole | None = None,
    allowed_roles: set[UserRole] | None = None,
) -> AuthResponse:
    enforce_login_protection(db, request=request, endpoint_scope=endpoint_scope, email=payload.email)
    try:
        session = user_login_with_policy(db, payload, target_role=target_role, allowed_roles=allowed_roles)
    except HTTPException as exc:
        record_login_failure(
            db,
            request=request,
            endpoint_scope=endpoint_scope,
            email=payload.email,
            reason=str(exc.detail),
            user_id=None,
        )
        raise

    user = session.user
    identity_profile = get_or_create_identity_profile(db, user.id)
    if identity_profile.password_expires_at is not None:
        expires_at = identity_profile.password_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            record_login_failure(
                db,
                request=request,
                endpoint_scope=endpoint_scope,
                email=user.email,
                reason="password_rotation_required",
                user_id=user.id,
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="password_rotation_required")

    mfa_context = get_mfa_enforcement_context(user_email=user.email, endpoint_scope=endpoint_scope)
    if bool(mfa_context.get("bypass_active")):
        create_audit_log(
            db,
            action="MFA_ENFORCEMENT_BYPASS_ACTIVE",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            actor_role=user.role.value,
            severity="warning",
            details={
                "email": user.email,
                "reason": mfa_context.get("bypass_reason") or "allow_list",
                "environment": mfa_context.get("environment") or "unknown",
                "endpoint_scope": endpoint_scope,
            },
        )

    if bool(mfa_context.get("enforcement_required")):
        mfa_settings = get_mfa_settings(db, user.id)
        if not bool(mfa_settings.get("is_enabled")) or "totp" not in (mfa_settings.get("enabled_methods") or []):
            record_login_failure(
                db,
                request=request,
                endpoint_scope=endpoint_scope,
                email=user.email,
                reason="mfa_enforced_not_configured",
                user_id=user.id,
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="mfa_enforced_not_configured")

    mfa_payload = start_mfa_challenge_if_required(db, user=user)
    if mfa_payload:
        create_audit_log(
            db,
            action="user_login_mfa_required",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            actor_role=user.role.value,
            details={"email": user.email, "mfa_methods": mfa_payload.get("mfa_methods")},
        )
        return AuthResponse(
            access_token=None,
            token=None,
            token_type="mfa_challenge",
            role=user.role.value,
            user=user,
            mfa_required=True,
            mfa_challenge_token=mfa_payload.get("mfa_challenge_token"),
            mfa_methods=list(mfa_payload.get("mfa_methods") or []),
            mfa_expires_at=mfa_payload.get("mfa_expires_at"),
            email_delivery_status=mfa_payload.get("email_delivery_status"),
            email_code_preview=mfa_payload.get("email_code_preview"),
        )

    register_auth_session(db, user=user, access_token=session.access_token, request=request, commit=False)
    create_audit_log(
        db,
        action="user_login",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        actor_role=user.role.value,
        details={"email": user.email},
        commit=False,
    )
    db.commit()
    return AuthResponse(
        access_token=session.access_token,
        token=session.access_token,
        token_type="bearer",
        role=user.role.value,
        user=user,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LocalLoginRequest, request: Request, db: Session = Depends(get_db)):
    return _login_with_policy(payload, request, "login", db)


@router.post("/login/admin", response_model=AuthResponse)
def admin_login(payload: LocalLoginRequest, request: Request, db: Session = Depends(get_db)):
    return _login_with_policy(payload, request, "login_admin", db, allowed_roles={UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS})


@router.post("/login/user", response_model=AuthResponse)
def user_login(payload: LocalLoginRequest, request: Request, db: Session = Depends(get_db)):
    return _login_with_policy(payload, request, "login_user", db, target_role=UserRole.USER)


@router.get("/sessions/active")
def get_active_sessions(
    user_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = list_active_sessions(db, actor=current_user, user_id=user_id)
    return {"items": items, "total": len(items)}


class SessionRevokeRequest(BaseModel):
    reason: str = "manual_revoke"


@router.post("/sessions/{session_id}/revoke")
def revoke_active_session(
    session_id: str,
    payload: SessionRevokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return revoke_session(db, actor=current_user, session_id=session_id, reason=payload.reason)


@router.post("/password-reset/request", response_model=PasswordResetRequestResponse)
async def request_password_reset(payload: PasswordResetRequestPayload, db: Session = Depends(get_db)):
    issued = issue_password_reset_token(db, str(payload.email))
    user = issued.get("user")
    token = issued.get("token")

    if user is not None and token:
        delivery_status = "SENT"
        delivery_id = None
        try:
            reset_link = build_password_reset_link(token)
            delivery = await send_password_reset_email(user.email, reset_link)
            delivery_id = delivery.get("id")
        except Exception as exc:  # pragma: no cover - runtime network branch
            delivery_status = "FAILED"
            logger.warning("password_reset_email_failed", extra={"email": user.email, "error": str(exc)[:300]})

        create_audit_log(
            db,
            action="user_password_reset_requested",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            actor_role=user.role.value,
            details={
                "email": user.email,
                "delivery_status": delivery_status,
                "delivery_id": delivery_id,
            },
        )

    return PasswordResetRequestResponse(
        status="accepted",
        message=GENERIC_PASSWORD_RESET_MESSAGE,
    )


@router.post("/password-reset/confirm", response_model=PasswordResetConfirmResponse)
def confirm_password_reset(payload: PasswordResetConfirmPayload, db: Session = Depends(get_db)):
    user = consume_password_reset_token(db, token=payload.token, new_password=payload.new_password)
    create_audit_log(
        db,
        action="user_password_reset_completed",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        actor_role=user.role.value,
        details={"email": user.email},
    )
    return PasswordResetConfirmResponse(status="success", message="Şifreniz güncellendi. Giriş yapabilirsiniz.")


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
    payload: OnboardingDecisionRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    execute_onboarding_decision(
        db,
        user_id=user_id,
        actor=current_admin,
        decision="approve",
        reason=payload.reason,
        confirm_token=payload.confirm_token,
        decision_source="auth_legacy_manual",
    )
    user = db.query(User).filter(User.id == user_id).first()
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
    payload: OnboardingDecisionRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    execute_onboarding_decision(
        db,
        user_id=user_id,
        actor=current_admin,
        decision="reject",
        reason=payload.reason,
        confirm_token=payload.confirm_token,
        decision_source="auth_legacy_manual",
    )
    user = db.query(User).filter(User.id == user_id).first()
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