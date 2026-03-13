from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.users.user_scanner_signal_service import (
    activate_scanner_automation_profile,
    approve_pending_signal,
    bulk_fix_blocked_signals,
    create_scanner_automation_profile,
    delete_scanner_automation_profile,
    diagnose_pending_signal,
    get_or_create_scanner_automation_config,
    get_or_create_signal_mode,
    list_scanner_automation_profiles,
    list_user_scanner_results,
    list_user_signals,
    reject_pending_signal,
    run_user_scanner,
    scanner_automation_config_response_payload,
    scanner_automation_profile_response_payload,
    update_signal_mode,
    update_scanner_automation_profile,
    update_scanner_automation_config,
)
from db import get_db
from deps import require_user
from models import PendingSignal, User, UserScannerResult
from schemas import (
    UserScannerOverviewResponse,
    UserScannerAutomationConfigResponse,
    UserScannerAutomationConfigUpdateRequest,
    UserScannerAutomationProfileCreateRequest,
    UserScannerAutomationProfileResponse,
    UserScannerAutomationProfileUpdateRequest,
    UserScannerResultResponse,
    UserScannerRunRequest,
    UserScannerRunResponse,
    UserSignalDecisionRequest,
    UserSignalDecisionResponse,
    UserSignalDiagnoseResponse,
    UserSignalModeResponse,
    UserSignalModeUpdateRequest,
    UserSignalsBulkFixResponse,
    UserSignalResponse,
)
from services.audit_service import create_audit_log

router = APIRouter(prefix="/user", tags=["user_scanner_signals"])


@router.get("/signal-mode", response_model=UserSignalModeResponse)
def get_signal_mode(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    row = get_or_create_signal_mode(db, current_user.id)
    return UserSignalModeResponse(mode=row.mode, updated_at=row.updated_at)


@router.put("/signal-mode", response_model=UserSignalModeResponse)
def put_signal_mode(
    payload: UserSignalModeUpdateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    row = update_signal_mode(db, current_user.id, payload.mode)
    create_audit_log(
        db,
        action="user_signal_mode_updated",
        entity_type="user_signal_mode",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"mode": row.mode},
    )
    return UserSignalModeResponse(mode=row.mode, updated_at=row.updated_at)


@router.get("/scanner/automation", response_model=UserScannerAutomationConfigResponse)
def get_scanner_automation_config(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    row = get_or_create_scanner_automation_config(db, current_user.id)
    payload = scanner_automation_config_response_payload(row)
    return UserScannerAutomationConfigResponse(**payload)


@router.put("/scanner/automation", response_model=UserScannerAutomationConfigResponse)
def put_scanner_automation_config(
    payload: UserScannerAutomationConfigUpdateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    row = update_scanner_automation_config(
        db,
        current_user.id,
        auto_enabled=payload.auto_enabled,
        interval_seconds=payload.interval_seconds,
        max_results=payload.max_results,
        symbol_source=payload.symbol_source,
        symbol_selection_mode=payload.symbol_selection_mode,
        selected_symbols=payload.selected_symbols,
    )
    create_audit_log(
        db,
        action="user_scanner_automation_config_updated",
        entity_type="user_scanner_automation_config",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "auto_enabled": bool(row.auto_enabled),
            "interval_seconds": int(row.interval_seconds or 180),
            "max_results": int(row.max_results or 25),
            "symbol_source": row.symbol_source,
            "symbol_selection_mode": row.symbol_selection_mode,
            "selected_symbol_count": len(row.selected_symbols or []),
        },
    )
    response_payload = scanner_automation_config_response_payload(row)
    return UserScannerAutomationConfigResponse(**response_payload)


@router.get("/scanner/automation-profiles", response_model=list[UserScannerAutomationProfileResponse])
def get_scanner_automation_profiles(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    rows = list_scanner_automation_profiles(db, current_user.id)
    return [UserScannerAutomationProfileResponse(**scanner_automation_profile_response_payload(row)) for row in rows]


@router.post("/scanner/automation-profiles", response_model=UserScannerAutomationProfileResponse)
def post_scanner_automation_profile(
    payload: UserScannerAutomationProfileCreateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        row = create_scanner_automation_profile(
            db,
            current_user.id,
            name=payload.name,
            auto_enabled=payload.auto_enabled,
            is_active=payload.is_active,
            interval_seconds=payload.interval_seconds,
            max_results=payload.max_results,
            symbol_source=payload.symbol_source,
            symbol_selection_mode=payload.symbol_selection_mode,
            selected_symbols=payload.selected_symbols,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="user_scanner_automation_profile_created",
        entity_type="user_scanner_automation_profile",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "name": row.name,
            "auto_enabled": bool(row.auto_enabled),
            "interval_seconds": int(row.interval_seconds or 180),
            "selected_symbol_count": len(row.selected_symbols or []),
        },
    )
    return UserScannerAutomationProfileResponse(**scanner_automation_profile_response_payload(row))


@router.put("/scanner/automation-profiles/{profile_id}", response_model=UserScannerAutomationProfileResponse)
def put_scanner_automation_profile(
    profile_id: str,
    payload: UserScannerAutomationProfileUpdateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        row = update_scanner_automation_profile(
            db,
            current_user.id,
            profile_id,
            name=payload.name,
            auto_enabled=payload.auto_enabled,
            is_active=payload.is_active,
            interval_seconds=payload.interval_seconds,
            max_results=payload.max_results,
            symbol_source=payload.symbol_source,
            symbol_selection_mode=payload.symbol_selection_mode,
            selected_symbols=payload.selected_symbols,
        )
    except ValueError as exc:
        message = str(exc)
        if message == "scanner_automation_profile_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc

    create_audit_log(
        db,
        action="user_scanner_automation_profile_updated",
        entity_type="user_scanner_automation_profile",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "name": row.name,
            "auto_enabled": bool(row.auto_enabled),
            "is_active": bool(row.is_active),
            "interval_seconds": int(row.interval_seconds or 180),
            "selected_symbol_count": len(row.selected_symbols or []),
        },
    )
    return UserScannerAutomationProfileResponse(**scanner_automation_profile_response_payload(row))


@router.post("/scanner/automation-profiles/{profile_id}/activate", response_model=UserScannerAutomationProfileResponse)
def post_activate_scanner_automation_profile(
    profile_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        row = activate_scanner_automation_profile(db, current_user.id, profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="user_scanner_automation_profile_activated",
        entity_type="user_scanner_automation_profile",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"name": row.name},
    )
    return UserScannerAutomationProfileResponse(**scanner_automation_profile_response_payload(row))


@router.delete("/scanner/automation-profiles/{profile_id}")
def delete_scanner_automation_profile_route(
    profile_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    deleted = delete_scanner_automation_profile(db, current_user.id, profile_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scanner_automation_profile_not_found")

    create_audit_log(
        db,
        action="user_scanner_automation_profile_deleted",
        entity_type="user_scanner_automation_profile",
        entity_id=profile_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={},
    )
    return {"status": "ok", "deleted": True, "profile_id": profile_id}


@router.post("/scanner/run", response_model=UserScannerRunResponse)
def scanner_run(
    payload: UserScannerRunRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    result = run_user_scanner(
        db,
        current_user.id,
        requested_mode=payload.mode,
        max_results=payload.max_results,
        symbol_source=payload.symbol_source,
        selected_symbols=payload.selected_symbols,
        symbol_selection_mode=payload.symbol_selection_mode,
    )
    create_audit_log(
        db,
        action="user_scanner_run",
        entity_type="user_scanner",
        entity_id=result["run_id"],
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "mode": result["mode"],
            "result_count": result["result_count"],
            "actionable_count": result["actionable_count"],
            "queued_count": result["queued_count"],
        },
    )
    return UserScannerRunResponse(**result)


@router.get("/scanner/results", response_model=list[UserScannerResultResponse])
def scanner_results(
    limit: int = Query(default=50, ge=5, le=200),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return list_user_scanner_results(db, current_user.id, limit=limit)


@router.get("/scanner", response_model=UserScannerOverviewResponse)
def scanner_overview(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    mode_row = get_or_create_signal_mode(db, current_user.id)
    latest_result = (
        db.query(UserScannerResult)
        .filter(UserScannerResult.user_id == current_user.id)
        .order_by(UserScannerResult.generated_at.desc())
        .first()
    )
    total_results = len(list_user_scanner_results(db, current_user.id, limit=200))
    pending_signals = (
        db.query(PendingSignal)
        .filter(PendingSignal.user_id == current_user.id, PendingSignal.status == "pending")
        .count()
    )
    return UserScannerOverviewResponse(
        mode=mode_row.mode,
        total_results=total_results,
        pending_signals=pending_signals,
        latest_run_id=latest_result.run_id if latest_result else None,
        latest_generated_at=latest_result.generated_at if latest_result else None,
    )


@router.get("/signals", response_model=list[UserSignalResponse])
def signals(
    limit: int = Query(default=100, ge=5, le=300),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return list_user_signals(db, current_user.id, limit=limit)


@router.post("/signal/{signal_id}/approve", response_model=UserSignalDecisionResponse)
def approve_signal(
    signal_id: str,
    payload: UserSignalDecisionRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        row = approve_pending_signal(db, current_user.id, signal_id, note=payload.note)
    except ValueError as exc:
        message = str(exc)
        if message == "pending_signal_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc

    create_audit_log(
        db,
        action="user_pending_signal_approved",
        entity_type="pending_signal",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"order_position_id": row.order_position_id},
    )
    return UserSignalDecisionResponse(
        id=row.id,
        status=row.status,
        order_position_id=row.order_position_id,
        decided_at=row.decided_at,
        decision_note=row.decision_note,
        current_state=row.current_state,
        blocked_reason_code=row.blocked_reason_code,
        created_order_intent_id=row.created_order_intent_id,
    )


@router.post("/signal/{signal_id}/reject", response_model=UserSignalDecisionResponse)
def reject_signal(
    signal_id: str,
    payload: UserSignalDecisionRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        row = reject_pending_signal(db, current_user.id, signal_id, note=payload.note)
    except ValueError as exc:
        message = str(exc)
        if message == "pending_signal_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc

    create_audit_log(
        db,
        action="user_pending_signal_rejected",
        entity_type="pending_signal",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"decision_note": row.decision_note},
    )
    return UserSignalDecisionResponse(
        id=row.id,
        status=row.status,
        order_position_id=row.order_position_id,
        decided_at=row.decided_at,
        decision_note=row.decision_note,
        current_state=row.current_state,
        blocked_reason_code=row.blocked_reason_code,
        created_order_intent_id=row.created_order_intent_id,
    )


@router.post("/signal/{signal_id}/diagnose", response_model=UserSignalDiagnoseResponse)
def diagnose_signal(
    signal_id: str,
    auto_fix: bool = Query(default=False),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        row, actions_applied = diagnose_pending_signal(db, current_user.id, signal_id, auto_fix=auto_fix)
    except ValueError as exc:
        message = str(exc)
        if message == "pending_signal_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc

    create_audit_log(
        db,
        action="user_pending_signal_diagnosed",
        entity_type="pending_signal",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"auto_fix": bool(auto_fix), "actions_applied": actions_applied},
    )

    return UserSignalDiagnoseResponse(
        id=row.id,
        status=row.status,
        current_state=row.current_state or "DETECTED",
        blocked_reason_code=row.blocked_reason_code or "",
        blocked_reason_message=row.blocked_reason_message or "",
        blocked_solution_hint=row.blocked_solution_hint or "",
        requires_manual_approval=bool(row.requires_manual_approval),
        execution_eligible=bool(row.execution_eligible),
        bot_profile_id=row.bot_profile_id,
        risk_policy_id=row.risk_policy_id,
        exchange_connection_id=row.exchange_connection_id,
        created_order_intent_id=row.created_order_intent_id,
        runtime_owner=row.runtime_owner or "",
        last_eligibility_check_at=row.last_eligibility_check_at,
        actions_applied=actions_applied,
    )


@router.post("/signals/fix-all-blockers", response_model=UserSignalsBulkFixResponse)
def fix_all_blocked_signals(
    limit: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    payload = bulk_fix_blocked_signals(db, current_user.id, limit=limit)
    create_audit_log(
        db,
        action="user_signals_fix_all_blockers",
        entity_type="pending_signal",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "scanned_count": payload.get("scanned_count", 0),
            "fixed_count": payload.get("fixed_count", 0),
            "remaining_blocked": payload.get("remaining_blocked", 0),
            "actions_summary": payload.get("actions_summary") or {},
        },
    )
    return UserSignalsBulkFixResponse(**payload)