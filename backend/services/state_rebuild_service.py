from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import BotProfile, PaperPosition, StateRebuildLog


def run_state_rebuild(db: Session, trigger_source: str = "startup") -> StateRebuildLog:
    rebuild_log = StateRebuildLog(
        rebuild_type="full_runtime_state",
        status="started",
        trigger_source=trigger_source,
        details={},
    )
    db.add(rebuild_log)
    db.commit()
    db.refresh(rebuild_log)

    open_positions = db.query(PaperPosition).filter(PaperPosition.status == "open").count()
    running_bots = db.query(BotProfile).filter(BotProfile.is_running.is_(True)).count()
    pending_positions = db.query(PaperPosition).filter(PaperPosition.status == "open").limit(20).all()

    rebuild_log.status = "completed"
    rebuild_log.finished_at = datetime.now(timezone.utc)
    rebuild_log.details = {
        "open_positions_count": open_positions,
        "running_bots_count": running_bots,
        "position_sample": [position.id for position in pending_positions],
    }
    db.commit()
    db.refresh(rebuild_log)
    return rebuild_log
