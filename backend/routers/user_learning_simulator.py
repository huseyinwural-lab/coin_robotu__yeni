from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_user
from models import User
from schemas import (
    LearningImpactSimulationResponse,
    UserLearningImpactSimulationRequest,
    UserLearningSuggestionCreateRequest,
    UserLearningSuggestionResponse,
)
from services.audit_service import create_audit_log
from services.learning_memory_service import simulate_learning_recommendation_impact
from services.user_learning_simulator_service import create_user_learning_suggestion, list_user_learning_suggestions


router = APIRouter(prefix="/user/learning-simulator", tags=["user_learning_simulator"])


@router.post("/simulate", response_model=LearningImpactSimulationResponse)
def user_simulate_learning_impact(
    payload: UserLearningImpactSimulationRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    return simulate_learning_recommendation_impact(
        db,
        strategy_id=payload.strategy_id,
        family=payload.family,
        recommendation_type=payload.recommendation_type,
        suggested_weight_multiplier=payload.suggested_weight_multiplier,
    )


@router.post("/suggestions", response_model=UserLearningSuggestionResponse)
def user_submit_learning_suggestion(
    payload: UserLearningSuggestionCreateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    row = create_user_learning_suggestion(
        db,
        user_id=current_user.id,
        symbol=payload.symbol,
        strategy_id=payload.strategy_id,
        family=payload.family,
        recommendation_type=payload.recommendation_type,
        simulation_payload=payload.simulation_payload,
        note=payload.note,
    )
    create_audit_log(
        db,
        action="user_learning_simulation_suggestion_submitted",
        entity_type="user_learning_simulation_suggestion",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "symbol": row.symbol,
            "strategy_id": row.strategy_id,
            "family": row.family,
            "recommendation_type": row.recommendation_type,
            "status": row.status,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return UserLearningSuggestionResponse(
        id=row.id,
        user_id=row.user_id,
        symbol=row.symbol,
        strategy_id=row.strategy_id,
        family=row.family,
        recommendation_type=row.recommendation_type,
        simulation_payload=row.simulation_payload or {},
        note=row.note,
        status=row.status,
        created_at=row.created_at,
    )


@router.get("/suggestions", response_model=list[UserLearningSuggestionResponse])
def user_list_learning_suggestions(
    limit: int = Query(default=30, ge=1, le=200),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    rows = list_user_learning_suggestions(db, user_id=current_user.id, limit=limit)
    return [
        UserLearningSuggestionResponse(
            id=row.id,
            user_id=row.user_id,
            symbol=row.symbol,
            strategy_id=row.strategy_id,
            family=row.family,
            recommendation_type=row.recommendation_type,
            simulation_payload=row.simulation_payload or {},
            note=row.note,
            status=row.status,
            created_at=row.created_at,
        )
        for row in rows
    ]
