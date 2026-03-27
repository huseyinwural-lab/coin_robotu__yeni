from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
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
from core.security import create_access_token
from db import get_db
from deps import get_current_user, require_admin
from models import User, UserRole
from schemas import (
    AuthOnboardingStatusResponse,
    AuthResponse,
    AuthStepUpVerifyRequest,
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
from services.auth_policy_service import is_temporary_mfa_bypass_user
from services.admin_profile_service import change_admin_password, update_admin_profile
from services.auth_session_security_service import resolve_or_create_device_id, set_device_cookie
from services.mfa_service import start_mfa_challenge_if_required, verify_step_up_code
from services.identity_control_service import (
    enforce_login_protection,
    get_or_create_identity_profile,
    is_known_device,
    list_active_sessions,
    record_login_failure,
    record_login_success,
    register_auth_session,
    resolve_device_fingerprint,
    resolve_ip_hash,
    revoke_session,
)
from services.risk_policy_service import evaluate_request_risk, standardized_risk_response
from services.security_audit_context_service import build_security_audit_context
from services.suspicious_activity_service import create_risk_event, maybe_create_suspicious_alert
from services.password_reset_service import (
    build_password_reset_link,
    consume_password_reset_token,
    issue_password_reset_token,
    send_password_reset_email,
)
from services.onboarding_approval_service import execute_onboarding_decision
router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)
AUTH_PROTECTION_SCOPE = "auth_access"
MANDATORY_MFA_ROLES = {UserRole.OPS}


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
    response: Response,
    endpoint_scope: str,
    db: Session,
    target_role: UserRole | None = None,
    allowed_roles: set[UserRole] | None = None,
) -> AuthResponse:
    audit_context = build_security_audit_context(request)
    enforce_login_protection(db, request=request, endpoint_scope=AUTH_PROTECTION_SCOPE, email=payload.email)
    try:
        session = user_login_with_policy(db, payload, target_role=target_role, allowed_roles=allowed_roles)
    except HTTPException as exc:
        record_login_failure(
            db,
            request=request,
            endpoint_scope=AUTH_PROTECTION_SCOPE,
            email=payload.email,
            reason=str(exc.detail),
            user_id=None,
        )
        raise

    user = session.user
    current_device_fingerprint = resolve_device_fingerprint(request)
    is_new_device = not is_known_device(db, user_id=user.id, device_fingerprint=current_device_fingerprint)
    risk_eval = evaluate_request_risk(db, user=user, request=request, action_name="login")
    mandatory_mfa = user.role in MANDATORY_MFA_ROLES
    risk_requires_challenge = bool(risk_eval.requires_step_up)
    temporary_bypass = is_temporary_mfa_bypass_user(user.email)
    requires_challenge = bool((mandatory_mfa or risk_eval.requires_step_up) and not temporary_bypass)

    risk_event = create_risk_event(
        db,
        user=user,
        action_name="login",
        risk_level=risk_eval.risk_level,
        risk_reasons=risk_eval.risk_reasons,
        requires_step_up=requires_challenge,
        ip_address=(risk_eval.context.get("context") or {}).get("ip_address"),
        country_iso=(risk_eval.context.get("context") or {}).get("country_iso"),
        device_fingerprint=current_device_fingerprint,
        metadata={"mandatory_mfa": mandatory_mfa, "new_device": is_new_device},
    )
    maybe_create_suspicious_alert(db, user=user, risk_event=risk_event)

    session_context = {
        "ip_hash": resolve_ip_hash(request),
        "device_fingerprint": current_device_fingerprint,
    }
    identity_profile = get_or_create_identity_profile(db, user.id)
    if identity_profile.password_expires_at is not None:
        expires_at = identity_profile.password_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            record_login_failure(
                db,
                request=request,
                endpoint_scope=AUTH_PROTECTION_SCOPE,
                email=user.email,
                reason="password_rotation_required",
                user_id=user.id,
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="password_rotation_required")

    device_id, _ = resolve_or_create_device_id(request)

    mfa_payload = None
    if not temporary_bypass:
        mfa_payload = start_mfa_challenge_if_required(
            db,
            user=user,
            force_challenge=risk_requires_challenge,
            challenge_reason=(risk_eval.risk_reasons[0] if risk_eval.risk_reasons else ("mandatory_mfa" if mandatory_mfa else "standard_login")),
            request_ip=audit_context.get("ip_address"),
        )
    if mfa_payload:
        if bool(mfa_payload.get("login_blocked")):
            block_reason = str(mfa_payload.get("block_reason") or "mfa_setup_required_after_grace")
            record_login_failure(
                db,
                request=request,
                endpoint_scope=AUTH_PROTECTION_SCOPE,
                email=user.email,
                reason=block_reason,
                user_id=user.id,
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=block_reason)

        set_device_cookie(response, request, device_id=device_id)
        create_audit_log(
            db,
            action="user_login_mfa_required",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            actor_role=user.role.value,
            details={
                "email": user.email,
                "mfa_methods": mfa_payload.get("mfa_methods"),
                **audit_context,
                "new_device": is_new_device,
            },
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
            mfa_grace_active=bool(mfa_payload.get("mfa_grace_active")),
            mfa_grace_expires_at=mfa_payload.get("mfa_grace_expires_at"),
            mfa_setup_required=bool(mfa_payload.get("mfa_setup_required")),
            requires_step_up=True,
            risk_level=risk_eval.risk_level,
            risk_reasons=list(risk_eval.risk_reasons or []),
            challenge_reason=mfa_payload.get("challenge_reason") or (risk_eval.risk_reasons[0] if risk_eval.risk_reasons else None),
            email_delivery_status=mfa_payload.get("email_delivery_status"),
            email_code_preview=mfa_payload.get("email_code_preview"),
        )

    access_token = create_access_token(
        subject=user.id,
        role=user.role.value,
        email=user.email,
        mfa_verified=False,
        device_id=device_id,
        ip_hash=session_context.get("ip_hash"),
        device_fingerprint=session_context.get("device_fingerprint"),
        step_up_scope=["auth_login"],
    )
    set_device_cookie(response, request, device_id=device_id)
    register_auth_session(db, user=user, access_token=access_token, request=request, commit=False)
    record_login_success(
        db,
        request=request,
        endpoint_scope=AUTH_PROTECTION_SCOPE,
        email=user.email,
        user=user,
        identity_profile=identity_profile,
        commit=False,
    )
    create_audit_log(
        db,
        action="user_login",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        actor_role=user.role.value,
        details={"email": user.email, **audit_context, "new_device": is_new_device},
        commit=False,
    )
    db.commit()
    return AuthResponse(
        access_token=access_token,
        token=access_token,
        token_type="bearer",
        role=user.role.value,
        user=user,
        mfa_verified=False,
        requires_step_up=False,
        risk_level=risk_eval.risk_level,
        risk_reasons=list(risk_eval.risk_reasons or []),
        step_up_scope=["auth_login"],
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LocalLoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    return _login_with_policy(payload, request, response, "login", db)


@router.post("/login/admin", response_model=AuthResponse)
def admin_login(payload: LocalLoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    return _login_with_policy(
        payload,
        request,
        response,
        "login_admin",
        db,
        allowed_roles={UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS},
    )


@router.post("/login/user", response_model=AuthResponse)
def user_login(payload: LocalLoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    return _login_with_policy(payload, request, response, "login_user", db, target_role=UserRole.USER)


@router.post("/step-up", response_model=AuthResponse)
def post_step_up_auth(
    payload: AuthStepUpVerifyRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    audit_context = build_security_audit_context(request)
    session_context = {
        "ip_hash": resolve_ip_hash(request),
        "device_fingerprint": resolve_device_fingerprint(request),
    }
    requested_scope = [str(item or "").strip().lower() for item in (payload.scope or []) if str(item or "").strip()]
    if not requested_scope:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="step_up_scope_required")

    risk_eval = evaluate_request_risk(db, user=current_user, request=request, action_name=requested_scope[0])
    risk_response = standardized_risk_response(risk_eval)

    enforce_login_protection(
        db,
        request=request,
        endpoint_scope=AUTH_PROTECTION_SCOPE,
        email=current_user.email,
    )
    device_id, _ = resolve_or_create_device_id(request)
    try:
        result = verify_step_up_code(
            db,
            user=current_user,
            method=payload.method,
            code=payload.code,
            device_id=device_id,
            session_context=session_context,
            step_up_scope=requested_scope,
        )
    except HTTPException as exc:
        record_login_failure(
            db,
            request=request,
            endpoint_scope=AUTH_PROTECTION_SCOPE,
            email=current_user.email,
            reason=f"step_up:{str(exc.detail)}",
            user_id=current_user.id,
        )
        raise
    access_token = result.get("access_token")
    if access_token:
        register_auth_session(db, user=current_user, access_token=access_token, request=request, commit=False)
    record_login_success(
        db,
        request=request,
        endpoint_scope=AUTH_PROTECTION_SCOPE,
        email=current_user.email,
        user=current_user,
        commit=False,
    )
    set_device_cookie(response, request, device_id=device_id)
    create_audit_log(
        db,
        action="auth_step_up_verified",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"method": payload.method, **audit_context},
        commit=False,
    )
    db.commit()
    return AuthResponse(
        **result,
        requires_step_up=False,
        risk_level=risk_response.get("risk_level", "low"),
        risk_reasons=risk_response.get("risk_reasons") or [],
    )


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