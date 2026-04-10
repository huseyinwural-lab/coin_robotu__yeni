import json
import csv
import io
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path as FilePath
from typing import Callable

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Path as FastAPIPath, Query, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import SessionLocal, engine, get_db, redis_client
from deps import require_admin
from models import AdminControl, AuditLog, ExecutionMetric, ScannerPerformanceSnapshot, UniverseExportJob, User, UserRole, UserScannerResult
from services.audit_service import create_audit_log
from services.pipeline.cache_store import get_json
from services.pipeline.universe_engine import debug_effective_universe
from services.risk_engine_service import build_admin_risk_status, patch_risk_config
from services.indicator_screener.market_data_provider import BinanceMarketDataProvider, MarketDataProviderError
from services.scanner_observability_service import (
    approve_rollout_transition,
    export_perf_trend_csv,
    get_fallback_state,
    get_freshness_heatmap,
    get_monitor_breakdown,
    get_perf_trend,
    get_rollout_state,
    list_fallback_events,
    recommend_rollout_transition,
)


router = APIRouter(prefix="/admin/universe-monitor", tags=["admin_universe_monitor"])

SCANNER_START_PHRASE = "START SCANNER"
SCANNER_STOP_PHRASE = "STOP SCANNER"
SCANNER_TRIGGER_PHRASE = "TRIGGER MANUAL SCAN"
SCANNER_SYMBOL_LIST_PHRASE = "UPDATE SYMBOL LIST"
SCANNER_SYMBOL_BULK_PHRASE = "BULK UPDATE SYMBOLS"
SCANNER_FILTER_CONFIG_PHRASE = "UPDATE FILTER CONFIG"

ROLLOUT_PROMOTE_PHRASE = "PROMOTE ROLLOUT"
ROLLOUT_DEMOTE_PHRASE = "DEMOTE ROLLOUT"
ROLLOUT_ROLLBACK_PHRASE = "ROLLBACK ROLLOUT"

RISK_EXPOSURE_PHRASE = "UPDATE EXPOSURE LIMIT"
RISK_OVERRIDE_PHRASE = "APPLY EXPOSURE OVERRIDE"

STRATEGY_DISABLE_PHRASE = "DISABLE STRATEGY"
STRATEGY_THROTTLE_PHRASE = "THROTTLE STRATEGY"
SYMBOL_PAUSE_PHRASE = "PAUSE SYMBOL"

SCANNER_RUNTIME_STATE_KEY = "universe:scanner:runtime_state"
UNIVERSE_FILTER_CONFIG_KEY = "universe:filter:config"
ROLLOUT_HISTORY_KEY = "universe:rollout:history"
RISK_EXPOSURE_OVERRIDE_KEY = "universe:risk:exposure_overrides"
SLOW_CONTROL_STATE_KEY = "universe:slow:control_state"
SLA_CONFIG_KEY = "universe:freshness:sla_config"
KPI_RECOMMENDATION_ACTIVE_KEY = "universe:kpi:recommendations:active"
KPI_RECOMMENDATION_HISTORY_KEY = "universe:kpi:recommendations:history"
SCANNER_ENGINE_CONFIG_KEY = "universe:scanner_engine:config"
SCANNER_ENGINE_LAST_RUN_KEY = "universe:scanner_engine:last_run"
SCANNER_ENGINE_BOT_JOB_QUEUE_KEY = "universe:scanner_engine:bot_jobs"
SCANNER_ENGINE_BOT_JOB_KEY_PREFIX = "universe:scanner_engine:bot_job"
SCANNER_ENGINE_DEFAULT_SCAN_LIMIT = 80
SCANNER_ENGINE_MAX_SCAN_LIMIT = 220


def _raise_admin_scanner_action_moved_to_user(action_name: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "PURE_LIVE_410",
            "message": "Admin scanner aksiyonları user paneline taşındı.",
            "action": action_name,
        },
    )


def _admin_scanner_action_removed_dependency() -> None:
    _raise_admin_scanner_action_moved_to_user("admin_scanner_action")

SLA_UPDATE_PHRASE = "UPDATE SLA CONFIG"
RESCAN_STALE_PHRASE = "RESCAN STALE"
KPI_GENERATE_PHRASE = "GENERATE KPI RECOMMENDATION"
KPI_APPLY_PHRASE = "APPLY RECOMMENDATION"
KPI_REJECT_PHRASE = "REJECT RECOMMENDATION"
KPI_POSTPONE_PHRASE = "POSTPONE RECOMMENDATION"
EXPORT_JOB_PHRASE = "CREATE EXPORT JOB"
BULK_IMPORT_PREVIEW_PHRASE = "PREVIEW BULK IMPORT"
BULK_IMPORT_APPLY_PHRASE = "APPLY BULK IMPORT"

scanner_market_data_provider = BinanceMarketDataProvider()

EXPORT_STORAGE_DIR = FilePath("/app/backend/exports")
BULK_IMPORT_PREVIEW_KEY = "universe:bulk_import:preview"


class RuntimeActionRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=4, max_length=100)


class ScannerTriggerRequest(RuntimeActionRequest):
    pass


class ScannerSymbolRequest(RuntimeActionRequest):
    symbol: str = Field(min_length=3, max_length=30)


class ScannerSymbolListUpdateRequest(RuntimeActionRequest):
    action: str = Field(pattern="^(add|remove|replace)$")
    symbols: list[str] = Field(min_length=1, max_length=500)


class ScannerUniverseBulkRequest(RuntimeActionRequest):
    symbols: list[str] = Field(min_length=1, max_length=1000)
    enabled: bool


class UniverseFilterConfigRequest(RuntimeActionRequest):
    min_liquidity_usd: float = Field(ge=0)
    min_volume_24h_usd: float = Field(ge=0)
    max_spread_bps: float = Field(ge=0)


class RolloutActionRequest(RuntimeActionRequest):
    pass


class ExposureLimitRequest(RuntimeActionRequest):
    max_total_exposure_pct: float = Field(ge=1, le=100)
    max_symbol_exposure_pct: float = Field(ge=1, le=100)
    max_cluster_exposure_pct: float = Field(ge=1, le=100)
    force: bool = False


class ExposureOverrideRequest(RuntimeActionRequest):
    override_type: str = Field(pattern="^(force_allow|force_reject|pause)$")
    scope: str = Field(default="global", min_length=3, max_length=80)
    ttl_minutes: int = Field(default=30, ge=5, le=240)


class StrategyThrottleRequest(RuntimeActionRequest):
    throttle_profile: str = Field(pattern="^(soft|medium|hard)$")


class SymbolPauseRequest(RuntimeActionRequest):
    pause: bool = True


class FreshnessSlaConfigRequest(RuntimeActionRequest):
    latency_threshold: float = Field(ge=0)
    stale_threshold_sec: int = Field(ge=30, le=86400)


class RescanStaleRequest(RuntimeActionRequest):
    limit: int = Field(default=200, ge=1, le=2000)


class RecommendationGenerateRequest(RuntimeActionRequest):
    pass


class RecommendationDecisionRequest(RuntimeActionRequest):
    recommendation_id: str = Field(min_length=8, max_length=120)


class ExportJobRequest(RuntimeActionRequest):
    range: str = Field(default="24h", pattern="^(1h|24h|7d|30d)$")
    output_format: str = Field(default="csv", pattern="^(csv|json)$")
    metrics: list[str] = Field(default_factory=list)
    symbol: str | None = None
    strategy: str | None = None


class BulkImportPreviewRequest(RuntimeActionRequest):
    csv_text: str = Field(min_length=1)


class BulkImportApplyRequest(RuntimeActionRequest):
    preview_id: str = Field(min_length=8, max_length=120)
    apply_mode: str = Field(default="apply_valid_only", pattern="^(apply_all|apply_valid_only)$")


class ScannerEngineConfigSaveRequest(BaseModel):
    exchange: str = Field(default="binance", pattern="^binance$")
    include_spot: bool = True
    include_futures: bool = True
    market_scope: dict = Field(default_factory=dict)
    signal_mode: str = Field(default="manual", pattern="^(manual|auto)$")
    auto_interval_minutes: int = Field(default=3, ge=1, le=5)
    scan_limit: int = Field(default=SCANNER_ENGINE_DEFAULT_SCAN_LIMIT, ge=1)
    top_n: int = Field(default=20, ge=1, le=150)
    manual_symbols: list[str] = Field(default_factory=list)
    trend_weight: int = Field(default=10, ge=0, le=200)
    volume_weight: int = Field(default=50, ge=0, le=200)
    momentum_weight: int = Field(default=100, ge=0, le=300)
    bollinger_weight: int = Field(default=1, ge=0, le=50)
    decision_boxes: dict = Field(default_factory=dict)
    reason: str = Field(default="scanner_engine_config_save", min_length=3, max_length=240)


class ScannerEngineRunRequest(BaseModel):
    force_refresh: bool = False
    reason: str = Field(default="manual_scanner_run", min_length=3, max_length=240)


class ScannerEngineStartBotRequest(BaseModel):
    selection_mode: str = Field(default="top_n", pattern="^(top_n|manual)$")
    top_n: int = Field(default=20, ge=1, le=150)
    selected_symbols: list[str] = Field(default_factory=list)
    side_filter: str = Field(default="all", pattern="^(all|long|short|strong_long|strong_short)$")
    reason: str = Field(default="start_scanner_job", min_length=3, max_length=240)


class ScannerEngineJobListResponse(BaseModel):
    count: int
    items: list[dict]


def _manager_required(current_admin: User) -> User:
    if current_admin.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="manager_role_required")
    return current_admin


def _super_admin_required(current_admin: User) -> User:
    if current_admin.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_required")
    return current_admin


def _read_json_value(key: str, default):
    raw = redis_client.get(key)
    if not raw:
        return default
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except Exception:
        return default


def _write_json_value(key: str, payload):
    redis_client.set(key, json.dumps(payload, ensure_ascii=False, default=str))


def _normalize_symbols(symbols: list[str]) -> list[str]:
    return sorted({str(item or "").upper().strip() for item in symbols if str(item or "").strip()})


def _require_phrase(actual_phrase: str, expected_phrase: str):
    if str(actual_phrase or "").strip().upper() != expected_phrase:
        raise HTTPException(status_code=400, detail={"expected_phrase": expected_phrase})


def _action_result(*, trace_id: str, message: str, state_snapshot: dict, **extra):
    payload = {
        "status": "success",
        "trace_id": trace_id,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state_snapshot": state_snapshot,
    }
    payload.update(extra)
    return payload


def _reason_set(item: UserScannerResult) -> set[str]:
    payload = item.payload or {}
    reason_codes = payload.get("reason_codes") or []
    merged = set(str(code or "").strip().lower() for code in reason_codes if str(code or "").strip())
    merged.update(str(code or "").strip().lower() for code in (item.reason_codes or []) if str(code or "").strip())
    blocked_reason = str(payload.get("blocked_reason_current") or "").strip().lower()
    if blocked_reason:
        merged.add(blocked_reason)
    return merged


def _scanner_runtime_state() -> dict:
    state = _read_json_value(
        SCANNER_RUNTIME_STATE_KEY,
        {
            "running": True,
            "last_started_at": None,
            "last_stopped_at": None,
            "last_manual_trigger_status": None,
            "last_manual_trigger_request_id": None,
        },
    )
    runtime_health = _read_json_value("pipeline:scanner:health", {})
    return {
        **state,
        "runtime_health": runtime_health,
    }


def _load_admin_control(db: Session) -> AdminControl:
    row = db.query(AdminControl).filter(AdminControl.id == "global").first()
    if row is None:
        row = AdminControl(id="global")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _load_rollout_history() -> list[dict]:
    rows = _read_json_value(ROLLOUT_HISTORY_KEY, [])
    if not isinstance(rows, list):
        return []
    return rows


def _append_rollout_history(entry: dict):
    rows = _load_rollout_history()
    rows.append(entry)
    _write_json_value(ROLLOUT_HISTORY_KEY, rows[-100:])


def _rollout_status_payload(row) -> dict:
    meta = row.recommendation_payload or {}
    return {
        "current_stage": row.current_stage,
        "recommended_stage": row.recommended_stage,
        "recommendation_payload": meta,
        "requires_admin_approval": bool(row.requires_admin_approval),
        "approved_by": row.approved_by,
        "approved_at": row.approved_at,
        "updated_at": row.updated_at,
        "previous_stage": meta.get("previous_stage"),
        "changed_by": meta.get("changed_by"),
        "change_reason": meta.get("change_reason"),
        "rollback_available": bool(meta.get("previous_stage")),
        "pending_approvers": meta.get("pending_approvers") or ["super_admin"],
        "approval_policy": meta.get("approval_policy") or "double_confirm_required",
        "approval_started_at": meta.get("approval_started_at"),
        "history": _load_rollout_history()[-30:],
    }


def _rollout_transition(db: Session, *, row, next_stage: str, changed_by: str, change_reason: str):
    previous_stage = row.current_stage
    now_iso = datetime.now(timezone.utc).isoformat()
    meta = dict(row.recommendation_payload or {})
    meta.update(
        {
            "previous_stage": previous_stage,
            "changed_by": changed_by,
            "change_reason": change_reason,
            "rollback_available": True,
            "pending_approvers": ["super_admin"],
            "approval_policy": "double_confirm_required",
            "approval_started_at": now_iso,
        }
    )
    row.current_stage = next_stage
    row.recommended_stage = next_stage
    row.recommendation_payload = meta
    row.requires_admin_approval = True
    row.updated_at = datetime.now(timezone.utc)
    db.commit()

    _append_rollout_history(
        {
            "changed_at": now_iso,
            "previous_stage": previous_stage,
            "current_stage": next_stage,
            "changed_by": changed_by,
            "change_reason": change_reason,
        }
    )


def _default_sla_config() -> dict:
    return {
        "latency_threshold": 1200.0,
        "stale_threshold_sec": 900,
        "updated_at": None,
        "updated_by": None,
    }


def _get_sla_config() -> dict:
    return _read_json_value(SLA_CONFIG_KEY, _default_sla_config())


def _derive_stale_entities(db: Session, *, stale_threshold_sec: int, limit: int = 500) -> list[dict]:
    now = datetime.now(timezone.utc)
    stale_items: list[dict] = []

    symbol_rows = (
        db.query(UserScannerResult.symbol, UserScannerResult.generated_at)
        .order_by(UserScannerResult.generated_at.desc())
        .limit(5000)
        .all()
    )
    symbol_last_seen: dict[str, datetime] = {}
    for symbol, generated_at in symbol_rows:
        key = str(symbol or "").upper().strip()
        if not key or key in symbol_last_seen or generated_at is None:
            continue
        symbol_last_seen[key] = generated_at

    for symbol, last_seen in symbol_last_seen.items():
        age = int((now - last_seen).total_seconds())
        if age >= stale_threshold_sec:
            stale_items.append(
                {
                    "entity_type": "symbol",
                    "entity_id": symbol,
                    "last_update_ts": last_seen.isoformat(),
                    "age_sec": age,
                    "severity": "critical" if age >= stale_threshold_sec * 2 else "warning",
                    "reason": "symbol_scan_stale",
                }
            )

    strategy_rows = (
        db.query(ExecutionMetric.strategy_type, ExecutionMetric.created_at)
        .order_by(ExecutionMetric.created_at.desc())
        .limit(5000)
        .all()
    )
    strategy_last_seen: dict[str, datetime] = {}
    for strategy_type, created_at in strategy_rows:
        key = str(strategy_type or "unknown").strip()
        if key in strategy_last_seen or created_at is None:
            continue
        strategy_last_seen[key] = created_at

    for strategy, last_seen in strategy_last_seen.items():
        age = int((now - last_seen).total_seconds())
        if age >= stale_threshold_sec:
            stale_items.append(
                {
                    "entity_type": "strategy",
                    "entity_id": strategy,
                    "last_update_ts": last_seen.isoformat(),
                    "age_sec": age,
                    "severity": "critical" if age >= stale_threshold_sec * 2 else "warning",
                    "reason": "strategy_execution_stale",
                }
            )

    cycle_row = db.query(ScannerPerformanceSnapshot).order_by(ScannerPerformanceSnapshot.created_at.desc()).first()
    if cycle_row and cycle_row.created_at:
        age = int((now - cycle_row.created_at).total_seconds())
        if age >= stale_threshold_sec:
            stale_items.append(
                {
                    "entity_type": "scanner_cycle",
                    "entity_id": str(cycle_row.run_id or cycle_row.stage or "latest_cycle"),
                    "last_update_ts": cycle_row.created_at.isoformat(),
                    "age_sec": age,
                    "severity": "critical" if age >= stale_threshold_sec * 2 else "warning",
                    "reason": "scanner_cycle_stale",
                }
            )

    stale_items.sort(key=lambda item: (0 if item["severity"] == "critical" else 1, item["age_sec"]), reverse=True)
    return stale_items[:limit]


def _kpi_active_recommendations() -> list[dict]:
    rows = _read_json_value(KPI_RECOMMENDATION_ACTIVE_KEY, [])
    return rows if isinstance(rows, list) else []


def _kpi_history() -> list[dict]:
    rows = _read_json_value(KPI_RECOMMENDATION_HISTORY_KEY, [])
    return rows if isinstance(rows, list) else []


def _ensure_export_job_table():
    UniverseExportJob.__table__.create(bind=engine, checkfirst=True)


def _resolve_range_to_since(range_value: str, now: datetime) -> datetime:
    if range_value == "1h":
        return now - timedelta(hours=1)
    if range_value == "7d":
        return now - timedelta(days=7)
    if range_value == "30d":
        return now - timedelta(days=30)
    return now - timedelta(hours=24)


def _build_export_rows(db: Session, *, params: dict) -> list[dict]:
    range_value = str(params.get("range") or "24h")
    symbol = str(params.get("symbol") or "").upper().strip() or None
    strategy = str(params.get("strategy") or "").strip() or None
    selected_metrics = {str(item).strip() for item in (params.get("metrics") or []) if str(item).strip()}

    series_payload = metrics_history(
        range=range_value,
        symbol=symbol,
        strategy=strategy,
        current_admin=None,  # type: ignore[arg-type]
        db=db,
    )

    latency_map = {item["ts"]: item for item in series_payload.get("latency_series") or []}
    pnl_map = {item["ts"]: item for item in series_payload.get("pnl_series") or []}
    veto_map = {item["ts"]: item for item in series_payload.get("risk_veto_series") or []}

    ts_keys = sorted(set(latency_map.keys()) | set(pnl_map.keys()) | set(veto_map.keys()))
    rows = []
    for ts_key in ts_keys:
        latency = latency_map.get(ts_key, {})
        pnl = pnl_map.get(ts_key, {})
        veto = veto_map.get(ts_key, {})
        row = {
            "ts": ts_key,
            "latency_avg_ms": latency.get("avg_ms"),
            "latency_p95_ms": latency.get("p95_ms"),
            "latency_count": latency.get("count"),
            "pnl_sum": pnl.get("sum"),
            "pnl_avg": pnl.get("avg"),
            "risk_veto_count": veto.get("count"),
        }
        if selected_metrics:
            row = {k: v for k, v in row.items() if k == "ts" or k in selected_metrics}
        rows.append(row)

    overlays = series_payload.get("overlays") or []
    for item in overlays[:300]:
        rows.append(
            {
                "ts": item.get("ts"),
                "overlay_event": item.get("event"),
                "overlay_message": item.get("message"),
            }
        )

    return rows


def _write_export_file(*, job_id: str, output_format: str, rows: list[dict]) -> FilePath:
    EXPORT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ".json" if output_format == "json" else ".csv"
    path = EXPORT_STORAGE_DIR / f"{job_id}{suffix}"

    if output_format == "json":
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return path

    headers = sorted({key for row in rows for key in row.keys()}) if rows else ["ts", "symbol", "strategy_type", "latency_ms"]
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _process_export_job_async(*, job_id: str):
    _ensure_export_job_table()
    db = SessionLocal()
    try:
        row = db.query(UniverseExportJob).filter(UniverseExportJob.job_id == job_id).first()
        if row is None:
            return
        row.status = "running"
        row.updated_at = datetime.now(timezone.utc)
        db.commit()

        export_rows = _build_export_rows(db, params=row.params or {})
        output_format = str(row.result_format or "csv").lower()
        result_path = _write_export_file(job_id=row.job_id, output_format=output_format, rows=export_rows)

        row.status = "done"
        row.result_row_count = len(export_rows)
        row.result_url = f"/api/admin/universe-monitor/export/job/{row.job_id}/download"
        row.updated_at = datetime.now(timezone.utc)
        db.commit()

        create_audit_log(
            db,
            action="UNIVERSE_EXPORT_JOB_DONE",
            entity_type="export_job",
            entity_id=row.job_id,
            actor_user_id=row.created_by,
            actor_role="admin",
            severity="info",
            details={"trace_id": row.trace_id, "result_url": row.result_url, "row_count": len(export_rows), "file_path": str(result_path)},
        )
    except Exception as exc:
        db.rollback()
        row = db.query(UniverseExportJob).filter(UniverseExportJob.job_id == job_id).first()
        if row:
            row.status = "failed"
            row.error_message = str(exc)[:500]
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
            create_audit_log(
                db,
                action="UNIVERSE_EXPORT_JOB_FAILED",
                entity_type="export_job",
                entity_id=row.job_id,
                actor_user_id=row.created_by,
                actor_role="admin",
                severity="critical",
                details={"trace_id": row.trace_id, "error": row.error_message},
            )
    finally:
        db.close()


def _parse_bulk_csv_symbols(csv_text: str) -> list[str]:
    text = str(csv_text or "")
    rows = []
    for line in text.splitlines():
        parts = [item.strip() for item in re.split(r"[,;\t ]+", line) if item.strip()]
        rows.extend(parts)
    return [str(item).upper().strip() for item in rows if str(item).strip()]


def _build_bulk_preview(*, symbols: list[str], blacklist: set[str]) -> dict:
    symbol_regex = re.compile(r"^[A-Z0-9]{5,20}$")
    seen: set[str] = set()
    valid_symbols: list[str] = []
    errors: list[dict] = []

    for symbol in symbols:
        if not symbol_regex.match(symbol):
            errors.append({"symbol": symbol, "reason": "invalid_symbol"})
            continue
        if symbol in seen:
            errors.append({"symbol": symbol, "reason": "duplicate"})
            continue
        seen.add(symbol)
        if symbol in blacklist:
            errors.append({"symbol": symbol, "reason": "blacklist_conflict"})
            continue
        valid_symbols.append(symbol)

    reason_counts: dict[str, int] = {}
    for item in errors:
        reason = item["reason"]
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    return {
        "total_input": len(symbols),
        "valid_count": len(valid_symbols),
        "invalid_count": len(errors),
        "reason_counts": reason_counts,
        "valid_symbols": valid_symbols,
        "invalid_items": errors,
    }


def _default_scanner_engine_config() -> dict:
    return {
        "exchange": "binance",
        "include_spot": True,
        "include_futures": True,
        "market_scope": {
            "spot_mode": "all",
            "futures_mode": "all",
        },
        "signal_mode": "manual",
        "auto_interval_minutes": 3,
        "scan_limit": SCANNER_ENGINE_DEFAULT_SCAN_LIMIT,
        "top_n": 20,
        "manual_symbols": [],
        "indicator_timeframe": "1h",
        "execution_timeframe": "15m",
        "weights": {
            "trend": 10,
            "volume": 50,
            "momentum": 100,
            "bollinger": 1,
            "max_score": 161,
        },
        "decision_boxes": {
            "bc01": {
                "ema_period": 20,
                "stddev_multiplier": 1.6,
            },
            "bc02": {
                "y1_period": 120,
                "y2_period": 210,
                "y2y_period": 90,
                "y3_period": 5,
            },
            "bc03": {
                "z1_ma_period": 21,
                "z1_ref_bars": 3,
                "z2_ma_period": 3,
                "hlf_period": 25,
                "hhv_h_period": 20,
                "z4_threshold": 0.0,
            },
            "bc04": {
                "stofk_k_period": 14,
                "stofk_d_period": 6,
                "rsi_period": 14,
                "mfi_period": 14,
                "cci_period": 14,
                "willr_period": 14,
                "mo_period": 14,
                "ult_fast": 7,
                "ult_mid": 14,
                "ult_slow": 28,
                "tke_threshold": 79.0,
            },
        },
        "updated_at": None,
        "updated_by": None,
    }


def _load_scanner_engine_config() -> dict:
    saved = _read_json_value(SCANNER_ENGINE_CONFIG_KEY, _default_scanner_engine_config())
    if not isinstance(saved, dict):
        saved = {}
    auto_interval_minutes = 3
    try:
        parsed_interval = int(saved.get("auto_interval_minutes") or 3)
        auto_interval_minutes = parsed_interval if parsed_interval in {1, 3, 5} else 3
    except Exception:
        auto_interval_minutes = 3

    return {
        **_default_scanner_engine_config(),
        **saved,
        "manual_symbols": _normalize_symbols(saved.get("manual_symbols") or []),
        "market_scope": _sanitize_market_scope(saved.get("market_scope") or {}),
        "auto_interval_minutes": auto_interval_minutes,
        "decision_boxes": _sanitize_decision_boxes(saved.get("decision_boxes") or {}),
    }


def _save_scanner_engine_config(config: dict):
    _write_json_value(SCANNER_ENGINE_CONFIG_KEY, config)


def _sanitize_market_scope(input_scope: dict) -> dict:
    scope = dict(input_scope or {})

    def _normalize_mode(value: str | None, fallback: str) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"all", "manual", "top50", "top100"}:
            return raw
        if raw.startswith("top"):
            tail = raw[3:]
            if tail.isdigit():
                parsed = max(1, min(int(tail), 500))
                return f"top{parsed}"
        return fallback

    return {
        "spot_mode": _normalize_mode(scope.get("spot_mode"), "all"),
        "futures_mode": _normalize_mode(scope.get("futures_mode"), "all"),
    }


def _resolve_top_limit(mode: str | None, *, default: int = 50) -> int:
    raw = str(mode or "").strip().lower()
    if not raw.startswith("top"):
        return default
    digits = raw[3:]
    if digits.isdigit():
        return max(1, min(int(digits), 500))
    return default


def _apply_market_mode(
    rows: list[dict],
    *,
    mode: str,
    manual_symbols: set[str],
) -> list[dict]:
    normalized_mode = str(mode or "all").strip().lower()
    if normalized_mode == "manual":
        if not manual_symbols:
            return []
        return [item for item in rows if str(item.get("symbol") or "").upper() in manual_symbols]
    if normalized_mode.startswith("top"):
        return rows[: _resolve_top_limit(normalized_mode)]
    return list(rows)


def _sanitize_decision_boxes(input_boxes: dict) -> dict:
    defaults = _default_scanner_engine_config().get("decision_boxes") or {}
    if not isinstance(input_boxes, dict):
        input_boxes = {}

    def _read(path: str, fallback):
        group, key = path.split(".", 1)
        try:
            return input_boxes.get(group, {}).get(key, fallback)
        except Exception:
            return fallback

    def _clamp_int(value, minimum: int, maximum: int, fallback: int) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = fallback
        return max(minimum, min(maximum, parsed))

    def _clamp_float(value, minimum: float, maximum: float, fallback: float) -> float:
        try:
            parsed = float(value)
        except Exception:
            parsed = fallback
        return max(minimum, min(maximum, parsed))

    return {
        "bc01": {
            "ema_period": _clamp_int(_read("bc01.ema_period", defaults["bc01"]["ema_period"]), 5, 200, defaults["bc01"]["ema_period"]),
            "stddev_multiplier": _clamp_float(
                _read("bc01.stddev_multiplier", defaults["bc01"]["stddev_multiplier"]),
                0.2,
                5.0,
                defaults["bc01"]["stddev_multiplier"],
            ),
        },
        "bc02": {
            "y1_period": _clamp_int(_read("bc02.y1_period", defaults["bc02"]["y1_period"]), 10, 500, defaults["bc02"]["y1_period"]),
            "y2_period": _clamp_int(_read("bc02.y2_period", defaults["bc02"]["y2_period"]), 10, 800, defaults["bc02"]["y2_period"]),
            "y2y_period": _clamp_int(_read("bc02.y2y_period", defaults["bc02"]["y2y_period"]), 5, 300, defaults["bc02"]["y2y_period"]),
            "y3_period": _clamp_int(_read("bc02.y3_period", defaults["bc02"]["y3_period"]), 2, 100, defaults["bc02"]["y3_period"]),
        },
        "bc03": {
            "z1_ma_period": _clamp_int(_read("bc03.z1_ma_period", defaults["bc03"]["z1_ma_period"]), 5, 120, defaults["bc03"]["z1_ma_period"]),
            "z1_ref_bars": _clamp_int(_read("bc03.z1_ref_bars", defaults["bc03"]["z1_ref_bars"]), 1, 20, defaults["bc03"]["z1_ref_bars"]),
            "z2_ma_period": _clamp_int(_read("bc03.z2_ma_period", defaults["bc03"]["z2_ma_period"]), 2, 30, defaults["bc03"]["z2_ma_period"]),
            "hlf_period": _clamp_int(_read("bc03.hlf_period", defaults["bc03"]["hlf_period"]), 5, 120, defaults["bc03"]["hlf_period"]),
            "hhv_h_period": _clamp_int(_read("bc03.hhv_h_period", defaults["bc03"]["hhv_h_period"]), 5, 120, defaults["bc03"]["hhv_h_period"]),
            "z4_threshold": _clamp_float(_read("bc03.z4_threshold", defaults["bc03"]["z4_threshold"]), -1000.0, 1000.0, defaults["bc03"]["z4_threshold"]),
        },
        "bc04": {
            "stofk_k_period": _clamp_int(_read("bc04.stofk_k_period", defaults["bc04"]["stofk_k_period"]), 5, 120, defaults["bc04"]["stofk_k_period"]),
            "stofk_d_period": _clamp_int(_read("bc04.stofk_d_period", defaults["bc04"]["stofk_d_period"]), 2, 60, defaults["bc04"]["stofk_d_period"]),
            "rsi_period": _clamp_int(_read("bc04.rsi_period", defaults["bc04"]["rsi_period"]), 5, 120, defaults["bc04"]["rsi_period"]),
            "mfi_period": _clamp_int(_read("bc04.mfi_period", defaults["bc04"]["mfi_period"]), 5, 120, defaults["bc04"]["mfi_period"]),
            "cci_period": _clamp_int(_read("bc04.cci_period", defaults["bc04"]["cci_period"]), 5, 120, defaults["bc04"]["cci_period"]),
            "willr_period": _clamp_int(_read("bc04.willr_period", defaults["bc04"]["willr_period"]), 5, 120, defaults["bc04"]["willr_period"]),
            "mo_period": _clamp_int(_read("bc04.mo_period", defaults["bc04"]["mo_period"]), 5, 120, defaults["bc04"]["mo_period"]),
            "ult_fast": _clamp_int(_read("bc04.ult_fast", defaults["bc04"]["ult_fast"]), 3, 30, defaults["bc04"]["ult_fast"]),
            "ult_mid": _clamp_int(_read("bc04.ult_mid", defaults["bc04"]["ult_mid"]), 5, 60, defaults["bc04"]["ult_mid"]),
            "ult_slow": _clamp_int(_read("bc04.ult_slow", defaults["bc04"]["ult_slow"]), 8, 120, defaults["bc04"]["ult_slow"]),
            "tke_threshold": _clamp_float(_read("bc04.tke_threshold", defaults["bc04"]["tke_threshold"]), 1.0, 99.0, defaults["bc04"]["tke_threshold"]),
        },
    }


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _sma(values: list[float], period: int) -> float:
    if len(values) < period or period <= 0:
        return 0.0
    sample = values[-period:]
    return sum(sample) / float(period)


def _std(values: list[float], period: int) -> float:
    if len(values) < period or period <= 1:
        return 0.0
    sample = values[-period:]
    mean = sum(sample) / float(period)
    variance = sum((item - mean) ** 2 for item in sample) / float(period)
    return math.sqrt(max(variance, 0.0))


def _compute_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = 0.0
    losses = 0.0
    for idx in range(len(closes) - period, len(closes)):
        delta = closes[idx] - closes[idx - 1]
        if delta >= 0:
            gains += delta
        else:
            losses += abs(delta)
    avg_gain = gains / float(period)
    avg_loss = losses / float(period)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _ema(values: list[float], period: int) -> float:
    if period <= 1 or len(values) < period:
        return _sma(values, min(len(values), max(period, 1))) if values else 0.0
    k = 2.0 / float(period + 1)
    ema = _sma(values[:period], period)
    for value in values[period:]:
        ema = (value * k) + (ema * (1.0 - k))
    return ema


def _hhv(values: list[float], period: int) -> float:
    if period <= 0 or len(values) < period:
        return max(values) if values else 0.0
    return max(values[-period:])


def _llv(values: list[float], period: int) -> float:
    if period <= 0 or len(values) < period:
        return min(values) if values else 0.0
    return min(values[-period:])


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _sma_with_offset(values: list[float], period: int, offset: int = 0) -> float:
    end_idx = len(values) - max(0, offset)
    if end_idx <= 0:
        return 0.0
    start_idx = end_idx - period
    if start_idx < 0:
        return 0.0
    sample = values[start_idx:end_idx]
    return sum(sample) / float(period)


def _compute_mfi(highs: list[float], lows: list[float], closes: list[float], volumes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    typical_prices = [((highs[i] + lows[i] + closes[i]) / 3.0) for i in range(len(closes))]
    positive_flow = 0.0
    negative_flow = 0.0
    for idx in range(len(closes) - period, len(closes)):
        flow = typical_prices[idx] * volumes[idx]
        if typical_prices[idx] >= typical_prices[idx - 1]:
            positive_flow += flow
        else:
            negative_flow += flow
    if negative_flow == 0:
        return 100.0
    mfr = positive_flow / negative_flow
    return 100.0 - (100.0 / (1.0 + mfr))


def _compute_cci(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    if len(closes) < period:
        return 0.0
    typical_prices = [((highs[i] + lows[i] + closes[i]) / 3.0) for i in range(len(closes))]
    sample = typical_prices[-period:]
    sma_tp = sum(sample) / float(period)
    mean_dev = sum(abs(item - sma_tp) for item in sample) / float(period)
    if mean_dev == 0:
        return 0.0
    return (sample[-1] - sma_tp) / (0.015 * mean_dev)


def _compute_willr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    if len(closes) < period:
        return -50.0
    highest = _hhv(highs, period)
    lowest = _llv(lows, period)
    if highest == lowest:
        return -50.0
    return ((highest - closes[-1]) / (highest - lowest)) * -100.0


def _compute_stofk(highs: list[float], lows: list[float], closes: list[float], k_period: int = 14) -> float:
    if len(closes) < k_period:
        return 50.0
    highest = _hhv(highs, k_period)
    lowest = _llv(lows, k_period)
    if highest == lowest:
        return 50.0
    return ((closes[-1] - lowest) / (highest - lowest)) * 100.0


def _compute_ultimate_oscillator(highs: list[float], lows: list[float], closes: list[float], fast: int, mid: int, slow: int) -> float:
    if len(closes) < slow + 1:
        return 50.0
    buying_pressure: list[float] = []
    true_range: list[float] = []
    for idx in range(1, len(closes)):
        prev_close = closes[idx - 1]
        bp = closes[idx] - min(lows[idx], prev_close)
        tr = max(highs[idx], prev_close) - min(lows[idx], prev_close)
        buying_pressure.append(bp)
        true_range.append(tr)

    def _avg(period: int) -> float:
        bp_sum = sum(buying_pressure[-period:])
        tr_sum = sum(true_range[-period:])
        if tr_sum == 0:
            return 0.0
        return bp_sum / tr_sum

    uo = 100.0 * ((4 * _avg(fast)) + (2 * _avg(mid)) + _avg(slow)) / 7.0
    return _clamp(uo, 0.0, 100.0)


def _evaluate_scanner_layers(indicator_candles: list[dict], weights: dict, decision_boxes: dict | None = None) -> dict:
    closes = [_to_float(item.get("close")) for item in indicator_candles if item.get("close") is not None]
    highs = [_to_float(item.get("high")) for item in indicator_candles if item.get("high") is not None]
    lows = [_to_float(item.get("low")) for item in indicator_candles if item.get("low") is not None]
    volumes = [_to_float(item.get("volume")) for item in indicator_candles if item.get("volume") is not None]
    decision_boxes = _sanitize_decision_boxes(decision_boxes or {})
    min_required = max(
        int((decision_boxes.get("bc02") or {}).get("y2_period") or 210) + 3,
        int((decision_boxes.get("bc03") or {}).get("z1_ma_period") or 21) + int((decision_boxes.get("bc03") or {}).get("z1_ref_bars") or 3) + 4,
        int((decision_boxes.get("bc04") or {}).get("ult_slow") or 28) + 3,
        60,
    )
    if len(closes) < min_required or len(volumes) < 30 or len(highs) < min_required or len(lows) < min_required:
        raise MarketDataProviderError("Yetersiz indikatör verisi")

    trend_w = int(weights.get("trend") or 10)
    volume_w = int(weights.get("volume") or 50)
    momentum_w = int(weights.get("momentum") or 100)
    bollinger_w = int(weights.get("bollinger") or 1)

    close_latest = closes[-1]
    close_prev = closes[-2]

    bc01_cfg = decision_boxes.get("bc01") or {}
    bc02_cfg = decision_boxes.get("bc02") or {}
    bc03_cfg = decision_boxes.get("bc03") or {}
    bc04_cfg = decision_boxes.get("bc04") or {}

    bc01_period = int(bc01_cfg.get("ema_period") or 20)
    bc01_std_mult = float(bc01_cfg.get("stddev_multiplier") or 1.6)
    ema_now = _ema(closes, bc01_period)
    ema_prev = _ema(closes[:-1], bc01_period)
    std_now = _std(closes, bc01_period)
    std_prev = _std(closes[:-1], bc01_period)
    upper_now = ema_now + (bc01_std_mult * std_now)
    upper_prev = ema_prev + (bc01_std_mult * std_prev)
    lower_now = ema_now - (bc01_std_mult * std_now)
    lower_prev = ema_prev - (bc01_std_mult * std_prev)
    bc01_long = bool(close_prev <= upper_prev and close_latest > upper_now)
    bc01_short = bool(close_prev >= lower_prev and close_latest < lower_now)

    y1 = _hhv(highs[:-1], int(bc02_cfg.get("y1_period") or 120))
    y2 = _hhv(highs[:-1], int(bc02_cfg.get("y2_period") or 210))
    y2y = _hhv(highs[:-1], int(bc02_cfg.get("y2y_period") or 90))
    y3 = _hhv(highs[:-1], int(bc02_cfg.get("y3_period") or 5))
    l1 = _llv(lows[:-1], int(bc02_cfg.get("y1_period") or 120))
    l2 = _llv(lows[:-1], int(bc02_cfg.get("y2_period") or 210))
    l2y = _llv(lows[:-1], int(bc02_cfg.get("y2y_period") or 90))
    l3 = _llv(lows[:-1], int(bc02_cfg.get("y3_period") or 5))
    bc02_long = bool(close_latest > max(y1, y2, y2y, y3))
    bc02_short = bool(close_latest < min(l1, l2, l2y, l3))

    z1_period = int(bc03_cfg.get("z1_ma_period") or 21)
    z1_ref = int(bc03_cfg.get("z1_ref_bars") or 3)
    z2_period = int(bc03_cfg.get("z2_ma_period") or 3)
    z4_threshold = float(bc03_cfg.get("z4_threshold") or 0.0)
    hlf_period = int(bc03_cfg.get("hlf_period") or 25)
    hhv_h_period = int(bc03_cfg.get("hhv_h_period") or 20)

    z1 = _sma_with_offset(closes, z1_period, z1_ref)
    z1v = _sma_with_offset(volumes, z1_period, z1_ref)
    z2 = _sma(closes, z2_period)
    z2v = _sma(volumes, z2_period)
    z3 = ((z2 - z1) / abs(z1) * 100.0) if z1 else 0.0
    z3v = ((z2v - z1v) / abs(z1v) * 100.0) if z1v else 0.0
    z4 = z3 * z3v
    hlf = _hhv([highs[i] - lows[i] for i in range(len(highs) - hlf_period - 1, len(highs) - 1) if i >= 0], hlf_period)
    hhv_h = _hhv(highs, hhv_h_period)
    llv_l = _llv(lows, hhv_h_period)
    abs_z4_threshold = abs(z4_threshold)
    bc03_long = bool(z4 >= abs_z4_threshold and z3 > 0 and z3v > 0 and (close_latest >= hhv_h or (highs[-1] - lows[-1]) >= hlf * 0.8))
    bc03_short = bool(z4 <= -abs_z4_threshold and z3 < 0 and z3v > 0 and (close_latest <= llv_l or (highs[-1] - lows[-1]) >= hlf * 0.8))

    stofk = _compute_stofk(highs, lows, closes, int(bc04_cfg.get("stofk_k_period") or 14))
    rsi = _compute_rsi(closes, int(bc04_cfg.get("rsi_period") or 14))
    mfi = _compute_mfi(highs, lows, closes, volumes, int(bc04_cfg.get("mfi_period") or 14))
    cci = _compute_cci(highs, lows, closes, int(bc04_cfg.get("cci_period") or 14))
    cci_norm = _clamp((cci + 200.0) / 4.0, 0.0, 100.0)
    willr = _compute_willr(highs, lows, closes, int(bc04_cfg.get("willr_period") or 14))
    willr_norm = _clamp(willr + 100.0, 0.0, 100.0)
    mo_period = int(bc04_cfg.get("mo_period") or 14)
    momentum_abs = closes[-1] - closes[-mo_period - 1] if len(closes) > mo_period + 1 else 0.0
    momentum_base = abs(closes[-mo_period - 1]) if len(closes) > mo_period + 1 else max(abs(closes[-1]), 1.0)
    mo_norm = _clamp(50.0 + (((momentum_abs / momentum_base) * 100.0) * 5.0), 0.0, 100.0)
    ult = _compute_ultimate_oscillator(
        highs,
        lows,
        closes,
        int(bc04_cfg.get("ult_fast") or 7),
        int(bc04_cfg.get("ult_mid") or 14),
        int(bc04_cfg.get("ult_slow") or 28),
    )
    tke = (stofk + rsi + mfi + cci_norm + willr_norm + mo_norm + ult) / 7.0

    tke_prev = tke
    if len(closes) >= min_required + 1:
        prev_stofk = _compute_stofk(highs[:-1], lows[:-1], closes[:-1], int(bc04_cfg.get("stofk_k_period") or 14))
        prev_rsi = _compute_rsi(closes[:-1], int(bc04_cfg.get("rsi_period") or 14))
        prev_mfi = _compute_mfi(highs[:-1], lows[:-1], closes[:-1], volumes[:-1], int(bc04_cfg.get("mfi_period") or 14))
        prev_cci = _compute_cci(highs[:-1], lows[:-1], closes[:-1], int(bc04_cfg.get("cci_period") or 14))
        prev_cci_norm = _clamp((prev_cci + 200.0) / 4.0, 0.0, 100.0)
        prev_willr = _compute_willr(highs[:-1], lows[:-1], closes[:-1], int(bc04_cfg.get("willr_period") or 14))
        prev_willr_norm = _clamp(prev_willr + 100.0, 0.0, 100.0)
        prev_mo_abs = closes[-2] - closes[-mo_period - 2] if len(closes) > mo_period + 2 else 0.0
        prev_mo_base = abs(closes[-mo_period - 2]) if len(closes) > mo_period + 2 else max(abs(closes[-2]), 1.0)
        prev_mo_norm = _clamp(50.0 + (((prev_mo_abs / prev_mo_base) * 100.0) * 5.0), 0.0, 100.0)
        prev_ult = _compute_ultimate_oscillator(
            highs[:-1],
            lows[:-1],
            closes[:-1],
            int(bc04_cfg.get("ult_fast") or 7),
            int(bc04_cfg.get("ult_mid") or 14),
            int(bc04_cfg.get("ult_slow") or 28),
        )
        tke_prev = (prev_stofk + prev_rsi + prev_mfi + prev_cci_norm + prev_willr_norm + prev_mo_norm + prev_ult) / 7.0

    tke_threshold = float(bc04_cfg.get("tke_threshold") or 79.0)
    tke_short_threshold = 100.0 - tke_threshold
    bc04_long = bool(tke_prev <= tke_threshold and tke > tke_threshold)
    bc04_short = bool(tke_prev >= tke_short_threshold and tke < tke_short_threshold)

    avg_volume20 = _sma(volumes, 20)
    volume_latest = volumes[-1]
    volume_ratio = (volume_latest / avg_volume20) if avg_volume20 > 0 else 0.0
    momentum_window = closes[-7] if len(closes) >= 7 else closes[0]
    momentum_pct = ((close_latest - momentum_window) / momentum_window * 100.0) if momentum_window else 0.0
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)

    long_layers: list[str] = []
    short_layers: list[str] = []

    if bc02_long:
        long_layers.append("TREND")
    if bc02_short:
        short_layers.append("TREND")

    if bc03_long:
        long_layers.append("VOLUME")
    if bc03_short:
        short_layers.append("VOLUME")

    if bc03_long or bc04_long:
        long_layers.append("MOMENTUM")
    if bc03_short or bc04_short:
        short_layers.append("MOMENTUM")

    if bc01_long:
        long_layers.append("BOLLINGER")
    if bc01_short:
        short_layers.append("BOLLINGER")

    long_score = (
        (trend_w if "TREND" in long_layers else 0)
        + (volume_w if "VOLUME" in long_layers else 0)
        + (momentum_w if "MOMENTUM" in long_layers else 0)
        + (bollinger_w if "BOLLINGER" in long_layers else 0)
    )
    short_score = (
        (trend_w if "TREND" in short_layers else 0)
        + (volume_w if "VOLUME" in short_layers else 0)
        + (momentum_w if "MOMENTUM" in short_layers else 0)
        + (bollinger_w if "BOLLINGER" in short_layers else 0)
    )

    is_strong_long = "MOMENTUM" in long_layers and "VOLUME" in long_layers
    is_strong_short = "MOMENTUM" in short_layers and "VOLUME" in short_layers
    if is_strong_long and not is_strong_short:
        classification = "strong_long"
    elif is_strong_short and not is_strong_long:
        classification = "strong_short"
    elif long_score >= short_score:
        classification = "long_bias"
    else:
        classification = "short_bias"

    return {
        "long_score": int(long_score),
        "short_score": int(short_score),
        "long_layers": long_layers,
        "short_layers": short_layers,
        "classification": classification,
        "is_strong_long": is_strong_long,
        "is_strong_short": is_strong_short,
        "metrics": {
            "close": close_latest,
            "sma20": sma20,
            "sma50": sma50,
            "volume_ratio": volume_ratio,
            "rsi14": rsi,
            "momentum_pct": momentum_pct,
            "bollinger_lower": lower_now,
            "bollinger_upper": upper_now,
            "tke": tke,
        },
        "decisions": {
            "bc01": {
                "label": "KARAR1 (BC01)",
                "long": bc01_long,
                "short": bc01_short,
                "values": {
                    "X1": upper_now,
                    "C": close_latest,
                    "REF_C": close_prev,
                    "REF_X1": upper_prev,
                    "ema_period": bc01_period,
                    "stddev_multiplier": bc01_std_mult,
                },
            },
            "bc02": {
                "label": "KARAR2 (BC02)",
                "long": bc02_long,
                "short": bc02_short,
                "values": {
                    "Y1": y1,
                    "Y2": y2,
                    "Y2Y": y2y,
                    "Y3": y3,
                },
            },
            "bc03": {
                "label": "KARAR3 (BC03)",
                "long": bc03_long,
                "short": bc03_short,
                "values": {
                    "Z1": z1,
                    "Z1v": z1v,
                    "Z2": z2,
                    "Z2v": z2v,
                    "Z3": z3,
                    "Z3v": z3v,
                    "Z4": z4,
                    "HLF": hlf,
                    "HHV_H": hhv_h,
                },
            },
            "bc04": {
                "label": "KARAR4 (BC04)",
                "long": bc04_long,
                "short": bc04_short,
                "values": {
                    "STOFK": stofk,
                    "RSI": rsi,
                    "MFI": mfi,
                    "CCI": cci,
                    "WILLR": willr,
                    "MO": momentum_abs,
                    "ULT": ult,
                    "TKE": tke,
                    "TKE_PREV": tke_prev,
                    "threshold": tke_threshold,
                },
            },
        },
        "breakdown": {
            "long": f"[{','.join(long_layers) if long_layers else 'NONE'}] L:{long_score}",
            "short": f"[{','.join(short_layers) if short_layers else 'NONE'}] S:{short_score}",
        },
    }


def _score_sort_key(item: dict) -> tuple:
    classification = str(item.get("classification") or "")
    strong_bucket = 0 if classification in {"strong_long", "strong_short"} else 1
    max_score = max(int(item.get("long_score") or 0), int(item.get("short_score") or 0))
    return (
        strong_bucket,
        -max_score,
        -int(item.get("long_score") or 0),
        -int(item.get("short_score") or 0),
        str(item.get("symbol") or ""),
        str(item.get("market_type") or ""),
    )


def _score_candidate_symbol(candidate: dict, config: dict, force_refresh: bool) -> dict | None:
    symbol = str(candidate.get("symbol") or "").upper().strip()
    market_type = str(candidate.get("market_type") or "spot").lower().strip()
    if not symbol or market_type not in {"spot", "futures"}:
        return None

    decision_boxes = _sanitize_decision_boxes(config.get("decision_boxes") or {})
    bc02 = decision_boxes.get("bc02") or {}
    bc03 = decision_boxes.get("bc03") or {}
    bc04 = decision_boxes.get("bc04") or {}
    min_indicator_bars = max(
        int(bc02.get("y2_period") or 210) + 8,
        int(bc03.get("z1_ma_period") or 21) + int(bc03.get("z1_ref_bars") or 3) + 8,
        int(bc04.get("ult_slow") or 28) + 8,
        220,
    )

    candles = scanner_market_data_provider.fetch_indicator_and_execution_candles(
        exchange="binance",
        market_type=market_type,
        symbol=symbol,
        indicator_timeframe=str(config.get("indicator_timeframe") or "1h"),
        execution_timeframe=str(config.get("execution_timeframe") or "15m"),
        indicator_limit=min(400, max(220, min_indicator_bars)),
        execution_limit=140,
        force_refresh=force_refresh,
    )
    indicator_candles = list((candles.get("indicator") or {}).get("candles") or [])
    execution_candles = list((candles.get("execution") or {}).get("candles") or [])
    scoring = _evaluate_scanner_layers(
        indicator_candles,
        config.get("weights") or {},
        config.get("decision_boxes") or {},
    )

    execution_close = _to_float(execution_candles[-1].get("close")) if execution_candles else None
    execution_prev = _to_float(execution_candles[-2].get("close")) if len(execution_candles) >= 2 else None
    execution_change_pct = None
    if execution_close is not None and execution_prev and execution_prev != 0:
        execution_change_pct = ((execution_close - execution_prev) / execution_prev) * 100.0

    return {
        "symbol": symbol,
        "market_type": market_type,
        "long_score": scoring["long_score"],
        "short_score": scoring["short_score"],
        "long_layers": scoring["long_layers"],
        "short_layers": scoring["short_layers"],
        "classification": scoring["classification"],
        "is_strong_long": scoring["is_strong_long"],
        "is_strong_short": scoring["is_strong_short"],
        "breakdown": scoring["breakdown"],
        "decisions": scoring.get("decisions") or {},
        "indicator_metrics": scoring["metrics"],
        "execution_context": {
            "timeframe": str(config.get("execution_timeframe") or "15m"),
            "last_close": execution_close,
            "change_pct": execution_change_pct,
            "last_candle_time": (candles.get("execution") or {}).get("last_candle_time"),
        },
        "volume_24h": _to_float(candidate.get("volume_24h")),
        "spread_pct_24h": _to_float(candidate.get("spread_pct_24h"), default=0.0),
    }


def _run_scanner_engine(
    config: dict,
    *,
    force_refresh: bool = False,
    batch_size: int | None = None,
    progress_callback: Callable[[dict], None] | None = None,
) -> dict:
    universe = scanner_market_data_provider.get_tradable_symbols_parallel(
        exchange="binance",
        include_spot=bool(config.get("include_spot", True)),
        include_futures=bool(config.get("include_futures", True)),
        force_refresh=force_refresh,
    )

    rows = [item for item in (universe.get("rows") or []) if str(item.get("symbol") or "").strip()]

    market_scope = _sanitize_market_scope(config.get("market_scope") or {})
    spot_mode = str(market_scope.get("spot_mode") or "top50")
    futures_mode = str(market_scope.get("futures_mode") or "top50")

    spot_rows = [item for item in rows if str(item.get("market_type") or "") == "spot"]
    futures_rows = [item for item in rows if str(item.get("market_type") or "") == "futures"]
    spot_rows.sort(key=lambda item: _to_float(item.get("volume_24h")), reverse=True)
    futures_rows.sort(key=lambda item: _to_float(item.get("volume_24h")), reverse=True)

    scoped_rows: list[dict] = []
    manual_symbols = set(_normalize_symbols(config.get("manual_symbols") or []))

    if bool(config.get("include_spot", True)):
        scoped_rows.extend(_apply_market_mode(spot_rows, mode=spot_mode, manual_symbols=manual_symbols))
    if bool(config.get("include_futures", True)):
        scoped_rows.extend(_apply_market_mode(futures_rows, mode=futures_mode, manual_symbols=manual_symbols))

    rows = scoped_rows

    if str(config.get("signal_mode") or "manual") == "manual" and manual_symbols:
        rows = [item for item in rows if str(item.get("symbol") or "").upper() in manual_symbols]

    rows.sort(key=lambda item: _to_float(item.get("volume_24h")), reverse=True)

    scan_limit = max(1, min(int(config.get("scan_limit") or SCANNER_ENGINE_DEFAULT_SCAN_LIMIT), 5000))
    candidates = rows[:scan_limit]

    scored: list[dict] = []
    errors: list[dict] = []
    resolved_batch_size = max(1, min(int(batch_size or 25), 200))
    total_batches = int(math.ceil(len(candidates) / resolved_batch_size)) if candidates else 0

    if candidates:
        for batch_index in range(total_batches):
            batch_start = batch_index * resolved_batch_size
            batch_end = min(len(candidates), batch_start + resolved_batch_size)
            batch_rows = candidates[batch_start:batch_end]

            for candidate in batch_rows:
                try:
                    scored_item = _score_candidate_symbol(candidate, config, force_refresh)
                    if scored_item:
                        scored.append(scored_item)
                except Exception as exc:
                    errors.append(
                        {
                            "symbol": candidate.get("symbol"),
                            "market_type": candidate.get("market_type"),
                            "error": str(exc)[:320],
                        }
                    )

            if progress_callback is not None:
                progress_callback(
                    {
                        "current_batch": batch_index + 1,
                        "total_batches": total_batches,
                        "processed_symbols": batch_end,
                        "scored_count": len(scored),
                        "error_count": len(errors),
                    }
                )

    scored.sort(key=_score_sort_key)
    run_id = str(uuid.uuid4())
    generated_at = datetime.now(timezone.utc).isoformat()
    top_n = max(1, min(int(config.get("top_n") or 20), 150))

    strong_long_count = len([item for item in scored if item.get("classification") == "strong_long"])
    strong_short_count = len([item for item in scored if item.get("classification") == "strong_short"])
    long_signal_count = len([item for item in scored if int(item.get("long_score") or 0) >= 100])
    short_signal_count = len([item for item in scored if int(item.get("short_score") or 0) >= 100])

    payload = {
        "run_id": run_id,
        "generated_at": generated_at,
        "config": config,
        "summary": {
            "exchange": "binance",
            "indicator_timeframe": str(config.get("indicator_timeframe") or "1h"),
            "execution_timeframe": str(config.get("execution_timeframe") or "15m"),
            "market_selection": {
                "spot": bool(config.get("include_spot", True)),
                "futures": bool(config.get("include_futures", True)),
                "spot_mode": spot_mode,
                "futures_mode": futures_mode,
            },
            "candidate_count": len(candidates),
            "scored_count": len(scored),
            "error_count": len(errors),
            "scan_limit": scan_limit,
            "batch_size": resolved_batch_size,
            "total_batches": total_batches,
            "strong_long_count": strong_long_count,
            "strong_short_count": strong_short_count,
            "long_signal_count": long_signal_count,
            "short_signal_count": short_signal_count,
            "top_n": top_n,
            "max_score": int((config.get("weights") or {}).get("max_score") or 161),
        },
        "top_results": scored[:top_n],
        "results": scored,
        "errors": errors,
    }
    _write_json_value(SCANNER_ENGINE_LAST_RUN_KEY, payload)
    _write_json_value(f"{SCANNER_ENGINE_LAST_RUN_KEY}:{run_id}", payload)
    if hasattr(redis_client, "expire"):
        redis_client.expire(f"{SCANNER_ENGINE_LAST_RUN_KEY}:{run_id}", 60 * 60 * 12)
    return payload


def _dedupe_best_by_symbol(items: list[dict]) -> list[dict]:
    bucket: dict[str, dict] = {}
    for item in items:
        symbol = str(item.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        current = bucket.get(symbol)
        if current is None or _score_sort_key(item) < _score_sort_key(current):
            bucket[symbol] = item
    rows = list(bucket.values())
    rows.sort(key=_score_sort_key)
    return rows


def _build_scanner_job_entries(*, latest_run: dict, payload: ScannerEngineStartBotRequest) -> list[dict]:
    results = list(latest_run.get("results") or [])
    side_filter = str(payload.side_filter or "all")
    if side_filter == "long":
        results = [item for item in results if int(item.get("long_score") or 0) >= int(item.get("short_score") or 0)]
    elif side_filter == "short":
        results = [item for item in results if int(item.get("short_score") or 0) > int(item.get("long_score") or 0)]
    elif side_filter == "strong_long":
        results = [item for item in results if item.get("classification") == "strong_long"]
    elif side_filter == "strong_short":
        results = [item for item in results if item.get("classification") == "strong_short"]

    if payload.selection_mode == "manual":
        selected = set(_normalize_symbols(payload.selected_symbols or []))
        results = [item for item in results if str(item.get("symbol") or "").upper() in selected]
    else:
        results = results[: max(1, payload.top_n)]

    return _dedupe_best_by_symbol(results)


def _save_scanner_job(job_payload: dict):
    job_id = str(job_payload.get("job_id") or "")
    if not job_id:
        return
    _write_json_value(f"{SCANNER_ENGINE_BOT_JOB_KEY_PREFIX}:{job_id}", job_payload)
    queue_rows = _read_json_value(SCANNER_ENGINE_BOT_JOB_QUEUE_KEY, [])
    if not isinstance(queue_rows, list):
        queue_rows = []
    queue_rows.append(job_id)
    _write_json_value(SCANNER_ENGINE_BOT_JOB_QUEUE_KEY, queue_rows[-500:])


def _list_scanner_jobs(limit: int = 30) -> list[dict]:
    queue_rows = _read_json_value(SCANNER_ENGINE_BOT_JOB_QUEUE_KEY, [])
    if not isinstance(queue_rows, list):
        return []
    items: list[dict] = []
    for job_id in reversed(queue_rows[-max(1, limit):]):
        payload = _read_json_value(f"{SCANNER_ENGINE_BOT_JOB_KEY_PREFIX}:{job_id}", None)
        if isinstance(payload, dict):
            items.append(payload)
    return items


@router.get("")
def admin_universe_monitor_summary(
    market_type: str = Query(default="spot", pattern="^(spot|futures)$"),
    scanner_mode: str = Query(default="ALL_MARKET_SYMBOLS"),
    top_n: int = Query(default=200, ge=1, le=1000),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    debug_payload = debug_effective_universe(
        db,
        redis_client,
        market_type=market_type,
        scanner_mode=scanner_mode,
        selected_symbols=[],
        top_n=top_n,
    )

    recent_rows = (
        db.query(UserScannerResult)
        .order_by(UserScannerResult.generated_at.desc())
        .limit(2000)
        .all()
    )

    permission_codes = {
        "symbol_not_allowed",
        "symbol_permission_block",
        "symbol_not_allowed_by_whitelist",
        "symbol_not_allowed_by_live_config",
    }
    risk_codes = {
        "risk_limit_blocked",
        "max_positions_reached",
        "position_limit_reached",
        "risk_blocked",
    }
    liquidity_codes = {
        "liquidity_volume_low",
        "liquidity_spread_high",
        "data_unavailable",
    }

    blocked_by_permission = 0
    blocked_by_risk = 0
    blocked_by_liquidity = 0
    scanned_symbols = set()
    for row in recent_rows:
        symbol = str(row.symbol or "").upper().strip()
        if symbol:
            scanned_symbols.add(symbol)
        reasons = _reason_set(row)
        if reasons.intersection(permission_codes):
            blocked_by_permission += 1
        if reasons.intersection(risk_codes):
            blocked_by_risk += 1
        if reasons.intersection(liquidity_codes):
            blocked_by_liquidity += 1

    queue_state = get_json(redis_client, "scanner:queue:state") or {}
    perf_state = get_json(redis_client, "scanner:perf:latest:global") or {}
    fallback_state = get_fallback_state(redis_client)
    scanner_runtime = _scanner_runtime_state()

    return {
        "market_type": market_type,
        "scanner_mode": debug_payload.get("scanner_mode"),
        "total_exchange_symbols": debug_payload.get("market_symbols_count", 0),
        "active_scan_symbols": debug_payload.get("after_scanner_mode", 0),
        "total_scanned_symbols": int(perf_state.get("total_active_symbols") or debug_payload.get("after_scanner_mode", 0)),
        "symbols_evaluated_this_cycle": int(perf_state.get("symbols_evaluated") or 0),
        "average_cycle_latency_ms": float(perf_state.get("cycle_duration_ms") or queue_state.get("cycle_latency_ms") or 0),
        "avg_symbol_eval_ms": float(perf_state.get("avg_symbol_eval_ms") or 0),
        "snapshot_age_avg_sec": perf_state.get("snapshot_age_avg_sec"),
        "queue_depth": int(queue_state.get("depth") or 0),
        "blocked_by_permission": blocked_by_permission,
        "blocked_by_risk": blocked_by_risk,
        "blocked_by_liquidity": blocked_by_liquidity,
        "stale_blocks": int(queue_state.get("stale_blocks") or perf_state.get("stale_block_count") or 0),
        "dropped_evaluations": int(queue_state.get("dropped_jobs") or 0) + int(perf_state.get("dropped_symbol_count") or 0),
        "worker_utilization": float(queue_state.get("worker_utilization") or 0),
        "fallback_active": bool(fallback_state.get("active", False)),
        "fallback_healthy_streak": int(fallback_state.get("healthy_streak", 0)),
        "fallback_last_trigger_metric": fallback_state.get("last_trigger_metric"),
        "fallback_last_exit_reason": fallback_state.get("last_exit_reason"),
        "top_slow_strategies": list(perf_state.get("top_slow_strategies") or []),
        "top_slow_symbols": list(perf_state.get("top_slow_symbols") or []),
        "recent_scanned_symbols": len(scanned_symbols),
        "final_symbols": debug_payload.get("final_symbols", []),
        "scanner_runtime": scanner_runtime,
        "generated_at": datetime.now(timezone.utc),
    }


@router.get("/scanner/state")
def scanner_state(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    row = _load_admin_control(db)
    universe_payload = _read_json_value("control_layer:scanner_symbol_universe", {"symbols": []})
    manual_trigger = _read_json_value("control_layer:scanner_manual_trigger", {})
    return {
        "runtime": _scanner_runtime_state(),
        "manual_trigger": manual_trigger,
        "symbol_universe": _normalize_symbols(universe_payload.get("symbols") or []),
        "whitelist": _normalize_symbols(row.whitelist or []),
        "blacklist": _normalize_symbols(row.blacklist or []),
    }


@router.get("/scanner-engine/config")
def scanner_engine_get_config(current_admin: User = Depends(require_admin)):
    _super_admin_required(current_admin)
    return _load_scanner_engine_config()


@router.post("/scanner-engine/config/save", dependencies=[Depends(_admin_scanner_action_removed_dependency)])
def scanner_engine_save_config(payload: ScannerEngineConfigSaveRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _raise_admin_scanner_action_moved_to_user("scanner_engine_config_save")
    manager = _super_admin_required(current_admin)
    if not payload.include_spot and not payload.include_futures:
        raise HTTPException(status_code=400, detail="spot_or_futures_required")

    trace_id = str(uuid.uuid4())
    previous_config = _load_scanner_engine_config()
    merged_decision_boxes = payload.decision_boxes if payload.decision_boxes else (previous_config.get("decision_boxes") or {})
    merged_market_scope = payload.market_scope if payload.market_scope else (previous_config.get("market_scope") or {})
    config = {
        **previous_config,
        "exchange": "binance",
        "include_spot": bool(payload.include_spot),
        "include_futures": bool(payload.include_futures),
        "market_scope": _sanitize_market_scope(merged_market_scope),
        "signal_mode": payload.signal_mode,
        "auto_interval_minutes": int(payload.auto_interval_minutes) if int(payload.auto_interval_minutes) in {1, 3, 5} else 3,
        "scan_limit": int(payload.scan_limit),
        "top_n": int(payload.top_n),
        "manual_symbols": _normalize_symbols(payload.manual_symbols or []),
        "weights": {
            "trend": int(payload.trend_weight),
            "volume": int(payload.volume_weight),
            "momentum": int(payload.momentum_weight),
            "bollinger": int(payload.bollinger_weight),
            "max_score": int(payload.trend_weight + payload.volume_weight + payload.momentum_weight + payload.bollinger_weight),
        },
        "decision_boxes": _sanitize_decision_boxes(merged_decision_boxes),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": manager.id,
    }
    _save_scanner_engine_config(config)

    audit = create_audit_log(
        db,
        action="UNIVERSE_SCANNER_ENGINE_CONFIG_SAVED",
        entity_type="scanner_engine",
        entity_id="global",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason, "config": config},
    )
    return _action_result(
        trace_id=trace_id,
        message="scanner engine config saved",
        state_snapshot={"scanner_engine_config": config},
        config=config,
        audit_log_id=audit.id,
    )


@router.post("/scanner-engine/run", dependencies=[Depends(_admin_scanner_action_removed_dependency)])
def scanner_engine_run(payload: ScannerEngineRunRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _raise_admin_scanner_action_moved_to_user("scanner_engine_run")
    manager = _super_admin_required(current_admin)
    trace_id = str(uuid.uuid4())
    config = _load_scanner_engine_config()
    try:
        run_payload = _run_scanner_engine(config, force_refresh=bool(payload.force_refresh))
    except MarketDataProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"scanner_engine_run_failed: {str(exc)[:240]}") from exc

    audit = create_audit_log(
        db,
        action="UNIVERSE_SCANNER_ENGINE_RUN",
        entity_type="scanner_engine",
        entity_id=str(run_payload.get("run_id") or "unknown"),
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="info",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "summary": run_payload.get("summary") or {},
            "error_count": len(run_payload.get("errors") or []),
        },
    )
    return {
        "status": "success",
        "trace_id": trace_id,
        "run_id": run_payload.get("run_id"),
        "generated_at": run_payload.get("generated_at"),
        "config": run_payload.get("config") or {},
        "summary": run_payload.get("summary") or {},
        "top_results": run_payload.get("top_results") or [],
        "results": run_payload.get("results") or [],
        "errors": run_payload.get("errors") or [],
        "audit_log_id": audit.id,
    }


@router.post("/scanner-engine/analyze", dependencies=[Depends(_admin_scanner_action_removed_dependency)])
def scanner_engine_analyze(payload: ScannerEngineRunRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _raise_admin_scanner_action_moved_to_user("scanner_engine_analyze")
    return scanner_engine_run(payload=payload, current_admin=current_admin, db=db)


@router.get("/scanner-engine/last-run")
def scanner_engine_last_run(current_admin: User = Depends(require_admin)):
    _super_admin_required(current_admin)
    payload = _read_json_value(SCANNER_ENGINE_LAST_RUN_KEY, {})
    if not isinstance(payload, dict) or not payload.get("run_id"):
        return {
            "status": "empty",
            "config": _load_scanner_engine_config(),
            "summary": {
                "exchange": "binance",
                "indicator_timeframe": "1h",
                "execution_timeframe": "15m",
                "candidate_count": 0,
                "scored_count": 0,
                "error_count": 0,
                "strong_long_count": 0,
                "strong_short_count": 0,
                "top_n": int(_load_scanner_engine_config().get("top_n") or 20),
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
        "config": payload.get("config") or _load_scanner_engine_config(),
        "summary": payload.get("summary") or {},
        "top_results": payload.get("top_results") or [],
        "results": payload.get("results") or [],
        "errors": payload.get("errors") or [],
    }


@router.post("/scanner-engine/bot/start", dependencies=[Depends(_admin_scanner_action_removed_dependency)])
def scanner_engine_bot_start(payload: ScannerEngineStartBotRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _raise_admin_scanner_action_moved_to_user("scanner_engine_bot_start")
    manager = _super_admin_required(current_admin)
    trace_id = str(uuid.uuid4())
    latest_run = _read_json_value(SCANNER_ENGINE_LAST_RUN_KEY, {})
    if not isinstance(latest_run, dict) or not latest_run.get("run_id"):
        raise HTTPException(status_code=409, detail="scanner_engine_run_required")

    selected_entries = _build_scanner_job_entries(latest_run=latest_run, payload=payload)
    if not selected_entries:
        raise HTTPException(status_code=400, detail="scanner_engine_no_symbols_selected")

    job_id = str(uuid.uuid4())
    job_payload = {
        "job_id": job_id,
        "trace_id": trace_id,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": manager.id,
        "source": "scanner_engine",
        "source_run_id": latest_run.get("run_id"),
        "selection_mode": payload.selection_mode,
        "side_filter": payload.side_filter,
        "symbol_count": len(selected_entries),
        "symbols": [item.get("symbol") for item in selected_entries],
        "entries": selected_entries,
        "execution_timeframe": str((latest_run.get("summary") or {}).get("execution_timeframe") or "15m"),
        "reason": payload.reason,
    }
    _save_scanner_job(job_payload)

    audit = create_audit_log(
        db,
        action="UNIVERSE_SCANNER_ENGINE_BOT_JOB_CREATED",
        entity_type="scanner_engine_job",
        entity_id=job_id,
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "selection_mode": payload.selection_mode,
            "side_filter": payload.side_filter,
            "symbol_count": len(selected_entries),
            "source_run_id": latest_run.get("run_id"),
        },
    )
    return _action_result(
        trace_id=trace_id,
        message="scanner bot job queued",
        state_snapshot={"job_id": job_id, "symbol_count": len(selected_entries), "selection_mode": payload.selection_mode},
        job=job_payload,
        audit_log_id=audit.id,
    )


@router.get("/scanner-engine/bot/jobs", response_model=ScannerEngineJobListResponse)
def scanner_engine_bot_jobs(limit: int = Query(default=30, ge=1, le=200), current_admin: User = Depends(require_admin)):
    _super_admin_required(current_admin)
    jobs = _list_scanner_jobs(limit=limit)
    return {"count": len(jobs), "items": jobs}


@router.post("/scanner/start", dependencies=[Depends(_admin_scanner_action_removed_dependency)])
def scanner_start(payload: RuntimeActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _raise_admin_scanner_action_moved_to_user("scanner_start")
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, SCANNER_START_PHRASE)

    trace_id = str(uuid.uuid4())
    runtime = _scanner_runtime_state()
    runtime.update(
        {
            "running": True,
            "last_started_at": datetime.now(timezone.utc).isoformat(),
            "last_action_by": manager.id,
            "last_action_reason": payload.reason,
        }
    )
    _write_json_value(SCANNER_RUNTIME_STATE_KEY, runtime)
    _write_json_value("pipeline:scanner:health", {"status": "running", "updated_at": datetime.now(timezone.utc).isoformat()})

    audit = create_audit_log(
        db,
        action="UNIVERSE_SCANNER_START",
        entity_type="scanner",
        entity_id="global",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason, "runtime": runtime},
    )
    return _action_result(
        trace_id=trace_id,
        message="scanner started",
        state_snapshot={"scanner_runtime": runtime},
        audit_log_id=audit.id,
    )


@router.post("/scanner/stop", dependencies=[Depends(_admin_scanner_action_removed_dependency)])
def scanner_stop(payload: RuntimeActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _raise_admin_scanner_action_moved_to_user("scanner_stop")
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, SCANNER_STOP_PHRASE)

    trace_id = str(uuid.uuid4())
    runtime = _scanner_runtime_state()
    runtime.update(
        {
            "running": False,
            "last_stopped_at": datetime.now(timezone.utc).isoformat(),
            "last_action_by": manager.id,
            "last_action_reason": payload.reason,
        }
    )
    _write_json_value(SCANNER_RUNTIME_STATE_KEY, runtime)
    _write_json_value("pipeline:scanner:health", {"status": "stopped", "updated_at": datetime.now(timezone.utc).isoformat()})

    audit = create_audit_log(
        db,
        action="UNIVERSE_SCANNER_STOP",
        entity_type="scanner",
        entity_id="global",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason, "runtime": runtime},
    )
    return _action_result(
        trace_id=trace_id,
        message="scanner stopped",
        state_snapshot={"scanner_runtime": runtime},
        audit_log_id=audit.id,
    )


@router.post("/scanner/trigger", dependencies=[Depends(_admin_scanner_action_removed_dependency)])
def scanner_trigger(payload: ScannerTriggerRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _raise_admin_scanner_action_moved_to_user("scanner_trigger")
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, SCANNER_TRIGGER_PHRASE)

    trace_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    trigger = {
        "request_id": request_id,
        "requested_at": now,
        "requested_by": manager.id,
        "reason": payload.reason,
        "status": "queued",
    }
    queue_rows = _read_json_value("scanner:manual:queue", [])
    if not isinstance(queue_rows, list):
        queue_rows = []
    queue_rows.append(trigger)
    _write_json_value("scanner:manual:queue", queue_rows[-500:])
    _write_json_value("control_layer:scanner_manual_trigger", trigger)

    runtime = _scanner_runtime_state()
    runtime["last_manual_trigger_status"] = "queued"
    runtime["last_manual_trigger_request_id"] = request_id
    _write_json_value(SCANNER_RUNTIME_STATE_KEY, runtime)

    queue_depth = len(queue_rows)
    audit = create_audit_log(
        db,
        action="UNIVERSE_SCANNER_MANUAL_TRIGGER",
        entity_type="scanner",
        entity_id="manual_trigger",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="info",
        details={"trace_id": trace_id, **trigger, "queue_depth": queue_depth},
    )
    return _action_result(
        trace_id=trace_id,
        message="manual scan trigger queued",
        state_snapshot={"manual_trigger": trigger, "queue_depth": int(queue_depth)},
        queue_id=request_id,
        audit_log_id=audit.id,
    )


@router.get("/scanner/symbol-lists")
def scanner_symbol_lists(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    row = _load_admin_control(db)
    return {
        "whitelist": _normalize_symbols(row.whitelist or []),
        "blacklist": _normalize_symbols(row.blacklist or []),
    }


@router.post("/scanner/symbol-lists/{list_type}")
def scanner_update_symbol_list(
    list_type: str = FastAPIPath(pattern="^(whitelist|blacklist)$"),
    payload: ScannerSymbolListUpdateRequest = Body(...),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, SCANNER_SYMBOL_LIST_PHRASE)

    trace_id = str(uuid.uuid4())
    row = _load_admin_control(db)
    incoming = _normalize_symbols(payload.symbols)
    base = set(_normalize_symbols((row.whitelist if list_type == "whitelist" else row.blacklist) or []))

    if payload.action == "add":
        base.update(incoming)
    elif payload.action == "remove":
        base.difference_update(incoming)
    else:
        base = set(incoming)

    updated = sorted(base)
    if list_type == "whitelist":
        row.whitelist = updated
    else:
        row.blacklist = updated
    db.commit()

    audit = create_audit_log(
        db,
        action="UNIVERSE_SCANNER_SYMBOL_LIST_UPDATED",
        entity_type="scanner_symbol_list",
        entity_id=list_type,
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "list_type": list_type, "action": payload.action, "symbols": incoming, "reason": payload.reason},
    )
    return _action_result(
        trace_id=trace_id,
        message=f"{list_type} updated",
        state_snapshot={"list_type": list_type, "items": updated},
        audit_log_id=audit.id,
    )


@router.post("/universe/symbol")
def universe_add_symbol(payload: ScannerSymbolRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, SCANNER_SYMBOL_LIST_PHRASE)

    trace_id = str(uuid.uuid4())
    universe_payload = _read_json_value("control_layer:scanner_symbol_universe", {"symbols": []})
    symbols = set(_normalize_symbols(universe_payload.get("symbols") or []))
    symbol = str(payload.symbol or "").upper().strip()
    symbols.add(symbol)
    updated = sorted(symbols)
    _write_json_value("control_layer:scanner_symbol_universe", {"symbols": updated})

    audit = create_audit_log(
        db,
        action="UNIVERSE_SYMBOL_ADDED",
        entity_type="universe",
        entity_id=symbol,
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason},
    )
    return _action_result(
        trace_id=trace_id,
        message="symbol added to universe",
        state_snapshot={"symbol_universe": updated},
        audit_log_id=audit.id,
    )


@router.delete("/universe/symbol")
def universe_delete_symbol(payload: ScannerSymbolRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, SCANNER_SYMBOL_LIST_PHRASE)

    trace_id = str(uuid.uuid4())
    universe_payload = _read_json_value("control_layer:scanner_symbol_universe", {"symbols": []})
    symbols = set(_normalize_symbols(universe_payload.get("symbols") or []))
    symbol = str(payload.symbol or "").upper().strip()
    symbols.discard(symbol)
    updated = sorted(symbols)
    _write_json_value("control_layer:scanner_symbol_universe", {"symbols": updated})

    audit = create_audit_log(
        db,
        action="UNIVERSE_SYMBOL_REMOVED",
        entity_type="universe",
        entity_id=symbol,
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason},
    )
    return _action_result(
        trace_id=trace_id,
        message="symbol removed from universe",
        state_snapshot={"symbol_universe": updated},
        audit_log_id=audit.id,
    )


@router.post("/universe/symbols/bulk-toggle")
def universe_bulk_toggle(payload: ScannerUniverseBulkRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, SCANNER_SYMBOL_BULK_PHRASE)

    trace_id = str(uuid.uuid4())
    universe_payload = _read_json_value("control_layer:scanner_symbol_universe", {"symbols": []})
    symbols = set(_normalize_symbols(universe_payload.get("symbols") or []))
    incoming = set(_normalize_symbols(payload.symbols))

    if payload.enabled:
        symbols.update(incoming)
    else:
        symbols.difference_update(incoming)

    updated = sorted(symbols)
    _write_json_value("control_layer:scanner_symbol_universe", {"symbols": updated})

    audit = create_audit_log(
        db,
        action="UNIVERSE_SYMBOL_BULK_TOGGLE",
        entity_type="universe",
        entity_id="bulk",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "enabled": payload.enabled,
            "symbols_count": len(incoming),
        },
    )
    return _action_result(
        trace_id=trace_id,
        message="bulk symbol toggle completed",
        state_snapshot={"enabled": payload.enabled, "symbols_count": len(incoming), "universe_size": len(updated)},
        audit_log_id=audit.id,
    )


@router.get("/universe/filter-config")
def universe_filter_config(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return _read_json_value(
        UNIVERSE_FILTER_CONFIG_KEY,
        {
            "min_liquidity_usd": 1_000_000,
            "min_volume_24h_usd": 5_000_000,
            "max_spread_bps": 40,
            "updated_at": None,
        },
    )


@router.put("/universe/filter-config")
def universe_update_filter_config(payload: UniverseFilterConfigRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, SCANNER_FILTER_CONFIG_PHRASE)

    trace_id = str(uuid.uuid4())
    config = {
        "min_liquidity_usd": float(payload.min_liquidity_usd),
        "min_volume_24h_usd": float(payload.min_volume_24h_usd),
        "max_spread_bps": float(payload.max_spread_bps),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": manager.id,
    }
    _write_json_value(UNIVERSE_FILTER_CONFIG_KEY, config)

    audit = create_audit_log(
        db,
        action="UNIVERSE_FILTER_CONFIG_UPDATED",
        entity_type="universe_filter",
        entity_id="global",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason, "config": config},
    )
    return _action_result(
        trace_id=trace_id,
        message="universe filter config updated",
        state_snapshot={"filter_config": config},
        audit_log_id=audit.id,
    )


@router.post("/export/job")
def create_export_job(
    payload: ExportJobRequest,
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, EXPORT_JOB_PHRASE)
    _ensure_export_job_table()

    trace_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    row = UniverseExportJob(
        job_id=job_id,
        trace_id=trace_id,
        status="pending",
        params={
            "range": payload.range,
            "metrics": payload.metrics,
            "symbol": payload.symbol,
            "strategy": payload.strategy,
        },
        result_format=payload.output_format,
        created_by=manager.id,
    )
    db.add(row)
    db.commit()

    audit = create_audit_log(
        db,
        action="UNIVERSE_EXPORT_JOB_CREATED",
        entity_type="export_job",
        entity_id=job_id,
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "params": row.params,
            "output_format": payload.output_format,
        },
    )
    background_tasks.add_task(_process_export_job_async, job_id=job_id)
    return _action_result(
        trace_id=trace_id,
        message="export job queued",
        state_snapshot={"job_id": job_id, "status": "pending", "output_format": payload.output_format},
        job_id=job_id,
        audit_log_id=audit.id,
    )


@router.get("/export/jobs")
def list_export_jobs(
    limit: int = Query(default=30, ge=1, le=200),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    _ensure_export_job_table()
    rows = db.query(UniverseExportJob).order_by(UniverseExportJob.created_at.desc()).limit(limit).all()
    return {
        "count": len(rows),
        "items": [
            {
                "job_id": row.job_id,
                "trace_id": row.trace_id,
                "status": row.status,
                "params": row.params or {},
                "result_url": row.result_url,
                "result_format": row.result_format,
                "result_row_count": row.result_row_count,
                "error_message": row.error_message,
                "created_by": row.created_by,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ],
    }


@router.get("/export/job/{job_id}")
def get_export_job(job_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    _ensure_export_job_table()
    row = db.query(UniverseExportJob).filter(UniverseExportJob.job_id == job_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="export_job_not_found")
    return {
        "job_id": row.job_id,
        "trace_id": row.trace_id,
        "status": row.status,
        "params": row.params or {},
        "result_url": row.result_url,
        "result_format": row.result_format,
        "result_row_count": row.result_row_count,
        "error_message": row.error_message,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/export/job/{job_id}/download")
def download_export_job(job_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    _ensure_export_job_table()
    row = db.query(UniverseExportJob).filter(UniverseExportJob.job_id == job_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="export_job_not_found")
    if row.status != "done":
        raise HTTPException(status_code=409, detail="export_job_not_ready")

    ext = "json" if str(row.result_format).lower() == "json" else "csv"
    file_path = EXPORT_STORAGE_DIR / f"{row.job_id}.{ext}"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="export_file_not_found")

    media_type = "application/json" if ext == "json" else "text/csv"
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=f"universe_export_{row.job_id}.{ext}",
    )


@router.post("/export/job/{job_id}/retry")
def retry_export_job(
    job_id: str,
    payload: RuntimeActionRequest,
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, EXPORT_JOB_PHRASE)
    _ensure_export_job_table()
    row = db.query(UniverseExportJob).filter(UniverseExportJob.job_id == job_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="export_job_not_found")

    row.status = "pending"
    row.error_message = None
    row.updated_at = datetime.now(timezone.utc)
    db.commit()

    audit = create_audit_log(
        db,
        action="UNIVERSE_EXPORT_JOB_RETRY",
        entity_type="export_job",
        entity_id=job_id,
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": row.trace_id, "reason": payload.reason},
    )
    background_tasks.add_task(_process_export_job_async, job_id=job_id)
    return _action_result(
        trace_id=row.trace_id,
        message="export job retried",
        state_snapshot={"job_id": job_id, "status": "pending"},
        audit_log_id=audit.id,
    )


@router.post("/universe/symbols/bulk-import/preview")
def universe_bulk_import_preview(payload: BulkImportPreviewRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, BULK_IMPORT_PREVIEW_PHRASE)

    trace_id = str(uuid.uuid4())
    symbols = _parse_bulk_csv_symbols(payload.csv_text)
    row = _load_admin_control(db)
    blacklist = set(_normalize_symbols(row.blacklist or []))
    preview = _build_bulk_preview(symbols=symbols, blacklist=blacklist)
    preview_id = str(uuid.uuid4())
    preview_payload = {
        "preview_id": preview_id,
        "trace_id": trace_id,
        "created_by": manager.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": payload.reason,
        **preview,
    }
    _write_json_value(f"{BULK_IMPORT_PREVIEW_KEY}:{preview_id}", preview_payload)

    audit = create_audit_log(
        db,
        action="UNIVERSE_BULK_IMPORT_PREVIEW",
        entity_type="universe_bulk_import",
        entity_id=preview_id,
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "total_input": preview_payload["total_input"],
            "valid_count": preview_payload["valid_count"],
            "invalid_count": preview_payload["invalid_count"],
            "reason_counts": preview_payload["reason_counts"],
        },
    )
    return _action_result(
        trace_id=trace_id,
        message="bulk import preview created",
        state_snapshot={
            "preview_id": preview_id,
            "total_input": preview_payload["total_input"],
            "valid_count": preview_payload["valid_count"],
            "invalid_count": preview_payload["invalid_count"],
        },
        preview=preview_payload,
        errors_csv_url=f"/api/admin/universe-monitor/universe/symbols/bulk-import/{preview_id}/errors.csv",
        audit_log_id=audit.id,
    )


@router.post("/universe/symbols/bulk-import/apply")
def universe_bulk_import_apply(payload: BulkImportApplyRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, BULK_IMPORT_APPLY_PHRASE)

    trace_id = str(uuid.uuid4())
    preview_payload = _read_json_value(f"{BULK_IMPORT_PREVIEW_KEY}:{payload.preview_id}", None)
    if not isinstance(preview_payload, dict):
        raise HTTPException(status_code=404, detail="bulk_import_preview_not_found")

    valid_symbols = _normalize_symbols(preview_payload.get("valid_symbols") or [])
    invalid_items = list(preview_payload.get("invalid_items") or [])
    universe_payload = _read_json_value("control_layer:scanner_symbol_universe", {"symbols": []})
    current_symbols = set(_normalize_symbols(universe_payload.get("symbols") or []))

    applied_symbols = []
    rejected_items = list(invalid_items)
    for symbol in valid_symbols:
        if symbol in current_symbols:
            rejected_items.append({"symbol": symbol, "reason": "already_exists"})
            continue
        current_symbols.add(symbol)
        applied_symbols.append(symbol)

    _write_json_value("control_layer:scanner_symbol_universe", {"symbols": sorted(current_symbols)})

    reason_counts: dict[str, int] = {}
    for item in rejected_items:
        reason = str(item.get("reason") or "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    summary = {
        "preview_id": payload.preview_id,
        "apply_mode": payload.apply_mode,
        "processed_count": len(valid_symbols) + len(invalid_items),
        "applied_count": len(applied_symbols),
        "rejected_count": len(rejected_items),
        "reason_counts": reason_counts,
    }
    preview_payload["last_apply_summary"] = summary
    preview_payload["last_rejected_items"] = rejected_items
    _write_json_value(f"{BULK_IMPORT_PREVIEW_KEY}:{payload.preview_id}", preview_payload)

    audit = create_audit_log(
        db,
        action="UNIVERSE_BULK_IMPORT_APPLY",
        entity_type="universe_bulk_import",
        entity_id=payload.preview_id,
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason, **summary},
    )
    return _action_result(
        trace_id=trace_id,
        message="bulk import applied",
        state_snapshot={"summary": summary, "universe_size": len(current_symbols)},
        summary=summary,
        rejected_items=rejected_items,
        errors_csv_url=f"/api/admin/universe-monitor/universe/symbols/bulk-import/{payload.preview_id}/errors.csv",
        audit_log_id=audit.id,
    )


@router.get("/universe/symbols/bulk-import/{preview_id}/errors.csv")
def universe_bulk_import_errors_csv(preview_id: str, current_admin: User = Depends(require_admin)):
    _ = current_admin
    preview_payload = _read_json_value(f"{BULK_IMPORT_PREVIEW_KEY}:{preview_id}", None)
    if not isinstance(preview_payload, dict):
        raise HTTPException(status_code=404, detail="bulk_import_preview_not_found")
    items = list(preview_payload.get("invalid_items") or [])
    items.extend(list(preview_payload.get("last_rejected_items") or []))

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["symbol", "reason"])
    writer.writeheader()
    for item in items:
        writer.writerow({"symbol": item.get("symbol"), "reason": item.get("reason")})

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=bulk_import_errors_{preview_id}.csv"},
    )


@router.get("/freshness/sla-config")
def freshness_sla_config(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return _get_sla_config()


@router.put("/freshness/sla-config")
def freshness_update_sla_config(payload: FreshnessSlaConfigRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, SLA_UPDATE_PHRASE)

    trace_id = str(uuid.uuid4())
    config = {
        "latency_threshold": float(payload.latency_threshold),
        "stale_threshold_sec": int(payload.stale_threshold_sec),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": manager.id,
    }
    _write_json_value(SLA_CONFIG_KEY, config)

    audit = create_audit_log(
        db,
        action="UNIVERSE_SLA_CONFIG_UPDATED",
        entity_type="freshness_sla",
        entity_id="global",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason, "config": config},
    )
    return _action_result(
        trace_id=trace_id,
        message="freshness sla config updated",
        state_snapshot={"sla_config": config},
        audit_log_id=audit.id,
    )


@router.get("/freshness/stale-list")
def freshness_stale_list(
    limit: int = Query(default=300, ge=1, le=2000),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    config = _get_sla_config()
    items = _derive_stale_entities(db, stale_threshold_sec=int(config.get("stale_threshold_sec") or 900), limit=limit)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sla_config": config,
        "count": len(items),
        "items": items,
        "reason_if_empty": "No stale entities detected in current window" if len(items) == 0 else None,
    }


@router.post("/scanner/rescan-stale", dependencies=[Depends(_admin_scanner_action_removed_dependency)])
def scanner_rescan_stale(payload: RescanStaleRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _raise_admin_scanner_action_moved_to_user("scanner_rescan_stale")
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, RESCAN_STALE_PHRASE)

    trace_id = str(uuid.uuid4())
    config = _get_sla_config()
    stale_items = _derive_stale_entities(db, stale_threshold_sec=int(config.get("stale_threshold_sec") or 900), limit=payload.limit)
    symbol_candidates = [item["entity_id"] for item in stale_items if item.get("entity_type") == "symbol"]
    request_id = str(uuid.uuid4())
    queue_entry = {
        "request_id": request_id,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "requested_by": manager.id,
        "reason": payload.reason,
        "status": "queued",
        "symbols": symbol_candidates,
        "source": "rescan_stale",
    }
    queue_rows = _read_json_value("scanner:manual:queue", [])
    if not isinstance(queue_rows, list):
        queue_rows = []
    queue_rows.append(queue_entry)
    _write_json_value("scanner:manual:queue", queue_rows[-500:])

    runtime = _scanner_runtime_state()
    runtime["last_manual_trigger_status"] = "queued"
    runtime["last_manual_trigger_request_id"] = request_id
    _write_json_value(SCANNER_RUNTIME_STATE_KEY, runtime)

    audit = create_audit_log(
        db,
        action="UNIVERSE_SCANNER_RESCAN_STALE",
        entity_type="scanner",
        entity_id="stale_rescan",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason, "stale_count": len(stale_items), "symbol_count": len(symbol_candidates), "queue_id": request_id},
    )
    return _action_result(
        trace_id=trace_id,
        message="stale entities queued for rescan",
        state_snapshot={"stale_count": len(stale_items), "symbol_rescan_count": len(symbol_candidates), "queue_id": request_id},
        queue_id=request_id,
        audit_log_id=audit.id,
    )


@router.post("/recommendation/generate")
def recommendation_generate(payload: RecommendationGenerateRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, KPI_GENERATE_PHRASE)

    trace_id = str(uuid.uuid4())
    config = _get_sla_config()
    stale_items = _derive_stale_entities(db, stale_threshold_sec=int(config.get("stale_threshold_sec") or 900), limit=300)
    queue_state = _read_json_value("scanner:queue:state", {})
    perf_latest = _read_json_value("scanner:perf:latest:global", {})
    latency = float(perf_latest.get("cycle_duration_ms") or queue_state.get("cycle_latency_ms") or 0)

    generated: list[dict] = []
    if latency > float(config.get("latency_threshold") or 1200):
        generated.append(
            {
                "id": str(uuid.uuid4()),
                "metric_source": "scanner_latency",
                "problem": f"Latency {latency:.2f}ms threshold üstünde",
                "recommendation": "Rollout stage demote veya universe bulk disable ile yükü azalt",
                "expected_impact": "latency düşüşü",
                "confidence_score": 0.82,
                "action_code": "rollout_demote",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
            }
        )
    if len(stale_items) > 0:
        generated.append(
            {
                "id": str(uuid.uuid4()),
                "metric_source": "stale_entities",
                "problem": f"{len(stale_items)} stale entity tespit edildi",
                "recommendation": "Rescan stale çalıştır ve stale thresholdu yeniden değerlendir",
                "expected_impact": "daha taze veri",
                "confidence_score": 0.88,
                "action_code": "rescan_stale",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
            }
        )
    queue_depth = int(queue_state.get("depth") or 0)
    if queue_depth > 500:
        generated.append(
            {
                "id": str(uuid.uuid4()),
                "metric_source": "queue_depth",
                "problem": f"Queue depth yüksek ({queue_depth})",
                "recommendation": "Slow strategy throttle uygula",
                "expected_impact": "drop rate azalır",
                "confidence_score": 0.75,
                "action_code": "strategy_throttle",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
            }
        )
    if not generated:
        generated.append(
            {
                "id": str(uuid.uuid4()),
                "metric_source": "monitoring",
                "problem": "Kritik anomaly tespit edilmedi",
                "recommendation": "SLA değerlerini haftalık trend ile optimize et",
                "expected_impact": "stabil operasyon",
                "confidence_score": 0.6,
                "action_code": "optimize_sla",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
            }
        )

    active = _kpi_active_recommendations()
    existing_problems = {str(item.get("problem")) for item in active}
    for rec in generated:
        if rec["problem"] in existing_problems:
            continue
        active.append(rec)
    _write_json_value(KPI_RECOMMENDATION_ACTIVE_KEY, active[-200:])

    audit = create_audit_log(
        db,
        action="UNIVERSE_RECOMMENDATION_GENERATED",
        entity_type="kpi_recommendation",
        entity_id="batch",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="info",
        details={"trace_id": trace_id, "reason": payload.reason, "generated_count": len(generated)},
    )
    return _action_result(
        trace_id=trace_id,
        message="recommendations generated",
        state_snapshot={"generated_count": len(generated), "active_count": len(active)},
        items=generated,
        audit_log_id=audit.id,
    )


@router.get("/recommendation/active")
def recommendation_active(current_admin: User = Depends(require_admin)):
    _ = current_admin
    rows = _kpi_active_recommendations()
    return {"count": len(rows), "items": rows}


@router.get("/recommendation/history")
def recommendation_history(current_admin: User = Depends(require_admin)):
    _ = current_admin
    rows = _kpi_history()
    return {"count": len(rows), "items": rows[-300:]}


def _recommendation_decision(*, decision: str, phrase: str, expected_phrase: str, payload: RecommendationDecisionRequest, current_admin: User, db: Session):
    manager = _manager_required(current_admin)
    _require_phrase(phrase, expected_phrase)
    trace_id = str(uuid.uuid4())

    active = _kpi_active_recommendations()
    target = None
    remaining = []
    for item in active:
        if str(item.get("id")) == payload.recommendation_id:
            target = item
            continue
        remaining.append(item)
    if target is None:
        raise HTTPException(status_code=404, detail="recommendation_not_found")

    effect = {}
    if decision == "apply":
        action_code = target.get("action_code")
        if action_code == "rescan_stale":
            stale = _derive_stale_entities(db, stale_threshold_sec=int(_get_sla_config().get("stale_threshold_sec") or 900), limit=100)
            effect = {"rescan_candidate_count": len([item for item in stale if item.get("entity_type") == "symbol"])}
        elif action_code == "optimize_sla":
            cfg = _get_sla_config()
            cfg["latency_threshold"] = float(cfg.get("latency_threshold") or 1200) * 1.1
            cfg["updated_at"] = datetime.now(timezone.utc).isoformat()
            cfg["updated_by"] = manager.id
            _write_json_value(SLA_CONFIG_KEY, cfg)
            effect = {"sla_config": cfg}
        else:
            effect = {"applied_action_code": action_code}

    target["status"] = decision
    target["decided_at"] = datetime.now(timezone.utc).isoformat()
    target["decided_by"] = manager.id
    target["decision_reason"] = payload.reason
    target["effect"] = effect

    history = _kpi_history()
    history.append(target)
    _write_json_value(KPI_RECOMMENDATION_HISTORY_KEY, history[-1000:])
    _write_json_value(KPI_RECOMMENDATION_ACTIVE_KEY, remaining)

    audit = create_audit_log(
        db,
        action=f"UNIVERSE_RECOMMENDATION_{decision.upper()}",
        entity_type="kpi_recommendation",
        entity_id=str(payload.recommendation_id),
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning" if decision == "reject" else "info",
        details={"trace_id": trace_id, "reason": payload.reason, "decision": decision, "effect": effect},
    )
    return _action_result(
        trace_id=trace_id,
        message=f"recommendation {decision}",
        state_snapshot={"recommendation": target, "active_count": len(remaining)},
        audit_log_id=audit.id,
    )


@router.post("/recommendation/apply")
def recommendation_apply(payload: RecommendationDecisionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _recommendation_decision(
        decision="apply",
        phrase=payload.confirmation_phrase,
        expected_phrase=KPI_APPLY_PHRASE,
        payload=payload,
        current_admin=current_admin,
        db=db,
    )


@router.post("/recommendation/reject")
def recommendation_reject(payload: RecommendationDecisionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _recommendation_decision(
        decision="reject",
        phrase=payload.confirmation_phrase,
        expected_phrase=KPI_REJECT_PHRASE,
        payload=payload,
        current_admin=current_admin,
        db=db,
    )


@router.post("/recommendation/postpone")
def recommendation_postpone(payload: RecommendationDecisionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _recommendation_decision(
        decision="postpone",
        phrase=payload.confirmation_phrase,
        expected_phrase=KPI_POSTPONE_PHRASE,
        payload=payload,
        current_admin=current_admin,
        db=db,
    )


@router.get("/metrics/history")
def metrics_history(
    range: str = Query(default="24h", pattern="^(1h|24h|7d|30d)$"),
    symbol: str | None = Query(default=None),
    strategy: str | None = Query(default=None),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    now = datetime.now(timezone.utc)
    if range == "1h":
        since = now - timedelta(hours=1)
    elif range == "7d":
        since = now - timedelta(days=7)
    elif range == "30d":
        since = now - timedelta(days=30)
    else:
        since = now - timedelta(hours=24)

    query = db.query(ExecutionMetric).filter(ExecutionMetric.created_at >= since)
    if symbol:
        query = query.filter(ExecutionMetric.symbol == symbol.upper())
    if strategy:
        query = query.filter(ExecutionMetric.strategy_type == strategy)
    rows = query.order_by(ExecutionMetric.created_at.asc()).limit(6000).all()

    bucket_map: dict[str, dict] = {}
    for row in rows:
        ts = row.created_at or now
        if range == "1h":
            bucket = ts.replace(second=0, microsecond=0)
        else:
            bucket = ts.replace(minute=0, second=0, microsecond=0)
        key = bucket.isoformat()
        cell = bucket_map.setdefault(
            key,
            {
                "ts": key,
                "latencies": [],
                "pnl_values": [],
            },
        )
        if isinstance(row.execution_time_ms, (int, float)):
            cell["latencies"].append(float(row.execution_time_ms))

        pnl_value = 0.0
        if isinstance(row.price_avg, (int, float)) and isinstance(row.mid_price, (int, float)) and isinstance(row.executed_qty, (int, float)):
            direction = 1.0 if str(row.side or "BUY").upper() == "SELL" else -1.0
            pnl_value = direction * (float(row.price_avg) - float(row.mid_price)) * float(row.executed_qty)
        elif isinstance(row.execution_quality_score, (int, float)):
            pnl_value = float(row.execution_quality_score)
        cell["pnl_values"].append(pnl_value)

    latency_series = []
    pnl_series = []
    for key in sorted(bucket_map.keys()):
        latencies = sorted(bucket_map[key]["latencies"])
        pnl_values = bucket_map[key]["pnl_values"]
        p95 = latencies[int(max(len(latencies) - 1, 0) * 0.95)] if latencies else 0.0
        avg = sum(latencies) / max(len(latencies), 1)
        latency_series.append({"ts": key, "avg_ms": round(avg, 4), "p95_ms": round(p95, 4), "count": len(latencies)})
        pnl_series.append({"ts": key, "sum": round(sum(pnl_values), 6), "avg": round(sum(pnl_values) / max(len(pnl_values), 1), 6)})

    result_query = db.query(UserScannerResult).filter(UserScannerResult.generated_at >= since)
    if symbol:
        result_query = result_query.filter(UserScannerResult.symbol == symbol.upper())
    result_rows = result_query.order_by(UserScannerResult.generated_at.asc()).limit(8000).all()
    risk_veto_bucket: dict[str, int] = {}
    for row in result_rows:
        reasons = {str(item or "").lower() for item in (row.reason_codes or [])}
        if "risk_limit_blocked" not in reasons and "risk_blocked" not in reasons and "max_positions_reached" not in reasons:
            continue
        ts = row.generated_at or now
        bucket = ts.replace(second=0, microsecond=0) if range == "1h" else ts.replace(minute=0, second=0, microsecond=0)
        key = bucket.isoformat()
        risk_veto_bucket[key] = risk_veto_bucket.get(key, 0) + 1
    risk_veto_series = [{"ts": key, "count": value} for key, value in sorted(risk_veto_bucket.items())]

    overlay_rows = (
        db.query(AuditLog)
        .filter(AuditLog.created_at >= since)
        .order_by(AuditLog.created_at.desc())
        .limit(300)
        .all()
    )
    overlays = []
    for row in overlay_rows:
        action = str(row.action or "")
        if "ROLLOUT" not in action and "OVERRIDE" not in action and "FALLBACK" not in action:
            continue
        overlays.append(
            {
                "ts": row.created_at.isoformat() if row.created_at else None,
                "event": action,
                "message": str((row.details or {}).get("reason") or (row.details or {}).get("message") or ""),
            }
        )

    if len(latency_series) == 0 and len(pnl_series) == 0 and len(risk_veto_series) == 0:
        perf_latest = _read_json_value("scanner:perf:latest:global", {})
        queue_state = _read_json_value("scanner:queue:state", {})
        fallback_ts = now.replace(second=0, microsecond=0).isoformat()
        fallback_latency = float(perf_latest.get("cycle_duration_ms") or queue_state.get("cycle_latency_ms") or 0)
        latency_series.append({"ts": fallback_ts, "avg_ms": fallback_latency, "p95_ms": fallback_latency, "count": int(perf_latest.get("symbols_evaluated") or 0)})
        pnl_series.append({"ts": fallback_ts, "sum": float(perf_latest.get("execution_quality_score") or 0), "avg": float(perf_latest.get("execution_quality_score") or 0)})
        risk_veto_series.append({"ts": fallback_ts, "count": 0})

    return {
        "range": range,
        "symbol": symbol,
        "strategy": strategy,
        "generated_at": now.isoformat(),
        "latency_series": latency_series,
        "pnl_series": pnl_series,
        "risk_veto_series": risk_veto_series,
        "overlays": overlays[:100],
        "reason_if_empty": None if len(rows) > 0 else "No data yet. Fallback snapshot gösteriliyor.",
    }


@router.get("/trends")
def admin_universe_monitor_trends(
    window: str = Query(default="24h", pattern="^(24h|7d|30d)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_perf_trend(db, window=window)


@router.get("/export.csv")
def admin_universe_monitor_export_csv(
    window: str = Query(default="24h", pattern="^(24h|7d|30d)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    content = export_perf_trend_csv(db, window=window)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=universe_monitor_{window}.csv"},
    )


@router.get("/breakdown")
def admin_universe_monitor_breakdown(
    window: str = Query(default="7d", pattern="^(24h|7d|30d)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_monitor_breakdown(db, window=window)


@router.get("/freshness-heatmap")
def admin_freshness_heatmap(
    window: str = Query(default="24h", pattern="^(24h|7d|30d)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_freshness_heatmap(db, window=window)


@router.get("/fallback-events")
def admin_fallback_events(
    limit: int = Query(default=80, ge=1, le=500),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    items = list_fallback_events(db, limit=limit)
    if len(items) == 0:
        fallback_state = get_fallback_state(redis_client)
        if fallback_state:
            items = [
                {
                    "id": "derived-fallback-state",
                    "event_type": "derived",
                    "requested_mode": fallback_state.get("requested_mode"),
                    "effective_mode": fallback_state.get("effective_mode"),
                    "trigger_metric": fallback_state.get("last_trigger_metric"),
                    "threshold_breach": fallback_state.get("last_threshold_breach") or {},
                    "exit_reason": fallback_state.get("last_exit_reason"),
                    "cycle_snapshot": fallback_state,
                    "created_at": fallback_state.get("updated_at"),
                }
            ]
    return {
        "generated_at": datetime.now(timezone.utc),
        "items": items,
        "reason_if_empty": "No fallback events yet" if len(items) == 0 else None,
    }


@router.get("/rollout/status")
def admin_rollout_status(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    row = get_rollout_state(db)
    return _rollout_status_payload(row)


@router.post("/rollout/recommend")
def admin_rollout_recommend(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    latest = get_json(redis_client, "scanner:perf:latest:global") or {}
    payload = recommend_rollout_transition(db, latest_metrics=latest)
    row = get_rollout_state(db)
    meta = dict(row.recommendation_payload or {})
    meta.update(
        {
            "pending_approvers": ["super_admin"],
            "approval_policy": "double_confirm_required",
            "approval_started_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    row.recommendation_payload = meta
    db.commit()
    return payload


@router.post("/rollout/approve")
def admin_rollout_approve(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = approve_rollout_transition(db, admin_user_id=current_admin.id)
    row = get_rollout_state(db)
    return {
        **result,
        **_rollout_status_payload(row),
    }


@router.post("/rollout/promote")
def rollout_promote(payload: RolloutActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, ROLLOUT_PROMOTE_PHRASE)

    stages = ["top_volume_subset", "mid_segment", "full_market"]
    row = get_rollout_state(db)
    idx = stages.index(row.current_stage) if row.current_stage in stages else 0
    next_idx = min(idx + 1, len(stages) - 1)
    next_stage = stages[next_idx]

    trace_id = str(uuid.uuid4())
    _rollout_transition(db, row=row, next_stage=next_stage, changed_by=manager.id, change_reason=payload.reason)
    latest = _rollout_status_payload(row)

    audit = create_audit_log(
        db,
        action="UNIVERSE_ROLLOUT_PROMOTE",
        entity_type="rollout",
        entity_id="global",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason, "next_stage": next_stage},
    )
    return _action_result(
        trace_id=trace_id,
        message="rollout promoted",
        state_snapshot={"rollout": latest},
        audit_log_id=audit.id,
    )


@router.post("/rollout/demote")
def rollout_demote(payload: RolloutActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, ROLLOUT_DEMOTE_PHRASE)

    stages = ["top_volume_subset", "mid_segment", "full_market"]
    row = get_rollout_state(db)
    idx = stages.index(row.current_stage) if row.current_stage in stages else 0
    next_idx = max(idx - 1, 0)
    next_stage = stages[next_idx]

    trace_id = str(uuid.uuid4())
    _rollout_transition(db, row=row, next_stage=next_stage, changed_by=manager.id, change_reason=payload.reason)
    latest = _rollout_status_payload(row)

    audit = create_audit_log(
        db,
        action="UNIVERSE_ROLLOUT_DEMOTE",
        entity_type="rollout",
        entity_id="global",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason, "next_stage": next_stage},
    )
    return _action_result(
        trace_id=trace_id,
        message="rollout demoted",
        state_snapshot={"rollout": latest},
        audit_log_id=audit.id,
    )


@router.post("/rollout/rollback")
def rollout_rollback(payload: RolloutActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, ROLLOUT_ROLLBACK_PHRASE)

    row = get_rollout_state(db)
    previous_stage = (row.recommendation_payload or {}).get("previous_stage")
    if not previous_stage:
        raise HTTPException(status_code=400, detail="rollback_not_available")

    trace_id = str(uuid.uuid4())
    _rollout_transition(db, row=row, next_stage=previous_stage, changed_by=manager.id, change_reason=f"rollback:{payload.reason}")
    meta = dict(row.recommendation_payload or {})
    meta["previous_stage"] = None
    meta["rollback_available"] = False
    row.recommendation_payload = meta
    db.commit()
    latest = _rollout_status_payload(row)

    audit = create_audit_log(
        db,
        action="UNIVERSE_ROLLOUT_ROLLBACK",
        entity_type="rollout",
        entity_id="global",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason, "rollback_to": previous_stage},
    )
    return _action_result(
        trace_id=trace_id,
        message="rollout rollback completed",
        state_snapshot={"rollout": latest},
        audit_log_id=audit.id,
    )


@router.get("/risk/exposure-clusters")
def risk_exposure_clusters(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    status_payload = build_admin_risk_status(db, redis_client)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio_exposure": status_payload.get("portfolio_exposure"),
        "cluster_exposure": status_payload.get("cluster_exposure") or [],
        "symbol_exposure": status_payload.get("symbol_exposure") or [],
        "config": status_payload.get("config") or {},
    }


@router.put("/risk/exposure-limit")
def risk_exposure_limit(payload: ExposureLimitRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, RISK_EXPOSURE_PHRASE)

    trace_id = str(uuid.uuid4())
    updated = patch_risk_config(
        redis_client,
        {
            "max_total_exposure_pct": payload.max_total_exposure_pct,
            "max_symbol_exposure_pct": payload.max_symbol_exposure_pct,
            "max_cluster_exposure_pct": payload.max_cluster_exposure_pct,
        },
        changed_by=manager.id,
    )

    audit = create_audit_log(
        db,
        action="UNIVERSE_RISK_EXPOSURE_LIMIT_UPDATED",
        entity_type="risk_exposure",
        entity_id="global",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason, "updated": updated},
    )
    return _action_result(
        trace_id=trace_id,
        message="exposure limits updated",
        state_snapshot={"risk_config": updated},
        audit_log_id=audit.id,
    )


def _active_exposure_overrides() -> list[dict]:
    rows = _read_json_value(RISK_EXPOSURE_OVERRIDE_KEY, [])
    if not isinstance(rows, list):
        return []
    now = datetime.now(timezone.utc)
    active: list[dict] = []
    for row in rows:
        expires_at = row.get("expires_at")
        if not expires_at:
            continue
        try:
            expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except Exception:
            continue
        if expires > now:
            ttl_remaining = int((expires - now).total_seconds())
            active.append({**row, "ttl_remaining_seconds": ttl_remaining})
    _write_json_value(RISK_EXPOSURE_OVERRIDE_KEY, active)
    return active


@router.get("/risk/exposure-override/active")
def risk_exposure_override_active(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return {"items": _active_exposure_overrides()}


@router.post("/risk/exposure-override")
def risk_exposure_override(payload: ExposureOverrideRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, RISK_OVERRIDE_PHRASE)

    trace_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    row = {
        "override_id": str(uuid.uuid4()),
        "override_type": payload.override_type,
        "scope": payload.scope,
        "reason": payload.reason,
        "created_by": manager.id,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=payload.ttl_minutes)).isoformat(),
    }
    active = _active_exposure_overrides()
    active.append(row)
    _write_json_value(RISK_EXPOSURE_OVERRIDE_KEY, active)

    audit = create_audit_log(
        db,
        action="UNIVERSE_RISK_EXPOSURE_OVERRIDE_CREATED",
        entity_type="risk_exposure_override",
        entity_id=row["override_id"],
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, **row},
    )
    return _action_result(
        trace_id=trace_id,
        message="exposure override created",
        state_snapshot={"override": row, "active_overrides": len(active)},
        audit_log_id=audit.id,
    )


@router.get("/slow-controls/status")
def slow_controls_status(current_admin: User = Depends(require_admin)):
    _ = current_admin
    payload = _read_json_value(
        SLOW_CONTROL_STATE_KEY,
        {
            "disabled_strategies": [],
            "throttled_strategies": {},
            "paused_symbols": [],
            "updated_at": None,
        },
    )
    return payload


@router.post("/strategy/{strategy_id}/disable")
def disable_strategy(
    strategy_id: str,
    payload: RuntimeActionRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, STRATEGY_DISABLE_PHRASE)

    trace_id = str(uuid.uuid4())
    state = slow_controls_status(current_admin)
    disabled = set(state.get("disabled_strategies") or [])
    disabled.add(strategy_id)
    state["disabled_strategies"] = sorted(disabled)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json_value(SLOW_CONTROL_STATE_KEY, state)

    audit = create_audit_log(
        db,
        action="UNIVERSE_STRATEGY_DISABLED",
        entity_type="strategy",
        entity_id=strategy_id,
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason},
    )
    return _action_result(
        trace_id=trace_id,
        message="strategy disabled",
        state_snapshot={"disabled_strategies": state["disabled_strategies"]},
        audit_log_id=audit.id,
    )


@router.post("/strategy/{strategy_id}/throttle")
def throttle_strategy(
    strategy_id: str,
    payload: StrategyThrottleRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, STRATEGY_THROTTLE_PHRASE)

    trace_id = str(uuid.uuid4())
    state = slow_controls_status(current_admin)
    throttled = dict(state.get("throttled_strategies") or {})
    throttled[strategy_id] = {
        "profile": payload.throttle_profile,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "reason": payload.reason,
        "updated_by": manager.id,
    }
    state["throttled_strategies"] = throttled
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json_value(SLOW_CONTROL_STATE_KEY, state)

    audit = create_audit_log(
        db,
        action="UNIVERSE_STRATEGY_THROTTLED",
        entity_type="strategy",
        entity_id=strategy_id,
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason, "throttle_profile": payload.throttle_profile},
    )
    return _action_result(
        trace_id=trace_id,
        message="strategy throttled",
        state_snapshot={"strategy_id": strategy_id, "throttle": throttled[strategy_id]},
        audit_log_id=audit.id,
    )


@router.post("/symbol/{symbol}/pause")
def pause_symbol(
    symbol: str,
    payload: SymbolPauseRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _manager_required(current_admin)
    _require_phrase(payload.confirmation_phrase, SYMBOL_PAUSE_PHRASE)

    trace_id = str(uuid.uuid4())
    state = slow_controls_status(current_admin)
    paused = set(_normalize_symbols(state.get("paused_symbols") or []))
    symbol_upper = str(symbol or "").upper().strip()
    if payload.pause:
        paused.add(symbol_upper)
    else:
        paused.discard(symbol_upper)
    state["paused_symbols"] = sorted(paused)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json_value(SLOW_CONTROL_STATE_KEY, state)

    audit = create_audit_log(
        db,
        action="UNIVERSE_SYMBOL_PAUSED" if payload.pause else "UNIVERSE_SYMBOL_RESUMED",
        entity_type="symbol",
        entity_id=symbol_upper,
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"trace_id": trace_id, "reason": payload.reason, "pause": payload.pause},
    )
    return _action_result(
        trace_id=trace_id,
        message="symbol paused" if payload.pause else "symbol resumed",
        state_snapshot={"paused_symbols": state["paused_symbols"]},
        audit_log_id=audit.id,
    )
