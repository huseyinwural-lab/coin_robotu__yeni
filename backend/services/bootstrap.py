from sqlalchemy.orm import Session

from core.config import settings
from core.security import hash_password
from db import SessionLocal
from models import User, UserRole
from services.audit_service import create_audit_log


def _seed_admin(db: Session):
    if not settings.default_admin_email or not settings.default_admin_password:
        return

    existing_admin = db.query(User).filter(User.email == settings.default_admin_email).first()
    if existing_admin:
        return

    admin = User(
        email=settings.default_admin_email,
        password_hash=hash_password(settings.default_admin_password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    create_audit_log(
        db,
        action="bootstrap_admin_created",
        entity_type="user",
        entity_id=admin.id,
        actor_user_id=admin.id,
        actor_role=admin.role.value,
        details={"email": admin.email},
    )


def seed_default_admin():
    db = SessionLocal()
    try:
        _seed_admin(db)
    finally:
        db.close()