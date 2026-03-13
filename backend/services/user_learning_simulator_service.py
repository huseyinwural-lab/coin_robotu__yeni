from datetime import datetime, timezone

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from models import UserLearningSimulationSuggestion


def _ensure_user_learning_table(db: Session) -> None:
    inspector = inspect(db.bind)
    if UserLearningSimulationSuggestion.__table__.name not in set(inspector.get_table_names()):
        UserLearningSimulationSuggestion.__table__.create(bind=db.bind, checkfirst=True)


def create_user_learning_suggestion(
    db: Session,
    *,
    user_id: str,
    symbol: str | None,
    strategy_id: str | None,
    family: str | None,
    recommendation_type: str,
    simulation_payload: dict,
    note: str,
) -> UserLearningSimulationSuggestion:
    _ensure_user_learning_table(db)
    row = UserLearningSimulationSuggestion(
        user_id=user_id,
        symbol=str(symbol).upper() if symbol else None,
        strategy_id=str(strategy_id) if strategy_id else None,
        family=str(family) if family else None,
        recommendation_type=str(recommendation_type or "decrease_weight_recommendation"),
        simulation_payload=simulation_payload or {},
        note=str(note or "")[:280],
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_user_learning_suggestions(db: Session, *, user_id: str, limit: int = 50) -> list[UserLearningSimulationSuggestion]:
    _ensure_user_learning_table(db)
    return (
        db.query(UserLearningSimulationSuggestion)
        .filter(UserLearningSimulationSuggestion.user_id == user_id)
        .order_by(UserLearningSimulationSuggestion.created_at.desc())
        .limit(max(1, min(limit, 300)))
        .all()
    )


def list_admin_learning_suggestions(db: Session, *, limit: int = 200) -> list[UserLearningSimulationSuggestion]:
    _ensure_user_learning_table(db)
    return (
        db.query(UserLearningSimulationSuggestion)
        .order_by(UserLearningSimulationSuggestion.created_at.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
