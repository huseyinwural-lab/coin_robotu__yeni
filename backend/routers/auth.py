from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.users.user_registry import (
    approve_user_account,
    list_user_accounts_for_approval,
    register_user_account,
    reject_user_account,
    user_login_with_policy,
)
from db import get_db
from deps import get_current_user, require_admin
from models import User, UserRole
from schemas import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from services.audit_service import create_audit_log

router = APIRouter(prefix="/auth", tags=["auth"])


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


def _login_with_policy(
    payload: LoginRequest,
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
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    return _login_with_policy(payload, db)


@router.post("/login/admin", response_model=AuthResponse)
def admin_login(payload: LoginRequest, db: Session = Depends(get_db)):
    return _login_with_policy(payload, db, allowed_roles={UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS})


@router.post("/login/user", response_model=AuthResponse)
def user_login(payload: LoginRequest, db: Session = Depends(get_db)):
    return _login_with_policy(payload, db, target_role=UserRole.USER)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


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