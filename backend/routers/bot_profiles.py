from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, is_admin_role
from models import BotProfile, User
from schemas import BotProfileCreate, BotProfileResponse, BotProfileUpdate, BotRuntimeActionResponse, BotRuntimePerformanceResponse, BotRuntimeStatusResponse
from services.audit_service import create_audit_log
from services.bot_runtime_service import (
    get_bot_runtime_logs,
    get_bot_runtime_performance,
    get_bot_runtime_status,
    get_bot_runtime_trades,
    list_bot_runtime_summaries,
    pause_bot_runtime,
    start_bot_runtime,
    stop_bot_runtime,
)

router = APIRouter(prefix="/bot-profiles", tags=["bot_profiles"])


def _authorized_bot_query(db: Session, bot_id: str, current_user: User):
    query = db.query(BotProfile).filter(BotProfile.id == bot_id, BotProfile.is_deleted.is_(False))
    if not is_admin_role(current_user.role):
        query = query.filter(BotProfile.user_id == current_user.id)
    return query


@router.get("", response_model=list[BotRuntimeStatusResponse])
def list_bot_profiles(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ = db
    return list_bot_runtime_summaries(db, user_id=current_user.id)


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


@router.delete("/{bot_id}")
def delete_bot_profile(
    bot_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot_profile = _authorized_bot_query(db, bot_id, current_user).first()
    if bot_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot profile not found")

    bot_profile.is_running = False
    bot_profile.is_enabled = False
    bot_profile.is_deleted = True
    bot_profile.deleted_at = datetime.now(timezone.utc)
    db.commit()

    create_audit_log(
        db,
        action="bot_profile_deleted",
        entity_type="bot_profile",
        entity_id=bot_profile.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"name": bot_profile.name, "market_type": bot_profile.market_type},
    )
    return {"id": bot_profile.id, "deleted": True}


@router.post("/{bot_id}/start", response_model=BotRuntimeActionResponse)
def start_bot_profile_runtime(bot_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bot_profile = _authorized_bot_query(db, bot_id, current_user).first()
    if bot_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot profile not found")
    payload = start_bot_runtime(db, bot=bot_profile, actor_id=current_user.id)
    create_audit_log(db, action="bot_runtime_start", entity_type="bot_profile", entity_id=bot_profile.id, actor_user_id=current_user.id, actor_role=current_user.role.value, details={"status": payload.get("status"), "binding_ok": payload.get("binding_ok")})
    return BotRuntimeActionResponse(**payload)


@router.post("/{bot_id}/pause", response_model=BotRuntimeActionResponse)
def pause_bot_profile_runtime(bot_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bot_profile = _authorized_bot_query(db, bot_id, current_user).first()
    if bot_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot profile not found")
    payload = pause_bot_runtime(db, bot=bot_profile, actor_id=current_user.id)
    create_audit_log(db, action="bot_runtime_pause", entity_type="bot_profile", entity_id=bot_profile.id, actor_user_id=current_user.id, actor_role=current_user.role.value, details={"status": payload.get("status")})
    return BotRuntimeActionResponse(**payload)


@router.post("/{bot_id}/stop", response_model=BotRuntimeActionResponse)
def stop_bot_profile_runtime(bot_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bot_profile = _authorized_bot_query(db, bot_id, current_user).first()
    if bot_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot profile not found")
    payload = stop_bot_runtime(db, bot=bot_profile, actor_id=current_user.id)
    create_audit_log(db, action="bot_runtime_stop", entity_type="bot_profile", entity_id=bot_profile.id, actor_user_id=current_user.id, actor_role=current_user.role.value, details={"status": payload.get("status"), "force_close_available": payload.get("force_close_available")})
    return BotRuntimeActionResponse(**payload)


@router.get("/{bot_id}/status", response_model=BotRuntimeStatusResponse)
def get_bot_profile_runtime_status(bot_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bot_profile = _authorized_bot_query(db, bot_id, current_user).first()
    if bot_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot profile not found")
    return BotRuntimeStatusResponse(**get_bot_runtime_status(db, bot=bot_profile))


@router.get("/{bot_id}/performance", response_model=BotRuntimePerformanceResponse)
def get_bot_profile_runtime_performance(bot_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bot_profile = _authorized_bot_query(db, bot_id, current_user).first()
    if bot_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot profile not found")
    return BotRuntimePerformanceResponse(**get_bot_runtime_performance(db, bot=bot_profile))


@router.get("/{bot_id}/logs")
def get_bot_profile_runtime_logs(bot_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bot_profile = _authorized_bot_query(db, bot_id, current_user).first()
    if bot_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot profile not found")
    return get_bot_runtime_logs(db, bot=bot_profile)


@router.get("/{bot_id}/trades")
def get_bot_profile_runtime_trades(bot_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bot_profile = _authorized_bot_query(db, bot_id, current_user).first()
    if bot_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot profile not found")
    return get_bot_runtime_trades(db, bot=bot_profile)