import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin
from models import AdminControl, AuditLog, ExecutionMetric, ScannerFallbackEvent, ScannerPerformanceSnapshot, User, UserRole, UserScannerResult
from services.audit_service import create_audit_log
from services.pipeline.cache_store import get_json, set_json
from services.pipeline.universe_engine import debug_effective_universe
from services.risk_engine_service import build_admin_risk_status, patch_risk_config
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

SLA_UPDATE_PHRASE = "UPDATE SLA CONFIG"
RESCAN_STALE_PHRASE = "RESCAN STALE"
KPI_GENERATE_PHRASE = "GENERATE KPI RECOMMENDATION"
KPI_APPLY_PHRASE = "APPLY RECOMMENDATION"
KPI_REJECT_PHRASE = "REJECT RECOMMENDATION"
KPI_POSTPONE_PHRASE = "POSTPONE RECOMMENDATION"


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


def _manager_required(current_admin: User) -> User:
    if current_admin.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="manager_role_required")
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


@router.post("/scanner/start")
def scanner_start(payload: RuntimeActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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


@router.post("/scanner/stop")
def scanner_stop(payload: RuntimeActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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


@router.post("/scanner/trigger")
def scanner_trigger(payload: ScannerTriggerRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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
    list_type: str = Path(pattern="^(whitelist|blacklist)$"),
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


@router.post("/scanner/rescan-stale")
def scanner_rescan_stale(payload: RescanStaleRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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
