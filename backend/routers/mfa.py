from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from core.users.user_registry import user_login_with_policy
from db import get_db
from deps import get_current_user
from models import User, UserRole
from schemas import (
    AuthResponse,
    MfaBackupCodesResponse,
    MfaChallengeVerifyRequest,
    MfaSettingsResponse,
    MfaSettingsUpdateRequest,
    MfaTotpSetupResponse,
    MfaTotpVerifyRequest,
)
from services.audit_service import create_audit_log
from services.identity_control_service import record_login_success, register_auth_session
from services.mfa_service import (
    begin_totp_setup,
    get_mfa_settings,
    regenerate_backup_codes,
    update_mfa_settings,
    verify_mfa_challenge,
    verify_totp_setup,
)

router = APIRouter(prefix="/auth/mfa", tags=["mfa"])


class MfaChallengeResendRequest(BaseModel):
    challenge_token: str = Field(min_length=20, max_length=200)


class MfaBootstrapStartRequest(BaseModel):
    email: str
    password: str


class MfaBootstrapVerifyRequest(BaseModel):
    email: str
    password: str
    code: str = Field(min_length=6, max_length=10)


@router.get("/settings", response_model=MfaSettingsResponse)
def get_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = get_mfa_settings(db, current_user.id)
    return MfaSettingsResponse(**payload)


@router.put("/settings", response_model=MfaSettingsResponse)
def put_settings(
    payload: MfaSettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = update_mfa_settings(
        db,
        current_user.id,
        is_enabled=payload.is_enabled,
        enabled_methods=payload.enabled_methods,
    )
    create_audit_log(
        db,
        action="mfa_settings_updated",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"is_enabled": result.get("is_enabled"), "enabled_methods": result.get("enabled_methods")},
    )
    return MfaSettingsResponse(**result)


@router.post("/totp/setup", response_model=MfaTotpSetupResponse)
def post_totp_setup(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = begin_totp_setup(db, user=current_user)
    create_audit_log(
        db,
        action="mfa_totp_setup_started",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
    )
    return MfaTotpSetupResponse(**payload)


@router.post("/totp/verify-setup", response_model=MfaSettingsResponse)
def post_totp_verify_setup(
    payload: MfaTotpVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = verify_totp_setup(db, user_id=current_user.id, code=payload.code)
    create_audit_log(
        db,
        action="mfa_totp_verified",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
    )
    return MfaSettingsResponse(**result)


@router.post("/backup-codes/regenerate", response_model=MfaBackupCodesResponse)
def post_backup_codes_regenerate(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = regenerate_backup_codes(db, user_id=current_user.id)
    create_audit_log(
        db,
        action="mfa_backup_codes_regenerated",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"count": payload.get("backup_codes_remaining", 0)},
    )
    return MfaBackupCodesResponse(**payload)


@router.post("/challenge/verify", response_model=AuthResponse)
def post_mfa_challenge_verify(payload: MfaChallengeVerifyRequest, request: Request, db: Session = Depends(get_db)):
    result = verify_mfa_challenge(
        db,
        challenge_token=payload.challenge_token,
        method=payload.method,
        code=payload.code,
    )
    user = result.get("user")
    if user is not None:
        access_token = result.get("access_token")
        if access_token:
            register_auth_session(db, user=user, access_token=access_token, request=request)
            record_login_success(db, request=request, endpoint_scope="mfa_verify", email=user.email, user=user)
        create_audit_log(
            db,
            action="mfa_login_verified",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            actor_role=user.role.value,
            details={"method": payload.method},
        )
    return AuthResponse(**result)


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
