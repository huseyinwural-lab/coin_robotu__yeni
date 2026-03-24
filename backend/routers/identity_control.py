from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from model_domains.identity_control import IdentityApprovalRequest, IdentityRolePolicy, LoginHistoryEvent, UserBotScope, UserInviteToken, UserStrategyScope
from model_domains.identity_control import ApprovalPolicyConfig
from models import User, UserRole
from services.audit_service import create_audit_log
from services.identity_control_service import (
    ApprovalService,
    CRITICAL_APPROVAL_ACTIONS,
    HIGH_RISK_REASON_ACTIONS,
    InviteService,
    assign_custom_role_to_user,
    archive_custom_role,
    cancel_invite,
    clone_custom_role,
    create_custom_role,
    create_invite,
    create_approval_request,
    enforce_permission,
    evaluate_user_eligibility,
    get_or_create_identity_profile,
    hard_delete_candidate_snapshot,
    list_active_sessions,
    list_identity_users,
    resend_invite,
    role_assignment_impact_preview,
    role_permission_preview,
    reject_request,
    set_kill_switch,
    unlock_user_policy_lock,
    update_custom_role,
    expire_invite,
    REQUEST_REASON_MIN_LEN,
)
from services.mfa_service import get_mfa_enforcement_context, get_mfa_settings
from services.user_observability_service import (
    get_user_activity_timeline,
    get_user_execution_metrics,
    get_user_security_telemetry,
    get_user_trading_observability,
)

router = APIRouter(prefix="/admin/identity", tags=["identity-control"])


def _serialize_for_json(obj):
    """Convert datetime objects to ISO strings for JSON serialization"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    return obj


REQUEST_REASON_ENFORCED_ACTIONS = {
    "disable_user",
    "disable_admin",
    "delete_user",
    "soft_delete_user",
    "hard_delete_user",
    "restore_user",
    "grant_privileged_role",
    "enable_live_trading",
    "raise_capital_limit",
    "bulk_disable_users",
    "bulk_enable_users",
    "bulk_soft_delete_users",
    "bulk_restore_users",
}


OBSERVABILITY_ROUTE_CONFIG = {
    "activity_timeline": {
        "path": "/users/{user_id}/activity-timeline",
        "loader": lambda db, user_id, limit=120: get_user_activity_timeline(db, user_id=user_id, limit=limit),
    },
    "security_telemetry": {
        "path": "/users/{user_id}/security-telemetry",
        "loader": lambda db, user_id, limit=120: get_user_security_telemetry(db, user_id=user_id),
    },
    "execution_metrics": {
        "path": "/users/{user_id}/execution-metrics",
        "loader": lambda db, user_id, limit=120: get_user_execution_metrics(db, user_id=user_id),
    },
    "trading_observability": {
        "path": "/users/{user_id}/trading-observability",
        "loader": lambda db, user_id, limit=120: get_user_trading_observability(db, user_id=user_id),
    },
}


def _enforce_request_reason_min_len(action_key: str, reason: str | None) -> None:
    if action_key not in REQUEST_REASON_ENFORCED_ACTIONS:
        return
    if len(str(reason or "").strip()) < int(REQUEST_REASON_MIN_LEN):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request_reason_too_short")


def _observability_contract(*, user_id: str, metric: str, payload: dict) -> dict:
    return {
        "status": "ok",
        "contract_version": "identity_observability_v1",
        "user_id": user_id,
        "metric": metric,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data": _serialize_for_json(payload),
    }


class BulkStatusRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list)
    status: str = Field(default="disabled")
    action: str | None = None
    reason: str = "bulk_status_change"
    critical_confirmed: bool = False
    override_reason: str | None = None


class InlineUserUpdateRequest(BaseModel):
    role: str | None = None
    status: str | None = None
    trading_enabled: bool | None = None
    capital_limit: float | None = None
    reason: str = "inline_update"
    critical_confirmed: bool = False
    override_reason: str | None = None


class ApprovalRequestCreatePayload(BaseModel):
    action_key: str
    target_user_id: str
    payload: dict = Field(default_factory=dict)
    reason: str = "manual_request"


class ApprovalDecisionPayload(BaseModel):
    note: str = ""
    override_reason: str | None = None


class InviteCreatePayload(BaseModel):
    email: str
    invited_role: str = "user"
    expires_hours: int = 24


class InviteAcceptPayload(BaseModel):
    preview_token: str = Field(min_length=20)


class KillSwitchPayload(BaseModel):
    active: bool
    reason: str = "manual_kill_switch"


class CustomRoleCreatePayload(BaseModel):
    role_key: str
    description: str = ""
    permissions: list[str] = Field(default_factory=list)
    is_privileged: bool = False
    priority: int = 100


class AssignRolePayload(BaseModel):
    role_policy_id: str


class CustomRoleUpdatePayload(BaseModel):
    description: str | None = None
    permissions: list[str] | None = None
    priority: int | None = Field(default=None, ge=1, le=999)
    is_privileged: bool | None = None


class CustomRoleClonePayload(BaseModel):
    new_role_key: str


class UserScopePayload(BaseModel):
    strategy_code: str | None = None
    bot_profile_id: str | None = None
    is_enabled: bool = True


class ReactivateUserPayload(BaseModel):
    reason: str = "manual_reactivation"
    override_reason: str | None = None


class CriticalActionRequestPayload(BaseModel):
    reason: str
    critical_confirmed: bool = False
    override_reason: str | None = None


class UnlockPolicyPayload(BaseModel):
    reason: str = "manual_unlock"


class ApprovalPolicyUpdatePayload(BaseModel):
    is_enabled: bool | None = None
    required_approvals: int | None = Field(default=None, ge=1, le=5)
    requester_roles: list[str] | None = None
    approver_roles: list[str] | None = None


def _request_if_critical(
    *,
    db: Session,
    actor: User,
    action_key: str,
    target_user_id: str,
    payload: dict,
    reason: str,
) -> dict:
    if action_key not in CRITICAL_APPROVAL_ACTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="critical_action_required")

    _enforce_request_reason_min_len(action_key, reason)

    request_payload = dict(payload or {})
    if action_key in HIGH_RISK_REASON_ACTIONS:
        if not str(request_payload.get("override_reason") or request_payload.get("approval_reason") or "").strip():
            request_payload["override_reason"] = str(reason or "")

    row = create_approval_request(
        db,
        actor=actor,
        action_key=action_key,
        target_user_id=target_user_id,
        payload=request_payload,
        reason=reason,
    )
    return {
        "status": "approval_required",
        "request_id": row.id,
        "action_key": row.action_key,
        "required_approvals": row.required_approvals,
    }


def _resolve_bulk_action_key(payload: BulkStatusRequest) -> str:
    requested_action = (payload.action or "").strip().lower()
    if not requested_action:
        requested_action = {
            "disabled": "bulk_disable_users",
            "active": "bulk_enable_users",
            "deleted": "bulk_soft_delete_users",
        }.get(payload.status, "")
    if requested_action not in {"bulk_disable_users", "bulk_enable_users", "bulk_soft_delete_users", "bulk_restore_users"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_bulk_action")
    return requested_action


def _approval_risk_score(action_key: str) -> int:
    score_map = {
        "hard_delete_user": 95,
        "soft_delete_user": 88,
        "delete_user": 88,
        "grant_privileged_role": 90,
        "raise_capital_limit": 82,
        "enable_live_trading": 75,
        "restore_user": 70,
        "bulk_soft_delete_users": 85,
        "bulk_disable_users": 75,
    }
    return score_map.get(action_key, 45)


def _approval_risk_level(score: int) -> str:
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _build_approval_impact_delta(db: Session, *, row: IdentityApprovalRequest) -> dict:
    payload = dict(row.payload or {})
    target = db.query(User).filter(User.id == row.target_user_id).first()
    profile = get_or_create_identity_profile(db, row.target_user_id) if target else None

    previous = {
        "role": target.role.value if target else None,
        "status": target.status if target else None,
        "trading_enabled": bool(profile.trading_enabled) if profile else None,
        "capital_limit": float(profile.capital_limit or 0) if profile else None,
        "delete_state": "hard_deleted" if profile and profile.hard_deleted_at else "soft_deleted" if profile and profile.deleted_at else "active",
    }
    desired = dict(previous)

    if row.action_key in {"disable_user", "disable_admin", "bulk_disable_users"}:
        desired["status"] = "disabled"
    if row.action_key in {"enable_user", "restore_user", "bulk_enable_users", "bulk_restore_users"}:
        desired["status"] = "active"
        desired["delete_state"] = "active"
    if row.action_key in {"delete_user", "soft_delete_user", "bulk_soft_delete_users"}:
        desired["status"] = "deleted"
        desired["delete_state"] = "soft_deleted"
    if row.action_key == "hard_delete_user":
        desired["delete_state"] = "hard_deleted"
    if row.action_key == "grant_privileged_role":
        desired["role"] = payload.get("role")
    if row.action_key == "enable_live_trading":
        desired["trading_enabled"] = True
    if row.action_key == "raise_capital_limit":
        desired["capital_limit"] = payload.get("capital_limit")

    changed_fields = [
        key for key in ["role", "status", "trading_enabled", "capital_limit", "delete_state"] if previous.get(key) != desired.get(key)
    ]

    impacted_users_count = len(payload.get("user_ids") or []) if row.action_key.startswith("bulk_") else 1
    blockers = []
    if target and row.action_key in {"hard_delete_user", "soft_delete_user", "delete_user", "restore_user"}:
        blockers = list(hard_delete_candidate_snapshot(db, user=target).get("blockers") or [])

    risk_score = _approval_risk_score(row.action_key)
    numeric_changes = {}
    previous_capital = previous.get("capital_limit")
    desired_capital = desired.get("capital_limit")
    if isinstance(previous_capital, (int, float)) and isinstance(desired_capital, (int, float)):
        numeric_changes["capital_limit_delta"] = round(float(desired_capital) - float(previous_capital), 2)

    if row.action_key.startswith("bulk_"):
        numeric_changes["impacted_users_count"] = impacted_users_count

    baseline_score = 30 + (len(changed_fields) * 3)
    risk_delta = risk_score - baseline_score
    return {
        "previous": previous,
        "desired": desired,
        "changed_fields": changed_fields,
        "risk_score": risk_score,
        "risk_delta": risk_delta,
        "risk_level": _approval_risk_level(risk_score),
        "blockers": blockers,
        "numeric_changes": numeric_changes,
        "impacted_users_count": impacted_users_count,
        "high_risk": risk_score >= 75,
    }


@router.get("/users")
def admin_identity_users(
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    risk_level: str | None = Query(default=None),
    trading_enabled: bool | None = Query(default=None),
    exchange: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.users.read")
    payload = list_identity_users(
        db,
        search=search,
        role=role,
        status=status_filter,
        risk_level=risk_level,
        trading_enabled=trading_enabled,
        exchange=exchange,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
    )
    return payload


@router.get("/users/{user_id}/security")
def admin_identity_user_security_detail(
    user_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.audit.read")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")

    profile = get_or_create_identity_profile(db, user_id)
    sessions = list_active_sessions(db, actor=current_admin, user_id=user_id)
    login_history = (
        db.query(LoginHistoryEvent)
        .filter(LoginHistoryEvent.user_id == user_id)
        .order_by(LoginHistoryEvent.created_at.desc())
        .limit(50)
        .all()
    )
    mfa = get_mfa_settings(db, user_id)
    mfa_enforcement = get_mfa_enforcement_context(user_email=user.email, endpoint_scope="login")
    return {
        "user_id": user_id,
        "email": user.email,
        "mfa": {
            "is_enabled": mfa.get("is_enabled"),
            "enabled_methods": mfa.get("enabled_methods"),
            "totp_configured": mfa.get("totp_configured"),
            "totp_verified": mfa.get("totp_verified"),
            "backup_codes_remaining": mfa.get("backup_codes_remaining"),
            "bypass_active": bool(mfa_enforcement.get("bypass_active")),
            "bypass_reason": mfa_enforcement.get("bypass_reason"),
            "enforcement_required": bool(mfa_enforcement.get("enforcement_required")),
            "environment": mfa_enforcement.get("environment"),
        },
        "security_state": {
            "policy_locked_until": profile.policy_locked_until,
            "password_expires_at": profile.password_expires_at,
            "password_changed_at": profile.password_changed_at,
            "last_seen_ip": profile.last_seen_ip,
            "last_seen_device": profile.last_seen_device,
            "eligible_for_login": profile.eligible_for_login,
            "eligible_for_ops": profile.eligible_for_ops,
        },
        "sessions": sessions,
        "login_history": [
            {
                "id": row.id,
                "outcome": row.outcome,
                "failure_reason": row.failure_reason,
                "ip_address": row.ip_address,
                "device_fingerprint": row.device_fingerprint,
                "user_agent": row.user_agent,
                "attempt_count": row.attempt_count,
                "lock_until": row.lock_until,
                "created_at": row.created_at,
            }
            for row in login_history
        ],
    }


def _make_observability_endpoint(metric_key: str, loader):
    def endpoint(
        user_id: str,
        limit: int = Query(default=120, ge=1, le=300),
        current_admin: User = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        enforce_permission(db, actor=current_admin, permission="identity.users.read")
        user_exists = db.query(User.id).filter(User.id == user_id).first() is not None
        if not user_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
        payload = loader(db, user_id, limit)
        return _observability_contract(user_id=user_id, metric=metric_key, payload=payload)

    endpoint.__name__ = f"admin_identity_observability_{metric_key}"
    return endpoint


for metric_key, config in OBSERVABILITY_ROUTE_CONFIG.items():
    router.add_api_route(
        config["path"],
        _make_observability_endpoint(metric_key, config["loader"]),
        methods=["GET"],
        name=f"admin_identity_observability_{metric_key}",
    )


@router.patch("/users/{user_id}/inline")
def admin_identity_user_inline_update(
    user_id: str,
    payload: InlineUserUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.users.write")
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")

    if payload.status in {"disabled", "deleted", "active"}:
        if not payload.critical_confirmed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="critical_confirmation_required")
        if payload.status == "deleted":
            action_key = "soft_delete_user"
        elif payload.status == "active":
            action_key = "enable_user"
        else:
            action_key = "disable_admin" if target.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN} else "disable_user"
        return _request_if_critical(
            db=db,
            actor=current_admin,
            action_key=action_key,
            target_user_id=target.id,
            payload={"status": payload.status, "critical_confirmed": True, "override_reason": payload.override_reason},
            reason=payload.reason,
        )

    if payload.role:
        if payload.role in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}:
            if not payload.critical_confirmed:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="critical_confirmation_required")
            return _request_if_critical(
                db=db,
                actor=current_admin,
                action_key="grant_privileged_role",
                target_user_id=target.id,
                payload={"role": payload.role, "critical_confirmed": True, "override_reason": payload.override_reason},
                reason=payload.reason,
            )
        target.role = UserRole(payload.role)

    profile = get_or_create_identity_profile(db, target.id)

    if payload.status == "active":
        target.is_active = True
        target.disabled_at = None
    if payload.trading_enabled is not None:
        if payload.trading_enabled:
            if not payload.critical_confirmed:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="critical_confirmation_required")
            return _request_if_critical(
                db=db,
                actor=current_admin,
                action_key="enable_live_trading",
                target_user_id=target.id,
                payload={"trading_enabled": True, "critical_confirmed": True, "override_reason": payload.override_reason},
                reason=payload.reason,
            )
        profile.trading_enabled = False

    if payload.capital_limit is not None:
        if not payload.critical_confirmed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="critical_confirmation_required")
        return _request_if_critical(
            db=db,
            actor=current_admin,
            action_key="raise_capital_limit",
            target_user_id=target.id,
            payload={"capital_limit": float(payload.capital_limit), "critical_confirmed": True, "override_reason": payload.override_reason},
            reason=payload.reason,
        )

    target.updated_at = datetime.now(timezone.utc)
    db.commit()

    eligibility = evaluate_user_eligibility(db, user=target, commit=True)
    create_audit_log(
        db,
        action="IDENTITY_INLINE_USER_UPDATED",
        entity_type="user",
        entity_id=target.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details=_serialize_for_json({"payload": payload.model_dump(), "eligibility": eligibility}),
    )

    return {
        "status": "updated",
        "user_id": target.id,
        "eligibility": eligibility,
    }


@router.post("/users/bulk-status")
def admin_identity_bulk_status(
    payload: BulkStatusRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.users.write")
    user_ids = [item for item in payload.user_ids if str(item).strip()]
    if not user_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_ids_required")

    if not payload.critical_confirmed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="critical_confirmation_required")

    requested_action = _resolve_bulk_action_key(payload)
    _enforce_request_reason_min_len(requested_action, payload.reason)

    success = 0
    failed = []
    requests_created = []
    for user_id in user_ids:
        target = db.query(User).filter(User.id == user_id).first()
        if target is None:
            failed.append({"user_id": user_id, "error": "user_not_found"})
            continue
        if target.role == UserRole.SUPER_ADMIN:
            failed.append({"user_id": user_id, "error": "super_admin_protected"})
            continue

        try:
            if requested_action == "bulk_disable_users":
                action_key = "disable_admin" if target.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN} else "disable_user"
            elif requested_action == "bulk_enable_users":
                action_key = "enable_user"
            elif requested_action == "bulk_soft_delete_users":
                action_key = "soft_delete_user"
            else:
                action_key = "restore_user"

            req = create_approval_request(
                db,
                actor=current_admin,
                action_key=action_key,
                target_user_id=target.id,
                payload={
                    "bulk_action": requested_action,
                    "critical_confirmed": True,
                    "target_status": payload.status,
                    "override_reason": payload.override_reason,
                },
                reason=payload.reason,
            )
            requests_created.append({"user_id": target.id, "request_id": req.id, "action_key": action_key})
            success += 1
        except Exception as exc:
            failed.append({"user_id": user_id, "error": str(exc)})

    create_audit_log(
        db,
        action="IDENTITY_BULK_APPROVAL_REQUEST_CREATED",
        entity_type="user",
        entity_id=f"bulk:{len(user_ids)}",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "bulk_action": requested_action,
            "status": payload.status,
            "success": success,
            "failed": failed,
            "requests_created": requests_created,
            "reason": payload.reason,
        },
    )
    return {
        "requested": len(user_ids),
        "success": success,
        "failed": failed,
        "requests_created": requests_created,
        "status": "approval_required",
    }


@router.post("/users/bulk-status/preview")
def admin_identity_bulk_status_preview(
    payload: BulkStatusRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.users.read")
    requested_action = _resolve_bulk_action_key(payload)

    user_ids = list(dict.fromkeys([str(item).strip() for item in payload.user_ids if str(item).strip()]))
    if not user_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_ids_required")

    preview_items = []
    for user_id in user_ids:
        target = db.query(User).filter(User.id == user_id).first()
        if target is None:
            preview_items.append(
                {
                    "user_id": user_id,
                    "email": None,
                    "eligible": False,
                    "approval_required": True,
                    "risk_score": 100,
                    "risk_badge": "high",
                    "blockers": ["user_not_found"],
                }
            )
            continue

        profile = get_or_create_identity_profile(db, target.id)
        eligibility = evaluate_user_eligibility(db, user=target, grace_days=7, commit=True)
        blockers: list[str] = []

        if requested_action == "bulk_soft_delete_users" and target.role == UserRole.SUPER_ADMIN:
            blockers.append("super_admin_protected")
        if requested_action in {"bulk_enable_users", "bulk_restore_users"} and profile.hard_deleted_at is not None:
            blockers.append("hard_deleted_user_cannot_be_restored")
        if requested_action == "bulk_enable_users" and bool(eligibility.get("checks", {}).get("kill_switch_inactive")) is False:
            blockers.append("kill_switch_active")

        risk_score = 25
        if blockers:
            risk_score = min(100, 55 + (len(set(blockers)) * 12))

        risk_badge = "low"
        if risk_score >= 80:
            risk_badge = "high"
        elif risk_score >= 50:
            risk_badge = "medium"

        preview_items.append(
            {
                "user_id": target.id,
                "email": target.email,
                "role": target.role.value,
                "current_status": target.status,
                "eligible": len(blockers) == 0,
                "approval_required": True,
                "risk_score": risk_score,
                "risk_badge": risk_badge,
                "blockers": list(dict.fromkeys(blockers)),
            }
        )

    blocked_count = len([item for item in preview_items if not item.get("eligible")])
    total = len(preview_items)
    eligible_count = total - blocked_count
    high_risk_count = len([item for item in preview_items if item.get("risk_badge") == "high"])
    risk_score_total = int(sum(int(item.get("risk_score") or 0) for item in preview_items))
    blocker_counter: dict[str, int] = {}
    for item in preview_items:
        for blocker in item.get("blockers") or []:
            blocker_counter[blocker] = blocker_counter.get(blocker, 0) + 1

    return {
        "action_key": requested_action,
        "approval_required": True,
        "items": preview_items,
        "summary": {
            "total": total,
            "eligible_count": eligible_count,
            "blocked_count": blocked_count,
            "high_risk_count": high_risk_count,
            "risk_score_total": risk_score_total,
            "blocker_breakdown": blocker_counter,
            "action_summary": {
                "action_key": requested_action,
                "approval_required": True,
                "impacted_users_count": total,
            },
            "partial_execution_expected": blocked_count > 0,
        },
    }


@router.post("/users/{user_id}/kill-switch")
def admin_identity_kill_switch(
    user_id: str,
    payload: KillSwitchPayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return set_kill_switch(db, actor=current_admin, user_id=user_id, active=payload.active, reason=payload.reason)


@router.post("/users/{user_id}/unlock-policy-lock")
def admin_identity_unlock_policy_lock(
    user_id: str,
    payload: UnlockPolicyPayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    result = unlock_user_policy_lock(db, actor=current_admin, target_user=target)
    create_audit_log(
        db,
        action="IDENTITY_POLICY_LOCK_UNLOCK_REQUESTED",
        entity_type="user",
        entity_id=user_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"reason": payload.reason},
    )
    return result


@router.post("/users/{user_id}/reactivate")
def admin_identity_reactivate_user(
    user_id: str,
    payload: ReactivateUserPayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.users.write")
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")

    response = _request_if_critical(
        db=db,
        actor=current_admin,
        action_key="restore_user",
        target_user_id=target.id,
        payload={"critical_confirmed": True, "reason": payload.reason, "override_reason": payload.override_reason},
        reason=payload.reason,
    )

    create_audit_log(
        db,
        action="IDENTITY_USER_RESTORE_REQUESTED",
        entity_type="approval_request",
        entity_id=response.get("request_id") or user_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"reason": payload.reason, "user_id": user_id, "action_key": "restore_user"},
    )
    return response


@router.post("/users/{user_id}/hard-delete/request")
def admin_identity_hard_delete_request(
    user_id: str,
    payload: CriticalActionRequestPayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not payload.critical_confirmed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="critical_confirmation_required")
    _enforce_request_reason_min_len("hard_delete_user", payload.reason)
    row = create_approval_request(
        db,
        actor=current_admin,
        action_key="hard_delete_user",
        target_user_id=user_id,
        payload={"critical_confirmed": True, "reason": payload.reason, "override_reason": payload.override_reason},
        reason=payload.reason,
    )
    return {"status": "approval_required", "request_id": row.id, "action_key": row.action_key}


@router.post("/users/{user_id}/soft-delete/request")
def admin_identity_soft_delete_request(
    user_id: str,
    payload: CriticalActionRequestPayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not payload.critical_confirmed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="critical_confirmation_required")
    _enforce_request_reason_min_len("soft_delete_user", payload.reason)
    row = create_approval_request(
        db,
        actor=current_admin,
        action_key="soft_delete_user",
        target_user_id=user_id,
        payload={"critical_confirmed": True, "reason": payload.reason, "override_reason": payload.override_reason},
        reason=payload.reason,
    )
    return {"status": "approval_required", "request_id": row.id, "action_key": row.action_key}


@router.post("/roles/custom")
def admin_identity_custom_role_create(
    payload: CustomRoleCreatePayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = create_custom_role(
        db,
        actor=current_admin,
        role_key=payload.role_key,
        description=payload.description,
        permissions=payload.permissions,
        is_privileged=payload.is_privileged,
        priority=payload.priority,
    )
    return {
        "id": row.id,
        "role_key": row.role_key,
        "permissions": row.permissions,
        "is_privileged": row.is_privileged,
        "priority": row.priority,
        "is_active": row.is_active,
    }


@router.patch("/roles/custom/{role_policy_id}")
def admin_identity_custom_role_update(
    role_policy_id: str,
    payload: CustomRoleUpdatePayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = update_custom_role(
        db,
        actor=current_admin,
        role_policy_id=role_policy_id,
        description=payload.description,
        permissions=payload.permissions,
        priority=payload.priority,
        is_privileged=payload.is_privileged,
    )
    return {
        "id": row.id,
        "role_key": row.role_key,
        "description": row.description,
        "permissions": row.permissions,
        "is_privileged": row.is_privileged,
        "priority": row.priority,
        "is_active": row.is_active,
    }


@router.post("/roles/custom/{role_policy_id}/archive")
def admin_identity_custom_role_archive(
    role_policy_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = archive_custom_role(db, actor=current_admin, role_policy_id=role_policy_id)
    return {
        "id": row.id,
        "role_key": row.role_key,
        "is_active": row.is_active,
        "archived_at": row.archived_at,
    }


@router.post("/roles/custom/{role_policy_id}/clone")
def admin_identity_custom_role_clone(
    role_policy_id: str,
    payload: CustomRoleClonePayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = clone_custom_role(db, actor=current_admin, role_policy_id=role_policy_id, new_role_key=payload.new_role_key)
    return {
        "id": row.id,
        "role_key": row.role_key,
        "permissions": row.permissions,
        "is_privileged": row.is_privileged,
        "priority": row.priority,
        "is_active": row.is_active,
    }


@router.get("/roles/custom/{role_policy_id}/permission-preview")
def admin_identity_custom_role_permission_preview(
    role_policy_id: str,
    user_id: str | None = Query(default=None),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.roles.manage")
    return role_permission_preview(db, role_policy_id=role_policy_id, user_id=user_id)


@router.get("/roles/custom/{role_policy_id}/assignment-impact")
def admin_identity_custom_role_assignment_impact(
    role_policy_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.roles.manage")
    return role_assignment_impact_preview(db, role_policy_id=role_policy_id)


@router.get("/roles/custom")
def admin_identity_custom_roles(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.roles.manage")
    rows = db.query(IdentityRolePolicy).filter(IdentityRolePolicy.is_system.is_(False)).order_by(IdentityRolePolicy.created_at.desc()).all()
    return {
        "items": [
            {
                "id": row.id,
                "role_key": row.role_key,
                "permissions": row.permissions,
                "is_privileged": row.is_privileged,
                "priority": row.priority,
                "is_active": row.is_active,
                "archived_at": row.archived_at,
            }
            for row in rows
        ]
    }


@router.post("/users/{user_id}/assign-custom-role")
def admin_identity_assign_custom_role(
    user_id: str,
    payload: AssignRolePayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = assign_custom_role_to_user(db, actor=current_admin, user_id=user_id, role_policy_id=payload.role_policy_id)
    return {
        "binding_id": row.id,
        "user_id": row.user_id,
        "role_policy_id": row.role_policy_id,
    }


@router.post("/approvals/request")
def admin_identity_create_approval_request(
    payload: ApprovalRequestCreatePayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _enforce_request_reason_min_len(payload.action_key, payload.reason)
    row = create_approval_request(
        db,
        actor=current_admin,
        action_key=payload.action_key,
        target_user_id=payload.target_user_id,
        payload=payload.payload,
        reason=payload.reason,
    )
    return {
        "request_id": row.id,
        "status": row.status,
        "action_key": row.action_key,
        "target_user_id": row.target_user_id,
    }


@router.get("/approvals")
def admin_identity_list_approvals(
    status_filter: str = Query(default="pending"),
    limit: int = Query(default=100, ge=1, le=500),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.approvals.manage")
    query = db.query(IdentityApprovalRequest)
    if status_filter and status_filter != "all":
        query = query.filter(IdentityApprovalRequest.status == status_filter)
    rows = query.order_by(IdentityApprovalRequest.created_at.desc()).limit(limit).all()
    items = []
    for row in rows:
        impact_delta = _build_approval_impact_delta(db, row=row)
        items.append(
            {
                "id": row.id,
                "action_key": row.action_key,
                "target_user_id": row.target_user_id,
                "status": row.status,
                "requested_by": row.requested_by,
                "required_approvals": row.required_approvals,
                "approval_count": row.approval_count,
                "request_reason": row.request_reason,
                "created_at": row.created_at,
                "impact_delta": impact_delta,
                "risk_level": impact_delta.get("risk_level"),
                "risk_score": impact_delta.get("risk_score"),
                "impacted_users_count": impact_delta.get("impacted_users_count"),
            }
        )
    return {"items": items}


@router.get("/approval-policies")
def admin_identity_approval_policies(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.approvals.manage")
    rows = db.query(ApprovalPolicyConfig).order_by(ApprovalPolicyConfig.action_key.asc()).all()
    return {
        "items": [
            {
                "id": row.id,
                "action_key": row.action_key,
                "is_enabled": row.is_enabled,
                "required_approvals": row.required_approvals,
                "requester_roles": row.requester_roles,
                "approver_roles": row.approver_roles,
                "override_allowed_for_super_admin": row.override_allowed_for_super_admin,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
    }


@router.patch("/approval-policies/{action_key}")
def admin_identity_update_approval_policy(
    action_key: str,
    payload: ApprovalPolicyUpdatePayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.approvals.manage")
    row = db.query(ApprovalPolicyConfig).filter(ApprovalPolicyConfig.action_key == action_key).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval_policy_not_found")

    if payload.is_enabled is not None:
        row.is_enabled = bool(payload.is_enabled)
    if payload.required_approvals is not None:
        row.required_approvals = int(payload.required_approvals)
    if payload.requester_roles is not None:
        row.requester_roles = [str(item).strip().lower() for item in payload.requester_roles if str(item).strip()]
    if payload.approver_roles is not None:
        row.approver_roles = [str(item).strip().lower() for item in payload.approver_roles if str(item).strip()]
    row.updated_by = current_admin.id
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "action_key": row.action_key,
        "is_enabled": row.is_enabled,
        "required_approvals": row.required_approvals,
        "requester_roles": row.requester_roles,
        "approver_roles": row.approver_roles,
    }


@router.post("/approvals/{request_id}/approve")
def admin_identity_approve(
    request_id: str,
    payload: ApprovalDecisionPayload = Body(default_factory=ApprovalDecisionPayload),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    service = ApprovalService()
    row = service.approve(
        db,
        actor=current_admin,
        request_id=request_id,
        approval_note=payload.note,
        override_reason=payload.override_reason,
    )
    return {
        "request_id": row.id,
        "status": row.status,
        "approval_count": row.approval_count,
        "reviewed_at": row.reviewed_at,
    }


@router.post("/approvals/{request_id}/reject")
def admin_identity_reject(
    request_id: str,
    payload: ApprovalDecisionPayload = Body(default_factory=ApprovalDecisionPayload),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = reject_request(db, actor=current_admin, request_id=request_id, note=payload.note)
    return {
        "request_id": row.id,
        "status": row.status,
        "reviewed_at": row.reviewed_at,
    }


@router.post("/invites")
def admin_identity_create_invite(
    payload: InviteCreatePayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    service = InviteService()
    return create_invite(
        db,
        actor=current_admin,
        email=payload.email,
        invited_role=payload.invited_role,
        service=service,
        expires_hours=payload.expires_hours,
    )


@router.post("/invites/{invite_id}/resend")
def admin_identity_resend_invite(
    invite_id: str,
    expires_hours: int = Query(default=24, ge=1, le=168),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    service = InviteService()
    return resend_invite(db, actor=current_admin, invite_id=invite_id, service=service, expires_hours=expires_hours)


@router.post("/invites/{invite_id}/cancel")
def admin_identity_cancel_invite(
    invite_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return cancel_invite(db, actor=current_admin, invite_id=invite_id)


@router.post("/invites/{invite_id}/expire")
def admin_identity_expire_invite(
    invite_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return expire_invite(db, actor=current_admin, invite_id=invite_id)


@router.post("/invites/accept")
def admin_identity_accept_invite(payload: InviteAcceptPayload, db: Session = Depends(get_db)):
    from services.identity_control_service import accept_invite

    return accept_invite(db, preview_token=payload.preview_token)


@router.get("/invites")
def admin_identity_invites(
    status_filter: str = Query(default="all"),
    limit: int = Query(default=100, ge=1, le=500),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.invite.manage")
    query = db.query(UserInviteToken)
    if status_filter != "all":
        query = query.filter(UserInviteToken.status == status_filter)
    rows = query.order_by(UserInviteToken.created_at.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": row.id,
                "email": row.email,
                "invited_role": row.invited_role,
                "status": row.status,
                "delivery_status": row.invite_delivery_status,
                "preview_token": row.invite_preview_token,
                "resend_count": row.resend_count,
                "last_sent_at": row.last_sent_at,
                "cancelled_at": row.cancelled_at,
                "expires_at": row.expires_at,
                "accepted_at": row.accepted_at,
            }
            for row in rows
        ]
    }


@router.get("/users/hard-delete-candidates")
def admin_identity_hard_delete_candidates(
    limit: int = Query(default=200, ge=1, le=500),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.users.read")
    users = db.query(User).order_by(User.created_at.desc()).limit(limit).all()
    items = []
    for user in users:
        snapshot = hard_delete_candidate_snapshot(db, user=user)
        deleted_at = snapshot.get("deleted_at")
        if not deleted_at:
            continue
        items.append(snapshot)
    return {"items": items, "total": len(items)}


@router.get("/users/deleted-lifecycle")
def admin_identity_deleted_lifecycle(
    limit: int = Query(default=200, ge=1, le=500),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.users.read")
    users = db.query(User).order_by(User.created_at.desc()).limit(limit).all()
    items: list[dict] = []
    for user in users:
        snapshot = hard_delete_candidate_snapshot(db, user=user)
        if not snapshot.get("deleted_at"):
            continue
        eligibility = evaluate_user_eligibility(db, user=user, grace_days=7, commit=True)
        items.append(
            {
                "user_id": user.id,
                "email": user.email,
                "role": user.role.value,
                "status": user.status,
                "is_active": bool(user.is_active),
                "deleted_at": snapshot.get("deleted_at"),
                "deleted_age_days": snapshot.get("deleted_age_days", 0),
                "retention_days_remaining": snapshot.get("retention_days_remaining", 0),
                "eligible_for_hard_delete": bool(snapshot.get("eligible")),
                "risk_score": int(snapshot.get("risk_score") or 0),
                "blockers": list(snapshot.get("blockers") or []),
                "live_trading_eligible": bool(eligibility.get("live_trading_eligible")),
                "trading_enabled": bool(eligibility.get("trading_enabled")),
            }
        )
    return {"items": items, "total": len(items)}


@router.get("/login-history")
def admin_identity_login_history(
    email: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.audit.read")
    query = db.query(LoginHistoryEvent)
    if email:
        query = query.filter(LoginHistoryEvent.email.ilike(f"%{email.strip().lower()}%"))
    if outcome:
        query = query.filter(LoginHistoryEvent.outcome == outcome.upper())
    rows = query.order_by(LoginHistoryEvent.created_at.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": row.id,
                "email": row.email,
                "user_id": row.user_id,
                "outcome": row.outcome,
                "failure_reason": row.failure_reason,
                "ip_address": row.ip_address,
                "user_agent": row.user_agent,
                "device_fingerprint": row.device_fingerprint,
                "attempt_count": row.attempt_count,
                "lock_until": row.lock_until,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@router.post("/users/{user_id}/strategy-scope")
def admin_identity_strategy_scope(
    user_id: str,
    payload: UserScopePayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.trading.manage")
    if not payload.strategy_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="strategy_code_required")
    row = UserStrategyScope(
        user_id=user_id,
        strategy_code=payload.strategy_code,
        is_enabled=payload.is_enabled,
        created_by=current_admin.id,
    )
    db.add(row)
    db.commit()
    target = db.query(User).filter(User.id == user_id).first()
    if target is not None:
        evaluate_user_eligibility(db, user=target, commit=True)
    return {"id": row.id, "user_id": row.user_id, "strategy_code": row.strategy_code, "is_enabled": row.is_enabled}


@router.post("/users/{user_id}/bot-scope")
def admin_identity_bot_scope(
    user_id: str,
    payload: UserScopePayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enforce_permission(db, actor=current_admin, permission="identity.trading.manage")
    if not payload.bot_profile_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bot_profile_id_required")
    row = UserBotScope(
        user_id=user_id,
        bot_profile_id=payload.bot_profile_id,
        is_enabled=payload.is_enabled,
        created_by=current_admin.id,
    )
    db.add(row)
    db.commit()
    target = db.query(User).filter(User.id == user_id).first()
    if target is not None:
        evaluate_user_eligibility(db, user=target, commit=True)
    return {"id": row.id, "user_id": row.user_id, "bot_profile_id": row.bot_profile_id, "is_enabled": row.is_enabled}
