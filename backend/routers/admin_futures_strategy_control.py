import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.strategies.governance.strategy_throttle_engine import LEVEL_CONFIG
from db import get_db
from deps import require_super_admin
from models import AuditLog, User
from services.audit_service import create_audit_log
from services.futures_strategy_service import get_futures_strategy_status
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures", tags=["admin_futures_strategy_control"])

_LIFECYCLE_KEY = "futures:strategy:lifecycle:{user_id}"
_THROTTLE_KEY = "futures:strategy:throttle:{user_id}"
_MANUAL_KEY = "futures:strategy:manual-controls:{user_id}"

_DISABLE_CONFIRM = "DISABLE STRATEGY"
_DECOMMISSION_CONFIRM = "DECOMMISSION STRATEGY"
_VALID_THROTTLE_LEVELS = ["L1", "L2", "L3"]


class StrategyControlActionRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    confirm_phrase: str | None = Field(default=None, max_length=120)
    throttle_level: str | None = Field(default=None, max_length=2)
    dry_run: bool = False


def _safe_json(raw, default):
    if not raw:
        return default
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        if isinstance(raw, str):
            return json.loads(raw)
        if isinstance(raw, (dict, list)):
            return raw
    except Exception:
        return default
    return default


def _cache_get(cache, key: str, default):
    if not cache:
        return default
    return _safe_json(cache.get(key), default)


def _cache_set(cache, key: str, payload: dict):
    if not cache:
        return
    cache.set(key, json.dumps(payload))


def _build_maps(status: dict) -> dict:
    metadata_map = {
        str(item.get("strategy") or ""): item
        for item in (status.get("strategy_metadata") or [])
        if str(item.get("strategy") or "")
    }
    health_map = {
        str(item.get("strategy") or ""): item
        for item in (status.get("strategy_health_score") or [])
        if str(item.get("strategy") or "")
    }
    pnl_map = {
        str(item.get("strategy") or ""): item
        for item in (status.get("strategy_attribution") or [])
        if str(item.get("strategy") or "")
    }
    drift_map: dict[str, dict] = {}
    for row in (status.get("strategy_drift_alerts") or []):
        strategy_id = str(row.get("strategy") or "")
        if not strategy_id:
            continue
        existing = drift_map.get(strategy_id)
        if not existing:
            drift_map[strategy_id] = {
                "count": 1,
                "severity": str(row.get("severity") or "LOW").upper(),
                "reasons": list(row.get("trigger_reason") or []),
            }
            continue
        existing["count"] = int(existing.get("count", 0) + 1)
    return {
        "metadata_map": metadata_map,
        "health_map": health_map,
        "pnl_map": pnl_map,
        "drift_map": drift_map,
    }


def _compose_strategy_rows(status: dict, lifecycle_registry: dict, throttle_payload: dict, manual_controls: dict) -> list[dict]:
    maps = _build_maps(status)
    metadata_map = maps["metadata_map"]
    health_map = maps["health_map"]
    pnl_map = maps["pnl_map"]
    drift_map = maps["drift_map"]

    throttle_map = throttle_payload.get("by_strategy") if isinstance(throttle_payload, dict) else {}
    if not isinstance(throttle_map, dict):
        throttle_map = {}

    rows: list[dict] = []
    for strategy_id in (status.get("strategy_registry") or []):
        sid = str(strategy_id)
        lifecycle = dict(lifecycle_registry.get(sid) or {})
        throttle = dict(throttle_map.get(sid) or {})
        manual = dict(manual_controls.get(sid) or {})
        health = dict(health_map.get(sid) or {})
        pnl = dict(pnl_map.get(sid) or {})
        drift = dict(drift_map.get(sid) or {})
        meta = dict(metadata_map.get(sid) or {})

        lifecycle_state = str(lifecycle.get("lifecycle_state") or "ACTIVE").upper()
        throttle_level = str(throttle.get("throttle_level") or "NONE").upper()
        control_state = str(manual.get("control_state") or lifecycle_state).upper()
        if control_state == "THROTTLED" and throttle_level == "L3":
            control_state = "PAUSED"

        source_type = str(meta.get("source_type") or "strategy_engine")
        shadow_live_state = "SHADOW" if source_type == "legacy_formula" else "LIVE"

        rows.append(
            {
                "strategy_id": sid,
                "strategy_name": sid,
                "family_code": meta.get("family_code") or "default",
                "source_type": source_type,
                "shadow_live_state": shadow_live_state,
                "lifecycle_state": lifecycle_state,
                "control_state": control_state,
                "throttle_level": throttle_level,
                "health_score": float(health.get("strategy_health_score") or 0),
                "pnl_rolling": float(health.get("strategy_pnl_rolling") or pnl.get("pnl_rolling") or 0),
                "win_rate": float(health.get("strategy_win_rate_rolling") or 0),
                "execution_quality": float(health.get("strategy_execution_quality") or 0),
                "drift_count": int(drift.get("count") or 0),
                "drift_severity": drift.get("severity") or "NONE",
                "drift_reasons": drift.get("reasons") or [],
                "last_transition_at": lifecycle.get("last_transition_at"),
                "last_transition_reason": lifecycle.get("last_transition_reason") or "n/a",
                "transition_history": lifecycle.get("transition_history") or [],
                "manual_reason": manual.get("reason") or "",
                "updated_at": manual.get("updated_at") or lifecycle.get("last_transition_at"),
            }
        )
    return rows


def _load_control_state(db: Session, current_admin: User, refresh: bool = False):
    status = get_futures_strategy_status(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    lifecycle_key = _LIFECYCLE_KEY.format(user_id=current_admin.id)
    throttle_key = _THROTTLE_KEY.format(user_id=current_admin.id)
    manual_key = _MANUAL_KEY.format(user_id=current_admin.id)

    lifecycle_registry = _cache_get(
        pipeline_runtime.cache,
        lifecycle_key,
        status.get("strategy_lifecycle_registry") or {},
    )
    throttle_payload = _cache_get(
        pipeline_runtime.cache,
        throttle_key,
        {
            "strategy_throttle_state": status.get("strategy_throttle_state") or [],
            "by_strategy": {
                str(item.get("strategy") or ""): item
                for item in (status.get("strategy_throttle_state") or [])
                if str(item.get("strategy") or "")
            },
        },
    )
    manual_controls = _cache_get(pipeline_runtime.cache, manual_key, {})
    rows = _compose_strategy_rows(status, lifecycle_registry, throttle_payload, manual_controls)
    return {
        "status_payload": status,
        "rows": rows,
        "lifecycle_registry": lifecycle_registry,
        "throttle_payload": throttle_payload,
        "manual_controls": manual_controls,
        "keys": {
            "lifecycle": lifecycle_key,
            "throttle": throttle_key,
            "manual": manual_key,
        },
    }


def _find_row(rows: list[dict], strategy_id: str) -> dict:
    for row in rows:
        if str(row.get("strategy_id")) == str(strategy_id):
            return row
    raise HTTPException(status_code=404, detail="strategy_not_found")


def _result_payload(*, status: str, trace_id: str, message: str, state_snapshot: dict, extra: dict | None = None) -> dict:
    payload = {
        "status": status,
        "trace_id": trace_id,
        "message": message,
        "state_snapshot": state_snapshot,
    }
    if extra:
        payload.update(extra)
    return payload


def _set_lifecycle_state(lifecycle_registry: dict, *, strategy_id: str, next_state: str, reason: str):
    now_iso = datetime.now(timezone.utc).isoformat()
    current = dict(lifecycle_registry.get(strategy_id) or {})
    current_state = str(current.get("lifecycle_state") or "ACTIVE")
    history = list(current.get("transition_history") or [])
    history.append({"from": current_state, "to": next_state, "reason": reason, "at": now_iso})
    lifecycle_registry[strategy_id] = {
        "strategy": strategy_id,
        "lifecycle_state": next_state,
        "last_transition_at": now_iso,
        "last_transition_reason": reason,
        "transition_history": history[-80:],
    }


def _set_throttle_state(throttle_payload: dict, *, strategy_id: str, level: str):
    now_iso = datetime.now(timezone.utc).isoformat()
    config = LEVEL_CONFIG.get(level) or LEVEL_CONFIG["L1"]
    by_strategy = throttle_payload.get("by_strategy") or {}
    row = {
        "strategy": strategy_id,
        "throttle_level": level,
        "confidence_clamp": config["confidence_cap"],
        "max_signals_per_cycle": config["max_signals_per_cycle"],
        "max_position_ratio": config["max_position_ratio"],
        "recovery_condition": "manual_override" if level != "NONE" else "n/a",
        "updated_at": now_iso,
    }
    by_strategy[strategy_id] = row
    throttle_payload["by_strategy"] = by_strategy
    throttle_payload["strategy_throttle_state"] = list(by_strategy.values())


def _set_manual_state(manual_controls: dict, *, strategy_id: str, control_state: str, reason: str, trace_id: str):
    manual_controls[strategy_id] = {
        "strategy": strategy_id,
        "control_state": control_state,
        "reason": reason,
        "trace_id": trace_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _validate_disable_flow(action: str, row: dict) -> tuple[bool, str]:
    state = str(row.get("control_state") or "ACTIVE").upper()
    if action == "disable" and state not in {"THROTTLED", "PAUSED", "DISABLED"}:
        return False, "Disable öncesi throttle veya pause zorunlu (throttle → pause → disable)."
    if action == "decommission" and state not in {"DISABLED", "DECOMMISSIONED"}:
        return False, "Decommission öncesi strategy DISABLED olmalı."
    if action == "resume" and state == "DECOMMISSIONED":
        return False, "Decommission edilmiş strategy resume edilemez."
    if action == "enable" and state == "DECOMMISSIONED":
        return False, "Decommission edilmiş strategy enable edilemez."
    return True, "ok"


@router.get("/strategy-control/overview")
def strategy_control_overview(
    refresh: bool = False,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    payload = _load_control_state(db, current_admin, refresh=refresh)
    rows = payload["rows"]
    create_audit_log(
        db,
        action="FUTURES_STRATEGY_CONTROL_OVERVIEW_VIEWED",
        entity_type="futures_strategy_control",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "strategy_count": len(rows),
            "disabled_count": len([row for row in rows if row.get("lifecycle_state") == "DISABLED"]),
            "throttled_count": len([row for row in rows if row.get("throttle_level") != "NONE"]),
        },
    )
    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tabs": [
            "overview",
            "universe_control",
            "rollout",
            "strategy_governance",
            "capital_governance",
            "drift_action_center",
            "audit_history",
        ],
        "phase_scope": "phase_1_control_foundation",
        "strategies": rows,
    }


@router.get("/strategy/{strategy_id}/detail")
def strategy_control_detail(
    strategy_id: str,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    payload = _load_control_state(db, current_admin, refresh=False)
    row = _find_row(payload["rows"], strategy_id)
    governance_events = [
        item
        for item in ((payload["status_payload"].get("strategy_governance") or {}).get("governance_events") or [])
        if str(item.get("strategy") or "") == strategy_id
    ]
    return {
        "status": "ok",
        "strategy": row,
        "execution_history": {
            "items": [],
            "reason": "Faz-1 kapsamında execution history aksiyonu henüz devrede değil.",
        },
        "trade_list": {
            "items": [],
            "reason": "Faz-1 kapsamında trade list aksiyonu henüz devrede değil.",
        },
        "governance_events": governance_events,
        "transition_history": row.get("transition_history") or [],
        "export": {
            "enabled": False,
            "reason": "Faz-2 backlog",
        },
    }


@router.get("/strategy/{strategy_id}/audit-history")
def strategy_control_audit_history(
    strategy_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "futures_strategy_control", AuditLog.entity_id == strategy_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "status": "ok",
        "items": [
            {
                "id": row.id,
                "action": row.action,
                "severity": row.severity,
                "actor_user_id": row.actor_user_id,
                "actor_role": row.actor_role,
                "details": row.details or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


def _run_strategy_action(
    *,
    action: str,
    strategy_id: str,
    payload: StrategyControlActionRequest,
    current_admin: User,
    db: Session,
):
    trace_id = f"strategy_ctrl_{uuid.uuid4().hex[:12]}"
    state = _load_control_state(db, current_admin, refresh=False)
    before_row = _find_row(state["rows"], strategy_id)

    is_valid, flow_message = _validate_disable_flow(action, before_row)
    if not is_valid:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message=flow_message,
            state_snapshot=before_row,
        )

    if action == "disable" and str(payload.confirm_phrase or "").strip().upper() != _DISABLE_CONFIRM:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message=f"Disable için onay ifadesi zorunlu: {_DISABLE_CONFIRM}",
            state_snapshot=before_row,
        )

    if action == "decommission" and str(payload.confirm_phrase or "").strip().upper() != _DECOMMISSION_CONFIRM:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message=f"Decommission için onay ifadesi zorunlu: {_DECOMMISSION_CONFIRM}",
            state_snapshot=before_row,
        )

    lifecycle_registry = state["lifecycle_registry"]
    throttle_payload = state["throttle_payload"]
    manual_controls = state["manual_controls"]

    action_upper = action.upper()
    next_control_state = "ACTIVE"
    message = ""
    rollback_reference = None

    if action == "enable":
        _set_lifecycle_state(lifecycle_registry, strategy_id=strategy_id, next_state="ACTIVE", reason=f"MANUAL_ENABLE:{payload.reason}")
        _set_throttle_state(throttle_payload, strategy_id=strategy_id, level="NONE")
        next_control_state = "ACTIVE"
        message = f"{strategy_id} enable edildi"
    elif action == "resume":
        _set_lifecycle_state(lifecycle_registry, strategy_id=strategy_id, next_state="ACTIVE", reason=f"MANUAL_RESUME:{payload.reason}")
        _set_throttle_state(throttle_payload, strategy_id=strategy_id, level="NONE")
        next_control_state = "ACTIVE"
        message = f"{strategy_id} resume edildi"
    elif action == "pause":
        _set_lifecycle_state(lifecycle_registry, strategy_id=strategy_id, next_state="THROTTLED", reason=f"MANUAL_PAUSE:{payload.reason}")
        _set_throttle_state(throttle_payload, strategy_id=strategy_id, level="L3")
        next_control_state = "PAUSED"
        message = f"{strategy_id} pause edildi (L3 throttle)"
    elif action == "throttle":
        throttle_level = str(payload.throttle_level or "L1").upper()
        if throttle_level not in _VALID_THROTTLE_LEVELS:
            throttle_level = "L1"
        _set_lifecycle_state(
            lifecycle_registry,
            strategy_id=strategy_id,
            next_state="THROTTLED",
            reason=f"MANUAL_THROTTLE_{throttle_level}:{payload.reason}",
        )
        _set_throttle_state(throttle_payload, strategy_id=strategy_id, level=throttle_level)
        next_control_state = "THROTTLED"
        message = f"{strategy_id} throttle seviyesi {throttle_level} olarak güncellendi"
    elif action == "disable":
        _set_lifecycle_state(lifecycle_registry, strategy_id=strategy_id, next_state="DISABLED", reason=f"MANUAL_DISABLE:{payload.reason}")
        _set_throttle_state(throttle_payload, strategy_id=strategy_id, level="L3")
        next_control_state = "DISABLED"
        rollback_reference = f"rollback_ref:{trace_id}"
        message = f"{strategy_id} disable edildi"
    elif action == "decommission":
        _set_lifecycle_state(lifecycle_registry, strategy_id=strategy_id, next_state="DISABLED", reason=f"MANUAL_DECOMMISSION:{payload.reason}")
        _set_throttle_state(throttle_payload, strategy_id=strategy_id, level="L3")
        next_control_state = "DECOMMISSIONED"
        rollback_reference = f"rollback_ref:{trace_id}"
        message = f"{strategy_id} decommission edildi"
    else:
        raise HTTPException(status_code=400, detail="unsupported_action")

    _set_manual_state(manual_controls, strategy_id=strategy_id, control_state=next_control_state, reason=payload.reason, trace_id=trace_id)

    if not payload.dry_run:
        _cache_set(pipeline_runtime.cache, state["keys"]["lifecycle"], lifecycle_registry)
        _cache_set(pipeline_runtime.cache, state["keys"]["throttle"], throttle_payload)
        _cache_set(pipeline_runtime.cache, state["keys"]["manual"], manual_controls)

    after_rows = _compose_strategy_rows(state["status_payload"], lifecycle_registry, throttle_payload, manual_controls)
    after_row = _find_row(after_rows, strategy_id)
    action_status = "dry_run" if payload.dry_run else "success"

    create_audit_log(
        db,
        action=f"FUTURES_STRATEGY_{action_upper}",
        entity_type="futures_strategy_control",
        entity_id=strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="critical" if action in {"disable", "decommission"} else "warning",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "confirm_phrase": payload.confirm_phrase,
            "dry_run": payload.dry_run,
            "before_state": before_row,
            "after_state": after_row,
            "rollback_reference": rollback_reference,
        },
    )

    return _result_payload(
        status=action_status,
        trace_id=trace_id,
        message=message,
        state_snapshot=after_row,
        extra={
            "before_state": before_row,
            "after_state": after_row,
            "rollback_reference": rollback_reference,
        },
    )


@router.post("/strategy/{strategy_id}/enable")
def strategy_enable(
    strategy_id: str,
    payload: StrategyControlActionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return _run_strategy_action(action="enable", strategy_id=strategy_id, payload=payload, current_admin=current_admin, db=db)


@router.post("/strategy/{strategy_id}/disable")
def strategy_disable(
    strategy_id: str,
    payload: StrategyControlActionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return _run_strategy_action(action="disable", strategy_id=strategy_id, payload=payload, current_admin=current_admin, db=db)


@router.post("/strategy/{strategy_id}/pause")
def strategy_pause(
    strategy_id: str,
    payload: StrategyControlActionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return _run_strategy_action(action="pause", strategy_id=strategy_id, payload=payload, current_admin=current_admin, db=db)


@router.post("/strategy/{strategy_id}/resume")
def strategy_resume(
    strategy_id: str,
    payload: StrategyControlActionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return _run_strategy_action(action="resume", strategy_id=strategy_id, payload=payload, current_admin=current_admin, db=db)


@router.post("/strategy/{strategy_id}/throttle")
def strategy_throttle(
    strategy_id: str,
    payload: StrategyControlActionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return _run_strategy_action(action="throttle", strategy_id=strategy_id, payload=payload, current_admin=current_admin, db=db)


@router.post("/strategy/{strategy_id}/decommission")
def strategy_decommission(
    strategy_id: str,
    payload: StrategyControlActionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return _run_strategy_action(action="decommission", strategy_id=strategy_id, payload=payload, current_admin=current_admin, db=db)
