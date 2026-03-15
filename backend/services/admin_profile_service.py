from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.security import hash_password, verify_password
from models import User, UserOnboardingProfile


def update_admin_profile(db: Session, current_admin: User, *, email: str | None, full_name: str | None) -> User:
    normalized_email = str(email or current_admin.email).strip().lower()
    if normalized_email != current_admin.email:
        existing = db.query(User).filter(User.email == normalized_email, User.id != current_admin.id).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email_already_exists")
        current_admin.email = normalized_email

    onboarding = db.query(UserOnboardingProfile).filter(UserOnboardingProfile.user_id == current_admin.id).first()
    if onboarding is None:
        onboarding = UserOnboardingProfile(user_id=current_admin.id)
        db.add(onboarding)

    if full_name is not None:
        onboarding.full_name = str(full_name).strip() or None

    current_admin.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(current_admin)
    return current_admin


def change_admin_password(db: Session, current_admin: User, *, current_password: str, new_password: str) -> User:
    if not verify_password(current_password, current_admin.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_current_password")

    current_admin.password_hash = hash_password(new_password)
    current_admin.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(current_admin)
    return current_admin
