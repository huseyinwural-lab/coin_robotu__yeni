from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User, UserRole
from schemas import UserResponse, UserRoleUpdateRequest, UserStatusUpdateRequest
from services.audit_service import create_audit_log

router = APIRouter(prefix="/admin/users", tags=["admin_users"])


def _ensure_can_modify(current_admin: User, target: User):
    if current_admin.role == UserRole.OPS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops_readonly")
    if target.id == current_admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot_modify_self")
    if target.role == UserRole.SUPER_ADMIN and current_admin.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_only")


def _apply_sort(query, sort_by: str, sort_dir: str):
    sort_dir = sort_dir.lower()
    if sort_by == "email":
        column = User.email
    else:
        column = User.created_at
    if sort_dir == "desc":
        return query.order_by(column.desc())
    return query.order_by(column.asc())


@router.get("", response_model=list[UserResponse])
def list_users(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    search: str | None = None,
    role: str | None = None,
    status_filter: str = Query(default="all", alias="status"),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
    limit: int = 200,
):
    _ = current_admin
    query = db.query(User)
    if search:
        query = query.filter(User.email.ilike(f"%{search}%"))
    if role:
        query = query.filter(User.role == role)
    if status_filter == "active":
        query = query.filter(User.is_active.is_(True))
    elif status_filter == "disabled":
        query = query.filter(User.is_active.is_(False))
    query = _apply_sort(query, sort_by, sort_dir)
    return query.limit(limit).all()


@router.post("/{user_id}/role", response_model=UserResponse)
def update_user_role_legacy(
    user_id: str,
    payload: UserRoleUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_user_role(user_id=user_id, payload=payload, current_admin=current_admin, db=db)


@router.patch("/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: str,
    payload: UserRoleUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    _ensure_can_modify(current_admin, target)

    role_value = payload.role
    if role_value not in {role.value for role in UserRole}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_role")
    if role_value == UserRole.SUPER_ADMIN.value and current_admin.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_only")

    previous_role = target.role.value
    target.role = UserRole(role_value)
    target.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(target)

    create_audit_log(
        db,
        action="USER_ROLE_CHANGED",
        entity_type="user",
        entity_id=target.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={"from": previous_role, "to": role_value, "user_id": target.id},
    )
    return target


@router.post("/{user_id}/disable", response_model=UserResponse)
def disable_user(
    user_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_user_status(
        user_id=user_id,
        payload=UserStatusUpdateRequest(status="disabled"),
        current_admin=current_admin,
        db=db,
    )


@router.post("/{user_id}/enable", response_model=UserResponse)
def enable_user(
    user_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_user_status(
        user_id=user_id,
        payload=UserStatusUpdateRequest(status="active"),
        current_admin=current_admin,
        db=db,
    )


@router.patch("/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: str,
    payload: UserStatusUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    _ensure_can_modify(current_admin, target)

    if payload.status not in {"active", "disabled"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_status")

    previous_status = target.status
    new_status = payload.status
    target.is_active = new_status == "active"
    target.disabled_at = None if target.is_active else datetime.now(timezone.utc)
    target.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(target)

    action = "USER_ENABLED" if target.is_active else "USER_DISABLED"
    severity = "info" if target.is_active else "warning"
    create_audit_log(
        db,
        action=action,
        entity_type="user",
        entity_id=target.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity=severity,
        details={"from": previous_status, "to": new_status, "user_id": target.id},
    )
    return target
