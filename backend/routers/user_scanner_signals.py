from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN
import time

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
from models import PendingSignal, User, UserExecutionIntent, UserScannerResult, UserExchangeConnection
from core.users.user_exchange_connector import decrypt_exchange_secret
from schemas import (
    IndicatorScreenerPresetResponse,
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
from services.explainability_rules_service import build_screener_explain
from services.indicator_screener.indicator_query_engine_service import indicator_screener_presets
from services.live_mode_service import (
    adapter as live_adapter,
    validate_exchange_credentials_for_user,
    _fetch_symbol_filters,
    _quantize_to_step,
)
from services.quote_asset_constraints import allowed_quote_assets
from services.quote_asset_policy import extract_quote_asset, filter_allowed_quote_symbols

router = APIRouter(prefix="/user", tags=["user_scanner_signals"])


@router.get("/scanner/presets", response_model=list[IndicatorScreenerPresetResponse])
def get_scanner_presets(
    active_only: bool = Query(True),
    current_user: User = Depends(require_user),
):
    presets = indicator_screener_presets()
    if active_only:
        presets = [item for item in presets if bool(item.get("is_active", True))]
    return presets


def _allowed_quote_notice() -> str:
    quotes = ", ".join(allowed_quote_assets())
    return f"İşlem için en az bir geçerli market seçmelisiniz. Allowed quote assets: {quotes}"


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
    selected_symbols = payload.selected_symbols or []
    valid_symbols = filter_allowed_quote_symbols(selected_symbols)
    if payload.symbol_selection_mode == "manual_selection" and len(valid_symbols) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_allowed_quote_notice())

    try:
        result = run_user_scanner(
            db,
            current_user.id,
            requested_mode=payload.mode,
            max_results=payload.max_results,
            symbol_source=payload.symbol_source,
            market_type=payload.market_type,
            selected_symbols=valid_symbols,
            symbol_selection_mode=payload.symbol_selection_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="scanner_run_failed") from exc
    create_audit_log(
        db,
        action="SCAN_RESULT",
        entity_type="user_scanner",
        entity_id=result["run_id"],
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "stage": "SCAN RESULT",
            "mode": result["mode"],
            "selected_symbols": result.get("selected_symbols") or [],
            "result_count": result["result_count"],
            "actionable_count": result["actionable_count"],
            "queued_count": result["queued_count"],
            "scanner_perf": result.get("scanner_perf") or {},
        },
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
    rows = list_user_scanner_results(db, current_user.id, limit=limit)
    return [
        UserScannerResultResponse(
            id=row.id,
            run_id=row.run_id,
            user_id=row.user_id,
            symbol=row.symbol,
            quote_asset=str((row.payload or {}).get("quote_asset") or extract_quote_asset(row.symbol) or "UNKNOWN"),
            strategy_code=row.strategy_code,
            signal=row.signal,
            confidence=float(row.confidence),
            score=float(row.signal_score),
            signal_score=float(row.signal_score),
            reason_codes=list(row.reason_codes or []),
            explain=build_screener_explain(payload=dict(row.payload or {}), signal=row.signal, signal_score=row.signal_score),
            payload=dict(row.payload or {}),
            generated_at=row.generated_at,
        )
        for row in rows
    ]


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
    rows = list_user_signals(db, current_user.id, limit=limit)

    def _safe_float(value, fallback: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    return [
        UserSignalResponse(
            id=row.id,
            signal_id=row.signal_id,
            user_id=row.user_id,
            symbol=row.symbol,
            quote_asset=extract_quote_asset(row.symbol),
            strategy_code=row.strategy_code,
            confidence=_safe_float(row.confidence),
            mode=row.mode,
            status=row.status,
            market_type=getattr(row, "market_type", "spot"),
            order_position_id=row.order_position_id,
            created_at=row.created_at,
            decided_at=row.decided_at,
            decision_note=row.decision_note or "",
            strategy_weight=row.strategy_weight,
            allocation_source=row.allocation_source,
            meta_engine_decision=row.meta_engine_decision,
            previous_state=row.previous_state,
            current_state=row.current_state,
            blocked_reason_code=row.blocked_reason_code,
            blocked_reason_message=row.blocked_reason_message,
            blocked_solution_hint=row.blocked_solution_hint,
            requires_manual_approval=row.requires_manual_approval,
            execution_eligible=row.execution_eligible,
            bot_profile_id=row.bot_profile_id,
            risk_policy_id=row.risk_policy_id,
            exchange_connection_id=row.exchange_connection_id,
            created_order_intent_id=row.created_order_intent_id,
            runtime_owner=row.runtime_owner,
            last_eligibility_check_at=row.last_eligibility_check_at,
            execution_mode_label=getattr(row, "execution_mode_label", None),
        )
        for row in rows
    ]


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


@router.post("/signals/cleanup-stale-intents")
def cleanup_stale_intents_and_signals(
    stale_minutes: int = Query(default=25, ge=5, le=1440),
    signal_stale_minutes: int = Query(default=180, ge=30, le=10080),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    intent_cutoff = now - timedelta(minutes=stale_minutes)
    signal_cutoff = now - timedelta(minutes=signal_stale_minutes)

    stale_intents = (
        db.query(UserExecutionIntent)
        .filter(
            UserExecutionIntent.user_id == current_user.id,
            UserExecutionIntent.status.in_(["PREVIEWED", "SUBMITTED", "QUEUED", "APPROVED"]),
            UserExecutionIntent.created_at <= intent_cutoff,
        )
        .order_by(UserExecutionIntent.created_at.asc())
        .limit(500)
        .all()
    )

    cancelled_intent_ids: list[str] = []
    for intent in stale_intents:
        intent.status = "CANCELLED"
        intent.cancelled_at = now
        note = str(intent.admin_note or "").strip()
        cleanup_note = "stale_cleanup_user_signals"
        intent.admin_note = f"{note} | {cleanup_note}".strip(" |") if note else cleanup_note
        cancelled_intent_ids.append(str(intent.id))

    stale_signals = (
        db.query(PendingSignal)
        .filter(
            PendingSignal.user_id == current_user.id,
            PendingSignal.status.in_(["pending", "blocked", "approved", "ready"]),
            PendingSignal.created_at <= signal_cutoff,
            PendingSignal.order_position_id.is_(None),
        )
        .order_by(PendingSignal.created_at.asc())
        .limit(500)
        .all()
    )

    expired_signal_ids: list[str] = []
    for row in stale_signals:
        row.status = "expired"
        row.current_state = "EXPIRED"
        row.previous_state = row.previous_state or "DETECTED"
        row.blocked_reason_code = "SIGNAL_EXPIRED"
        row.blocked_reason_message = "Sinyal süresi doldu (stale cleanup)."
        row.blocked_solution_hint = "Scanner'ı yeniden çalıştırarak güncel sinyal üretin."
        row.execution_eligible = False
        row.last_eligibility_check_at = now
        expired_signal_ids.append(str(row.id))

    db.commit()

    create_audit_log(
        db,
        action="user_signals_cleanup_stale",
        entity_type="pending_signal",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "stale_minutes": stale_minutes,
            "signal_stale_minutes": signal_stale_minutes,
            "cancelled_intent_count": len(cancelled_intent_ids),
            "expired_signal_count": len(expired_signal_ids),
        },
    )

    return {
        "status": "ok",
        "stale_minutes": stale_minutes,
        "signal_stale_minutes": signal_stale_minutes,
        "cancelled_intent_count": len(cancelled_intent_ids),
        "expired_signal_count": len(expired_signal_ids),
        "cancelled_intent_ids": cancelled_intent_ids,
        "expired_signal_ids": expired_signal_ids,
    }


@router.post("/scanner/live-spot-roundtrip")
def run_live_spot_roundtrip_from_scanner(
    max_symbols: int = Query(default=3, ge=1, le=10),
    hold_seconds: float = Query(default=1.0, ge=0.2, le=10.0),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(UserExchangeConnection)
        .filter(
            UserExchangeConnection.user_id == current_user.id,
            UserExchangeConnection.market_type == "spot",
            UserExchangeConnection.environment == "live",
        )
        .order_by(UserExchangeConnection.updated_at.desc())
        .first()
    )
    if connection is None:
        raise HTTPException(status_code=400, detail={"reason": "live_spot_connection_not_found"})

    validation_payload, validation_status = validate_exchange_credentials_for_user(
        db,
        current_user.id,
        exchange="binance",
        market_type="spot",
        environment="live",
        connection_id=connection.id,
    )
    if validation_status != 200:
        raise HTTPException(
            status_code=400,
            detail={
                "reason": "spot_live_validation_failed",
                "validation": validation_payload,
            },
        )

    api_key = decrypt_exchange_secret(connection.api_key_encrypted)
    api_secret = decrypt_exchange_secret(connection.api_secret_encrypted)

    wallet_before, wallet_status, _ = live_adapter.account_probe_spot(api_key, api_secret, environment="live")
    if wallet_status >= 400:
        raise HTTPException(status_code=400, detail={"reason": "spot_wallet_probe_failed", "payload": wallet_before})

    total_usdt_before = 0.0
    free_usdt_before = 0.0
    for balance in wallet_before.get("balances") or []:
        if str(balance.get("asset") or "").upper() == "USDT":
            free_usdt_before = float(balance.get("free") or 0.0)
            total_usdt_before = free_usdt_before + float(balance.get("locked") or 0.0)
            break

    quote_order_qty = round(max(total_usdt_before * 0.2, 5.0), 2)

    scanner_result = run_user_scanner(
        db,
        current_user.id,
        requested_mode="AUTO",
        max_results=max(30, max_symbols * 8),
        symbol_source="crypto",
        market_type="spot",
        selected_symbols=[],
        symbol_selection_mode="all_market_symbols",
    )

    rows = list_user_signals(db, current_user.id, limit=200)
    approved_symbols: list[str] = []
    for row in rows:
        if str(getattr(row, "market_type", "spot") or "spot").lower() != "spot":
            continue
        if not bool(getattr(row, "execution_eligible", False)):
            continue
        if str(getattr(row, "blocked_reason_code", "") or "").strip():
            continue
        symbol = str(getattr(row, "symbol", "") or "").upper().strip()
        if symbol and symbol not in approved_symbols:
            approved_symbols.append(symbol)
        if len(approved_symbols) >= max_symbols:
            break

    if len(approved_symbols) < max_symbols:
        for symbol in scanner_result.get("selected_symbols") or []:
            symbol = str(symbol or "").upper().strip()
            if symbol and symbol not in approved_symbols:
                approved_symbols.append(symbol)
            if len(approved_symbols) >= max_symbols:
                break

    approved_symbols = approved_symbols[:max_symbols]
    order_reports: list[dict] = []

    for symbol in approved_symbols:
        entry: dict = {"symbol": symbol, "quote_order_qty": quote_order_qty}
        buy_payload, buy_status = live_adapter.create_spot_market_order(
            api_key,
            api_secret,
            symbol=symbol,
            side="BUY",
            quote_order_qty=quote_order_qty,
            environment="live",
        )
        entry["buy_status"] = buy_status
        entry["buy_payload"] = buy_payload
        if buy_status >= 400:
            entry["error"] = "buy_failed"
            order_reports.append(entry)
            continue

        buy_order_id = int(float(buy_payload.get("orderId") or 0))
        buy_query = buy_payload
        for _ in range(8):
            time.sleep(0.3)
            queried, _ = live_adapter.query_spot_order(api_key, api_secret, symbol, buy_order_id, environment="live")
            buy_query = queried
            if str(queried.get("status") or "").upper() in {"FILLED", "CANCELED", "EXPIRED", "REJECTED", "PARTIALLY_FILLED"}:
                break

        entry["buy_query"] = buy_query
        executed_qty = float(buy_query.get("executedQty") or 0.0)
        if executed_qty <= 0:
            entry["error"] = "buy_executed_qty_zero"
            order_reports.append(entry)
            continue

        symbol_filters = _fetch_symbol_filters(symbol, environment="live")
        sell_qty = _quantize_to_step(
            executed_qty,
            float(symbol_filters.get("step_size") or 0.000001),
            int(symbol_filters.get("quantity_precision") or 6),
            rounding=ROUND_DOWN,
        )

        sell_params = {
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": str(sell_qty),
        }
        time.sleep(hold_seconds)
        sell_payload, sell_status = live_adapter._signed_post_spot(
            api_key,
            api_secret,
            "/api/v3/order",
            sell_params,
            environment="live",
        )
        entry["sell_status"] = sell_status
        entry["sell_payload"] = sell_payload
        if sell_status >= 400:
            entry["error"] = "sell_failed"
            order_reports.append(entry)
            continue

        sell_order_id = int(float(sell_payload.get("orderId") or 0))
        sell_query = sell_payload
        for _ in range(8):
            time.sleep(0.3)
            queried, _ = live_adapter.query_spot_order(api_key, api_secret, symbol, sell_order_id, environment="live")
            sell_query = queried
            if str(queried.get("status") or "").upper() in {"FILLED", "CANCELED", "EXPIRED", "REJECTED", "PARTIALLY_FILLED"}:
                break

        entry["sell_query"] = sell_query
        buy_quote = float(buy_query.get("cummulativeQuoteQty") or 0.0)
        sell_quote = float(sell_query.get("cummulativeQuoteQty") or 0.0)
        entry["round_trip_quote_pnl"] = round(sell_quote - buy_quote, 8)
        entry["exchange_order_ids"] = {
            "buy": str(buy_query.get("orderId") or buy_order_id),
            "sell": str(sell_query.get("orderId") or sell_order_id),
        }
        order_reports.append(entry)

    wallet_after, wallet_after_status, _ = live_adapter.account_probe_spot(api_key, api_secret, environment="live")
    total_usdt_after = total_usdt_before
    free_usdt_after = free_usdt_before
    if wallet_after_status < 400:
        for balance in wallet_after.get("balances") or []:
            if str(balance.get("asset") or "").upper() == "USDT":
                free_usdt_after = float(balance.get("free") or 0.0)
                total_usdt_after = free_usdt_after + float(balance.get("locked") or 0.0)
                break

    return {
        "status": "ok",
        "scanner": {
            "run_id": scanner_result.get("run_id"),
            "result_count": scanner_result.get("result_count"),
            "actionable_count": scanner_result.get("actionable_count"),
            "selected_symbols": scanner_result.get("selected_symbols") or [],
        },
        "approved_symbols_used": approved_symbols,
        "wallet_before": {
            "spot_total_usdt": total_usdt_before,
            "spot_free_usdt": free_usdt_before,
            "per_trade_quote_qty_20pct": quote_order_qty,
        },
        "wallet_after": {
            "spot_total_usdt": total_usdt_after,
            "spot_free_usdt": free_usdt_after,
            "delta_total_usdt": round(total_usdt_after - total_usdt_before, 8),
        },
        "orders": order_reports,
    }