from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.execution_safety_core_service import (
    apply_runtime_quarantine_action,
    build_execution_incident_package,
    get_execution_intent_state_machine_snapshot,
    get_execution_safety_gate,
    get_runtime_quarantine_snapshot,
)


router = APIRouter(prefix="/execution-readiness", tags=["execution_readiness_core"])


@router.get("/gate")
def execution_safety_gate(
    force_refresh: bool = Query(default=False),
    user_id: str | None = Query(default=None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_execution_safety_gate(db, user_id=user_id, force_refresh=force_refresh)


@router.get("/intents")
def execution_intents_state_machine(
    limit: int = Query(default=100, ge=1, le=250),
    include_events: bool = Query(default=False),
    auto_quarantine_stuck: bool = Query(default=True),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_execution_intent_state_machine_snapshot(
        db,
        limit=limit,
        include_events=include_events,
        auto_quarantine_stuck=auto_quarantine_stuck,
    )


@router.get("/quarantine")
def execution_quarantine_snapshot(
    limit: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_runtime_quarantine_snapshot(db, limit=limit)


@router.post("/quarantine/{event_id}/{action}")
def execution_quarantine_action(
    event_id: str,
    action: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return apply_runtime_quarantine_action(
            db,
            event_id=event_id,
            action=action,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail == "quarantine_event_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/incident/export")
def execution_incident_export(
    include_events: bool = Query(default=False),
    user_id: str | None = Query(default=None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return build_execution_incident_package(db, user_id=user_id, include_events=include_events)
