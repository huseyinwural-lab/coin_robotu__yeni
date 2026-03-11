from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.security import create_access_token, hash_password, verify_password
from db import get_db
from deps import get_current_user, require_admin
from models import User, UserRole
from schemas import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from services.audit_service import create_audit_log

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=UserRole.USER,
        is_active=False,
        approval_status="pending",
        approval_requested_at=datetime.now(timezone.utc),
        approved_at=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

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
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if target_role and user.role != target_role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yanlış giriş paneli")
    if allowed_roles and user.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yanlış giriş paneli")

    if user.role == UserRole.USER and user.approval_status == "pending":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesabınız admin onayı bekliyor")
    if user.role == UserRole.USER and user.approval_status == "rejected":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Onay talebiniz reddedildi")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesap pasif durumda")

    token = create_access_token(subject=user.id, role=user.role.value, email=user.email)
    create_audit_log(
        db,
        action="user_login",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        actor_role=user.role.value,
        details={"email": user.email},
    )
    return AuthResponse(access_token=token, token_type="bearer", user=user)


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
    query = db.query(User).filter(User.role == UserRole.USER)
    if status_filter in {"pending", "approved", "rejected"}:
        query = query.filter(User.approval_status == status_filter)
    return query.order_by(User.approval_requested_at.asc()).all()


@router.post("/admin/user-approval-requests/{user_id}/approve", response_model=UserResponse)
def approve_user_request(
    user_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.USER).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı")

    user.approval_status = "approved"
    user.is_active = True
    user.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
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
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.USER).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı")

    user.approval_status = "rejected"
    user.is_active = False
    user.approved_at = None
    db.commit()
    db.refresh(user)
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