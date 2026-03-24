from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    InviteService,
    assign_custom_role_to_user,
    create_custom_role,
    create_invite,
    create_approval_request,
    enforce_permission,
    evaluate_user_eligibility,
    get_or_create_identity_profile,
    list_identity_users,
    reject_request,
    set_kill_switch,
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


class BulkStatusRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list)
    status: str = Field(default="disabled")
    reason: str = "bulk_status_change"


class InlineUserUpdateRequest(BaseModel):
    role: str | None = None
    status: str | None = None
    trading_enabled: bool | None = None
    capital_limit: float | None = None
    reason: str = "inline_update"


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


class UserScopePayload(BaseModel):
    strategy_code: str | None = None
    bot_profile_id: str | None = None
    is_enabled: bool = True


class ReactivateUserPayload(BaseModel):
    reason: str = "manual_reactivation"


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
    row = create_approval_request(
        db,
        actor=actor,
        action_key=action_key,
        target_user_id=target_user_id,
        payload=payload,
        reason=reason,
    )
    return {
        "status": "approval_required",
        "request_id": row.id,
        "action_key": row.action_key,
        "required_approvals": row.required_approvals,
    }


@router.get("/users")
def admin_identity_users(
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    risk_level: str | None = Query(default=None),
    trading_enabled: bool | None = Query(default=None),
    exchange: str | None = Query(default=None),
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
        page=page,
        page_size=page_size,
    )
    return payload


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

    if payload.status in {"disabled", "deleted"}:
        action_key = "delete_user" if payload.status == "deleted" else "disable_user"
        return _request_if_critical(
            db=db,
            actor=current_admin,
            action_key=action_key,
            target_user_id=target.id,
            payload={"status": payload.status},
            reason=payload.reason,
        )

    if payload.role:
        if payload.role in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}:
            return _request_if_critical(
                db=db,
                actor=current_admin,
                action_key="grant_privileged_role",
                target_user_id=target.id,
                payload={"role": payload.role},
                reason=payload.reason,
            )
        target.role = UserRole(payload.role)

    profile = get_or_create_identity_profile(db, target.id)

    if payload.status == "active":
        target.is_active = True
        target.disabled_at = None
    if payload.trading_enabled is not None:
        if payload.trading_enabled:
            return _request_if_critical(
                db=db,
                actor=current_admin,
                action_key="enable_live_trading",
                target_user_id=target.id,
                payload={"trading_enabled": True},
                reason=payload.reason,
            )
        profile.trading_enabled = False

    if payload.capital_limit is not None:
        return _request_if_critical(
            db=db,
            actor=current_admin,
            action_key="raise_capital_limit",
            target_user_id=target.id,
            payload={"capital_limit": float(payload.capital_limit)},
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

    success = 0
    failed = []
    for user_id in user_ids:
        target = db.query(User).filter(User.id == user_id).first()
        if target is None:
            failed.append({"user_id": user_id, "error": "user_not_found"})
            continue
        if target.role == UserRole.SUPER_ADMIN:
            failed.append({"user_id": user_id, "error": "super_admin_protected"})
            continue

        profile = get_or_create_identity_profile(db, user_id)
        if payload.status == "disabled":
            target.is_active = False
            profile.trading_enabled = False
        elif payload.status == "active":
            target.is_active = True
        else:
            failed.append({"user_id": user_id, "error": "invalid_status"})
            continue
        target.updated_at = datetime.now(timezone.utc)
        success += 1

    db.commit()
    create_audit_log(
        db,
        action="IDENTITY_BULK_STATUS_UPDATED",
        entity_type="user",
        entity_id=f"bulk:{len(user_ids)}",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"status": payload.status, "success": success, "failed": failed, "reason": payload.reason},
    )
    return {"requested": len(user_ids), "success": success, "failed": failed}


@router.post("/users/{user_id}/kill-switch")
def admin_identity_kill_switch(
    user_id: str,
    payload: KillSwitchPayload,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return set_kill_switch(db, actor=current_admin, user_id=user_id, active=payload.active, reason=payload.reason)


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
    profile = get_or_create_identity_profile(db, user_id)
    profile.soft_deleted_at = None
    profile.reactivated_at = datetime.now(timezone.utc)
    target.is_active = True
    target.disabled_at = None
    db.commit()
    evaluate_user_eligibility(db, user=target, commit=True)
    create_audit_log(
        db,
        action="IDENTITY_USER_REACTIVATED",
        entity_type="user",
        entity_id=user_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"reason": payload.reason},
    )
    return {"user_id": user_id, "status": "reactivated"}


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
    }


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
    return {
        "items": [
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
            }
            for row in rows
        ]
    }


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
    payload: ApprovalDecisionPayload,
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
    payload: ApprovalDecisionPayload,
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
                "expires_at": row.expires_at,
                "accepted_at": row.accepted_at,
            }
            for row in rows
        ]
    }


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
