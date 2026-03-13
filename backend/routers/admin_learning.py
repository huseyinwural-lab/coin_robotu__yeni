from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import CanonicalStrategyRegistry, LearningRecommendation, User
from schemas import LearningImpactSimulationRequest, LearningImpactSimulationResponse
from services.audit_service import create_audit_log
from services.learning_memory_service import (
    get_learning_overview,
    list_learning_events,
    refresh_learning_memory,
    simulate_learning_recommendation_impact,
    simulate_recommendation_row_impact,
)


router = APIRouter(prefix="/admin/learning", tags=["admin_learning"])


@router.get("/overview")
def admin_learning_overview(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    return get_learning_overview(db)


@router.post("/refresh")
def admin_learning_refresh(
    days: int = Query(default=30, ge=7, le=180),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    import logging
    logger = logging.getLogger(__name__)
    try:
        payload = refresh_learning_memory(db, window_days=days)
        create_audit_log(
            db,
            action="learning_memory_refreshed",
            entity_type="learning_memory",
            entity_id="global",
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            details={"days": days, "events_count": payload.get("events_count")},
        )
        return payload
    except Exception as exc:
        logger.exception(f"Learning refresh failed: {exc}")
        raise HTTPException(status_code=500, detail=f"learning_refresh_failed: {str(exc)}")


@router.post("/recommendations/{recommendation_id}/apply")
def admin_apply_learning_recommendation(
    recommendation_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    recommendation = db.query(LearningRecommendation).filter(LearningRecommendation.id == recommendation_id).first()
    if recommendation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="learning_recommendation_not_found")

    if recommendation.strategy_id:
        strategy = (
            db.query(CanonicalStrategyRegistry)
            .filter(CanonicalStrategyRegistry.strategy_id == recommendation.strategy_id)
            .first()
        )
        if strategy is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found_for_recommendation")

        rec_type = recommendation.recommendation_type
        rec_val = recommendation.recommendation_value or {}
        if rec_type == "disable_recommendation":
            strategy.is_enabled = bool(rec_val.get("suggested_is_enabled", False))
        elif rec_type in {
            "auto_throttle_recommendation",
            "weight_boost_recommendation",
            "decrease_weight_recommendation",
            "increase_weight_recommendation",
        }:
            multiplier = float(rec_val.get("suggested_weight_multiplier", 1.0))
            strategy.weight = max(0.0, round(float(strategy.weight or 1.0) * multiplier, 4))

    recommendation.is_applied = True
    recommendation.applied_at = datetime.now(timezone.utc)
    db.commit()

    create_audit_log(
        db,
        action="learning_recommendation_applied",
        entity_type="learning_recommendation",
        entity_id=recommendation.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "strategy_id": recommendation.strategy_id,
            "recommendation_type": recommendation.recommendation_type,
        },
    )
    return {
        "status": "ok",
        "schema_version": "learning.v1",
        "engine_version": "learning-engine.v1",
        "generated_at": datetime.now(timezone.utc),
        "recommendation_id": recommendation.id,
        "applied": True,
        "guardrail": {
            "auto_change_forbidden": True,
            "admin_approval_required": True,
            "applied_by_admin": current_admin.id,
        },
    }


@router.get("/events")
def admin_learning_events(
    limit: int = Query(default=200, ge=1, le=1000),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return {
        "schema_version": "learning.v1",
        "engine_version": "learning-engine.v1",
        "generated_at": datetime.now(timezone.utc),
        "items": list_learning_events(db, limit=limit),
    }


@router.post("/recommendations/{recommendation_id}/simulate", response_model=LearningImpactSimulationResponse)
def admin_simulate_learning_recommendation(
    recommendation_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    recommendation = db.query(LearningRecommendation).filter(LearningRecommendation.id == recommendation_id).first()
    if recommendation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="learning_recommendation_not_found")
    return simulate_recommendation_row_impact(db, recommendation=recommendation)


@router.post("/simulate-impact", response_model=LearningImpactSimulationResponse)
def admin_simulate_learning_impact(
    payload: LearningImpactSimulationRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return simulate_learning_recommendation_impact(
        db,
        strategy_id=payload.strategy_id,
        family=payload.family,
        recommendation_type=payload.recommendation_type,
        suggested_weight_multiplier=payload.suggested_weight_multiplier,
    )
