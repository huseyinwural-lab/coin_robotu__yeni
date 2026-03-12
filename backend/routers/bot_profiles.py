from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, is_admin_role
from models import BotProfile, User
from schemas import BotProfileCreate, BotProfileResponse, BotProfileUpdate
from services.audit_service import create_audit_log

router = APIRouter(prefix="/bot-profiles", tags=["bot_profiles"])


def _authorized_bot_query(db: Session, bot_id: str, current_user: User):
    query = db.query(BotProfile).filter(BotProfile.id == bot_id)
    if not is_admin_role(current_user.role):
        query = query.filter(BotProfile.user_id == current_user.id)
    return query


@router.get("", response_model=list[BotProfileResponse])
def list_bot_profiles(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(BotProfile)
    if not is_admin_role(current_user.role):
        query = query.filter(BotProfile.user_id == current_user.id)
    return query.order_by(BotProfile.created_at.desc()).all()


@router.post("", response_model=BotProfileResponse)
def create_bot_profile(
    payload: BotProfileCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot_profile = BotProfile(user_id=current_user.id, **payload.model_dump())
    db.add(bot_profile)
    db.commit()
    db.refresh(bot_profile)

    create_audit_log(
        db,
        action="bot_profile_created",
        entity_type="bot_profile",
        entity_id=bot_profile.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"name": bot_profile.name, "exchange": bot_profile.exchange},
    )
    return bot_profile


@router.put("/{bot_id}", response_model=BotProfileResponse)
def update_bot_profile(
    bot_id: str,
    payload: BotProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot_profile = _authorized_bot_query(db, bot_id, current_user).first()
    if bot_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot profile not found")

    for key, value in payload.model_dump().items():
        setattr(bot_profile, key, value)

    db.commit()
    db.refresh(bot_profile)
    create_audit_log(
        db,
        action="bot_profile_updated",
        entity_type="bot_profile",
        entity_id=bot_profile.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"name": bot_profile.name},
    )
    return bot_profile