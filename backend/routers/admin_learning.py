from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import LearningRecommendation, User
from schemas import LearningImpactSimulationRequest, LearningImpactSimulationResponse
from schemas import UserLearningSuggestionResponse
from services.audit_service import create_audit_log
from services.learning_memory_service import (
    apply_learning_recommendation,
    approve_learning_recommendation,
    get_learning_overview,
    get_learning_post_change_monitoring,
    get_learning_version_history,
    list_learning_events,
    mark_learning_recommendation_simulated,
    reject_learning_recommendation,
    refresh_learning_memory,
    rollback_learning_recommendation,
    serialize_learning_recommendation,
    simulate_learning_recommendation_impact,
    simulate_recommendation_row_impact,
)
from services.user_learning_simulator_service import list_admin_learning_suggestions


router = APIRouter(prefix="/admin/learning", tags=["admin_learning"])


class LearningRecommendationDecisionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=400)


class LearningRecommendationApplyRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=400)


class LearningRecommendationRollbackRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=400)


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
    payload: LearningRecommendationApplyRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        response = apply_learning_recommendation(db, recommendation_id=recommendation_id, actor=current_admin.id, reason=payload.reason)
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail in {"learning_recommendation_not_found", "strategy_not_found_for_recommendation"} else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc

    create_audit_log(
        db,
        action="learning_recommendation_applied",
        entity_type="learning_recommendation",
        entity_id=recommendation_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "recommendation_id": recommendation_id,
            "reason": payload.reason,
            "lifecycle": response.get("lifecycle"),
            "version_ref": (response.get("version") or {}).get("current_version"),
            "before_payload": (response.get("status_history") or [{}])[-1].get("before_payload", {}),
            "after_payload": (response.get("status_history") or [{}])[-1].get("after_payload", {}),
        },
    )
    return {
        "status": "ok",
        "schema_version": "learning.v1",
        "engine_version": "learning-engine.v1",
        "generated_at": datetime.now(timezone.utc),
        "recommendation_id": recommendation_id,
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
    simulation = simulate_recommendation_row_impact(db, recommendation=recommendation)
    updated = mark_learning_recommendation_simulated(
        db,
        recommendation_id=recommendation_id,
        actor=current_admin.id,
        reason="row_simulation",
        simulation_payload=simulation,
    )
    create_audit_log(
        db,
        action="learning_recommendation_simulated",
        entity_type="learning_recommendation",
        entity_id=recommendation_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "reason": "row_simulation",
            "recommendation_id": recommendation_id,
            "version_ref": (updated.get("version") or {}).get("current_version"),
            "before_payload": {},
            "after_payload": {"simulation_scope": simulation.get("scope")},
        },
    )
    return simulation


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
        strategy_ids=payload.strategy_ids,
        family=payload.family,
        symbol_cluster=payload.symbol_cluster,
        scenario=payload.scenario,
        recommendation_type=payload.recommendation_type,
        suggested_weight_multiplier=payload.suggested_weight_multiplier,
    )


@router.post("/recommendations/{recommendation_id}/approve")
def admin_approve_learning_recommendation(
    recommendation_id: str,
    payload: LearningRecommendationDecisionRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        response = approve_learning_recommendation(db, recommendation_id=recommendation_id, actor=current_admin.id, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    create_audit_log(
        db,
        action="learning_recommendation_approved",
        entity_type="learning_recommendation",
        entity_id=recommendation_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "actor": current_admin.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": payload.reason,
            "recommendation_id": recommendation_id,
            "version_ref": (response.get("version") or {}).get("current_version"),
            "before_payload": (response.get("status_history") or [{}])[-1].get("before_payload", {}),
            "after_payload": (response.get("status_history") or [{}])[-1].get("after_payload", {}),
        },
    )
    return {"recommendation": response}


@router.post("/recommendations/{recommendation_id}/reject")
def admin_reject_learning_recommendation(
    recommendation_id: str,
    payload: LearningRecommendationDecisionRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        response = reject_learning_recommendation(db, recommendation_id=recommendation_id, actor=current_admin.id, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    create_audit_log(
        db,
        action="learning_recommendation_rejected",
        entity_type="learning_recommendation",
        entity_id=recommendation_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "actor": current_admin.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": payload.reason,
            "recommendation_id": recommendation_id,
            "version_ref": (response.get("version") or {}).get("current_version"),
            "before_payload": (response.get("status_history") or [{}])[-1].get("before_payload", {}),
            "after_payload": (response.get("status_history") or [{}])[-1].get("after_payload", {}),
        },
    )
    return {"recommendation": response}


@router.post("/recommendations/{recommendation_id}/rollback")
def admin_rollback_learning_recommendation(
    recommendation_id: str,
    payload: LearningRecommendationRollbackRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        response = rollback_learning_recommendation(db, recommendation_id=recommendation_id, actor=current_admin.id, reason=payload.reason)
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail == "learning_recommendation_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc
    create_audit_log(
        db,
        action="learning_recommendation_rolled_back",
        entity_type="learning_recommendation",
        entity_id=recommendation_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "actor": current_admin.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": payload.reason,
            "recommendation_id": recommendation_id,
            "version_ref": (response.get("version") or {}).get("current_version"),
            "before_payload": (response.get("status_history") or [{}])[-1].get("before_payload", {}),
            "after_payload": (response.get("status_history") or [{}])[-1].get("after_payload", {}),
        },
    )
    return {"recommendation": response}


@router.get("/recommendations/{recommendation_id}/version-history")
def admin_learning_recommendation_version_history(
    recommendation_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    try:
        return get_learning_version_history(db, recommendation_id=recommendation_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/recommendations/{recommendation_id}/post-change-monitoring")
def admin_learning_recommendation_post_change_monitoring(
    recommendation_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    try:
        return get_learning_post_change_monitoring(db, recommendation_id=recommendation_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/user-suggestions", response_model=list[UserLearningSuggestionResponse])
def admin_list_user_learning_suggestions(
    limit: int = Query(default=120, ge=1, le=500),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = list_admin_learning_suggestions(db, limit=limit)
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
