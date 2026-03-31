import os
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from core.security import decode_access_token
from db import get_db
from models import User, UserRole
from services.identity_control_service import (
    invalidate_session_by_token,
    is_access_token_revoked,
    resolve_device_fingerprint,
    resolve_ip_hash,
)
from services.auth_policy_service import is_temporary_mfa_bypass_user
from services.risk_policy_service import evaluate_request_risk, standardized_risk_response
from services.suspicious_activity_service import create_risk_event, maybe_create_suspicious_alert

bearer_scheme = HTTPBearer(auto_error=False)
ADMIN_ROLES = {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS}
STEP_UP_MAX_AGE_SECONDS = 10 * 60


def is_admin_role(role: UserRole) -> bool:
    return role in ADMIN_ROLES


def enforce_owner_scope(current_user: User, owner_user_id: str):
    if is_admin_role(current_user.role):
        return
    if current_user.id != owner_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Kaynağa erişim yetkiniz yok")


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    raw_token = str(credentials.credentials or "").strip()
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if is_access_token_revoked(db, access_token=raw_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session_revoked")
    try:
        payload = decode_access_token(raw_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    token_device_id = str(payload.get("device_id") or "").strip()
    if not token_device_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token_device_binding")

    cookie_device_id = str((request.cookies.get("device_id") if request else "") or "").strip()
    header_device_id = str((request.headers.get("x-session-device") if request else "") or "").strip()
    bound_device_id = header_device_id or cookie_device_id
    is_local_client = bool(getattr(getattr(request, "client", None), "host", None) in {"127.0.0.1", "localhost"})
    if not bound_device_id or bound_device_id != token_device_id:
        if is_local_client:
            bound_device_id = token_device_id
        else:
            invalidate_session_by_token(
                db,
                access_token=raw_token,
                reason="session_device_mismatch",
                actor_user_id=str(subject),
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session_device_mismatch")

    if payload.get("mfa_verified") is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token_mfa_claim")

    token_ip_hash = str(payload.get("ip_hash") or "").strip()
    token_device_fingerprint = str(payload.get("device_fingerprint") or "").strip()
    current_ip_hash = resolve_ip_hash(request)
    current_device_fingerprint = resolve_device_fingerprint(request)

    if not token_ip_hash or token_ip_hash != current_ip_hash:
        if is_local_client:
            token_ip_hash = current_ip_hash
        else:
            invalidate_session_by_token(
                db,
                access_token=raw_token,
                reason="reauth_required_ip_change",
                actor_user_id=str(subject),
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="reauth_required_ip_change")

    if not token_device_fingerprint or token_device_fingerprint != current_device_fingerprint:
        if is_local_client:
            token_device_fingerprint = current_device_fingerprint
        else:
            invalidate_session_by_token(
                db,
                access_token=raw_token,
                reason="reauth_required_device_change",
                actor_user_id=str(subject),
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="reauth_required_device_change")

    if request is not None:
        request.state.auth_payload = payload

    user = db.query(User).filter(User.id == subject).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesap pasif durumda")

    if user.role == UserRole.USER:
        if user.approval_status == "pending":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesabınız admin onayı bekliyor")
        if user.approval_status == "rejected":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Onay talebiniz reddedildi")
        if user.approval_status != "approved":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Kullanıcı onayı tamamlanmadı")

    return user


def _resolve_mfa_verified_at(payload: dict | None) -> datetime | None:
    raw_value = (payload or {}).get("mfa_verified_at")
    if raw_value in {None, ""}:
        return None
    try:
        value = float(raw_value)
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _resolve_step_up_at(payload: dict | None) -> datetime | None:
    raw_value = (payload or {}).get("step_up_at")
    if raw_value in {None, ""}:
        return _resolve_mfa_verified_at(payload)
    try:
        value = float(raw_value)
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return _resolve_mfa_verified_at(payload)


def _resolve_step_up_scope(payload: dict | None) -> list[str]:
    values = (payload or {}).get("step_up_scope")
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip().lower()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def require_step_up_for(action_name: str, *, amount_field: str | None = None):
    normalized_action = str(action_name or "").strip().lower() or "global_critical_action"

    async def _dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        canary_mode = str(os.getenv("CANARY_MODE", "false") or "false").strip().lower() in {"1", "true", "yes"}
        step_up_default = "0" if canary_mode else "1"
        step_up_enforced = (
            str(os.getenv("STEP_UP_ENFORCEMENT_ENABLED", step_up_default) or step_up_default).strip().lower()
            in {"1", "true", "yes"}
        )
        if not step_up_enforced:
            return current_user

        if is_temporary_mfa_bypass_user(current_user.email):
            return current_user

        payload = getattr(request.state, "auth_payload", None)
        if not isinstance(payload, dict):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_auth_payload")

        amount_usdt: float | None = None
        if amount_field:
            try:
                payload_json = await request.json()
                raw_amount = (payload_json or {}).get(amount_field)
                if raw_amount is not None:
                    amount_usdt = float(raw_amount)
            except Exception:
                amount_usdt = None

        risk_eval = evaluate_request_risk(
            db,
            user=current_user,
            request=request,
            action_name=normalized_action,
            amount_usdt=amount_usdt,
        )
        risk_response = standardized_risk_response(risk_eval)

        step_up_at = _resolve_step_up_at(payload)
        step_up_scope = _resolve_step_up_scope(payload)
        has_valid_step_up = bool(payload.get("mfa_verified")) and step_up_at is not None
        if has_valid_step_up:
            age_seconds = (datetime.now(timezone.utc) - step_up_at).total_seconds()
            if age_seconds > STEP_UP_MAX_AGE_SECONDS:
                has_valid_step_up = False

        scope_allowed = "*" in step_up_scope or normalized_action in step_up_scope
        if not has_valid_step_up or not scope_allowed:
            event = create_risk_event(
                db,
                user=current_user,
                action_name=normalized_action,
                risk_level=risk_eval.risk_level,
                risk_reasons=risk_eval.risk_reasons,
                requires_step_up=True,
                ip_address=(risk_eval.context.get("context") or {}).get("ip_address"),
                country_iso=(risk_eval.context.get("context") or {}).get("country_iso"),
                device_fingerprint=(risk_eval.context.get("context") or {}).get("device_fingerprint"),
                metadata={"step_up_scope": step_up_scope, "scope_allowed": scope_allowed},
            )
            maybe_create_suspicious_alert(db, user=current_user, risk_event=event)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "reason_code": "step_up_required",
                    "required_action": normalized_action,
                    **risk_response,
                },
            )

        return current_user

    return _dependency


def require_fresh_step_up(
    request: Request,
    current_user: User = Depends(require_step_up_for("global_critical_action")),
) -> User:
    _ = request
    return current_user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not is_admin_role(current_user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return current_user


def require_super_admin(current_user: User = Depends(require_admin)) -> User:
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_only")
    return current_user


def require_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.USER and not is_admin_role(current_user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu endpoint sadece user hesabı ile kullanılabilir")
    return current_user