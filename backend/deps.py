from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from core.security import decode_access_token
from db import get_db
from models import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)
ADMIN_ROLES = {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS}


def is_admin_role(role: UserRole) -> bool:
    return role in ADMIN_ROLES


def enforce_owner_scope(current_user: User, owner_user_id: str):
    if is_admin_role(current_user.role):
        return
    if current_user.id != owner_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Kaynağa erişim yetkiniz yok")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

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


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not is_admin_role(current_user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return current_user


def require_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.USER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu endpoint sadece user hesabı ile kullanılabilir")
    return current_user