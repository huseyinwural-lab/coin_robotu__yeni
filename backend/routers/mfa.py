from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from core.users.user_registry import user_login_with_policy
from db import get_db
from deps import get_current_user, require_admin
from models import User, UserRole
from schemas import (
    AuthResponse,
    MfaBackupCodesResponse,
    MfaSecureActionRequest,
    MfaChallengeCreateRequest,
    MfaChallengeResendResponse,
    MfaChallengeVerifyRequest,
    MfaSettingsResponse,
    MfaSettingsUpdateRequest,
    MfaTotpSetupResponse,
    MfaTotpVerifyRequest,
)
from core.security import verify_password
from services.audit_service import create_audit_log
from services.auth_session_security_service import resolve_or_create_device_id, set_device_cookie
from services.identity_control_service import (
    enforce_login_protection,
    record_login_failure,
    record_login_success,
    revoke_all_active_sessions_for_user,
    register_auth_session,
    resolve_device_fingerprint,
    resolve_ip_hash,
    resolve_client_ip,
)
from services.mfa_service import (
    admin_reset_user_mfa,
    begin_totp_setup,
    create_authenticated_mfa_challenge,
    disable_user_mfa,
    get_mfa_settings,
    regenerate_backup_codes,
    resend_email_otp_for_challenge,
    resolve_challenge_user,
    update_mfa_settings,
    verify_mfa_challenge,
    verify_step_up_code,
    verify_totp_setup,
)
from services.recovery_approval_service import (
    approve_recovery_request,
    create_recovery_request,
    finalize_recovery_request,
    list_recovery_requests,
)
from services.security_audit_context_service import build_security_audit_context

router = APIRouter(prefix="/auth/mfa", tags=["mfa"])
public_router = APIRouter(prefix="/mfa", tags=["mfa"])
AUTH_PROTECTION_SCOPE = "auth_access"


def _set_deprecated_headers(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["X-Deprecated-Endpoint"] = "true"
    response.headers["Link"] = '</api/mfa>; rel="successor-version"'


class MfaChallengeResendRequest(BaseModel):
    challenge_token: str = Field(min_length=20, max_length=200)


class MfaBootstrapStartRequest(BaseModel):
    email: str
    password: str


class MfaBootstrapVerifyRequest(BaseModel):
    email: str
    password: str
    code: str = Field(min_length=6, max_length=10)


class RecoveryRequestPayload(BaseModel):
    user_id: str | None = None
    reason: str = Field(min_length=12, max_length=1000)
    delay_minutes: int = Field(default=15, ge=1, le=1440)


class RecoveryApprovePayload(BaseModel):
    note: str = ""


@router.get("/settings", response_model=MfaSettingsResponse)
def get_settings(response: Response, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _set_deprecated_headers(response)
    payload = get_mfa_settings(db, current_user.id)
    return MfaSettingsResponse(**payload)


@router.put("/settings", response_model=MfaSettingsResponse)
def put_settings(
    response: Response,
    payload: MfaSettingsUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _set_deprecated_headers(response)
    if current_user.role in {UserRole.OPS} and not payload.is_enabled:
        raise HTTPException(status_code=403, detail="privileged_mfa_disable_forbidden")
    before = get_mfa_settings(db, current_user.id)
    result = update_mfa_settings(
        db,
        current_user.id,
        is_enabled=payload.is_enabled,
        enabled_methods=payload.enabled_methods,
    )
    audit_context = build_security_audit_context(request)
    state_action = "mfa_enabled" if (not before.get("is_enabled") and result.get("is_enabled")) else "mfa_disabled"
    if before.get("is_enabled") == result.get("is_enabled"):
        state_action = "mfa_settings_updated"
    create_audit_log(
        db,
        action=state_action,
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "is_enabled": result.get("is_enabled"),
            "enabled_methods": result.get("enabled_methods"),
            **audit_context,
        },
    )
    return MfaSettingsResponse(**result)


@router.post("/totp/setup", response_model=MfaTotpSetupResponse)
def post_totp_setup(response: Response, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _set_deprecated_headers(response)
    payload = begin_totp_setup(db, user=current_user)
    create_audit_log(
        db,
        action="mfa_totp_setup_started",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details=build_security_audit_context(request),
    )
    return MfaTotpSetupResponse(**payload)


@router.post("/totp/verify-setup", response_model=MfaSettingsResponse)
def post_totp_verify_setup(
    response: Response,
    payload: MfaTotpVerifyRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _set_deprecated_headers(response)
    result = verify_totp_setup(db, user_id=current_user.id, code=payload.code)
    create_audit_log(
        db,
        action="mfa_totp_verified",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details=build_security_audit_context(request),
    )
    return MfaSettingsResponse(**result)


@router.post("/backup-codes/regenerate", response_model=MfaBackupCodesResponse)
def post_backup_codes_regenerate(
    response: Response,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _set_deprecated_headers(response)
    payload = regenerate_backup_codes(db, user_id=current_user.id)
    create_audit_log(
        db,
        action="mfa_backup_codes_regenerated",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"count": payload.get("backup_codes_remaining", 0), **build_security_audit_context(request)},
    )
    return MfaBackupCodesResponse(**payload)


@router.post("/backup-codes/regenerate-secure", response_model=MfaBackupCodesResponse)
def post_backup_codes_regenerate_secure(
    payload: MfaSecureActionRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _set_deprecated_headers(response)
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="current_password_invalid")
    verify_step_up_code(
        db,
        user=current_user,
        method=payload.method,
        code=payload.code,
        device_id=str(request.cookies.get("device_id") or request.headers.get("X-Session-Device") or "secure-mfa-action"),
        session_context={"ip_hash": resolve_ip_hash(request), "device_fingerprint": resolve_device_fingerprint(request)},
        step_up_scope=["mfa_backup_regenerate"],
    )
    result = regenerate_backup_codes(db, user_id=current_user.id)
    create_audit_log(
        db,
        action="mfa_backup_codes_regenerated_secure",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning",
        details=build_security_audit_context(request),
    )
    return MfaBackupCodesResponse(**result)


def _verify_challenge_handler(
    payload: MfaChallengeVerifyRequest,
    request: Request,
    response: Response,
    db: Session,
) -> AuthResponse:
    audit_context = build_security_audit_context(request)
    challenge_user = resolve_challenge_user(db, challenge_token=payload.challenge_token)
    if challenge_user is not None:
        enforce_login_protection(
            db,
            request=request,
            endpoint_scope=AUTH_PROTECTION_SCOPE,
            email=challenge_user.email,
        )

    device_id, _ = resolve_or_create_device_id(request)
    session_context = {
        "ip_hash": resolve_ip_hash(request),
        "device_fingerprint": resolve_device_fingerprint(request),
    }

    try:
        result = verify_mfa_challenge(
            db,
            challenge_token=payload.challenge_token,
            method=payload.method,
            code=payload.code,
            device_id=device_id,
            session_context=session_context,
        )
    except HTTPException as exc:
        if challenge_user is not None:
            record_login_failure(
                db,
                request=request,
                endpoint_scope=AUTH_PROTECTION_SCOPE,
                email=challenge_user.email,
                reason=f"mfa_verify:{str(exc.detail)}",
                user_id=challenge_user.id,
            )
            create_audit_log(
                db,
                action="mfa_verification_failed",
                entity_type="user",
                entity_id=challenge_user.id,
                actor_user_id=challenge_user.id,
                actor_role=challenge_user.role.value,
                severity="warning",
                details={
                    "method": payload.method,
                    "error": str(exc.detail),
                    **audit_context,
                },
            )
        raise

    set_device_cookie(response, request, device_id=device_id)
    user = result.get("user")
    if user is not None:
        access_token = result.get("access_token")
        if access_token:
            register_auth_session(db, user=user, access_token=access_token, request=request)
            record_login_success(db, request=request, endpoint_scope=AUTH_PROTECTION_SCOPE, email=user.email, user=user)
        create_audit_log(
            db,
            action="mfa_login_verified",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            actor_role=user.role.value,
            details={"method": payload.method, **audit_context},
        )
        if str(payload.method or "").strip().lower() == "backup_code":
            create_audit_log(
                db,
                action="mfa_backup_code_used",
                entity_type="user",
                entity_id=user.id,
                actor_user_id=user.id,
                actor_role=user.role.value,
                severity="warning",
                details=audit_context,
            )
    return AuthResponse(**result)


@router.post("/challenge/verify", response_model=AuthResponse)
def post_mfa_challenge_verify(
    payload: MfaChallengeVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _set_deprecated_headers(response)
    return _verify_challenge_handler(payload, request, response, db)


@router.post("/verify", response_model=AuthResponse)
def post_mfa_verify(
    payload: MfaChallengeVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _set_deprecated_headers(response)
    return _verify_challenge_handler(payload, request, response, db)


@public_router.post("/verify", response_model=AuthResponse)
def post_public_mfa_verify(
    payload: MfaChallengeVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    return _verify_challenge_handler(payload, request, response, db)


@router.post("/challenge/resend", response_model=MfaChallengeResendResponse)
def post_mfa_challenge_resend(
    payload: MfaChallengeResendRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _set_deprecated_headers(response)
    result = resend_email_otp_for_challenge(
        db,
        challenge_token=payload.challenge_token,
        request_ip=resolve_client_ip(request),
    )
    challenge_user = resolve_challenge_user(db, challenge_token=payload.challenge_token)
    if challenge_user is not None:
        create_audit_log(
            db,
            action="mfa_email_otp_resent",
            entity_type="user",
            entity_id=challenge_user.id,
            actor_user_id=challenge_user.id,
            actor_role=challenge_user.role.value,
            details=build_security_audit_context(request),
        )
    return MfaChallengeResendResponse(**result)


@public_router.post("/challenge/resend", response_model=MfaChallengeResendResponse)
def post_public_mfa_challenge_resend(
    payload: MfaChallengeResendRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    result = resend_email_otp_for_challenge(
        db,
        challenge_token=payload.challenge_token,
        request_ip=resolve_client_ip(request),
    )
    return MfaChallengeResendResponse(**result)


@public_router.post("/setup", response_model=MfaTotpSetupResponse)
def post_public_mfa_setup(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = begin_totp_setup(db, user=current_user)
    create_audit_log(
        db,
        action="mfa_setup_started",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details=build_security_audit_context(request),
    )
    return MfaTotpSetupResponse(**payload)


@public_router.post("/challenge", response_model=AuthResponse)
def post_public_mfa_challenge(
    payload: MfaChallengeCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    challenge = create_authenticated_mfa_challenge(
        db,
        user=current_user,
        request_ip=resolve_client_ip(request),
        challenge_reason=payload.reason,
    )
    create_audit_log(
        db,
        action="mfa_challenge_created",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"reason": payload.reason, **build_security_audit_context(request)},
    )
    return AuthResponse(
        access_token=None,
        token=None,
        token_type="mfa_challenge",
        role=current_user.role.value,
        user=current_user,
        mfa_required=True,
        mfa_challenge_token=challenge.get("mfa_challenge_token"),
        mfa_methods=list(challenge.get("mfa_methods") or []),
        mfa_expires_at=challenge.get("mfa_expires_at"),
        requires_step_up=True,
        risk_level="medium",
        risk_reasons=[str(payload.reason or "manual_challenge")],
        challenge_reason=str(payload.reason or "manual_challenge"),
        email_delivery_status=challenge.get("email_delivery_status"),
        email_code_preview=challenge.get("email_code_preview"),
    )


@public_router.post("/disable", response_model=MfaSettingsResponse)
def post_public_mfa_disable(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role in {UserRole.OPS}:
        raise HTTPException(status_code=403, detail="privileged_mfa_disable_forbidden")
    result = disable_user_mfa(db, user_id=current_user.id)
    create_audit_log(
        db,
        action="mfa_disabled",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning",
        details=build_security_audit_context(request),
    )
    return MfaSettingsResponse(**result)


@router.post("/disable-secure", response_model=MfaSettingsResponse)
def post_mfa_disable_secure(
    payload: MfaSecureActionRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _set_deprecated_headers(response)
    if current_user.role in {UserRole.OPS}:
        raise HTTPException(status_code=403, detail="privileged_mfa_disable_forbidden")
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="current_password_invalid")
    verify_step_up_code(
        db,
        user=current_user,
        method=payload.method,
        code=payload.code,
        device_id=str(request.cookies.get("device_id") or request.headers.get("X-Session-Device") or "secure-mfa-disable"),
        session_context={"ip_hash": resolve_ip_hash(request), "device_fingerprint": resolve_device_fingerprint(request)},
        step_up_scope=["mfa_disable"],
    )
    result = disable_user_mfa(db, user_id=current_user.id)
    revoked = 0
    if payload.revoke_other_sessions:
        revoked = revoke_all_active_sessions_for_user(db, target_user_id=current_user.id, actor=current_user, reason="mfa_disable_secure")
        db.commit()
    create_audit_log(
        db,
        action="mfa_disabled_secure",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning",
        details={"revoked_sessions": revoked, **build_security_audit_context(request)},
    )
    return MfaSettingsResponse(**result)


@router.post("/disable", response_model=MfaSettingsResponse)
def post_mfa_disable(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _set_deprecated_headers(response)
    return post_public_mfa_disable(request=request, current_user=current_user, db=db)


@router.post("/admin/reset/{target_user_id}")
def post_admin_mfa_reset(
    target_user_id: str,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == target_user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    payload = admin_reset_user_mfa(db, user_id=target_user_id)
    revoked = revoke_all_active_sessions_for_user(
        db,
        target_user_id=target_user_id,
        actor=current_admin,
        reason="admin_mfa_reset",
    )
    db.commit()

    create_audit_log(
        db,
        action="admin_mfa_reset",
        entity_type="user",
        entity_id=target_user_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="critical",
        details={
            "revoked_sessions": revoked,
            "target_email": target.email,
            **build_security_audit_context(request),
        },
    )
    create_audit_log(
        db,
        action="fraud_recovery_mfa_reset",
        entity_type="user",
        entity_id=target_user_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"revoked_sessions": revoked, "target_email": target.email},
    )
    return {"status": "ok", "target_user_id": target_user_id, "revoked_sessions": revoked, "mfa": payload}


@router.post("/recovery/request")
def post_recovery_request(
    payload: RecoveryRequestPayload,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target_user_id = payload.user_id or current_user.id
    if target_user_id != current_user.id and current_user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS}:
        raise HTTPException(status_code=403, detail="recovery_target_forbidden")
    row = create_recovery_request(
        db,
        target_user_id=target_user_id,
        requested_by_user_id=current_user.id,
        reason=payload.reason,
        delay_minutes=payload.delay_minutes,
    )
    create_audit_log(
        db,
        action="mfa_recovery_requested",
        entity_type="user",
        entity_id=target_user_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning",
        details={"recovery_request_id": row.id, **build_security_audit_context(request)},
    )
    db.commit()
    return {
        "status": row.status,
        "recovery_request_id": row.id,
        "required_approvals": row.required_approvals,
        "approval_count": row.approval_count,
        "ready_after": row.ready_after,
    }


@router.post("/recovery/{request_id}/approve")
def post_recovery_approve(
    request_id: str,
    payload: RecoveryApprovePayload,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = approve_recovery_request(db, request_id=request_id, approver=current_admin, note=payload.note)
    create_audit_log(
        db,
        action="mfa_recovery_approval_added",
        entity_type="mfa_recovery_request",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"approval_count": row.approval_count, **build_security_audit_context(request)},
    )
    db.commit()
    return {
        "status": row.status,
        "recovery_request_id": row.id,
        "approval_count": row.approval_count,
        "required_approvals": row.required_approvals,
        "ready_after": row.ready_after,
    }


@router.post("/recovery/{request_id}/finalize")
def post_recovery_finalize(
    request_id: str,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = finalize_recovery_request(db, request_id=request_id, finalizer=current_admin)
    target_user = db.query(User).filter(User.id == row.user_id).first()
    if target_user is None:
        raise HTTPException(status_code=404, detail="recovery_target_user_not_found")

    payload = admin_reset_user_mfa(db, user_id=row.user_id)
    revoked = revoke_all_active_sessions_for_user(
        db,
        target_user_id=row.user_id,
        actor=current_admin,
        reason="recovery_finalize_mfa_reset",
    )
    create_audit_log(
        db,
        action="mfa_recovery_finalized",
        entity_type="mfa_recovery_request",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="critical",
        details={"target_user_id": row.user_id, "revoked_sessions": revoked, **build_security_audit_context(request)},
    )
    db.commit()
    return {
        "status": row.status,
        "recovery_request_id": row.id,
        "target_user_id": row.user_id,
        "revoked_sessions": revoked,
        "mfa": payload,
    }


@router.get("/recovery/requests")
def get_recovery_requests(
    status_filter: str | None = None,
    limit: int = 100,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = list_recovery_requests(db, status_filter=status_filter, limit=limit)
    return {
        "items": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "requested_by_user_id": row.requested_by_user_id,
                "status": row.status,
                "approval_count": row.approval_count,
                "required_approvals": row.required_approvals,
                "ready_after": row.ready_after,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "actor": current_admin.id,
    }


@router.post("/bootstrap/totp/start")
def post_mfa_bootstrap_totp_start(payload: MfaBootstrapStartRequest, db: Session = Depends(get_db)):
    session = user_login_with_policy(
        db,
        payload,
        allowed_roles={UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS},
    )
    setup = begin_totp_setup(db, user=session.user)
    return {
        "user_id": session.user.id,
        "email": session.user.email,
        "totp_secret": setup.get("secret"),
        "otpauth_uri": setup.get("otpauth_uri"),
        "issuer": setup.get("issuer"),
        "hint": "Authenticator uygulaması ile ekleyip verify endpointini çağırın",
    }


@router.post("/bootstrap/totp/verify")
def post_mfa_bootstrap_totp_verify(payload: MfaBootstrapVerifyRequest, db: Session = Depends(get_db)):
    session = user_login_with_policy(
        db,
        payload,
        allowed_roles={UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS},
    )
    verify = verify_totp_setup(db, user_id=session.user.id, code=payload.code)
    update_mfa_settings(db, session.user.id, is_enabled=True, enabled_methods=["totp"])
    backup = regenerate_backup_codes(db, user_id=session.user.id, count=8)
    return {
        "user_id": session.user.id,
        "email": session.user.email,
        "totp_verified": verify.get("totp_verified"),
        "backup_codes": backup.get("generated_codes", []),
        "backup_codes_remaining": backup.get("backup_codes_remaining", 0),
    }
