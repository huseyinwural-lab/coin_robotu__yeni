from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.execution_safety_core_service import (
    apply_runtime_quarantine_action,
    batch_recover_stuck_intents,
    build_execution_incident_package,
    get_gate_failure_trends,
    get_execution_intent_state_machine_snapshot,
    get_manual_intervention_audit_trail,
    get_order_reconciliation_summary,
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


@router.post("/intents/stuck/batch-recover")
def execution_stuck_intents_batch_recover(
    action: str = Query(default="replay"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return batch_recover_stuck_intents(
            db,
            action=action,
            limit=limit,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/reconciliation/summary")
def execution_reconciliation_summary(
    limit: int = Query(default=500, ge=1, le=2000),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_order_reconciliation_summary(db, limit=limit)


@router.get("/gate/trends")
def execution_gate_failure_trends(
    days: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(require_admin),
):
    _ = current_user
    return get_gate_failure_trends(days=days)


@router.get("/interventions/audit-trail")
def execution_interventions_audit_trail(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_manual_intervention_audit_trail(db, limit=limit)
