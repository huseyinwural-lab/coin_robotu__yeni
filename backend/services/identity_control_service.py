from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil

from fastapi import HTTPException, Request, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from db import redis_client
from model_domains.identity_control import (
    ApprovalPolicyConfig,
    AuthSession,
    IdentityApprovalRequest,
    IdentityRolePolicy,
    LoginHistoryEvent,
    UserBotScope,
    UserIdentityProfile,
    UserInviteToken,
    UserRoleBinding,
    UserStrategyScope,
)
from models import AuditLog, ExecutionMetric, User, UserExchangeConnection, UserOnboardingProfile, UserRiskSetting, UserRole
from services.audit_service import create_audit_log
from services.mfa_service import get_mfa_settings
from services.rate_limiter_service import TokenBucketRateLimiter


CRITICAL_APPROVAL_ACTIONS = {
    "disable_user",
    "delete_user",
    "enable_live_trading",
    "raise_capital_limit",
    "grant_privileged_role",
}

DEFAULT_ROLE_PERMISSIONS: dict[str, dict] = {
    "super_admin": {
        "priority": 1,
        "is_privileged": True,
        "permissions": [
            "identity.users.read",
            "identity.users.write",
            "identity.roles.manage",
            "identity.sessions.manage",
            "identity.approvals.manage",
            "identity.invite.manage",
            "identity.trading.manage",
            "identity.audit.read",
            "identity.override.super_admin",
        ],
    },
    "admin": {
        "priority": 2,
        "is_privileged": True,
        "permissions": [
            "identity.users.read",
            "identity.users.write",
            "identity.sessions.manage",
            "identity.approvals.manage",
            "identity.invite.manage",
            "identity.trading.manage",
            "identity.audit.read",
        ],
    },
    "ops": {
        "priority": 3,
        "is_privileged": False,
        "permissions": [
            "identity.users.read",
            "identity.audit.read",
            "identity.approvals.read",
        ],
    },
    "user": {
        "priority": 10,
        "is_privileged": False,
        "permissions": ["identity.self.read"],
    },
}

DEFAULT_APPROVAL_POLICIES: dict[str, dict] = {
    "disable_user": {
        "requester_roles": ["admin", "ops", "super_admin"],
        "approver_roles": ["admin", "super_admin"],
    },
    "delete_user": {
        "requester_roles": ["admin", "super_admin"],
        "approver_roles": ["super_admin"],
    },
    "enable_live_trading": {
        "requester_roles": ["admin", "ops", "super_admin"],
        "approver_roles": ["admin", "super_admin"],
    },
    "raise_capital_limit": {
        "requester_roles": ["admin", "ops", "super_admin"],
        "approver_roles": ["admin", "super_admin"],
    },
    "grant_privileged_role": {
        "requester_roles": ["admin", "super_admin"],
        "approver_roles": ["super_admin"],
    },
}


IP_RATE_LIMITER = TokenBucketRateLimiter(key_prefix="auth_ip_login", capacity=60, refill_per_second=1.0)
USER_RATE_LIMITER = TokenBucketRateLimiter(key_prefix="auth_user_login", capacity=25, refill_per_second=25 / 60.0)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(raw: str) -> str:
    return hashlib.sha256(str(raw or "").encode()).hexdigest()


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def resolve_client_ip(request: Request) -> str:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    if request.client and request.client.host:
        return str(request.client.host).strip()
    return "unknown"


def resolve_device_fingerprint(request: Request) -> str:
    user_agent = str(request.headers.get("user-agent") or "").strip()
    ip = resolve_client_ip(request)
    return _token_hash(f"{ip}|{user_agent}")[:40]


def _lock_key(email: str, scope: str) -> str:
    return f"auth:lock:{scope}:{_normalize_email(email)}"


def _failure_key(email: str, scope: str) -> str:
    return f"auth:fail:{scope}:{_normalize_email(email)}"


def _redis_set_with_ttl(key: str, ttl_seconds: int, value: str) -> None:
    if hasattr(redis_client, "setex"):
        redis_client.setex(key, int(ttl_seconds), value)
        return
    redis_client.set(key, value)
    if hasattr(redis_client, "expire"):
        redis_client.expire(key, int(ttl_seconds))


def _seed_role_policies(db: Session) -> None:
    created = False
    for role_key, config in DEFAULT_ROLE_PERMISSIONS.items():
        row = db.query(IdentityRolePolicy).filter(IdentityRolePolicy.role_key == role_key).first()
        if row is None:
            row = IdentityRolePolicy(
                role_key=role_key,
                description=f"system role {role_key}",
                is_system=True,
                is_privileged=bool(config.get("is_privileged")),
                priority=int(config.get("priority", 100)),
                permissions=list(config.get("permissions", [])),
            )
            db.add(row)
            created = True
    if created:
        db.commit()


def _seed_approval_policies(db: Session) -> None:
    changed = False
    for action_key, config in DEFAULT_APPROVAL_POLICIES.items():
        row = db.query(ApprovalPolicyConfig).filter(ApprovalPolicyConfig.action_key == action_key).first()
        if row is None:
            row = ApprovalPolicyConfig(
                action_key=action_key,
                is_enabled=True,
                required_approvals=1,
                requester_roles=config.get("requester_roles", []),
                approver_roles=config.get("approver_roles", []),
                override_allowed_for_super_admin=True,
            )
            db.add(row)
            changed = True
    if changed:
        db.commit()


def ensure_identity_control_seed(db: Session) -> None:
    _seed_role_policies(db)
    _seed_approval_policies(db)


def get_or_create_identity_profile(db: Session, user_id: str) -> UserIdentityProfile:
    row = db.query(UserIdentityProfile).filter(UserIdentityProfile.user_id == user_id).first()
    if row is not None:
        return row
    row = UserIdentityProfile(user_id=user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_effective_permissions(db: Session, user: User) -> set[str]:
    ensure_identity_control_seed(db)
    base_role = str(user.role.value if hasattr(user.role, "value") else user.role).lower()
    base = db.query(IdentityRolePolicy).filter(IdentityRolePolicy.role_key == base_role).first()
    permissions = set(base.permissions if base else [])
    binding = db.query(UserRoleBinding).filter(UserRoleBinding.user_id == user.id).first()
    if binding is not None and binding.role_policy_id:
        custom = db.query(IdentityRolePolicy).filter(IdentityRolePolicy.id == binding.role_policy_id).first()
        if custom is not None:
            permissions.update(custom.permissions or [])
    if binding is not None:
        permissions.update(binding.extra_permissions or [])
        permissions.difference_update(set(binding.denied_permissions or []))
    return permissions


def enforce_permission(db: Session, *, actor: User, permission: str) -> None:
    perms = get_effective_permissions(db, actor)
    if permission in perms:
        return
    if "identity.override.super_admin" in perms and str(actor.role.value) == "super_admin":
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission_denied")


def enforce_login_protection(db: Session, *, request: Request, endpoint_scope: str, email: str) -> None:
    normalized_email = _normalize_email(email)
    ip = resolve_client_ip(request)

    ip_allowed, ip_retry_after, _ = IP_RATE_LIMITER.consume(bucket_id=f"{endpoint_scope}:{ip}", tokens=1.0)
    if not ip_allowed:
        retry_after = max(int(ceil(ip_retry_after)), 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="login_rate_limit_ip_exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    user_allowed, user_retry_after, _ = USER_RATE_LIMITER.consume(bucket_id=f"{endpoint_scope}:{normalized_email}", tokens=1.0)
    if not user_allowed:
        retry_after = max(int(ceil(user_retry_after)), 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="login_rate_limit_user_exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    lock_key = _lock_key(normalized_email, endpoint_scope)
    lock_ttl = 0
    if hasattr(redis_client, "ttl"):
        try:
            lock_ttl = int(redis_client.ttl(lock_key) or 0)
        except Exception:  # pragma: no cover - defensive
            lock_ttl = 0
    else:
        lock_ttl = 900 if redis_client.get(lock_key) else 0

    if lock_ttl > 0:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="login_account_locked",
            headers={"Retry-After": str(int(lock_ttl))},
        )


def record_login_failure(
    db: Session,
    *,
    request: Request,
    endpoint_scope: str,
    email: str,
    reason: str,
    user_id: str | None = None,
) -> dict:
    normalized_email = _normalize_email(email)
    failure_key = _failure_key(normalized_email, endpoint_scope)
    current_attempt = redis_client.incr(failure_key)
    redis_client.expire(failure_key, int(timedelta(minutes=15).total_seconds()))

    lock_seconds = 0
    if current_attempt >= 5:
        progressive_backoff = min(900, 60 * (2 ** max(current_attempt - 5, 0)))
        lock_seconds = max(900, int(progressive_backoff))
        _redis_set_with_ttl(_lock_key(normalized_email, endpoint_scope), lock_seconds, str(current_attempt))

    ip = resolve_client_ip(request)
    user_agent = str(request.headers.get("user-agent") or "")
    fingerprint = resolve_device_fingerprint(request)
    lock_until = _utcnow() + timedelta(seconds=lock_seconds) if lock_seconds > 0 else None

    db.add(
        LoginHistoryEvent(
            email=normalized_email,
            user_id=user_id,
            endpoint_scope=endpoint_scope,
            outcome="FAILED",
            failure_reason=str(reason or "invalid_credentials")[:120],
            ip_address=ip,
            user_agent=user_agent[:300],
            device_fingerprint=fingerprint,
            attempt_count=int(current_attempt),
            lock_until=lock_until,
        )
    )
    create_audit_log(
        db,
        action="AUTH_LOGIN_FAILED",
        entity_type="auth",
        entity_id=user_id or normalized_email,
        actor_user_id=user_id,
        actor_role="system",
        severity="warning",
        details={
            "email": normalized_email,
            "endpoint_scope": endpoint_scope,
            "attempt_count": int(current_attempt),
            "locked": lock_seconds > 0,
            "lock_seconds": int(lock_seconds),
            "reason": str(reason or "invalid_credentials")[:120],
            "ip": ip,
            "device_fingerprint": fingerprint,
        },
    )
    db.commit()

    return {
        "attempt_count": int(current_attempt),
        "locked": lock_seconds > 0,
        "lock_seconds": int(lock_seconds),
    }


def record_login_success(db: Session, *, request: Request, endpoint_scope: str, email: str, user: User) -> None:
    normalized_email = _normalize_email(email)
    redis_client.delete(_failure_key(normalized_email, endpoint_scope))
    redis_client.delete(_lock_key(normalized_email, endpoint_scope))

    ip = resolve_client_ip(request)
    user_agent = str(request.headers.get("user-agent") or "")
    fingerprint = resolve_device_fingerprint(request)

    db.add(
        LoginHistoryEvent(
            email=normalized_email,
            user_id=user.id,
            endpoint_scope=endpoint_scope,
            outcome="SUCCESS",
            ip_address=ip,
            user_agent=user_agent[:300],
            device_fingerprint=fingerprint,
            attempt_count=0,
            lock_until=None,
        )
    )
    create_audit_log(
        db,
        action="AUTH_LOGIN_SUCCESS",
        entity_type="auth",
        entity_id=user.id,
        actor_user_id=user.id,
        actor_role=user.role.value,
        severity="info",
        details={
            "email": normalized_email,
            "endpoint_scope": endpoint_scope,
            "ip": ip,
            "device_fingerprint": fingerprint,
        },
    )

    profile = get_or_create_identity_profile(db, user.id)
    profile.last_seen_ip = ip
    profile.last_seen_device = fingerprint
    profile.updated_at = _utcnow()
    db.commit()


def enforce_admin_totp_policy(db: Session, *, user: User) -> None:
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS}:
        return
    settings = get_mfa_settings(db, user.id)
    enabled_methods = [str(item).lower() for item in (settings.get("enabled_methods") or [])]
    if not settings.get("is_enabled"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_totp_mfa_required")
    if "totp" not in enabled_methods:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_totp_mfa_required")
    if not settings.get("totp_verified"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_totp_setup_required")


def register_auth_session(db: Session, *, user: User, access_token: str, request: Request, expires_minutes: int = 60) -> AuthSession:
    token_hash = _token_hash(access_token)
    existing = db.query(AuthSession).filter(AuthSession.token_hash == token_hash).first()
    if existing is not None:
        existing.last_seen_at = _utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    ip = resolve_client_ip(request)
    user_agent = str(request.headers.get("user-agent") or "")
    fingerprint = resolve_device_fingerprint(request)
    row = AuthSession(
        user_id=user.id,
        token_hash=token_hash,
        ip_address=ip,
        user_agent=user_agent[:300],
        device_fingerprint=fingerprint,
        last_seen_at=_utcnow(),
        expires_at=_utcnow() + timedelta(minutes=max(expires_minutes, 1)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def is_access_token_revoked(db: Session, *, access_token: str) -> bool:
    token_hash = _token_hash(access_token)
    row = db.query(AuthSession).filter(AuthSession.token_hash == token_hash).first()
    if row is None:
        return False
    if row.is_revoked:
        return True
    if row.expires_at is not None:
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if _utcnow() > expires_at:
            return True
    return False


def list_active_sessions(db: Session, *, actor: User, user_id: str | None = None) -> list[dict]:
    target_user_id = user_id or actor.id
    if target_user_id != actor.id:
        enforce_permission(db, actor=actor, permission="identity.sessions.manage")
    query = db.query(AuthSession).filter(AuthSession.user_id == target_user_id, AuthSession.is_revoked.is_(False))
    rows = query.order_by(AuthSession.created_at.desc()).all()
    payload = []
    now = _utcnow()
    for row in rows:
        expired = False
        if row.expires_at is not None:
            expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            expired = now > expires
        payload.append(
            {
                "session_id": row.id,
                "user_id": row.user_id,
                "ip_address": row.ip_address,
                "user_agent": row.user_agent,
                "device_fingerprint": row.device_fingerprint,
                "created_at": row.created_at,
                "last_seen_at": row.last_seen_at,
                "expires_at": row.expires_at,
                "is_expired": expired,
            }
        )
    return payload


def revoke_session(db: Session, *, actor: User, session_id: str, reason: str) -> dict:
    row = db.query(AuthSession).filter(AuthSession.id == session_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session_not_found")
    if row.user_id != actor.id:
        enforce_permission(db, actor=actor, permission="identity.sessions.manage")
    row.is_revoked = True
    row.revoked_reason = str(reason or "revoked_by_admin")[:255]
    row.revoked_by = actor.id
    row.revoked_at = _utcnow()
    db.commit()
    create_audit_log(
        db,
        action="USER_SESSION_REVOKED",
        entity_type="auth_session",
        entity_id=row.id,
        actor_user_id=actor.id,
        actor_role=actor.role.value,
        severity="warning",
        details={"target_user_id": row.user_id, "reason": row.revoked_reason},
    )
    return {"session_id": row.id, "status": "revoked"}


def _resolve_risk_level(risk: UserRiskSetting | None) -> str:
    if risk is None:
        return "unassigned"
    trade_risk = float(risk.trade_risk_pct or 0)
    if trade_risk >= 20:
        return "high"
    if trade_risk >= 10:
        return "medium"
    return "low"


def evaluate_user_eligibility(db: Session, *, user: User, grace_days: int = 7, commit: bool = True) -> dict:
    profile = get_or_create_identity_profile(db, user.id)
    onboarding = db.query(UserOnboardingProfile).filter(UserOnboardingProfile.user_id == user.id).first()
    risk = db.query(UserRiskSetting).filter(UserRiskSetting.user_id == user.id).first()
    exchange_count = db.query(func.count(UserExchangeConnection.id)).filter(UserExchangeConnection.user_id == user.id).scalar() or 0
    strategy_scope_count = (
        db.query(func.count(UserStrategyScope.id))
        .filter(UserStrategyScope.user_id == user.id, UserStrategyScope.is_enabled.is_(True))
        .scalar()
        or 0
    )

    checks = {
        "identity_active": bool(user.is_active and profile.soft_deleted_at is None),
        "email_verified": bool(onboarding.email_verified if onboarding else False),
        "risk_profile_assigned": bool(risk is not None),
        "capital_limit_defined": bool(profile.capital_limit is not None and float(profile.capital_limit or 0) > 0),
        "exchange_connected": bool(exchange_count > 0),
        "strategy_scope_assigned": bool(strategy_scope_count > 0),
        "trading_enabled": bool(profile.trading_enabled and not profile.kill_switch_active),
    }

    all_good = all(checks.values())
    now = _utcnow()

    if all_good:
        profile.live_trading_eligible = True
        profile.non_compliant_since = None
        profile.grace_until = None
    else:
        profile.live_trading_eligible = False
        if profile.non_compliant_since is None:
            profile.non_compliant_since = now
        if profile.grace_until is None:
            profile.grace_until = now + timedelta(days=max(grace_days, 1))

        if profile.grace_until is not None:
            grace_until = profile.grace_until if profile.grace_until.tzinfo else profile.grace_until.replace(tzinfo=timezone.utc)
            if now > grace_until:
                profile.trading_enabled = False

    profile.compliance_snapshot = {
        **checks,
        "grace_until": profile.grace_until.isoformat() if profile.grace_until else None,
        "non_compliant_since": profile.non_compliant_since.isoformat() if profile.non_compliant_since else None,
    }
    profile.updated_at = now
    if commit:
        db.commit()
        db.refresh(profile)

    return {
        "checks": checks,
        "all_requirements_met": all_good,
        "live_trading_eligible": bool(profile.live_trading_eligible),
        "grace_until": profile.grace_until,
        "non_compliant_since": profile.non_compliant_since,
        "kill_switch_active": bool(profile.kill_switch_active),
        "trading_enabled": bool(profile.trading_enabled),
        "capital_limit": profile.capital_limit,
        "risk_level": _resolve_risk_level(risk),
        "exchange_connected_count": int(exchange_count),
        "strategy_scope_count": int(strategy_scope_count),
    }


def set_kill_switch(db: Session, *, actor: User, user_id: str, active: bool, reason: str) -> dict:
    enforce_permission(db, actor=actor, permission="identity.trading.manage")
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    if target.role == UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_protected")

    profile = get_or_create_identity_profile(db, user_id)
    profile.kill_switch_active = bool(active)
    if active:
        profile.trading_enabled = False
        profile.live_trading_eligible = False
    profile.updated_by = actor.id
    db.commit()

    create_audit_log(
        db,
        action="USER_KILL_SWITCH_UPDATED",
        entity_type="user",
        entity_id=user_id,
        actor_user_id=actor.id,
        actor_role=actor.role.value,
        severity="warning" if active else "info",
        details={"kill_switch_active": bool(active), "reason": str(reason or "")[:255]},
    )

    return {"user_id": user_id, "kill_switch_active": bool(profile.kill_switch_active)}


def create_custom_role(
    db: Session,
    *,
    actor: User,
    role_key: str,
    description: str,
    permissions: list[str],
    is_privileged: bool,
    priority: int,
) -> IdentityRolePolicy:
    enforce_permission(db, actor=actor, permission="identity.roles.manage")
    normalized_key = str(role_key or "").strip().lower()
    if not normalized_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="role_key_required")
    existing = db.query(IdentityRolePolicy).filter(IdentityRolePolicy.role_key == normalized_key).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="role_key_already_exists")

    perms = sorted({str(item).strip() for item in (permissions or []) if str(item).strip()})
    row = IdentityRolePolicy(
        role_key=normalized_key,
        description=str(description or "")[:255],
        is_system=False,
        is_privileged=bool(is_privileged),
        priority=max(int(priority or 10), 1),
        permissions=perms,
        created_by=actor.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="IDENTITY_CUSTOM_ROLE_CREATED",
        entity_type="identity_role",
        entity_id=row.id,
        actor_user_id=actor.id,
        actor_role=actor.role.value,
        severity="info",
        details={"role_key": row.role_key, "permissions": row.permissions},
    )
    return row


def assign_custom_role_to_user(db: Session, *, actor: User, user_id: str, role_policy_id: str) -> UserRoleBinding:
    enforce_permission(db, actor=actor, permission="identity.roles.manage")
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    if target.role == UserRole.SUPER_ADMIN and actor.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_protected")

    role = db.query(IdentityRolePolicy).filter(IdentityRolePolicy.id == role_policy_id).first()
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role_policy_not_found")

    actor_perms = get_effective_permissions(db, actor)
    if role.is_privileged and "identity.override.super_admin" not in actor_perms:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="privilege_escalation_blocked")
    if any(permission not in actor_perms for permission in (role.permissions or [])) and "identity.override.super_admin" not in actor_perms:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="privilege_escalation_blocked")

    binding = db.query(UserRoleBinding).filter(UserRoleBinding.user_id == user_id).first()
    if binding is None:
        binding = UserRoleBinding(user_id=user_id)
        db.add(binding)

    binding.role_policy_id = role.id
    binding.updated_by = actor.id
    binding.updated_at = _utcnow()
    db.commit()
    db.refresh(binding)

    create_audit_log(
        db,
        action="USER_CUSTOM_ROLE_ASSIGNED",
        entity_type="user",
        entity_id=user_id,
        actor_user_id=actor.id,
        actor_role=actor.role.value,
        details={"role_policy_id": role.id, "role_key": role.role_key},
    )
    return binding


def _approval_policy_for_action(db: Session, action_key: str) -> ApprovalPolicyConfig:
    ensure_identity_control_seed(db)
    row = db.query(ApprovalPolicyConfig).filter(ApprovalPolicyConfig.action_key == action_key).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approval_policy_missing")
    if not row.is_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approval_policy_disabled")
    return row


def create_approval_request(
    db: Session,
    *,
    actor: User,
    action_key: str,
    target_user_id: str,
    payload: dict,
    reason: str,
) -> IdentityApprovalRequest:
    policy = _approval_policy_for_action(db, action_key)
    actor_role = str(actor.role.value)
    if actor_role not in set(policy.requester_roles or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="requester_role_not_allowed")

    target = db.query(User).filter(User.id == target_user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    if target.role == UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_protected")

    request_row = IdentityApprovalRequest(
        action_key=action_key,
        target_user_id=target_user_id,
        payload=dict(payload or {}),
        status="pending",
        request_reason=str(reason or "")[:500],
        requested_by=actor.id,
        required_approvals=max(int(policy.required_approvals or 1), 1),
    )
    db.add(request_row)
    db.commit()
    db.refresh(request_row)

    create_audit_log(
        db,
        action="IDENTITY_APPROVAL_REQUEST_CREATED",
        entity_type="approval_request",
        entity_id=request_row.id,
        actor_user_id=actor.id,
        actor_role=actor.role.value,
        severity="warning",
        details={"action_key": action_key, "target_user_id": target_user_id, "reason": request_row.request_reason},
    )
    return request_row


def _apply_approval_action(db: Session, *, action_key: str, target: User, payload: dict, actor: User) -> None:
    profile = get_or_create_identity_profile(db, target.id)
    now = _utcnow()

    if action_key == "disable_user":
        target.is_active = False
        target.disabled_at = now
        profile.trading_enabled = False
        profile.live_trading_eligible = False
    elif action_key == "delete_user":
        if target.role == UserRole.SUPER_ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_protected")
        target.is_active = False
        profile.soft_deleted_at = now
        profile.trading_enabled = False
        profile.live_trading_eligible = False
    elif action_key == "enable_live_trading":
        profile.trading_enabled = True
    elif action_key == "raise_capital_limit":
        requested_limit = float(payload.get("capital_limit") or 0)
        if requested_limit <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="capital_limit_required")
        profile.capital_limit = requested_limit
    elif action_key == "grant_privileged_role":
        role_value = str(payload.get("role") or "").strip().lower()
        allowed = {item.value for item in UserRole}
        if role_value not in allowed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_role")
        if role_value == UserRole.SUPER_ADMIN.value and actor.role != UserRole.SUPER_ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_only")
        target.role = UserRole(role_value)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_action")

    profile.updated_by = actor.id
    profile.updated_at = now
    target.updated_at = now


def approve_request(db: Session, *, actor: User, request_id: str, approval_note: str, override_reason: str | None = None) -> IdentityApprovalRequest:
    row = db.query(IdentityApprovalRequest).filter(IdentityApprovalRequest.id == request_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval_request_not_found")
    if row.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approval_request_not_pending")
    if row.requested_by == actor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="same_actor_cannot_approve")

    policy = _approval_policy_for_action(db, row.action_key)
    if str(actor.role.value) not in set(policy.approver_roles or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="approver_role_not_allowed")

    target = db.query(User).filter(User.id == row.target_user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")

    _apply_approval_action(db, action_key=row.action_key, target=target, payload=dict(row.payload or {}), actor=actor)
    row.approval_count += 1
    row.approved_by = actor.id
    row.approval_note = str(approval_note or "")[:500]
    row.reviewed_at = _utcnow()

    if row.approval_count >= max(int(row.required_approvals or 1), 1):
        row.status = "approved"

    if actor.role == UserRole.SUPER_ADMIN and override_reason:
        row.payload = {
            **dict(row.payload or {}),
            "super_admin_override_reason": str(override_reason)[:500],
        }

    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="IDENTITY_APPROVAL_REQUEST_APPROVED",
        entity_type="approval_request",
        entity_id=row.id,
        actor_user_id=actor.id,
        actor_role=actor.role.value,
        severity="warning",
        details={"action_key": row.action_key, "target_user_id": row.target_user_id, "approval_note": row.approval_note},
    )
    return row


def reject_request(db: Session, *, actor: User, request_id: str, note: str) -> IdentityApprovalRequest:
    row = db.query(IdentityApprovalRequest).filter(IdentityApprovalRequest.id == request_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval_request_not_found")
    if row.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approval_request_not_pending")
    if row.requested_by == actor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="same_actor_cannot_reject")

    policy = _approval_policy_for_action(db, row.action_key)
    if str(actor.role.value) not in set(policy.approver_roles or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="approver_role_not_allowed")

    row.status = "rejected"
    row.rejected_by = actor.id
    row.approval_note = str(note or "")[:500]
    row.reviewed_at = _utcnow()
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="IDENTITY_APPROVAL_REQUEST_REJECTED",
        entity_type="approval_request",
        entity_id=row.id,
        actor_user_id=actor.id,
        actor_role=actor.role.value,
        severity="info",
        details={"action_key": row.action_key, "target_user_id": row.target_user_id, "note": row.approval_note},
    )
    return row


@dataclass
class InviteDeliveryResult:
    delivery_status: str
    preview_token: str | None


class InviteService:
    def send_invite(self, *, email: str, invite_token: str, role: str) -> InviteDeliveryResult:
        return InviteDeliveryResult(delivery_status="MOCKED_SENT", preview_token=invite_token)


class EmailVerificationService:
    def send_verification(self, *, email: str, verification_code: str) -> dict:
        return {
            "delivery_status": "MOCKED_SENT",
            "preview_code": verification_code,
            "email": email,
        }


class MfaService:
    def enforce_admin_totp(self, db: Session, user: User) -> None:
        enforce_admin_totp_policy(db, user=user)


class ApprovalService:
    def create(self, db: Session, *, actor: User, action_key: str, target_user_id: str, payload: dict, reason: str) -> IdentityApprovalRequest:
        return create_approval_request(db, actor=actor, action_key=action_key, target_user_id=target_user_id, payload=payload, reason=reason)

    def approve(self, db: Session, *, actor: User, request_id: str, approval_note: str, override_reason: str | None = None) -> IdentityApprovalRequest:
        return approve_request(db, actor=actor, request_id=request_id, approval_note=approval_note, override_reason=override_reason)

    def reject(self, db: Session, *, actor: User, request_id: str, note: str) -> IdentityApprovalRequest:
        return reject_request(db, actor=actor, request_id=request_id, note=note)


class AuditService:
    def write(self, db: Session, **kwargs) -> AuditLog:
        return create_audit_log(db, **kwargs)


class EligibilityService:
    def evaluate(self, db: Session, *, user: User, grace_days: int = 7, commit: bool = True) -> dict:
        return evaluate_user_eligibility(db, user=user, grace_days=grace_days, commit=commit)


def create_invite(
    db: Session,
    *,
    actor: User,
    email: str,
    invited_role: str,
    service: InviteService,
    expires_hours: int = 24,
) -> dict:
    enforce_permission(db, actor=actor, permission="identity.invite.manage")
    normalized_email = _normalize_email(email)
    if not normalized_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email_required")

    raw_token = secrets.token_urlsafe(32)
    row = UserInviteToken(
        email=normalized_email,
        token_hash=_token_hash(raw_token),
        invited_role=str(invited_role or "user").strip().lower() or "user",
        invited_by=actor.id,
        expires_at=_utcnow() + timedelta(hours=max(expires_hours, 1)),
    )
    delivery = service.send_invite(email=normalized_email, invite_token=raw_token, role=row.invited_role)
    row.invite_delivery_status = delivery.delivery_status
    row.invite_preview_token = delivery.preview_token
    db.add(row)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="USER_INVITE_CREATED",
        entity_type="invite",
        entity_id=row.id,
        actor_user_id=actor.id,
        actor_role=actor.role.value,
        details={"email": row.email, "invited_role": row.invited_role, "delivery_status": row.invite_delivery_status},
    )

    return {
        "invite_id": row.id,
        "email": row.email,
        "invited_role": row.invited_role,
        "status": row.status,
        "delivery_status": row.invite_delivery_status,
        "preview_token": row.invite_preview_token,
        "expires_at": row.expires_at,
    }


def accept_invite(db: Session, *, preview_token: str) -> dict:
    token_hash = _token_hash(preview_token)
    row = db.query(UserInviteToken).filter(UserInviteToken.token_hash == token_hash).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invite_not_found")
    if row.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invite_not_pending")

    now = _utcnow()
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if now > expires:
        row.status = "expired"
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invite_expired")

    row.status = "accepted"
    row.accepted_at = now
    db.commit()
    db.refresh(row)

    return {
        "invite_id": row.id,
        "status": row.status,
        "email": row.email,
        "accepted_at": row.accepted_at,
    }


def list_identity_users(
    db: Session,
    *,
    search: str | None,
    role: str | None,
    status: str | None,
    risk_level: str | None,
    trading_enabled: bool | None,
    exchange: str | None,
    page: int,
    page_size: int,
) -> dict:
    query = db.query(User)
    if search:
        search_value = f"%{search.strip()}%"
        query = query.filter(or_(User.email.ilike(search_value), User.id.ilike(search_value)))
    if role and role != "all":
        query = query.filter(User.role == role)
    if status == "active":
        query = query.filter(User.is_active.is_(True))
    elif status == "disabled":
        query = query.filter(User.is_active.is_(False))

    total = query.count()
    offset = max(page - 1, 0) * max(page_size, 1)
    users = query.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()

    items = []
    for user in users:
        eligibility = evaluate_user_eligibility(db, user=user, grace_days=7, commit=True)
        exchange_count = db.query(func.count(UserExchangeConnection.id)).filter(UserExchangeConnection.user_id == user.id).scalar() or 0
        if exchange and exchange.strip():
            has_exchange = (
                db.query(func.count(UserExchangeConnection.id))
                .filter(UserExchangeConnection.user_id == user.id, UserExchangeConnection.exchange == exchange.strip().lower())
                .scalar()
                or 0
            )
            if has_exchange == 0:
                continue

        if risk_level and risk_level != "all" and eligibility.get("risk_level") != risk_level:
            continue
        if trading_enabled is not None and bool(eligibility.get("trading_enabled")) != bool(trading_enabled):
            continue

        metric_query = db.query(ExecutionMetric).filter(ExecutionMetric.user_id == user.id)
        total_trades = metric_query.count()
        failed_trades = metric_query.filter(ExecutionMetric.final_status.in_(["FAILED", "REJECTED", "ERROR"])).count()
        avg_quality = metric_query.with_entities(func.avg(ExecutionMetric.execution_quality_score)).scalar()

        items.append(
            {
                "id": user.id,
                "email": user.email,
                "role": user.role.value,
                "status": user.status,
                "is_active": bool(user.is_active),
                "approval_status": user.approval_status,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
                "identity_controls": {
                    "risk_status": eligibility.get("risk_level"),
                    "trading_status": "eligible" if eligibility.get("live_trading_eligible") else "blocked",
                    "exchange_connected": bool(exchange_count > 0),
                    "error_state": "high" if failed_trades > 0 else "ok",
                    "live_trading_eligible": bool(eligibility.get("live_trading_eligible")),
                    "compliance_checks": eligibility.get("checks", {}),
                    "non_compliant": not bool(eligibility.get("all_requirements_met")),
                    "grace_until": eligibility.get("grace_until"),
                    "capital_limit": eligibility.get("capital_limit"),
                    "trading_enabled": eligibility.get("trading_enabled"),
                    "kill_switch_active": eligibility.get("kill_switch_active"),
                },
                "observability": {
                    "trade_count": int(total_trades),
                    "failed_trade_count": int(failed_trades),
                    "error_rate": round((failed_trades / total_trades), 4) if total_trades else 0.0,
                    "avg_execution_quality": round(float(avg_quality or 0.0), 4),
                    "trade_history_link": f"/admin/trades?user_id={user.id}",
                },
            }
        )

    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": max((total + page_size - 1) // page_size, 1),
        },
    }
