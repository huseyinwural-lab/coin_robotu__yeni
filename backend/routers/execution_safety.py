from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.execution_safety_namespace_service import (
    batch_execution_recovery,
    apply_execution_safety_quarantine_action,
    apply_intent_recovery_action,
    create_execution_attempt_artifact,
    evaluate_execution_safety_gate,
    export_execution_incident_package,
    get_execution_gate_trends,
    get_execution_intervention_audit,
    get_execution_observability_snapshot,
    get_execution_reconciliation_summary,
    get_execution_recovery_overview,
    get_execution_safety_intents,
    get_execution_safety_quarantine,
    get_unified_environment_policy,
    update_unified_environment_policy,
)
from services.execution_safety_advanced_service import (
    get_artifact_by_intent,
    get_intent_reconcile,
    get_intent_timeline,
    get_latest_testnet_acceptance,
    get_quarantine_detail,
    get_testnet_acceptance_history,
    run_bulk_recovery,
    run_testnet_acceptance,
)


router = APIRouter(prefix="/execution-safety", tags=["execution_safety"])


@router.get("/gate")
def execution_safety_gate(
    force_refresh: bool = Query(default=False),
    user_id: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return evaluate_execution_safety_gate(
        db,
        force_refresh=force_refresh,
        user_id=user_id,
        request_id=request_id,
        session_id=session_id,
        correlation_id=correlation_id,
    )


@router.get("/intents")
def execution_safety_intents(
    limit: int = Query(default=100, ge=1, le=300),
    include_events: bool = Query(default=False),
    auto_quarantine_stuck: bool = Query(default=True),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_execution_safety_intents(
        db,
        limit=limit,
        include_events=include_events,
        auto_quarantine_stuck=auto_quarantine_stuck,
    )


@router.get("/intents/{intent_id}/timeline")
def execution_safety_intent_timeline(
    intent_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    try:
        return get_intent_timeline(db, intent_id=intent_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/intents/{intent_id}/reconcile")
def execution_safety_intent_reconcile(
    intent_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    try:
        return get_intent_reconcile(db, intent_id=intent_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/quarantine")
def execution_safety_quarantine(
    limit: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_execution_safety_quarantine(db, limit=limit)


@router.get("/quarantine/{quarantine_id}")
def execution_safety_quarantine_detail(
    quarantine_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    try:
        return get_quarantine_detail(db, quarantine_id=quarantine_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/quarantine/{quarantine_id}/{action}")
def execution_safety_quarantine_action(
    quarantine_id: str,
    action: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return apply_execution_safety_quarantine_action(
            db,
            quarantine_id=quarantine_id,
            action=action,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail == "quarantine_event_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/artifacts")
def execution_safety_artifacts(
    intent_id: str = Query(...),
    request_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    execution_id: str | None = Query(default=None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    try:
        return create_execution_attempt_artifact(
            db,
            intent_id=intent_id,
            request_id=request_id,
            session_id=session_id,
            execution_id=execution_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail == "intent_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/artifacts/incident-export")
def execution_safety_incident_export(
    include_events: bool = Query(default=False),
    user_id: str | None = Query(default=None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return export_execution_incident_package(db, include_events=include_events, user_id=user_id)


@router.get("/artifacts/{intent_id}")
def execution_safety_artifact_by_intent(
    intent_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    try:
        return get_artifact_by_intent(db, intent_id=intent_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/recovery")
def execution_safety_recovery_overview(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_execution_recovery_overview(db)


@router.post("/recovery/batch")
def execution_safety_recovery_batch(
    action: str = Query(default="retry"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return batch_execution_recovery(
            db,
            action=action,
            limit=limit,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _parse_bulk_payload(payload: dict | None) -> dict:
    source = dict(payload or {})
    return {
        "selection_mode": str(source.get("selection_mode") or "explicit_ids"),
        "intent_ids": list(source.get("intent_ids") or []),
        "quarantine_ids": list(source.get("quarantine_ids") or []),
        "filters": dict(source.get("filters") or {}),
        "reason": str(source.get("reason") or "bulk_action"),
        "requested_by": str(source.get("requested_by") or "admin"),
    }


@router.post("/recovery/bulk-retry")
def execution_safety_bulk_retry(
    payload: dict = Body(default={}),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    parsed = _parse_bulk_payload(payload)
    return run_bulk_recovery(db, action="bulk_retry", **parsed)


@router.post("/recovery/bulk-cancel")
def execution_safety_bulk_cancel(
    payload: dict = Body(default={}),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    parsed = _parse_bulk_payload(payload)
    return run_bulk_recovery(db, action="bulk_cancel", **parsed)


@router.post("/recovery/bulk-reconcile")
def execution_safety_bulk_reconcile(
    payload: dict = Body(default={}),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    parsed = _parse_bulk_payload(payload)
    return run_bulk_recovery(db, action="bulk_reconcile", **parsed)


@router.get("/recovery/policy")
def execution_safety_recovery_policy(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_unified_environment_policy(db)


@router.post("/recovery/policy/{environment}")
def execution_safety_update_policy(
    environment: str,
    enable_flag: bool = Query(...),
    validation_status: str = Query(...),
    path_open: bool = Query(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return update_unified_environment_policy(
            db,
            environment=environment,
            enable_flag=enable_flag,
            validation_status=validation_status,
            path_open=path_open,
            verification_evidence={"updated_from": "api", "actor": current_user.id},
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/recovery/{intent_id}/{action}")
def execution_safety_recovery_action(
    intent_id: str,
    action: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return apply_intent_recovery_action(
            db,
            intent_id=intent_id,
            action=action,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail == "intent_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/acceptance/testnet/run")
def execution_safety_acceptance_run(
    symbol: str = Query(default="BTCUSDT"),
    qty: float = Query(default=0.001),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return run_testnet_acceptance(db, symbol=symbol, qty=qty, requested_by=current_user.id)


@router.get("/acceptance/testnet/latest")
def execution_safety_acceptance_latest(
    current_user: User = Depends(require_admin),
):
    _ = current_user
    return get_latest_testnet_acceptance()


@router.get("/acceptance/testnet/history")
def execution_safety_acceptance_history(
    limit: int = Query(default=50, ge=1, le=500),
    current_user: User = Depends(require_admin),
):
    _ = current_user
    return get_testnet_acceptance_history(limit=limit)


@router.get("/observability")
def execution_safety_observability(
    user_id: str | None = Query(default=None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_execution_observability_snapshot(db, user_id=user_id)


@router.get("/recovery/reconciliation-summary")
def execution_safety_reconciliation_summary(
    limit: int = Query(default=500, ge=1, le=2000),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_execution_reconciliation_summary(db, limit=limit)


@router.get("/recovery/gate-trends")
def execution_safety_gate_trends(
    days: int = Query(default=14, ge=1, le=90),
    current_user: User = Depends(require_admin),
):
    _ = current_user
    return get_execution_gate_trends(days=days)


@router.get("/recovery/intervention-audit")
def execution_safety_intervention_audit(
    limit: int = Query(default=120, ge=1, le=500),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_execution_intervention_audit(db, limit=limit)
