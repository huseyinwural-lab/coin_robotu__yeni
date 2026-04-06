from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN
import time
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
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
from db import SessionLocal, get_db, redis_client
from deps import require_user
from models import PendingSignal, User, UserExecutionIntent, UserScannerResult, UserExchangeConnection
from models import SignalEvent, UserTradeProjection
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
    get_or_create_live_config,
    validate_exchange_credentials_for_user,
    _fetch_symbol_filters,
    _quantize_to_step,
)
from services.quote_asset_constraints import allowed_quote_assets
from services.quote_asset_policy import extract_quote_asset, filter_allowed_quote_symbols
from services.pipeline.cache_store import get_json, set_json
from services.bot_runtime_service import list_bot_runtime_summaries
from services.execution_readiness_service import get_exchange_readiness

router = APIRouter(prefix="/user", tags=["user_scanner_signals"])

_FIX_ALL_BLOCKERS_ASYNC_FALLBACK: dict[str, dict] = {}


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


SCANNER_ASYNC_JOB_TTL_SECONDS = 60 * 30


def _scanner_async_job_key(user_id: str, job_id: str) -> str:
    return f"user:scanner:run_async:{user_id}:{job_id}"


def _set_scanner_async_payload(job_key: str, payload: dict) -> None:
    set_json(redis_client, job_key, payload)
    try:
        if hasattr(redis_client, "expire"):
            redis_client.expire(job_key, SCANNER_ASYNC_JOB_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass


def _fix_all_blockers_async_job_key(user_id: str, job_id: str) -> str:
    return f"user:signals:fix_all_blockers_async:{user_id}:{job_id}"


def _set_fix_all_blockers_async_payload(job_key: str, payload: dict) -> None:
    _FIX_ALL_BLOCKERS_ASYNC_FALLBACK[job_key] = payload
    try:
        set_json(redis_client, job_key, payload, ttl=600)
    except Exception:
        pass


def _get_fix_all_blockers_async_payload(job_key: str) -> dict | None:
    payload = get_json(redis_client, job_key)
    if isinstance(payload, dict):
        _FIX_ALL_BLOCKERS_ASYNC_FALLBACK[job_key] = payload
        return payload
    return _FIX_ALL_BLOCKERS_ASYNC_FALLBACK.get(job_key)


def _adaptive_batch_size(remaining: int) -> int:
    if remaining >= 250:
        return 50
    if remaining >= 120:
        return 30
    if remaining >= 50:
        return 20
    if remaining >= 20:
        return 10
    return 5


def _normalize_blocked_payload(*, status: str | None, blocked_reason_code: str | None, blocked_reason_message: str | None, blocked_solution_hint: str | None) -> tuple[str, str, str]:
    normalized_status = str(status or "").strip().lower()
    code = str(blocked_reason_code or "").strip()
    message = str(blocked_reason_message or "").strip()
    hint = str(blocked_solution_hint or "").strip()

    if normalized_status in {"blocked", "non_tradeable"}:
        if not code:
            code = "BLOCKED_UNSPECIFIED"
        if not message:
            message = "Sinyal execution öncesi bir precheck tarafından bloklandı."
        if not hint:
            hint = "Diagnose (auto_fix=true) çalıştırıp precheck detayını inceleyin."
    return code, message, hint


def _extract_first_precheck_failure_code(decision_note: str | None, blocked_reason_message: str | None) -> str:
    note = str(decision_note or "")
    marker = "first="
    if marker in note:
        suffix = note.split(marker, 1)[1]
        first = suffix.split(";", 1)[0].split("|", 1)[0].strip().upper()
        if first:
            return first

    message = str(blocked_reason_message or "")
    marker_codes = "/ codes:"
    if marker_codes in message:
        suffix = message.split(marker_codes, 1)[1]
        first = suffix.split(",", 1)[0].strip().upper()
        if first:
            return first
    return ""


def _normalize_signal_status_for_ui(*, status: str | None, blocked_reason_code: str | None) -> str:
    normalized_status = str(status or "").strip().lower()
    if normalized_status == "blocked" and str(blocked_reason_code or "").strip().upper() == "ORDER_PRECHECK_FAILED":
        return "non_tradeable"
    return normalized_status or "pending"


def _is_exchange_connection_ready(connection: UserExchangeConnection | None) -> bool:
    if connection is None:
        return False
    snapshot = dict(getattr(connection, "readiness_snapshot", {}) or {})
    health = str(snapshot.get("connection_health") or "unknown").strip().lower()
    can_trade = snapshot.get("can_trade_effective")
    if can_trade is None:
        can_trade = snapshot.get("can_trade_snapshot")
    if can_trade is None:
        can_trade = snapshot.get("can_trade")
    return bool(can_trade) and health in {"online", "degraded"}


def _build_user_status_contract(db: Session, user_id: str) -> dict:
    live_config = get_or_create_live_config(db)
    live_mode_enabled = bool(getattr(live_config, "live_mode_enabled", False))

    latest_scanner_row = (
        db.query(UserScannerResult)
        .filter(UserScannerResult.user_id == user_id)
        .order_by(UserScannerResult.generated_at.desc())
        .first()
    )
    scanner_ready = latest_scanner_row is not None

    bot_summaries = list_bot_runtime_summaries(db, user_id=user_id)
    primary_bot = (
        next((item for item in bot_summaries if bool(item.get("is_enabled")) and str(item.get("status") or "").upper() == "RUNNING"), None)
        or next((item for item in bot_summaries if bool(item.get("is_enabled"))), None)
        or (bot_summaries[0] if bot_summaries else None)
    )

    binding_validation = dict((primary_bot or {}).get("binding_validation") or {})
    resolved_symbols = list(binding_validation.get("resolved_symbols") or [])
    strategy_ready = bool(binding_validation.get("strategy_bound"))
    risk_ready = bool(binding_validation.get("risk_bound"))
    execution_ready = bool(binding_validation.get("execution_bound"))
    symbols_ready = bool(binding_validation.get("symbols_resolved"))

    selected_connection_id = str((primary_bot or {}).get("selected_exchange_connection_id") or "").strip()
    selected_connection = None
    if selected_connection_id:
        selected_connection = (
            db.query(UserExchangeConnection)
            .filter(UserExchangeConnection.id == selected_connection_id, UserExchangeConnection.user_id == user_id)
            .first()
        )
    if selected_connection is None:
        selected_connection = (
            db.query(UserExchangeConnection)
            .filter(UserExchangeConnection.user_id == user_id)
            .order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc())
            .first()
        )
    exchange_reason_code = "connection_not_selected"
    exchange_ready = bool(execution_ready)
    wallet_last_check_at = None
    wallet_available_balance = None
    wallet_balance = None
    if selected_connection is not None:
        readiness = get_exchange_readiness(
            db,
            connection_id=selected_connection.id,
            market_type=str((primary_bot or {}).get("market_type") or "spot"),
            symbol=(resolved_symbols[0] if resolved_symbols else None),
        )
        exchange_ready = bool(readiness.get("is_ready"))
        exchange_reason_code = str(readiness.get("reason_code") or "ready")
        wallet_last_check_at = readiness.get("last_check_at")
        perms = dict(readiness.get("permissions") or {})
        wallet_available_balance = perms.get("available_balance")
        wallet_balance = perms.get("wallet_balance")

    blocked_rows = (
        db.query(PendingSignal)
        .filter(PendingSignal.user_id == user_id, PendingSignal.status.in_(["blocked", "non_tradeable"]))
        .order_by(PendingSignal.created_at.desc())
        .limit(200)
        .all()
    )
    blocked_reason_counts: dict[str, int] = {}
    for row in blocked_rows:
        code, _, _ = _normalize_blocked_payload(
            status=row.status,
            blocked_reason_code=row.blocked_reason_code,
            blocked_reason_message=row.blocked_reason_message,
            blocked_solution_hint=row.blocked_solution_hint,
        )
        row_message = str(getattr(row, "blocked_reason_message", "") or "").upper()
        if (not live_mode_enabled) and code == "ORDER_PRECHECK_FAILED":
            if any(token in row_message for token in ["EXCHANGE_NOT_READY", "INVALID_KEY", "MIN_NOTIONAL_NOT_MET"]):
                continue
        if (not live_mode_enabled) and code == "SYMBOL_NOT_ALLOWED":
            continue
        if code:
            blocked_reason_counts[code] = blocked_reason_counts.get(code, 0) + 1

    blocking_reasons: list[dict] = []
    if not scanner_ready:
        blocking_reasons.append({"code": "SCANNER_NOT_READY", "message": "Henüz scanner sonucu yok.", "hint": "Scanner run-async tetikleyin."})
    if not strategy_ready:
        blocking_reasons.append({"code": "STRATEGY_NOT_READY", "message": "Strategy binding hazır değil.", "hint": "Bot strategy/template eşleşmesini kontrol edin."})
    if not risk_ready:
        blocking_reasons.append({"code": "RISK_NOT_READY", "message": "Risk binding hazır değil.", "hint": "Bot için risk policy atayın."})
    if not execution_ready:
        blocking_reasons.append({"code": "EXECUTION_NOT_READY", "message": "Execution binding hazır değil.", "hint": "Exchange connection bağlayın."})
    if not symbols_ready:
        blocking_reasons.append({"code": "SYMBOLS_NOT_READY", "message": "Symbol resolution tamamlanmadı.", "hint": "manual_selection sembollerini güncelleyin."})
    if not exchange_ready and live_mode_enabled:
        blocking_reasons.append({"code": "EXCHANGE_NOT_READY", "message": f"Exchange trade-ready değil ({exchange_reason_code}).", "hint": "connection revalidate / permission kontrol / market_type doğrulaması yapın."})
    if exchange_ready and wallet_available_balance in {None, 0, 0.0} and wallet_balance in {None, 0, 0.0} and live_mode_enabled:
        blocking_reasons.append({"code": "WALLET_REFRESH_FAILED", "message": "Cüzdan snapshot güncel değil veya boş.", "hint": "wallet refresh tetikleyin; güncel balance olmadan trade açılmaz."})

    for code, count in sorted(blocked_reason_counts.items(), key=lambda item: (-item[1], item[0]))[:5]:
        blocking_reasons.append(
            {
                "code": f"SIGNAL_BLOCKED::{code}",
                "message": f"{count} sinyal {code} nedeniyle blocked.",
                "hint": "Signals ekranından diagnose?auto_fix=true aksiyonunu çalıştırın.",
            }
        )

    return {
        "scanner_ready": bool(scanner_ready),
        "strategy_ready": bool(strategy_ready),
        "risk_ready": bool(risk_ready),
        "execution_ready": bool(execution_ready),
        "symbols_ready": bool(symbols_ready),
        "exchange_ready": bool(exchange_ready),
        "bot_status": str((primary_bot or {}).get("status") or "NOT_CONFIGURED"),
        "health": str((primary_bot or {}).get("health") or ("HEALTHY" if len(blocking_reasons) == 0 else "ERROR")),
        "blocking_reasons": blocking_reasons,
        "latest_scanner_run_at": latest_scanner_row.generated_at.isoformat() if latest_scanner_row and latest_scanner_row.generated_at else None,
        "active_bot_id": (primary_bot or {}).get("id"),
        "wallet_last_check_at": wallet_last_check_at,
        "wallet_available_balance": wallet_available_balance,
        "wallet_balance": wallet_balance,
    }


def _run_scanner_async_job(
    *,
    job_key: str,
    user_id: str,
    mode: str,
    max_results: int,
    symbol_source: str,
    market_type: str,
    selected_symbols: list[str],
    symbol_selection_mode: str,
) -> None:
    db = SessionLocal()
    started_at = datetime.now(timezone.utc)
    _set_scanner_async_payload(
        job_key,
        {
            "status": "running",
            "started_at": started_at.isoformat(),
            "mode": mode,
            "market_type": market_type,
            "selected_count": len(selected_symbols),
        },
    )
    try:
        result = run_user_scanner(
            db,
            user_id,
            requested_mode=mode,
            max_results=max_results,
            symbol_source=symbol_source,
            market_type=market_type,
            selected_symbols=selected_symbols,
            symbol_selection_mode=symbol_selection_mode,
        )
        _set_scanner_async_payload(
            job_key,
            {
                "status": "completed",
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "result": jsonable_encoder(result),
            },
        )
    except Exception as exc:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        _set_scanner_async_payload(
            job_key,
            {
                "status": "failed",
                "started_at": started_at.isoformat(),
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
            },
        )
    finally:
        db.close()


def _run_scanner_async_dual_market_job(
    *,
    job_key: str,
    user_id: str,
    mode: str,
    max_results: int,
    symbol_source: str,
    selected_symbols: list[str],
    symbol_selection_mode: str,
) -> None:
    db = SessionLocal()
    started_at = datetime.now(timezone.utc)
    _set_scanner_async_payload(
        job_key,
        {
            "status": "running",
            "started_at": started_at.isoformat(),
            "mode": mode,
            "market_type": "both",
            "selected_count": len(selected_symbols),
            "job_type": "dual_market",
        },
    )
    run_items: list[dict] = []
    total_result_count = 0
    total_actionable_count = 0
    total_non_tradeable_count = 0
    total_queued_count = 0
    pending_total = 0
    try:
        for market in ["spot", "futures"]:
            try:
                result = run_user_scanner(
                    db,
                    user_id,
                    requested_mode=mode,
                    max_results=max_results,
                    symbol_source=symbol_source,
                    market_type=market,
                    selected_symbols=selected_symbols,
                    symbol_selection_mode=symbol_selection_mode,
                )
                encoded_result = jsonable_encoder(result)
                run_items.append(
                    {
                        "market_type": market,
                        "status": "completed",
                        "result": encoded_result,
                    }
                )
                total_result_count += int(result.get("result_count") or 0)
                total_actionable_count += int(result.get("actionable_count") or 0)
                total_non_tradeable_count += int(result.get("non_tradeable_count") or 0)
                total_queued_count += int(result.get("queued_count") or 0)
                pending_total = max(pending_total, int(result.get("pending_total") or 0))
            except Exception as market_exc:  # noqa: BLE001
                try:
                    db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                run_items.append(
                    {
                        "market_type": market,
                        "status": "failed",
                        "error": str(market_exc),
                    }
                )

        completed_count = len([item for item in run_items if item.get("status") == "completed"])
        failed_count = len([item for item in run_items if item.get("status") == "failed"])
        if completed_count == 0:
            _set_scanner_async_payload(
                job_key,
                {
                    "status": "failed",
                    "started_at": started_at.isoformat(),
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                    "error": "dual_market_scan_all_failed",
                    "runs": run_items,
                },
            )
            return

        _set_scanner_async_payload(
            job_key,
            {
                "status": "completed",
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "result": {
                    "mode": mode,
                    "market_type": "both",
                    "status": "partial_failed" if failed_count > 0 else "success",
                    "runs": run_items,
                    "result_count": total_result_count,
                    "actionable_count": total_actionable_count,
                    "non_tradeable_count": total_non_tradeable_count,
                    "queued_count": total_queued_count,
                    "pending_total": pending_total,
                    "selected_symbols": selected_symbols,
                    "symbol_selection_mode": symbol_selection_mode,
                },
            },
        )
    finally:
        db.close()


def _run_fix_all_blockers_async_job(*, job_key: str, user_id: str, total_limit: int) -> None:
    db = SessionLocal()
    started_at = datetime.now(timezone.utc)
    _set_fix_all_blockers_async_payload(
        job_key,
        {
            "status": "running",
            "started_at": started_at.isoformat(),
            "processed": 0,
            "fixed": 0,
            "remaining_blocked": None,
            "actions_summary": {},
            "batch_history": [],
        },
    )

    processed_total = 0
    fixed_total = 0
    actions_summary: dict[str, int] = {}
    batch_history: list[dict] = []
    remaining_budget = max(min(int(total_limit or 20), 200), 1)

    try:
        while remaining_budget > 0:
            remaining_blocked = (
                db.query(PendingSignal)
                .filter(PendingSignal.user_id == user_id, PendingSignal.status.in_(["blocked", "non_tradeable"]))
                .count()
            )
            if remaining_blocked <= 0:
                break

            batch_size = min(_adaptive_batch_size(remaining_blocked), remaining_budget)
            result = bulk_fix_blocked_signals(db, user_id, limit=batch_size)
            processed_batch = int(result.get("processed") or 0)
            fixed_batch = int(result.get("fixed") or 0)
            processed_total += processed_batch
            fixed_total += fixed_batch
            remaining_budget = max(remaining_budget - processed_batch, 0)

            batch_history.append(
                {
                    "batch_size": batch_size,
                    "processed": processed_batch,
                    "fixed": fixed_batch,
                    "remaining_blocked": int(result.get("remaining_blocked") or 0),
                }
            )

            for action, count in (result.get("actions_summary") or {}).items():
                actions_summary[action] = actions_summary.get(action, 0) + int(count or 0)

            _set_fix_all_blockers_async_payload(
                job_key,
                {
                    "status": "running",
                    "started_at": started_at.isoformat(),
                    "processed": processed_total,
                    "fixed": fixed_total,
                    "remaining_blocked": int(result.get("remaining_blocked") or 0),
                    "actions_summary": actions_summary,
                    "batch_history": batch_history,
                },
            )

            if processed_batch <= 0:
                break

        final_remaining = (
            db.query(PendingSignal)
            .filter(PendingSignal.user_id == user_id, PendingSignal.status.in_(["blocked", "non_tradeable"]))
            .count()
        )
        _set_fix_all_blockers_async_payload(
            job_key,
            {
                "status": "completed",
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "processed": processed_total,
                "fixed": fixed_total,
                "remaining_blocked": final_remaining,
                "actions_summary": actions_summary,
                "batch_history": batch_history,
            },
        )
    except Exception as exc:  # noqa: BLE001
        _set_fix_all_blockers_async_payload(
            job_key,
            {
                "status": "failed",
                "started_at": started_at.isoformat(),
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
                "processed": processed_total,
                "fixed": fixed_total,
                "actions_summary": actions_summary,
                "batch_history": batch_history,
            },
        )
    finally:
        db.close()


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
            "non_tradeable_count": result.get("non_tradeable_count", 0),
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
            "non_tradeable_count": result.get("non_tradeable_count", 0),
            "queued_count": result["queued_count"],
        },
    )
    return UserScannerRunResponse(**result)


@router.post("/scanner/run-async")
def scanner_run_async(
    payload: UserScannerRunRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_user),
):
    selected_symbols = payload.selected_symbols or []
    valid_symbols = filter_allowed_quote_symbols(selected_symbols)
    if payload.symbol_selection_mode == "manual_selection" and len(valid_symbols) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_allowed_quote_notice())

    job_id = str(uuid4())
    job_key = _scanner_async_job_key(current_user.id, job_id)
    _set_scanner_async_payload(
        job_key,
        {
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": payload.mode,
            "market_type": payload.market_type,
            "selected_count": len(valid_symbols),
        },
    )

    background_tasks.add_task(
        _run_scanner_async_job,
        job_key=job_key,
        user_id=current_user.id,
        mode=payload.mode,
        max_results=payload.max_results,
        symbol_source=payload.symbol_source,
        market_type=payload.market_type,
        selected_symbols=valid_symbols,
        symbol_selection_mode=payload.symbol_selection_mode,
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "selected_count": len(valid_symbols),
        "market_type": payload.market_type,
    }


@router.get("/scanner/run-async/{job_id}")
def scanner_run_async_status(
    job_id: str,
    current_user: User = Depends(require_user),
):
    job_key = _scanner_async_job_key(current_user.id, job_id)
    payload = get_json(redis_client, job_key)
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scanner_run_async_job_not_found")
    return payload


@router.post("/scanner/run-async-both")
def scanner_run_async_both(
    payload: UserScannerRunRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_user),
):
    selected_symbols = payload.selected_symbols or []
    valid_symbols = filter_allowed_quote_symbols(selected_symbols)
    if payload.symbol_selection_mode == "manual_selection" and len(valid_symbols) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_allowed_quote_notice())

    job_id = str(uuid4())
    job_key = _scanner_async_job_key(current_user.id, job_id)
    _set_scanner_async_payload(
        job_key,
        {
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": payload.mode,
            "market_type": "both",
            "selected_count": len(valid_symbols),
            "job_type": "dual_market",
        },
    )

    background_tasks.add_task(
        _run_scanner_async_dual_market_job,
        job_key=job_key,
        user_id=current_user.id,
        mode=payload.mode,
        max_results=payload.max_results,
        symbol_source=payload.symbol_source,
        selected_symbols=valid_symbols,
        symbol_selection_mode=payload.symbol_selection_mode,
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "selected_count": len(valid_symbols),
        "market_type": "both",
    }


@router.get("/scanner/status-contract")
def scanner_status_contract(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return _build_user_status_contract(db, current_user.id)


@router.get("/scanner/exchange-readiness")
def scanner_exchange_readiness(
    market_type: str = Query(default="spot"),
    symbol: str | None = Query(default=None),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    normalized_market_type = str(market_type or "spot").lower()
    connection = (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.user_id == current_user.id, UserExchangeConnection.market_type == normalized_market_type)
        .order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc())
        .first()
    )
    if connection is None:
        connection = (
            db.query(UserExchangeConnection)
            .filter(UserExchangeConnection.user_id == current_user.id)
            .order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc())
            .first()
        )
    if connection is None:
        return {
            "is_ready": False,
            "reason_code": "connection_not_found",
            "permissions": {"can_trade": False, "list": []},
            "market_types": [],
            "last_check_at": datetime.now(timezone.utc).isoformat(),
            "connection_id": None,
            "market_type": normalized_market_type,
            "symbol": str(symbol or "").upper() or None,
        }

    return get_exchange_readiness(
        db,
        connection_id=connection.id,
        market_type=normalized_market_type,
        symbol=(str(symbol).upper() if symbol else None),
    )


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
            tradeable=((row.payload or {}).get("tradeable") if "tradeable" in (row.payload or {}) else None),
            first_precheck_failure_code=str((row.payload or {}).get("first_precheck_failure_code") or "") or None,
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
    rows = list_user_signals(db, current_user.id, limit=limit, refresh_snapshot=False)

    def _safe_float(value, fallback: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def _safe_optional_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _trade_signal_status(raw_status: str | None) -> str:
        value = str(raw_status or "").upper()
        if value in {"OPEN", "PARTIALLY_FILLED"}:
            return "submitted"
        if value in {"PENDING", "NEW"}:
            return "queued"
        if value in {"FILLED", "CLOSED"}:
            return "filled"
        if value in {"REJECTED", "CANCELLED", "CANCELED", "EXPIRED"}:
            return "rejected"
        return "submitted"

    def _latest_trade_time(trade_row: UserTradeProjection):
        return trade_row.opened_at or trade_row.created_at or trade_row.updated_at or datetime.now(timezone.utc)

    def _build_trade_links(
        *,
        signal_id: str | None,
        intent_db_id: str | None,
        intent_token: str | None,
        position_id: str | None,
        by_signal: dict[str, list[UserTradeProjection]],
        by_intent: dict[str, list[UserTradeProjection]],
        by_position: dict[str, list[UserTradeProjection]],
    ) -> list[UserTradeProjection]:
        merged: list[UserTradeProjection] = []
        seen: set[str] = set()

        def _append(items: list[UserTradeProjection] | None):
            for item in items or []:
                key = str(item.trade_id or "")
                if key and key not in seen:
                    seen.add(key)
                    merged.append(item)

        _append(by_signal.get(str(signal_id or "")))
        _append(by_intent.get(str(intent_token or "")))
        _append(by_intent.get(str(intent_db_id or "")))
        _append(by_position.get(str(position_id or "")))

        merged.sort(key=lambda row: row.updated_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return merged

    signal_ids = {str(row.signal_id or "") for row in rows if str(row.signal_id or "").strip()}
    intent_db_ids = {str(row.created_order_intent_id or "") for row in rows if str(row.created_order_intent_id or "").strip()}
    position_ids = {str(row.order_position_id or "") for row in rows if str(row.order_position_id or "").strip()}

    trade_rows = (
        db.query(UserTradeProjection)
        .filter(UserTradeProjection.user_id == current_user.id)
        .order_by(UserTradeProjection.updated_at.desc())
        .limit(max(limit * 3, 180))
        .all()
    )

    for trade in trade_rows:
        if str(trade.signal_id or "").strip():
            signal_ids.add(str(trade.signal_id))
        if str(trade.intent_id or "").strip():
            intent_db_ids.add(str(trade.intent_id))
        if str(trade.position_id or "").strip():
            position_ids.add(str(trade.position_id))

    signal_rows = (
        db.query(SignalEvent)
        .filter(SignalEvent.user_id == current_user.id, SignalEvent.id.in_(list(signal_ids)))
        .all()
        if signal_ids
        else []
    )
    signal_map = {str(item.id): item for item in signal_rows}

    intent_rows = (
        db.query(UserExecutionIntent)
        .filter(
            UserExecutionIntent.user_id == current_user.id,
            (UserExecutionIntent.id.in_(list(intent_db_ids))) | (UserExecutionIntent.intent_id.in_(list(intent_db_ids))),
        )
        .all()
        if intent_db_ids
        else []
    )
    intent_by_id = {str(item.id): item for item in intent_rows}
    intent_by_token = {str(item.intent_id): item for item in intent_rows if str(item.intent_id or "").strip()}

    trades_by_signal: dict[str, list[UserTradeProjection]] = {}
    trades_by_intent: dict[str, list[UserTradeProjection]] = {}
    trades_by_position: dict[str, list[UserTradeProjection]] = {}
    for trade in trade_rows:
        signal_key = str(trade.signal_id or "").strip()
        if signal_key:
            trades_by_signal.setdefault(signal_key, []).append(trade)
        intent_key = str(trade.intent_id or "").strip()
        if intent_key:
            trades_by_intent.setdefault(intent_key, []).append(trade)
        position_key = str(trade.position_id or "").strip()
        if position_key:
            trades_by_position.setdefault(position_key, []).append(trade)

    normalized_responses: list[UserSignalResponse] = []
    represented_trade_ids: set[str] = set()

    for row in rows:
        signal_event = signal_map.get(str(row.signal_id or ""))
        intent = intent_by_id.get(str(row.created_order_intent_id or "")) or intent_by_token.get(str(row.created_order_intent_id or ""))
        intent_token = str(getattr(intent, "intent_id", "") or "") if intent is not None else ""

        linked_trades = _build_trade_links(
            signal_id=row.signal_id,
            intent_db_id=row.created_order_intent_id,
            intent_token=intent_token,
            position_id=row.order_position_id,
            by_signal=trades_by_signal,
            by_intent=trades_by_intent,
            by_position=trades_by_position,
        )
        for trade in linked_trades:
            represented_trade_ids.add(str(trade.trade_id))

        linked_open_count = sum(1 for trade in linked_trades if str(trade.status or "").upper() in {"OPEN", "PARTIALLY_FILLED"})
        linked_primary = linked_trades[0] if linked_trades else None

        blocked_reason_code, blocked_reason_message, blocked_solution_hint = _normalize_blocked_payload(
            status=row.status,
            blocked_reason_code=row.blocked_reason_code,
            blocked_reason_message=row.blocked_reason_message,
            blocked_solution_hint=row.blocked_solution_hint,
        )
        first_precheck_failure_code = _extract_first_precheck_failure_code(row.decision_note, blocked_reason_message)
        normalized_status = _normalize_signal_status_for_ui(status=row.status, blocked_reason_code=blocked_reason_code)
        tradeable = bool(row.execution_eligible)
        if normalized_status in {"blocked", "non_tradeable"}:
            tradeable = False
        if first_precheck_failure_code:
            tradeable = False

        normalized_responses.append(
            UserSignalResponse(
                id=row.id,
                signal_id=row.signal_id,
                user_id=row.user_id,
                symbol=row.symbol,
                quote_asset=extract_quote_asset(row.symbol),
                strategy_code=row.strategy_code,
                signal=(str(signal_event.signal or "") if signal_event else None),
                signal_direction=(str(signal_event.direction or "") if signal_event else None),
                signal_generated_at=signal_event.generated_at if signal_event else None,
                confidence=_safe_float((signal_event.confidence if signal_event is not None else row.confidence)),
                mode=row.mode,
                status=normalized_status,
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
                blocked_reason_code=blocked_reason_code,
                blocked_reason_message=blocked_reason_message,
                blocked_solution_hint=blocked_solution_hint,
                tradeable=tradeable,
                first_precheck_failure_code=first_precheck_failure_code or None,
                requires_manual_approval=row.requires_manual_approval,
                execution_eligible=row.execution_eligible,
                bot_profile_id=row.bot_profile_id,
                risk_policy_id=row.risk_policy_id,
                exchange_connection_id=row.exchange_connection_id,
                created_order_intent_id=row.created_order_intent_id,
                execution_intent_status=(str(intent.status) if intent is not None else None),
                proposed_notional=_safe_optional_float(intent.notional if intent is not None else None),
                execution_intent_side=(str(intent.side) if intent is not None else None),
                execution_intent_market_type=(str(intent.market_type) if intent is not None else None),
                execution_intent_created_at=(intent.created_at if intent is not None else None),
                runtime_owner=row.runtime_owner,
                last_eligibility_check_at=row.last_eligibility_check_at,
                execution_mode_label=getattr(row, "execution_mode_label", None),
                linked_trade_id=(str(linked_primary.trade_id) if linked_primary is not None else None),
                linked_trade_status=(str(linked_primary.status) if linked_primary is not None else None),
                linked_open_trade_count=linked_open_count,
                has_open_position_link=linked_open_count > 0,
            )
        )

    for trade in trade_rows:
        trade_id = str(trade.trade_id or "").strip()
        if not trade_id or trade_id in represented_trade_ids:
            continue

        if not str(trade.signal_id or "").strip() and not str(trade.intent_id or "").strip():
            continue

        signal_event = signal_map.get(str(trade.signal_id or ""))
        linked_intent = intent_by_token.get(str(trade.intent_id or "")) or intent_by_id.get(str(trade.intent_id or ""))
        synthetic_status = _trade_signal_status(str(trade.status or ""))
        created_at = _latest_trade_time(trade)
        signal_value = None
        if signal_event is not None:
            signal_value = str(signal_event.signal or signal_event.direction or "") or None

        normalized_responses.append(
            UserSignalResponse(
                id=f"trade-link-{trade_id}",
                signal_id=str(trade.signal_id or trade_id),
                user_id=current_user.id,
                symbol=str(trade.symbol or "").upper(),
                quote_asset=extract_quote_asset(str(trade.symbol or "")),
                strategy_code=str(trade.strategy_name or (signal_event.strategy_id if signal_event is not None else "trade_linked")),
                signal=signal_value,
                signal_direction=(str(signal_event.direction) if signal_event is not None and signal_event.direction else None),
                signal_generated_at=(signal_event.generated_at if signal_event is not None else None),
                confidence=_safe_float(signal_event.confidence if signal_event is not None else 0.0),
                mode="AUTO",
                status=synthetic_status,
                market_type=str((trade.meta_json or {}).get("market_type") or "spot").lower(),
                order_position_id=str(trade.position_id or "") or None,
                created_at=created_at,
                decided_at=None,
                decision_note="trade_projection_linked_signal",
                strategy_weight=None,
                allocation_source=(trade.meta_json or {}).get("allocation_source"),
                meta_engine_decision=(trade.meta_json or {}).get("meta_engine_decision"),
                previous_state="EXECUTION_SUBMITTED",
                current_state="POSITION_OPEN" if synthetic_status == "submitted" else "EXECUTION_FILLED",
                blocked_reason_code="",
                blocked_reason_message="",
                blocked_solution_hint="",
                tradeable=True,
                first_precheck_failure_code=None,
                requires_manual_approval=False,
                execution_eligible=True,
                bot_profile_id=None,
                risk_policy_id=None,
                exchange_connection_id=None,
                created_order_intent_id=(str(linked_intent.id) if linked_intent is not None else None),
                execution_intent_status=(str(linked_intent.status) if linked_intent is not None else None),
                proposed_notional=_safe_optional_float(linked_intent.notional if linked_intent is not None else None),
                execution_intent_side=(str(linked_intent.side) if linked_intent is not None else None),
                execution_intent_market_type=(str(linked_intent.market_type) if linked_intent is not None else None),
                execution_intent_created_at=(linked_intent.created_at if linked_intent is not None else None),
                runtime_owner="trade_projection_sync",
                last_eligibility_check_at=trade.updated_at,
                execution_mode_label="Full Auto",
                linked_trade_id=trade_id,
                linked_trade_status=str(trade.status or ""),
                linked_open_trade_count=1 if str(trade.status or "").upper() in {"OPEN", "PARTIALLY_FILLED"} else 0,
                has_open_position_link=str(trade.status or "").upper() in {"OPEN", "PARTIALLY_FILLED"},
            )
        )

    normalized_responses.sort(key=lambda item: item.created_at, reverse=True)
    return normalized_responses[:limit]


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

    blocked_reason_code, blocked_reason_message, blocked_solution_hint = _normalize_blocked_payload(
        status=row.status,
        blocked_reason_code=row.blocked_reason_code,
        blocked_reason_message=row.blocked_reason_message,
        blocked_solution_hint=row.blocked_solution_hint,
    )

    return UserSignalDiagnoseResponse(
        id=row.id,
        status=row.status,
        current_state=row.current_state or "DETECTED",
        blocked_reason_code=blocked_reason_code,
        blocked_reason_message=blocked_reason_message,
        blocked_solution_hint=blocked_solution_hint,
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
    limit: int = Query(default=20, ge=1, le=50),
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


@router.post("/signals/fix-all-blockers-async")
def fix_all_blocked_signals_async(
    background_tasks: BackgroundTasks,
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_user),
):
    job_id = str(uuid4())
    job_key = _fix_all_blockers_async_job_key(current_user.id, job_id)
    _set_fix_all_blockers_async_payload(
        job_key,
        {
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "requested_limit": int(limit),
        },
    )
    background_tasks.add_task(
        _run_fix_all_blockers_async_job,
        job_key=job_key,
        user_id=current_user.id,
        total_limit=int(limit),
    )
    return {"job_id": job_id, "status": "queued", "requested_limit": int(limit)}


@router.get("/signals/fix-all-blockers-async/{job_id}")
def fix_all_blocked_signals_async_status(
    job_id: str,
    current_user: User = Depends(require_user),
):
    job_key = _fix_all_blockers_async_job_key(current_user.id, job_id)
    payload = _get_fix_all_blockers_async_payload(job_key)
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signals_fix_all_async_job_not_found")
    return payload


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