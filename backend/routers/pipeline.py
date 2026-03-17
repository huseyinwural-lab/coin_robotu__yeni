from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, is_admin_role, require_admin
from models import BotProfile, SignalEvent, User
from schemas import PipelineMonitoringResponse, SignalEventResponse
from services.audit_service import create_audit_log
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _authorized_bot(db: Session, bot_id: str, current_user: User):
    query = db.query(BotProfile).filter(BotProfile.id == bot_id, BotProfile.is_deleted.is_(False))
    if not is_admin_role(current_user.role):
        query = query.filter(BotProfile.user_id == current_user.id)
    bot = query.first()
    if bot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot profile not found")
    return bot


@router.post("/bots/{bot_id}/start")
def start_bot(bot_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _authorized_bot(db, bot_id, current_user)
    bot.is_running = True
    db.commit()
    create_audit_log(
        db,
        action="bot_start",
        entity_type="bot_profile",
        entity_id=bot.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"name": bot.name, "market_type": bot.market_type},
    )
    return {"id": bot.id, "is_running": True}


@router.post("/bots/{bot_id}/stop")
def stop_bot(bot_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _authorized_bot(db, bot_id, current_user)
    bot.is_running = False
    db.commit()
    create_audit_log(
        db,
        action="bot_stop",
        entity_type="bot_profile",
        entity_id=bot.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"name": bot.name, "market_type": bot.market_type},
    )
    return {"id": bot.id, "is_running": False}


@router.get("/monitoring", response_model=PipelineMonitoringResponse)
def get_pipeline_monitoring(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return pipeline_runtime.monitoring_snapshot(db)


@router.get("/signals", response_model=list[SignalEventResponse])
def list_signal_events(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=10, le=300),
):
    query = db.query(SignalEvent)
    if not is_admin_role(current_user.role):
        query = query.filter(SignalEvent.user_id == current_user.id)
    return query.order_by(SignalEvent.generated_at.desc()).limit(limit).all()