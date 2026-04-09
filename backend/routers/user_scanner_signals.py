from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN
import hashlib
import json
import logging
import time
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from core.users.user_scanner_signal_service import (
    bulk_fix_blocked_signals,
    diagnose_pending_signal,
    get_or_create_signal_mode,
    list_user_scanner_results,
    list_user_signals,
    reject_pending_signal,
    run_user_scanner,
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
from routers.admin_universe_monitor import (
    _default_scanner_engine_config as _admin_default_scanner_engine_config,
    _sanitize_decision_boxes as _admin_sanitize_decision_boxes,
    _run_scanner_engine as _admin_run_scanner_engine,
)

router = APIRouter(prefix="/user", tags=["user_scanner_signals"])
logger = logging.getLogger(__name__)

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


@router.get("/scanner-engine/config")
def user_scanner_engine_get_config(current_user: User = Depends(require_user)):
    return _load_user_scanner_engine_config(current_user.id)


@router.post("/scanner-engine/config/save")
def user_scanner_engine_save_config(payload: dict, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    include_spot = bool(payload.get("include_spot", True))
    include_futures = bool(payload.get("include_futures", True))
    if not include_spot and not include_futures:
        raise HTTPException(status_code=400, detail="spot_or_futures_required")

    previous = _load_user_scanner_engine_config(current_user.id)
    trend = _safe_int(payload.get("trend_weight"), int((previous.get("weights") or {}).get("trend") or 10))
    volume = _safe_int(payload.get("volume_weight"), int((previous.get("weights") or {}).get("volume") or 50))
    momentum = _safe_int(payload.get("momentum_weight"), int((previous.get("weights") or {}).get("momentum") or 100))
    bollinger = _safe_int(payload.get("bollinger_weight"), int((previous.get("weights") or {}).get("bollinger") or 1))

    auto_interval = _safe_int(payload.get("auto_interval_minutes"), int(previous.get("auto_interval_minutes") or 3))
    if auto_interval not in {1, 3, 5}:
        auto_interval = 3

    signal_mode = "auto"

    merged_decision_boxes = payload.get("decision_boxes") if isinstance(payload.get("decision_boxes"), dict) else (previous.get("decision_boxes") or {})

    incoming_manual_symbols = payload.get("manual_symbols") if "manual_symbols" in payload else (previous.get("manual_symbols") or [])

    config = {
        **previous,
        "exchange": "binance",
        "include_spot": include_spot,
        "include_futures": include_futures,
        "market_scope": {"spot_mode": "all", "futures_mode": "all"},
        "signal_mode": signal_mode,
        "auto_interval_minutes": auto_interval,
        "scan_limit": max(_safe_int(payload.get("scan_limit"), int(previous.get("scan_limit") or 2000)), 2000),
        "top_n": _safe_int(payload.get("top_n"), int(previous.get("top_n") or 20)),
        "manual_symbols": _normalize_symbols(incoming_manual_symbols or []),
        "weights": {
            "trend": trend,
            "volume": volume,
            "momentum": momentum,
            "bollinger": bollinger,
            "max_score": int(trend + volume + momentum + bollinger),
        },
        "decision_boxes": _admin_sanitize_decision_boxes(merged_decision_boxes),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": current_user.id,
    }
    _save_user_scanner_engine_config(current_user.id, config)

    create_audit_log(
        db,
        action="USER_SCANNER_ENGINE_CONFIG_SAVED",
        entity_type="user_scanner_engine",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="info",
        details={
            "reason": str(payload.get("reason") or "user_scanner_engine_config_save"),
            "config": config,
        },
    )
    return {"status": "success", "config": config}


@router.post("/scanner-engine/run")
def user_scanner_engine_run(payload: dict, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    config = _normalize_scanner_engine_config_for_runtime(_load_user_scanner_engine_config(current_user.id))
    config_fingerprint = _config_fingerprint(config)
    force_refresh = bool(payload.get("force_refresh", False))

    if not force_refresh:
        last_payload = get_json(redis_client, _user_scanner_engine_last_run_key(current_user.id))
        if _is_recent_run_reusable(last_payload, config_fingerprint=config_fingerprint):
            return {
                "status": "cached",
                "run_id": last_payload.get("run_id"),
                "generated_at": last_payload.get("generated_at"),
                "config": last_payload.get("config") or config,
                "summary": last_payload.get("summary") or {},
                "results": last_payload.get("results") or [],
                "top_results": last_payload.get("top_results") or [],
                "errors": last_payload.get("errors") or [],
            }

    lock_result = _acquire_scanner_engine_run_lock(
        user_id=current_user.id,
        job_id=str(uuid4()),
        config_fingerprint=config_fingerprint,
    )
    if not lock_result.get("acquired"):
        existing = lock_result.get("existing") or {}
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SCANNER_ENGINE_RUN_IN_PROGRESS",
                "job_id": existing.get("job_id"),
                "started_at": existing.get("started_at"),
                "message": "Scanner engine çalışıyor. Mevcut job bitince tekrar deneyin.",
            },
        )

    try:
        run_payload = _admin_run_scanner_engine(config, force_refresh=force_refresh)
    finally:
        _release_scanner_engine_run_lock(current_user.id)
    run_payload = {
        **(run_payload or {}),
        "config": config,
        "config_fingerprint": config_fingerprint,
    }
    _save_user_scanner_engine_last_run(current_user.id, run_payload)

    create_audit_log(
        db,
        action="USER_SCANNER_ENGINE_RUN",
        entity_type="user_scanner_engine",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="info",
        details={
            "reason": str(payload.get("reason") or "user_scanner_engine_run"),
            "run_id": run_payload.get("run_id"),
            "summary": run_payload.get("summary") or {},
        },
    )
    return {
        "status": "success",
        "run_id": run_payload.get("run_id"),
        "generated_at": run_payload.get("generated_at"),
        "config": run_payload.get("config") or {},
        "summary": run_payload.get("summary") or {},
        "results": run_payload.get("results") or [],
        "top_results": run_payload.get("top_results") or [],
        "errors": run_payload.get("errors") or [],
    }


@router.post("/scanner-engine/analyze")
def user_scanner_engine_analyze(payload: dict, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    return user_scanner_engine_run(payload=payload, current_user=current_user, db=db)


@router.post("/scanner-engine/run-async")
def user_scanner_engine_run_async(
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_user),
):
    config = _normalize_scanner_engine_config_for_runtime(_load_user_scanner_engine_config(current_user.id))
    config_fingerprint = _config_fingerprint(config)
    force_refresh = bool(payload.get("force_refresh", False))
    reason = str(payload.get("reason") or "user_scanner_engine_run_async")

    if not force_refresh:
        last_payload = get_json(redis_client, _user_scanner_engine_last_run_key(current_user.id))
        if _is_recent_run_reusable(last_payload, config_fingerprint=config_fingerprint):
            return {
                "status": "completed_cached",
                "job_id": None,
                "run_id": last_payload.get("run_id"),
                "generated_at": last_payload.get("generated_at"),
                "summary": last_payload.get("summary") or {},
            }

    job_id = str(uuid4())
    lock_result = _acquire_scanner_engine_run_lock(
        user_id=current_user.id,
        job_id=job_id,
        config_fingerprint=config_fingerprint,
    )
    if not lock_result.get("acquired"):
        existing = lock_result.get("existing") or {}
        return {
            "status": "already_running",
            "job_id": existing.get("job_id"),
            "started_at": existing.get("started_at"),
        }

    job_key = _user_scanner_engine_async_job_key(current_user.id, job_id)
    _set_scanner_engine_async_payload(
        job_key,
        {
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "config_fingerprint": config_fingerprint,
        },
    )

    background_tasks.add_task(
        _run_scanner_engine_async_job,
        user_id=current_user.id,
        job_id=job_id,
        job_key=job_key,
        config=config,
        force_refresh=force_refresh,
        reason=reason,
    )

    return {
        "status": "queued",
        "job_id": job_id,
        "config_fingerprint": config_fingerprint,
    }


@router.get("/scanner-engine/run-async/{job_id}")
def user_scanner_engine_run_async_status(job_id: str, current_user: User = Depends(require_user)):
    payload = get_json(redis_client, _user_scanner_engine_async_job_key(current_user.id, job_id))
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scanner_engine_run_async_job_not_found")
    return payload


@router.get("/scanner-engine/last-run")
def user_scanner_engine_last_run(current_user: User = Depends(require_user)):
    payload = get_json(redis_client, _user_scanner_engine_last_run_key(current_user.id))
    if not isinstance(payload, dict):
        payload = {}
    if not payload.get("run_id"):
        return {
            "status": "empty",
            "config": _load_user_scanner_engine_config(current_user.id),
            "summary": {
                "exchange": "binance",
                "candidate_count": 0,
                "scored_count": 0,
                "error_count": 0,
                "strong_long_count": 0,
                "strong_short_count": 0,
                "max_score": 161,
            },
            "results": [],
            "top_results": [],
            "errors": [],
        }
    return {
        "status": "success",
        "run_id": payload.get("run_id"),
        "generated_at": payload.get("generated_at"),
        "config": payload.get("config") or _load_user_scanner_engine_config(current_user.id),
        "summary": payload.get("summary") or {},
        "results": payload.get("results") or [],
        "top_results": payload.get("top_results") or [],
        "errors": payload.get("errors") or [],
    }


def _allowed_quote_notice() -> str:
    quotes = ", ".join(allowed_quote_assets())
    return f"İşlem için en az bir geçerli market seçmelisiniz. Allowed quote assets: {quotes}"


SCANNER_ASYNC_JOB_TTL_SECONDS = 60 * 30
SCANNER_ENGINE_ASYNC_JOB_TTL_SECONDS = 60 * 45
SCANNER_ENGINE_REUSE_WINDOW_SECONDS = 180
SCANNER_ENGINE_RUN_LOCK_SECONDS = 900
SCANNER_ENGINE_LAST_RUN_CACHE_KEY = "universe:scanner_engine:last_run"
USER_SCANNER_ENGINE_CONFIG_KEY_PREFIX = "user:scanner_engine:config"
USER_SCANNER_ENGINE_LAST_RUN_KEY_PREFIX = "user:scanner_engine:last_run"
USER_SCANNER_ENGINE_ASYNC_JOB_KEY_PREFIX = "user:scanner_engine:run_async"
USER_SCANNER_ENGINE_ACTIVE_RUN_KEY_PREFIX = "user:scanner_engine:run_active"


def _user_scanner_engine_config_key(user_id: str) -> str:
    return f"{USER_SCANNER_ENGINE_CONFIG_KEY_PREFIX}:{user_id}"


def _user_scanner_engine_last_run_key(user_id: str) -> str:
    return f"{USER_SCANNER_ENGINE_LAST_RUN_KEY_PREFIX}:{user_id}"


def _user_scanner_engine_async_job_key(user_id: str, job_id: str) -> str:
    return f"{USER_SCANNER_ENGINE_ASYNC_JOB_KEY_PREFIX}:{user_id}:{job_id}"


def _user_scanner_engine_active_run_key(user_id: str) -> str:
    return f"{USER_SCANNER_ENGINE_ACTIVE_RUN_KEY_PREFIX}:{user_id}"


def _set_json_with_ttl(key: str, payload: dict, ttl_seconds: int) -> None:
    set_json(redis_client, key, payload)
    try:
        if hasattr(redis_client, "expire"):
            redis_client.expire(key, max(int(ttl_seconds), 1))
    except Exception:  # noqa: BLE001
        pass


def _config_fingerprint(config: dict) -> str:
    raw = json.dumps(config or {}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _parse_iso_datetime(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _normalize_symbols(values) -> list[str]:
    if not values:
        return []
    return sorted({str(item).strip().upper() for item in values if str(item).strip()})


def _user_scanner_engine_default_config() -> dict:
    return _admin_default_scanner_engine_config()


def _safe_int(value, fallback: int) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _normalize_scanner_engine_config_for_runtime(config: dict) -> dict:
    base = dict(config or {})
    include_spot = bool(base.get("include_spot", True))
    include_futures = bool(base.get("include_futures", True))
    if not include_spot and not include_futures:
        include_spot = True

    requested_scan_limit = _safe_int(base.get("scan_limit"), 2000)
    return {
        **base,
        "include_spot": include_spot,
        "include_futures": include_futures,
        "market_scope": {"spot_mode": "all", "futures_mode": "all"},
        "scan_limit": max(requested_scan_limit, 2000),
        "manual_symbols": _normalize_symbols(base.get("manual_symbols") or []),
    }


def _is_recent_run_reusable(run_payload: dict, *, config_fingerprint: str) -> bool:
    if not isinstance(run_payload, dict):
        return False
    if not run_payload.get("run_id"):
        return False
    if str(run_payload.get("config_fingerprint") or "") != str(config_fingerprint):
        return False
    generated_at = _parse_iso_datetime(run_payload.get("generated_at"))
    if generated_at is None:
        return False
    age_seconds = (datetime.now(timezone.utc) - generated_at).total_seconds()
    return age_seconds <= SCANNER_ENGINE_REUSE_WINDOW_SECONDS


def _acquire_scanner_engine_run_lock(*, user_id: str, job_id: str, config_fingerprint: str) -> dict:
    lock_key = _user_scanner_engine_active_run_key(user_id)
    now = datetime.now(timezone.utc)
    existing = get_json(redis_client, lock_key)
    if isinstance(existing, dict) and str(existing.get("status") or "") == "running":
        started_at = _parse_iso_datetime(existing.get("started_at"))
        if started_at is not None:
            age_seconds = (now - started_at).total_seconds()
            if age_seconds <= SCANNER_ENGINE_RUN_LOCK_SECONDS:
                return {"acquired": False, "existing": existing, "lock_key": lock_key}

    payload = {
        "job_id": job_id,
        "status": "running",
        "started_at": now.isoformat(),
        "config_fingerprint": config_fingerprint,
    }
    _set_json_with_ttl(lock_key, payload, SCANNER_ENGINE_RUN_LOCK_SECONDS)
    return {"acquired": True, "existing": payload, "lock_key": lock_key}


def _release_scanner_engine_run_lock(user_id: str) -> None:
    try:
        if hasattr(redis_client, "delete"):
            redis_client.delete(_user_scanner_engine_active_run_key(user_id))
    except Exception:  # noqa: BLE001
        pass


def _set_scanner_engine_async_payload(job_key: str, payload: dict) -> None:
    _set_json_with_ttl(job_key, payload, SCANNER_ENGINE_ASYNC_JOB_TTL_SECONDS)


def _load_user_scanner_engine_config(user_id: str) -> dict:
    defaults = _user_scanner_engine_default_config()
    saved = get_json(redis_client, _user_scanner_engine_config_key(user_id))
    if not isinstance(saved, dict):
        saved = {}

    auto_interval = _safe_int(saved.get("auto_interval_minutes"), 3)
    if auto_interval not in {1, 3, 5}:
        auto_interval = 3

    return {
        **defaults,
        **saved,
        "signal_mode": "auto",
        "manual_symbols": _normalize_symbols(saved.get("manual_symbols") or defaults.get("manual_symbols") or []),
        "market_scope": {"spot_mode": "all", "futures_mode": "all"},
        "decision_boxes": _admin_sanitize_decision_boxes(saved.get("decision_boxes") or defaults.get("decision_boxes") or {}),
        "auto_interval_minutes": auto_interval,
        "scan_limit": max(_safe_int(saved.get("scan_limit"), _safe_int(defaults.get("scan_limit"), 2000)), 2000),
    }


def _save_user_scanner_engine_config(user_id: str, config: dict) -> None:
    set_json(redis_client, _user_scanner_engine_config_key(user_id), config)


def _save_user_scanner_engine_last_run(user_id: str, payload: dict) -> None:
    set_json(redis_client, _user_scanner_engine_last_run_key(user_id), payload)


def _run_scanner_engine_async_job(
    *,
    user_id: str,
    job_id: str,
    job_key: str,
    config: dict,
    force_refresh: bool,
    reason: str,
) -> None:
    db = SessionLocal()
    started_at = datetime.now(timezone.utc)
    config_fingerprint = _config_fingerprint(config)
    try:
        run_payload = _admin_run_scanner_engine(config, force_refresh=force_refresh)
        run_payload = {
            **(run_payload or {}),
            "config": config,
            "config_fingerprint": config_fingerprint,
        }
        _save_user_scanner_engine_last_run(user_id, run_payload)

        _set_scanner_engine_async_payload(
            job_key,
            {
                "job_id": job_id,
                "status": "completed",
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "run_id": run_payload.get("run_id"),
                "summary": run_payload.get("summary") or {},
                "config_fingerprint": config_fingerprint,
            },
        )

        create_audit_log(
            db,
            action="USER_SCANNER_ENGINE_RUN_ASYNC",
            entity_type="user_scanner_engine",
            entity_id=user_id,
            actor_user_id=user_id,
            actor_role="user",
            severity="info",
            details={
                "reason": str(reason or "user_scanner_engine_run_async"),
                "job_id": job_id,
                "run_id": run_payload.get("run_id"),
                "summary": run_payload.get("summary") or {},
            },
        )
    except Exception as exc:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        _set_scanner_engine_async_payload(
            job_key,
            {
                "job_id": job_id,
                "status": "failed",
                "started_at": started_at.isoformat(),
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc)[:500],
                "config_fingerprint": config_fingerprint,
            },
        )
    finally:
        _release_scanner_engine_run_lock(user_id)
        db.close()


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
        if first and first != "ORDER_PRECHECK_FAILED":
            return first

    message = str(blocked_reason_message or "")
    marker_codes = "/ codes:"
    if marker_codes in message:
        suffix = message.split(marker_codes, 1)[1]
        first = suffix.split(",", 1)[0].strip().upper()
        if first and first != "ORDER_PRECHECK_FAILED":
            return first
    return ""


def _normalize_signal_status_for_ui(*, status: str | None, blocked_reason_code: str | None) -> str:
    normalized_status = str(status or "").strip().lower()
    return normalized_status or "pending"


def _is_exchange_connection_ready(connection: UserExchangeConnection | None) -> bool:
    if connection is None:
        return False
    snapshot = dict(getattr(connection, "readiness_snapshot", {}) or {})
    health = str(snapshot.get("connection_health") or getattr(connection, "connection_health", "unknown") or "unknown").strip().lower()
    can_trade = snapshot.get("can_trade_effective")
    if can_trade is None:
        can_trade = snapshot.get("can_trade_snapshot")
    if can_trade is None:
        can_trade = snapshot.get("can_trade")
    if can_trade is None:
        can_trade = getattr(connection, "can_trade_effective", False)
    return bool(can_trade) and health in {"online", "degraded"}


def _select_primary_bot_for_market(bot_summaries: list[dict], market_type: str) -> dict | None:
    normalized_market_type = str(market_type or "spot").strip().lower()
    scoped = [item for item in bot_summaries if str(item.get("market_type") or "").strip().lower() == normalized_market_type]
    if not scoped:
        return None
    return (
        next((item for item in scoped if bool(item.get("is_enabled")) and str(item.get("status") or "").upper() == "RUNNING"), None)
        or next((item for item in scoped if bool(item.get("is_enabled"))), None)
        or next((item for item in scoped if str(item.get("status") or "").upper() == "RUNNING"), None)
        or scoped[0]
    )


def _resolve_status_contract_connection(
    db: Session,
    *,
    user_id: str,
    market_type: str,
    preferred_connection_id: str | None,
) -> UserExchangeConnection | None:
    normalized_market_type = str(market_type or "spot").strip().lower()
    base_query = db.query(UserExchangeConnection).filter(UserExchangeConnection.user_id == user_id)

    preferred = None
    if preferred_connection_id:
        preferred = base_query.filter(UserExchangeConnection.id == str(preferred_connection_id).strip()).first()
        if preferred is not None:
            preferred_market = str(getattr(preferred, "market_type", "") or "").strip().lower()
            if preferred_market == normalized_market_type and _is_exchange_connection_ready(preferred):
                return preferred

    market_candidates = (
        base_query
        .filter(UserExchangeConnection.market_type == normalized_market_type)
        .order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc())
        .all()
    )

    ready_market = next((row for row in market_candidates if _is_exchange_connection_ready(row)), None)
    if ready_market is not None:
        return ready_market

    if preferred is not None:
        preferred_market = str(getattr(preferred, "market_type", "") or "").strip().lower()
        if preferred_market == normalized_market_type:
            return preferred

    if market_candidates:
        return market_candidates[0]

    all_candidates = base_query.order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc()).all()
    ready_any = next((row for row in all_candidates if _is_exchange_connection_ready(row)), None)
    if ready_any is not None:
        return ready_any
    return all_candidates[0] if all_candidates else None


def _scanner_result_market_type(row: UserScannerResult | None) -> str | None:
    if row is None:
        return None
    payload = dict(getattr(row, "payload", {}) or {})
    candidate = (
        payload.get("market_type")
        or payload.get("scanner_market_type")
        or payload.get("execution_market_type")
    )
    normalized = str(candidate or "").strip().lower()
    if normalized in {"spot", "futures"}:
        return normalized
    return None


def _build_market_status_contract(
    db: Session,
    *,
    user_id: str,
    market_type: str,
    primary_bot: dict | None,
    latest_scanner_row: UserScannerResult | None,
    live_mode_enabled: bool,
) -> dict:
    binding_validation = dict((primary_bot or {}).get("binding_validation") or {})
    strategy_ready = bool(binding_validation.get("strategy_bound"))
    risk_ready = bool(binding_validation.get("risk_bound"))
    execution_ready = bool(binding_validation.get("execution_bound"))
    symbols_ready = bool(binding_validation.get("symbols_resolved"))

    selected_connection_id = str((primary_bot or {}).get("selected_exchange_connection_id") or "").strip() or None
    selected_connection = _resolve_status_contract_connection(
        db,
        user_id=user_id,
        market_type=market_type,
        preferred_connection_id=selected_connection_id,
    )

    exchange_ready = bool(execution_ready) and _is_exchange_connection_ready(selected_connection)
    wallet_last_check_at = None
    wallet_available_balance = None
    wallet_balance = None
    effective_connection_id = selected_connection_id
    if selected_connection is not None:
        snapshot = dict(getattr(selected_connection, "readiness_snapshot", None) or {})
        effective_connection_id = selected_connection.id
        wallet_last_check_at = (
            snapshot.get("checked_at")
            or snapshot.get("updated_at")
            or getattr(selected_connection, "updated_at", None)
        )
        permissions_payload = snapshot.get("permissions")
        if isinstance(permissions_payload, dict):
            wallet_available_balance = permissions_payload.get("available_balance")
            wallet_balance = permissions_payload.get("wallet_balance")

        if wallet_available_balance is None:
            wallet_available_balance = (
                snapshot.get("available_balance")
                or snapshot.get("free_balance")
            )

        if wallet_balance is None:
            wallet_balance = (
                snapshot.get("wallet_balance")
                or snapshot.get("account_equity")
                or snapshot.get("equity")
            )

    blocked_rows = (
        db.query(PendingSignal, SignalEvent.market_type)
        .outerjoin(SignalEvent, SignalEvent.id == PendingSignal.signal_id)
        .filter(
            PendingSignal.user_id == user_id,
            PendingSignal.status.in_(["blocked", "non_tradeable"]),
        )
        .order_by(PendingSignal.created_at.desc())
        .limit(400)
        .all()
    )
    blocked_reason_counts: dict[str, int] = {}
    for row, row_market_type in blocked_rows:
        normalized_row_market = str(row_market_type or "").strip().lower()
        if normalized_row_market in {"spot", "futures"} and normalized_row_market != str(market_type or "spot").lower():
            continue
        code, _, _ = _normalize_blocked_payload(
            status=row.status,
            blocked_reason_code=row.blocked_reason_code,
            blocked_reason_message=row.blocked_reason_message,
            blocked_solution_hint=row.blocked_solution_hint,
        )
        if (not live_mode_enabled) and code in {"ORDER_PRECHECK_FAILED", "SYMBOL_NOT_ALLOWED"}:
            continue
        if code:
            blocked_reason_counts[code] = blocked_reason_counts.get(code, 0) + 1

    blocking_reasons: list[dict] = []
    if latest_scanner_row is None:
        blocking_reasons.append({"code": "SCANNER_NOT_READY", "message": "Henüz scanner sonucu yok.", "hint": "Scanner run-async tetikleyin."})
    if not strategy_ready:
        blocking_reasons.append({"code": "STRATEGY_NOT_READY", "message": "Strategy binding hazır değil.", "hint": "Bot strategy/template eşleşmesini kontrol edin."})
    if not risk_ready:
        blocking_reasons.append({"code": "RISK_NOT_READY", "message": "Risk binding hazır değil.", "hint": "Bot için risk policy atayın."})
    if not execution_ready:
        blocking_reasons.append({"code": "EXECUTION_NOT_READY", "message": "Execution binding hazır değil.", "hint": "Exchange connection bağlayın."})
    if not symbols_ready:
        blocking_reasons.append({"code": "SYMBOLS_NOT_READY", "message": "Symbol resolution tamamlanmadı.", "hint": "manual_selection sembollerini güncelleyin."})
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

    health = "HEALTHY" if len(blocking_reasons) == 0 else "BLOCKED"
    latest_scanner_run_at = latest_scanner_row.generated_at.isoformat() if latest_scanner_row and latest_scanner_row.generated_at else None

    return {
        "market_type": str(market_type or "spot").lower(),
        "scanner_ready": bool(latest_scanner_row is not None),
        "strategy_ready": bool(strategy_ready),
        "risk_ready": bool(risk_ready),
        "execution_ready": bool(execution_ready),
        "symbols_ready": bool(symbols_ready),
        "exchange_ready": bool(exchange_ready),
        "bot_status": str((primary_bot or {}).get("status") or "NOT_CONFIGURED"),
        "health": health,
        "blocking_reasons": blocking_reasons,
        "latest_scanner_run_at": latest_scanner_run_at,
        "active_bot_id": (primary_bot or {}).get("id"),
        "wallet_last_check_at": wallet_last_check_at,
        "wallet_available_balance": wallet_available_balance,
        "wallet_balance": wallet_balance,
        "selected_exchange_connection_id": effective_connection_id,
    }


def _build_user_status_contract(db: Session, user_id: str, *, preferred_market: str | None = None) -> dict:
    live_config = get_or_create_live_config(db)
    live_mode_enabled = bool(getattr(live_config, "live_mode_enabled", False))

    bot_summaries = list_bot_runtime_summaries(db, user_id=user_id)

    recent_scanner_rows = (
        db.query(UserScannerResult)
        .filter(UserScannerResult.user_id == user_id)
        .order_by(UserScannerResult.generated_at.desc())
        .limit(400)
        .all()
    )

    latest_scanner_rows: dict[str, UserScannerResult | None] = {"spot": None, "futures": None}
    for row in recent_scanner_rows:
        market = _scanner_result_market_type(row)
        if market in latest_scanner_rows and latest_scanner_rows[market] is None:
            latest_scanner_rows[market] = row
        if latest_scanner_rows["spot"] is not None and latest_scanner_rows["futures"] is not None:
            break

    market_contracts: dict[str, dict] = {}
    for market in ("spot", "futures"):
        market_bot = _select_primary_bot_for_market(bot_summaries, market)
        if market_bot is None and latest_scanner_rows.get(market) is None:
            continue
        market_contracts[market] = _build_market_status_contract(
            db,
            user_id=user_id,
            market_type=market,
            primary_bot=market_bot,
            latest_scanner_row=latest_scanner_rows.get(market),
            live_mode_enabled=live_mode_enabled,
        )

    if not market_contracts:
        market_contracts["spot"] = _build_market_status_contract(
            db,
            user_id=user_id,
            market_type="spot",
            primary_bot=None,
            latest_scanner_row=None,
            live_mode_enabled=live_mode_enabled,
        )

    latest_scanner_row_global = recent_scanner_rows[0] if recent_scanner_rows else None

    preferred_market_candidate = str(preferred_market or "").strip().lower()
    if preferred_market_candidate not in {"spot", "futures"}:
        preferred_market_candidate = ""

    if not preferred_market_candidate and latest_scanner_row_global is not None:
        latest_market = _scanner_result_market_type(latest_scanner_row_global) or ""
        if latest_market in market_contracts:
            preferred_market_candidate = latest_market

    if not preferred_market_candidate:
        running_market = next(
            (
                market
                for market, contract in market_contracts.items()
                if str(contract.get("bot_status") or "").upper() == "RUNNING"
            ),
            None,
        )
        preferred_market_candidate = running_market or next(iter(market_contracts.keys()))

    selected_contract = market_contracts.get(preferred_market_candidate) or next(iter(market_contracts.values()))
    overall_health = "HEALTHY" if all(str(contract.get("health") or "").upper() == "HEALTHY" for contract in market_contracts.values()) else "BLOCKED"

    return {
        **selected_contract,
        "health": str(selected_contract.get("health") or "BLOCKED"),
        "overall_health": overall_health,
        "preferred_market": preferred_market_candidate,
        "market_contracts": market_contracts,
        "active_bot_ids": {market: contract.get("active_bot_id") for market, contract in market_contracts.items()},
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
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "PURE_LIVE_410", "message": "signal-mode kaldırıldı"})


@router.put("/signal-mode", response_model=UserSignalModeResponse)
def put_signal_mode(
    payload: UserSignalModeUpdateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "PURE_LIVE_410", "message": "signal-mode kaldırıldı"})


@router.get("/scanner/automation", response_model=UserScannerAutomationConfigResponse)
def get_scanner_automation_config(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "PURE_LIVE_410", "message": "scanner automation kaldırıldı"})


@router.put("/scanner/automation", response_model=UserScannerAutomationConfigResponse)
def put_scanner_automation_config(
    payload: UserScannerAutomationConfigUpdateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "PURE_LIVE_410", "message": "scanner automation kaldırıldı"})


@router.get("/scanner/automation-profiles", response_model=list[UserScannerAutomationProfileResponse])
def get_scanner_automation_profiles(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "PURE_LIVE_410", "message": "scanner automation profiles kaldırıldı"})


@router.post("/scanner/automation-profiles", response_model=UserScannerAutomationProfileResponse)
def post_scanner_automation_profile(
    payload: UserScannerAutomationProfileCreateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "PURE_LIVE_410", "message": "scanner automation profiles kaldırıldı"})


@router.put("/scanner/automation-profiles/{profile_id}", response_model=UserScannerAutomationProfileResponse)
def put_scanner_automation_profile(
    profile_id: str,
    payload: UserScannerAutomationProfileUpdateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "PURE_LIVE_410", "message": "scanner automation profiles kaldırıldı"})


@router.post("/scanner/automation-profiles/{profile_id}/activate", response_model=UserScannerAutomationProfileResponse)
def post_activate_scanner_automation_profile(
    profile_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "PURE_LIVE_410", "message": "scanner automation profiles kaldırıldı"})


@router.delete("/scanner/automation-profiles/{profile_id}")
def delete_scanner_automation_profile_route(
    profile_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "PURE_LIVE_410", "message": "scanner automation profiles kaldırıldı"})


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


@router.post("/scanner/analyze", response_model=UserScannerRunResponse)
def scanner_analyze(
    payload: UserScannerRunRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return scanner_run(payload=payload, current_user=current_user, db=db)


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
    market_type: str = Query(default="auto"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    normalized_market_type = str(market_type or "auto").strip().lower()
    preferred_market = normalized_market_type if normalized_market_type in {"spot", "futures"} else None
    try:
        return _build_user_status_contract(db, current_user.id, preferred_market=preferred_market)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "scanner_status_contract_failed user_id=%s market_type=%s error=%s",
            current_user.id,
            normalized_market_type,
            str(exc),
        )

        fallback_market = preferred_market or "spot"
        fallback_market_contract = {
            "market_type": fallback_market,
            "scanner_ready": False,
            "strategy_ready": False,
            "risk_ready": False,
            "execution_ready": False,
            "symbols_ready": False,
            "exchange_ready": False,
            "bot_status": "UNKNOWN",
            "health": "BLOCKED",
            "blocking_reasons": [
                {
                    "code": "STATUS_CONTRACT_INTERNAL_ERROR",
                    "message": "Status contract hesaplanırken iç hata oluştu.",
                    "hint": "Backend loglarını kontrol edin ve scanner/exchange snapshot verisini doğrulayın.",
                }
            ],
            "latest_scanner_run_at": None,
            "active_bot_id": None,
            "wallet_last_check_at": None,
            "wallet_available_balance": None,
            "wallet_balance": None,
            "selected_exchange_connection_id": None,
        }
        return {
            **fallback_market_contract,
            "overall_health": "BLOCKED",
            "preferred_market": fallback_market,
            "market_contracts": {fallback_market: fallback_market_contract},
            "active_bot_ids": {fallback_market: None},
        }


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


@router.get("/scanner-engine/decision-map")
def scanner_engine_decision_map(current_user: User = Depends(require_user)):
    payload = get_json(redis_client, _user_scanner_engine_last_run_key(current_user.id))
    if not isinstance(payload, dict) or not payload.get("run_id"):
        payload = get_json(redis_client, SCANNER_ENGINE_LAST_RUN_CACHE_KEY)
    if not isinstance(payload, dict):
        payload = {}

    results = payload.get("results") or []
    if not isinstance(results, list):
        results = []

    items: dict[str, dict] = {}
    for row in results:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper().strip()
        decisions = row.get("decisions")
        if symbol and isinstance(decisions, dict):
            items[symbol] = decisions

    return {
        "run_id": payload.get("run_id"),
        "generated_at": payload.get("generated_at"),
        "count": len(items),
        "items": items,
    }


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
    try:
        rows = list_user_signals(db, current_user.id, limit=limit, refresh_snapshot=False)
    except Exception:
        db.rollback()
        return []

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

    try:
        trade_rows = (
            db.query(UserTradeProjection)
            .filter(UserTradeProjection.user_id == current_user.id)
            .order_by(UserTradeProjection.updated_at.desc())
            .limit(max(limit * 3, 180))
            .all()
        )
    except Exception:
        db.rollback()
        trade_rows = []

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
        if blocked_reason_code == "MANUAL_APPROVAL_REQUIRED":
            blocked_reason_code = ""
            blocked_reason_message = ""
            blocked_solution_hint = ""
        first_precheck_failure_code = _extract_first_precheck_failure_code(row.decision_note, blocked_reason_message)
        if blocked_reason_code == "":
            first_precheck_failure_code = ""
        normalized_status = _normalize_signal_status_for_ui(status=row.status, blocked_reason_code=blocked_reason_code)
        tradeable = bool(row.execution_eligible)
        if normalized_status in {"blocked", "non_tradeable"}:
            tradeable = False
        if first_precheck_failure_code:
            tradeable = False
        if blocked_reason_code == "":
            tradeable = True

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
                requires_manual_approval=False,
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
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "PURE_LIVE_410",
            "message": "manuel_approve_kaldirildi_auto_signal_execution_aktif",
        },
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
    if blocked_reason_code == "MANUAL_APPROVAL_REQUIRED":
        blocked_reason_code = ""
        blocked_reason_message = ""
        blocked_solution_hint = ""

    return UserSignalDiagnoseResponse(
        id=row.id,
        status=row.status,
        current_state=row.current_state or "DETECTED",
        blocked_reason_code=blocked_reason_code,
        blocked_reason_message=blocked_reason_message,
        blocked_solution_hint=blocked_solution_hint,
        requires_manual_approval=False,
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