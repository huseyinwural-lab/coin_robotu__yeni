import csv
import io
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.strategies.governance.strategy_throttle_engine import LEVEL_CONFIG
from db import get_db
from deps import require_admin, require_super_admin
from models import AuditLog, User
from services.audit_service import create_audit_log
from services.futures_strategy_service import get_futures_strategy_status
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures", tags=["admin_futures_strategy_control"])

_LIFECYCLE_KEY = "futures:strategy:lifecycle:global"
_THROTTLE_KEY = "futures:strategy:throttle:global"
_MANUAL_KEY = "futures:strategy:manual-controls:global"
_ROLLOUT_KEY = "futures:strategy:rollout:global"
_HISTORY_KEY = "futures:strategy:control-history:global"
_DRIFT_ALERT_KEY = "futures:strategy:drift-alert-state:global"
_FEEDBACK_KEY = "futures:strategy:feedback:global"
_MODEL_UPDATE_KEY = "futures:strategy:model-update:global"
_APPROVAL_REQUEST_KEY = "futures:strategy:approval-requests:global"

_DISABLE_CONFIRM = "DISABLE STRATEGY"
_DECOMMISSION_CONFIRM = "DECOMMISSION STRATEGY"
_ROLLBACK_CONFIRM = "ROLLBACK LAST ACTION"
_ROLLOUT_CONFIRM = "APPLY ROLLOUT"
_PROMOTE_CONFIRM = "PROMOTE SHADOW"
_DRIFT_IGNORE_CONFIRM = "IGNORE DRIFT ALERT"
_DRIFT_DISABLE_CONFIRM = "DISABLE VIA DRIFT"

_VALID_THROTTLE_LEVELS = ["L1", "L2", "L3"]
_VALID_ROLLOUT_STEPS = [10, 25, 50, 100]

_AUTO_ROLLBACK_HEALTH_THRESHOLD = 50.0
_AUTO_ROLLBACK_ERROR_THRESHOLD = 3.0


class StrategyControlActionRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    confirm_phrase: str | None = Field(default=None, max_length=120)
    throttle_level: str | None = Field(default=None, max_length=2)
    dry_run: bool = False


class StrategyRolloutRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    confirm_phrase: str | None = Field(default=None, max_length=120)
    rollout_percentage: int = Field(default=10, ge=1, le=100)
    dry_run: bool = False


class StrategyRollbackRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    confirm_phrase: str | None = Field(default=None, max_length=120)
    dry_run: bool = False


class StrategyBulkActionRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    confirm_phrase: str = Field(..., min_length=3, max_length=80)
    strategy_ids: list[str] = Field(..., min_length=1)
    action: str = Field(..., min_length=3, max_length=20)
    throttle_level: str | None = Field(default=None, max_length=2)
    dry_run: bool = False


class DriftActionRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    confirm_phrase: str | None = Field(default=None, max_length=120)
    mute_duration_hours: int | None = Field(default=None, ge=1, le=168)
    dry_run: bool = False


class FeedbackLabelRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    drift_alert_id: str = Field(..., min_length=3, max_length=120)
    corrected_label: str = Field(..., min_length=3, max_length=80)
    reason_taxonomy: str = Field(..., min_length=3, max_length=80)
    sample_link: str | None = Field(default=None, max_length=400)
    related_data_slice: dict = Field(default_factory=dict)
    dry_run: bool = False


class ModelUpdateTriggerRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    dataset_version: int | None = Field(default=None, ge=1)
    dry_run: bool = False


class RollbackRequestCreateRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    snapshot_trace_id: str = Field(..., min_length=4, max_length=120)


class ApprovalDecisionRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


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


def _deep_copy(payload):
    return _safe_json(json.dumps(payload), payload)


def _cache_get(cache, key: str, default):
    if not cache:
        return default
    return _safe_json(cache.get(key), default)


def _cache_set(cache, key: str, payload):
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
    reject_map = {
        str(item.get("strategy") or ""): item
        for item in (status.get("strategy_reject_rate") or [])
        if str(item.get("strategy") or "")
    }

    checklist_rows = status.get("architecture_checklist_15") or []
    checklist_passed = bool(checklist_rows) and all(bool(item.get("status")) for item in checklist_rows)
    checklist_failed_items = [item.get("item") for item in checklist_rows if not bool(item.get("status"))]

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
        "reject_map": reject_map,
        "drift_map": drift_map,
        "checklist_passed": checklist_passed,
        "checklist_failed_items": checklist_failed_items,
    }


def _default_rollout_row(strategy_id: str, shadow_live_state: str) -> dict:
    return {
        "strategy_id": strategy_id,
        "rollout_mode": "SHADOW" if shadow_live_state == "SHADOW" else "LIVE",
        "rollout_percentage": 0 if shadow_live_state == "SHADOW" else 100,
        "auto_rollback_enabled": True,
        "auto_rollback_thresholds": {
            "health_score_min": _AUTO_ROLLBACK_HEALTH_THRESHOLD,
            "error_rate_max_pct": _AUTO_ROLLBACK_ERROR_THRESHOLD,
        },
        "last_rollout_at": None,
        "last_rollout_reason": None,
    }


def _compose_strategy_rows(
    status: dict,
    lifecycle_registry: dict,
    throttle_payload: dict,
    manual_controls: dict,
    rollout_payload: dict,
) -> list[dict]:
    maps = _build_maps(status)
    metadata_map = maps["metadata_map"]
    health_map = maps["health_map"]
    pnl_map = maps["pnl_map"]
    reject_map = maps["reject_map"]
    drift_map = maps["drift_map"]
    checklist_passed = maps["checklist_passed"]
    checklist_failed_items = maps["checklist_failed_items"]

    throttle_map = throttle_payload.get("by_strategy") if isinstance(throttle_payload, dict) else {}
    if not isinstance(throttle_map, dict):
        throttle_map = {}

    rollout_map = rollout_payload.get("by_strategy") if isinstance(rollout_payload, dict) else {}
    if not isinstance(rollout_map, dict):
        rollout_map = {}

    rows: list[dict] = []
    for strategy_id in (status.get("strategy_registry") or []):
        sid = str(strategy_id)
        lifecycle = dict(lifecycle_registry.get(sid) or {})
        throttle = dict(throttle_map.get(sid) or {})
        manual = dict(manual_controls.get(sid) or {})
        health = dict(health_map.get(sid) or {})
        pnl = dict(pnl_map.get(sid) or {})
        reject = dict(reject_map.get(sid) or {})
        drift = dict(drift_map.get(sid) or {})
        meta = dict(metadata_map.get(sid) or {})

        lifecycle_state = str(lifecycle.get("lifecycle_state") or "ACTIVE").upper()
        throttle_level = str(throttle.get("throttle_level") or "NONE").upper()
        control_state = str(manual.get("control_state") or lifecycle_state).upper()
        if control_state == "THROTTLED" and throttle_level == "L3":
            control_state = "PAUSED"

        source_type = str(meta.get("source_type") or "strategy_engine")
        shadow_live_state = "SHADOW" if source_type == "legacy_formula" else "LIVE"
        rollout = dict(rollout_map.get(sid) or _default_rollout_row(sid, shadow_live_state))

        raw_error_rate = float(reject.get("reject_rate") or 0)
        error_rate_pct = raw_error_rate * 100 if raw_error_rate <= 1 else raw_error_rate

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
                "error_rate_pct": round(error_rate_pct, 4),
                "drift_count": int(drift.get("count") or 0),
                "drift_severity": drift.get("severity") or "NONE",
                "drift_reasons": drift.get("reasons") or [],
                "checklist_passed": checklist_passed,
                "checklist_failed_items": checklist_failed_items,
                "rollout_mode": rollout.get("rollout_mode") or ("SHADOW" if shadow_live_state == "SHADOW" else "LIVE"),
                "rollout_percentage": int(rollout.get("rollout_percentage") or (0 if shadow_live_state == "SHADOW" else 100)),
                "auto_rollback_enabled": bool(rollout.get("auto_rollback_enabled", True)),
                "auto_rollback_thresholds": rollout.get("auto_rollback_thresholds")
                or {
                    "health_score_min": _AUTO_ROLLBACK_HEALTH_THRESHOLD,
                    "error_rate_max_pct": _AUTO_ROLLBACK_ERROR_THRESHOLD,
                },
                "last_rollout_at": rollout.get("last_rollout_at"),
                "last_rollout_reason": rollout.get("last_rollout_reason"),
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
    rollout_key = _ROLLOUT_KEY.format(user_id=current_admin.id)
    history_key = _HISTORY_KEY.format(user_id=current_admin.id)
    drift_alert_key = _DRIFT_ALERT_KEY.format(user_id=current_admin.id)
    feedback_key = _FEEDBACK_KEY.format(user_id=current_admin.id)
    model_update_key = _MODEL_UPDATE_KEY.format(user_id=current_admin.id)
    approval_key = _APPROVAL_REQUEST_KEY.format(user_id=current_admin.id)

    lifecycle_registry = _cache_get(pipeline_runtime.cache, lifecycle_key, status.get("strategy_lifecycle_registry") or {})
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
    rollout_payload = _cache_get(pipeline_runtime.cache, rollout_key, {"by_strategy": {}, "history": []})
    action_history = _cache_get(pipeline_runtime.cache, history_key, [])
    drift_alert_state = _cache_get(pipeline_runtime.cache, drift_alert_key, {})
    feedback_payload = _cache_get(pipeline_runtime.cache, feedback_key, {"items": [], "version_by_strategy": {}})
    model_update_payload = _cache_get(pipeline_runtime.cache, model_update_key, {"by_strategy": {}, "history": []})
    approval_requests_payload = _cache_get(pipeline_runtime.cache, approval_key, {"items": []})

    rows = _compose_strategy_rows(status, lifecycle_registry, throttle_payload, manual_controls, rollout_payload)
    return {
        "status_payload": status,
        "rows": rows,
        "lifecycle_registry": lifecycle_registry,
        "throttle_payload": throttle_payload,
        "manual_controls": manual_controls,
        "rollout_payload": rollout_payload,
        "action_history": action_history,
        "drift_alert_state": drift_alert_state,
        "feedback_payload": feedback_payload,
        "model_update_payload": model_update_payload,
        "approval_requests_payload": approval_requests_payload,
        "keys": {
            "lifecycle": lifecycle_key,
            "throttle": throttle_key,
            "manual": manual_key,
            "rollout": rollout_key,
            "history": history_key,
            "drift_alert": drift_alert_key,
            "feedback": feedback_key,
            "model_update": model_update_key,
            "approval_requests": approval_key,
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


def _set_rollout_state(
    rollout_payload: dict,
    *,
    strategy_id: str,
    mode: str,
    percentage: int,
    reason: str,
):
    now_iso = datetime.now(timezone.utc).isoformat()
    by_strategy = rollout_payload.get("by_strategy") or {}
    current = dict(by_strategy.get(strategy_id) or {})
    by_strategy[strategy_id] = {
        "strategy_id": strategy_id,
        "rollout_mode": mode,
        "rollout_percentage": int(percentage),
        "auto_rollback_enabled": bool(current.get("auto_rollback_enabled", True)),
        "auto_rollback_thresholds": current.get("auto_rollback_thresholds")
        or {
            "health_score_min": _AUTO_ROLLBACK_HEALTH_THRESHOLD,
            "error_rate_max_pct": _AUTO_ROLLBACK_ERROR_THRESHOLD,
        },
        "last_rollout_at": now_iso,
        "last_rollout_reason": reason,
    }
    rollout_payload["by_strategy"] = by_strategy
    rollout_history = list(rollout_payload.get("history") or [])
    rollout_history.append(
        {
            "strategy_id": strategy_id,
            "mode": mode,
            "rollout_percentage": int(percentage),
            "reason": reason,
            "at": now_iso,
        }
    )
    rollout_payload["history"] = rollout_history[-200:]


def _append_action_history(action_history: list, entry: dict) -> list:
    history = list(action_history or [])
    history.append(entry)
    return history[-500:]


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


def _build_rollout_precheck(row: dict) -> dict:
    health_score = float(row.get("health_score") or 0)
    error_rate_pct = float(row.get("error_rate_pct") or 0)
    drift_count = int(row.get("drift_count") or 0)
    checklist_passed = bool(row.get("checklist_passed"))
    failed_items = list(row.get("checklist_failed_items") or [])

    checks = {
        "health": {
            "ok": health_score >= _AUTO_ROLLBACK_HEALTH_THRESHOLD,
            "current": health_score,
            "required_min": _AUTO_ROLLBACK_HEALTH_THRESHOLD,
        },
        "recent_error": {
            "ok": error_rate_pct <= _AUTO_ROLLBACK_ERROR_THRESHOLD,
            "current": error_rate_pct,
            "max_allowed": _AUTO_ROLLBACK_ERROR_THRESHOLD,
        },
        "drift": {
            "ok": drift_count == 0,
            "current": drift_count,
            "required": 0,
        },
        "checklist": {
            "ok": checklist_passed,
            "failed_items": failed_items,
        },
    }
    passed = all(item.get("ok") for item in checks.values())
    return {
        "status": "pass" if passed else "fail",
        "checks": checks,
    }


def _resolve_bulk_confirm_phrase(action: str) -> str:
    action_upper = str(action or "").strip().upper()
    if action_upper == "PAUSE":
        return "BULK PAUSE"
    if action_upper == "RESUME":
        return "BULK RESUME"
    if action_upper == "THROTTLE":
        return "BULK THROTTLE"
    return ""


def _build_drift_alert_rows(status_payload: dict, drift_alert_state: dict) -> list[dict]:
    rows = []
    now = datetime.now(timezone.utc)
    for index, row in enumerate(status_payload.get("strategy_drift_alerts") or []):
        strategy_id = str(row.get("strategy") or "")
        if not strategy_id:
            continue
        alert_id = f"{strategy_id}::{index}"
        state = dict(drift_alert_state.get(alert_id) or {})
        muted_until = state.get("muted_until")
        muted_active = False
        if muted_until:
            try:
                muted_active = datetime.fromisoformat(str(muted_until)) > now
            except Exception:
                muted_active = False

        action_status = "OPEN"
        if state.get("ignored"):
            action_status = "IGNORED"
        elif muted_active:
            action_status = "MUTED"
        elif state.get("acked"):
            action_status = "ACKED"

        reasons = row.get("trigger_reason")
        if not isinstance(reasons, list):
            reasons = [str(reasons)] if reasons else []

        target_tab = "strategy_governance"
        if any("gate" in str(item).lower() for item in reasons):
            target_tab = "rollout"

        rows.append(
            {
                "alert_id": alert_id,
                "strategy_id": strategy_id,
                "severity": str(row.get("severity") or "LOW").upper(),
                "metric": row.get("metric") or "drift",
                "value": row.get("value"),
                "trigger_reason": reasons,
                "status": action_status,
                "acked": bool(state.get("acked")),
                "muted_until": muted_until,
                "ignored": bool(state.get("ignored")),
                "retrain_status": state.get("retrain_status") or "none",
                "retrain_job_id": state.get("retrain_job_id"),
                "last_action_trace_id": state.get("last_action_trace_id"),
                "deep_link": {
                    "target_tab": target_tab,
                    "strategy_id": strategy_id,
                    "context_filter": {
                        "strategy_id": strategy_id,
                        "severity": str(row.get("severity") or "LOW").upper(),
                    },
                },
            }
        )
    return rows


def _refresh_model_update_jobs(model_update_payload: dict) -> dict:
    by_strategy = model_update_payload.get("by_strategy") or {}
    now = datetime.now(timezone.utc)
    changed = False

    for strategy_id, job in list(by_strategy.items()):
        status = str(job.get("status") or "queued")
        if status == "queued":
            created_at = job.get("created_at")
            try:
                created_dt = datetime.fromisoformat(str(created_at))
            except Exception:
                created_dt = now
            if (now - created_dt).total_seconds() >= 4:
                job["status"] = "running"
                job["started_at"] = now.isoformat()
                changed = True
        elif status == "running":
            started_at = job.get("started_at")
            try:
                started_dt = datetime.fromisoformat(str(started_at))
            except Exception:
                started_dt = now
            if (now - started_dt).total_seconds() >= 8:
                job["status"] = "completed"
                job["completed_at"] = now.isoformat()
                job["result"] = "model_update_applied"
                changed = True
        by_strategy[strategy_id] = job

    model_update_payload["by_strategy"] = by_strategy
    model_update_payload.setdefault("history", [])
    return {"payload": model_update_payload, "changed": changed}


def _build_strategy_timeline(
    *,
    strategy_id: str,
    status_payload: dict,
    action_history: list,
    feedback_payload: dict,
    model_update_payload: dict,
) -> list[dict]:
    timeline = []
    for item in action_history or []:
        if str(item.get("strategy_id") or "") != strategy_id:
            continue
        timeline.append(
            {
                "event_type": "ACTION",
                "event_id": item.get("trace_id"),
                "timestamp": item.get("created_at"),
                "message": item.get("action"),
                "payload": item,
            }
        )

    for row in feedback_payload.get("items") or []:
        if str(row.get("strategy_id") or "") != strategy_id:
            continue
        timeline.append(
            {
                "event_type": "FEEDBACK",
                "event_id": row.get("entry_id"),
                "timestamp": row.get("created_at"),
                "message": f"label={row.get('corrected_label')} taxonomy={row.get('reason_taxonomy')}",
                "payload": row,
            }
        )

    for row in model_update_payload.get("history") or []:
        if str(row.get("strategy_id") or "") != strategy_id:
            continue
        timeline.append(
            {
                "event_type": "MODEL_UPDATE",
                "event_id": row.get("job_id"),
                "timestamp": row.get("created_at") or row.get("updated_at"),
                "message": f"status={row.get('status')}",
                "payload": row,
            }
        )

    for index, drift in enumerate(status_payload.get("strategy_drift_alerts") or []):
        if str(drift.get("strategy") or "") != strategy_id:
            continue
        timeline.append(
            {
                "event_type": "DRIFT_SIGNAL",
                "event_id": f"{strategy_id}_drift_{index}",
                "timestamp": drift.get("detected_at") or datetime.now(timezone.utc).isoformat(),
                "message": f"severity={drift.get('severity')} reasons={drift.get('trigger_reason')}",
                "payload": drift,
            }
        )

    timeline.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    return timeline


def _compute_diff_preview(before_state: dict, after_state: dict) -> dict:
    changed = {}
    keys = set((before_state or {}).keys()) | set((after_state or {}).keys())
    for key in keys:
        before_val = (before_state or {}).get(key)
        after_val = (after_state or {}).get(key)
        if before_val != after_val:
            changed[key] = {"before": before_val, "after": after_val}
    return changed


def _feedback_density(feedback_items: list[dict], strategy_id: str, within_hours: int) -> int:
    now = datetime.now(timezone.utc)
    count = 0
    for item in feedback_items or []:
        if str(item.get("strategy_id") or "") != strategy_id:
            continue
        created_at = item.get("created_at")
        try:
            created_dt = datetime.fromisoformat(str(created_at))
        except Exception:
            continue
        if (now - created_dt).total_seconds() <= within_hours * 3600:
            count += 1
    return count


def _build_recommended_action(alert: dict, strategy_row: dict | None, feedback_items: list[dict]) -> dict:
    severity = str(alert.get("severity") or "LOW").upper()
    strategy_id = str(alert.get("strategy_id") or "")
    pnl = float((strategy_row or {}).get("pnl_rolling") or 0)
    reject_rate = float((strategy_row or {}).get("error_rate_pct") or 0)
    feedback_intensity = _feedback_density(feedback_items, strategy_id, within_hours=24)

    recommendation = "ACK"
    confidence = 55
    reason = "Düşük risk: temel onayla takip önerisi"

    if severity == "HIGH" and (reject_rate > 3 or pnl < 0):
        recommendation = "DISABLE"
        confidence = 87
        reason = "Yüksek drift + performans bozulması: geçici disable zinciri önerilir"
    elif severity in {"MEDIUM", "HIGH"} and feedback_intensity >= 3:
        recommendation = "RETRAIN"
        confidence = 78
        reason = "Feedback yoğunluğu yükseldi: retrain kuyruğu önerilir"
    elif severity in {"LOW", "MEDIUM"} and reject_rate <= 3:
        recommendation = "MUTE"
        confidence = 64
        reason = "Düşük/orta risk: kısa süreli mute ile gürültü azaltılabilir"

    return {
        "type": recommendation,
        "confidence": confidence,
        "reason": reason,
        "inputs": {
            "severity": severity,
            "pnl_rolling": pnl,
            "reject_rate_pct": reject_rate,
            "feedback_density_24h": feedback_intensity,
        },
    }


def _build_policy_suggestions(feedback_items: list[dict]) -> dict:
    now = datetime.now(timezone.utc)
    taxonomy_24h = {}
    taxonomy_7d = {}

    for item in feedback_items or []:
        taxonomy = str(item.get("reason_taxonomy") or "unknown")
        created_at = item.get("created_at")
        try:
            created_dt = datetime.fromisoformat(str(created_at))
        except Exception:
            continue
        age_seconds = (now - created_dt).total_seconds()
        if age_seconds <= 24 * 3600:
            taxonomy_24h[taxonomy] = int(taxonomy_24h.get(taxonomy, 0) + 1)
        if age_seconds <= 7 * 24 * 3600:
            taxonomy_7d[taxonomy] = int(taxonomy_7d.get(taxonomy, 0) + 1)

    rules = []
    if taxonomy_7d.get("threshold_too_strict", 0) >= 2:
        rules.append("threshold too strict → loosen öner")
    if taxonomy_7d.get("threshold_too_loose", 0) >= 2:
        rules.append("threshold too loose → tighten öner")
    if taxonomy_7d.get("feature_drift", 0) >= 2:
        rules.append("feature drift → retrain öner")
    if taxonomy_7d.get("data_quality", 0) >= 2:
        rules.append("data quality → source validation artır")

    return {
        "taxonomy_24h": taxonomy_24h,
        "taxonomy_7d": taxonomy_7d,
        "rules": rules,
    }


def _build_rollback_snapshots(action_history: list, strategy_id: str) -> list[dict]:
    snapshots = []
    for item in action_history or []:
        if str(item.get("strategy_id") or "") != strategy_id:
            continue
        snapshots.append(
            {
                "snapshot_trace_id": item.get("trace_id"),
                "timestamp": item.get("created_at"),
                "actor": "system_or_admin",
                "action_type": item.get("action"),
                "before_state": item.get("before_row") or {},
                "after_state": item.get("after_row") or {},
                "diff_preview": _compute_diff_preview(item.get("before_row") or {}, item.get("after_row") or {}),
                "rollback_scope": "single_strategy",
            }
        )
    snapshots.sort(key=lambda row: str(row.get("timestamp") or ""), reverse=True)
    return snapshots


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
        "phase_scope": "phase_2_rollout_bulk_rollback",
        "bulk_capabilities": ["pause", "resume", "throttle"],
        "rollout_policy": {
            "canary_steps": _VALID_ROLLOUT_STEPS,
            "auto_rollback_thresholds": {
                "health_score_min": _AUTO_ROLLBACK_HEALTH_THRESHOLD,
                "error_rate_max_pct": _AUTO_ROLLBACK_ERROR_THRESHOLD,
            },
        },
        "permission_matrix": {
            "super_admin": "full",
            "admin": "request_only",
            "ops": "read_only",
        },
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
    precheck = _build_rollout_precheck(row)
    return {
        "status": "ok",
        "strategy": row,
        "rollout_precheck": precheck,
        "execution_history": {
            "items": [],
            "reason": "Faz-2 kapsamında execution history aksiyonu henüz devrede değil.",
        },
        "trade_list": {
            "items": [],
            "reason": "Faz-2 kapsamında trade list aksiyonu henüz devrede değil.",
        },
        "governance_events": governance_events,
        "transition_history": row.get("transition_history") or [],
        "export": {
            "enabled": False,
            "reason": "Faz-3 backlog",
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


@router.get("/strategy/{strategy_id}/rollout-precheck")
def strategy_rollout_precheck(
    strategy_id: str,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    state = _load_control_state(db, current_admin, refresh=False)
    row = _find_row(state["rows"], strategy_id)
    precheck = _build_rollout_precheck(row)
    return {
        "status": "ok",
        "strategy_id": strategy_id,
        "precheck": precheck,
    }


@router.get("/strategy-control/drift-alerts")
def strategy_control_drift_alerts(
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    state = _load_control_state(db, current_admin, refresh=False)
    alerts = _build_drift_alert_rows(state["status_payload"], state["drift_alert_state"])
    strategy_map = {str(row.get("strategy_id") or ""): row for row in state["rows"]}
    feedback_items = state["feedback_payload"].get("items") or []
    alerts = [
        {
            **item,
            "recommended_action": _build_recommended_action(item, strategy_map.get(str(item.get("strategy_id") or "")), feedback_items),
        }
        for item in alerts
    ]
    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": alerts,
        "summary": {
            "open": len([item for item in alerts if item.get("status") == "OPEN"]),
            "acked": len([item for item in alerts if item.get("status") == "ACKED"]),
            "muted": len([item for item in alerts if item.get("status") == "MUTED"]),
            "ignored": len([item for item in alerts if item.get("status") == "IGNORED"]),
        },
    }


def _find_alert(alerts: list[dict], alert_id: str) -> dict:
    for item in alerts:
        if str(item.get("alert_id") or "") == str(alert_id):
            return item
    raise HTTPException(status_code=404, detail="drift_alert_not_found")


def _run_drift_action(
    *,
    action: str,
    alert_id: str,
    payload: DriftActionRequest,
    current_admin: User,
    db: Session,
):
    trace_id = f"drift_action_{uuid.uuid4().hex[:12]}"
    state = _load_control_state(db, current_admin, refresh=False)
    alerts = _build_drift_alert_rows(state["status_payload"], state["drift_alert_state"])
    alert = _find_alert(alerts, alert_id)
    strategy_id = str(alert.get("strategy_id") or "")

    if action == "ignore" and str(payload.confirm_phrase or "").strip().upper() != _DRIFT_IGNORE_CONFIRM:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message=f"Ignore için onay ifadesi zorunlu: {_DRIFT_IGNORE_CONFIRM}",
            state_snapshot=alert,
        )

    if action == "disable_strategy" and str(payload.confirm_phrase or "").strip().upper() != _DRIFT_DISABLE_CONFIRM:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message=f"Disable için onay ifadesi zorunlu: {_DRIFT_DISABLE_CONFIRM}",
            state_snapshot=alert,
        )

    drift_alert_state = state["drift_alert_state"]
    before_state = _deep_copy(dict(drift_alert_state.get(alert_id) or {}))
    now_iso = datetime.now(timezone.utc).isoformat()
    current_state = dict(before_state)
    current_state.update({"last_action": action, "last_action_trace_id": trace_id, "updated_at": now_iso})

    linked_action_result = None
    if action == "ack":
        current_state["acked"] = True
    elif action == "mute":
        duration_hours = int(payload.mute_duration_hours or 1)
        if duration_hours not in {1, 24, 168}:
            return _result_payload(
                status="rejected",
                trace_id=trace_id,
                message="Mute süresi sadece 1h / 24h / 7d (168h) olabilir.",
                state_snapshot=alert,
            )
        muted_until = datetime.now(timezone.utc).timestamp() + (duration_hours * 3600)
        current_state["muted_until"] = datetime.fromtimestamp(muted_until, tz=timezone.utc).isoformat()
    elif action == "ignore":
        current_state["ignored"] = True
    elif action == "retrain":
        current_state["retrain_status"] = "queued"
        current_state["retrain_job_id"] = f"retrain_{uuid.uuid4().hex[:10]}"
    elif action == "disable_strategy":
        if payload.dry_run:
            linked_action_result = {
                "status": "dry_run",
                "message": "Dry-run: throttle->pause->disable zinciri yazılmadı.",
            }
        else:
            throttle_result = _run_strategy_action(
                action="throttle",
                strategy_id=strategy_id,
                payload=StrategyControlActionRequest(reason=f"DRIFT_DISABLE::{payload.reason}", throttle_level="L2", dry_run=False),
                current_admin=current_admin,
                db=db,
            )
            pause_result = _run_strategy_action(
                action="pause",
                strategy_id=strategy_id,
                payload=StrategyControlActionRequest(reason=f"DRIFT_DISABLE::{payload.reason}", dry_run=False),
                current_admin=current_admin,
                db=db,
            )
            disable_result = _run_strategy_action(
                action="disable",
                strategy_id=strategy_id,
                payload=StrategyControlActionRequest(
                    reason=f"DRIFT_DISABLE::{payload.reason}",
                    confirm_phrase=_DISABLE_CONFIRM,
                    dry_run=False,
                ),
                current_admin=current_admin,
                db=db,
            )
            linked_action_result = {
                "throttle": throttle_result,
                "pause": pause_result,
                "disable": disable_result,
            }
            current_state["disabled_via_drift"] = True
    else:
        raise HTTPException(status_code=400, detail="unsupported_drift_action")

    drift_alert_state[alert_id] = current_state
    if not payload.dry_run:
        _cache_set(pipeline_runtime.cache, state["keys"]["drift_alert"], drift_alert_state)

    latest_alert = _find_alert(_build_drift_alert_rows(state["status_payload"], drift_alert_state), alert_id)
    strategy_map = {str(row.get("strategy_id") or ""): row for row in state["rows"]}
    latest_alert["recommended_action"] = _build_recommended_action(
        latest_alert,
        strategy_map.get(str(latest_alert.get("strategy_id") or "")),
        state["feedback_payload"].get("items") or [],
    )
    create_audit_log(
        db,
        action=f"FUTURES_STRATEGY_DRIFT_{action.upper()}",
        entity_type="futures_strategy_control",
        entity_id=alert_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="critical" if action == "disable_strategy" else "warning",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "confirm_phrase": payload.confirm_phrase,
            "mute_duration_hours": payload.mute_duration_hours,
            "dry_run": payload.dry_run,
            "before_state": before_state,
            "after_state": current_state,
            "strategy_id": strategy_id,
            "linked_action_result": linked_action_result,
            "deep_link": latest_alert.get("deep_link"),
        },
    )

    return _result_payload(
        status="dry_run" if payload.dry_run else "success",
        trace_id=trace_id,
        message=f"Drift aksiyonu uygulandı: {action}",
        state_snapshot=latest_alert,
        extra={
            "before_state": before_state,
            "after_state": current_state,
            "linked_action_result": linked_action_result,
            "deep_link": latest_alert.get("deep_link"),
        },
    )


@router.post("/drift-alert/{alert_id}/ack")
def drift_alert_ack(
    alert_id: str,
    payload: DriftActionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return _run_drift_action(action="ack", alert_id=alert_id, payload=payload, current_admin=current_admin, db=db)


@router.post("/drift-alert/{alert_id}/mute")
def drift_alert_mute(
    alert_id: str,
    payload: DriftActionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return _run_drift_action(action="mute", alert_id=alert_id, payload=payload, current_admin=current_admin, db=db)


@router.post("/drift-alert/{alert_id}/ignore")
def drift_alert_ignore(
    alert_id: str,
    payload: DriftActionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return _run_drift_action(action="ignore", alert_id=alert_id, payload=payload, current_admin=current_admin, db=db)


@router.post("/drift-alert/{alert_id}/disable-strategy")
def drift_alert_disable_strategy(
    alert_id: str,
    payload: DriftActionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return _run_drift_action(action="disable_strategy", alert_id=alert_id, payload=payload, current_admin=current_admin, db=db)


@router.post("/drift-alert/{alert_id}/retrain")
def drift_alert_retrain(
    alert_id: str,
    payload: DriftActionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return _run_drift_action(action="retrain", alert_id=alert_id, payload=payload, current_admin=current_admin, db=db)


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
        return _result_payload(status="rejected", trace_id=trace_id, message=flow_message, state_snapshot=before_row)

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
    rollout_payload = state["rollout_payload"]

    lifecycle_before = _deep_copy(lifecycle_registry)
    throttle_before = _deep_copy(throttle_payload)
    manual_before = _deep_copy(manual_controls)
    rollout_before = _deep_copy(rollout_payload)

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
        _set_lifecycle_state(
            lifecycle_registry,
            strategy_id=strategy_id,
            next_state="DISABLED",
            reason=f"MANUAL_DECOMMISSION:{payload.reason}",
        )
        _set_throttle_state(throttle_payload, strategy_id=strategy_id, level="L3")
        next_control_state = "DECOMMISSIONED"
        rollback_reference = f"rollback_ref:{trace_id}"
        message = f"{strategy_id} decommission edildi"
    else:
        raise HTTPException(status_code=400, detail="unsupported_action")

    _set_manual_state(manual_controls, strategy_id=strategy_id, control_state=next_control_state, reason=payload.reason, trace_id=trace_id)

    after_rows = _compose_strategy_rows(state["status_payload"], lifecycle_registry, throttle_payload, manual_controls, rollout_payload)
    after_row = _find_row(after_rows, strategy_id)
    action_status = "dry_run" if payload.dry_run else "success"

    if not payload.dry_run:
        _cache_set(pipeline_runtime.cache, state["keys"]["lifecycle"], lifecycle_registry)
        _cache_set(pipeline_runtime.cache, state["keys"]["throttle"], throttle_payload)
        _cache_set(pipeline_runtime.cache, state["keys"]["manual"], manual_controls)

        history = _append_action_history(
            state["action_history"],
            {
                "trace_id": trace_id,
                "action": action,
                "strategy_id": strategy_id,
                "before_row": before_row,
                "after_row": after_row,
                "lifecycle_before": lifecycle_before,
                "throttle_before": throttle_before,
                "manual_before": manual_before,
                "rollout_before": rollout_before,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        _cache_set(pipeline_runtime.cache, state["keys"]["history"], history)

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


@router.post("/strategy/{strategy_id}/promote-shadow")
def strategy_promote_shadow(
    strategy_id: str,
    payload: StrategyRolloutRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    trace_id = f"strategy_promote_{uuid.uuid4().hex[:12]}"
    if str(payload.confirm_phrase or "").strip().upper() != _PROMOTE_CONFIRM:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message=f"Promote shadow için onay ifadesi zorunlu: {_PROMOTE_CONFIRM}",
            state_snapshot={"strategy_id": strategy_id},
        )

    state = _load_control_state(db, current_admin, refresh=False)
    before_row = _find_row(state["rows"], strategy_id)
    precheck = _build_rollout_precheck(before_row)
    if before_row.get("shadow_live_state") != "SHADOW":
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message="Promote shadow sadece SHADOW strategy için kullanılabilir.",
            state_snapshot=before_row,
            extra={"precheck": precheck},
        )
    if precheck.get("status") != "pass":
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message="Promote shadow pre-check başarısız.",
            state_snapshot=before_row,
            extra={"precheck": precheck},
        )

    rollout_payload = state["rollout_payload"]
    rollout_before = _deep_copy(rollout_payload)
    _set_rollout_state(
        rollout_payload,
        strategy_id=strategy_id,
        mode="LIVE_CANARY",
        percentage=10,
        reason=f"PROMOTE_SHADOW:{payload.reason}",
    )

    after_rows = _compose_strategy_rows(
        state["status_payload"],
        state["lifecycle_registry"],
        state["throttle_payload"],
        state["manual_controls"],
        rollout_payload,
    )
    after_row = _find_row(after_rows, strategy_id)

    if not payload.dry_run:
        _cache_set(pipeline_runtime.cache, state["keys"]["rollout"], rollout_payload)
        history = _append_action_history(
            state["action_history"],
            {
                "trace_id": trace_id,
                "action": "promote_shadow",
                "strategy_id": strategy_id,
                "before_row": before_row,
                "after_row": after_row,
                "lifecycle_before": _deep_copy(state["lifecycle_registry"]),
                "throttle_before": _deep_copy(state["throttle_payload"]),
                "manual_before": _deep_copy(state["manual_controls"]),
                "rollout_before": rollout_before,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        _cache_set(pipeline_runtime.cache, state["keys"]["history"], history)

    create_audit_log(
        db,
        action="FUTURES_STRATEGY_PROMOTE_SHADOW",
        entity_type="futures_strategy_control",
        entity_id=strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "confirm_phrase": payload.confirm_phrase,
            "dry_run": payload.dry_run,
            "precheck": precheck,
            "before_state": before_row,
            "after_state": after_row,
        },
    )

    return _result_payload(
        status="dry_run" if payload.dry_run else "success",
        trace_id=trace_id,
        message=f"{strategy_id} shadow→live canary %10 promote edildi",
        state_snapshot=after_row,
        extra={"precheck": precheck, "before_state": before_row, "after_state": after_row},
    )


@router.post("/strategy/{strategy_id}/rollout")
def strategy_rollout(
    strategy_id: str,
    payload: StrategyRolloutRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    trace_id = f"strategy_rollout_{uuid.uuid4().hex[:12]}"
    if str(payload.confirm_phrase or "").strip().upper() != _ROLLOUT_CONFIRM:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message=f"Rollout için onay ifadesi zorunlu: {_ROLLOUT_CONFIRM}",
            state_snapshot={"strategy_id": strategy_id},
        )

    if int(payload.rollout_percentage) not in _VALID_ROLLOUT_STEPS:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message=f"Rollout yüzdesi sadece {_VALID_ROLLOUT_STEPS} olabilir.",
            state_snapshot={"strategy_id": strategy_id},
        )

    state = _load_control_state(db, current_admin, refresh=False)
    before_row = _find_row(state["rows"], strategy_id)
    precheck = _build_rollout_precheck(before_row)
    if precheck.get("status") != "pass":
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message="Rollout pre-check başarısız.",
            state_snapshot=before_row,
            extra={"precheck": precheck},
        )

    rollout_payload = state["rollout_payload"]
    rollout_before = _deep_copy(rollout_payload)

    requested = int(payload.rollout_percentage)
    mode = "LIVE" if requested == 100 else "LIVE_CANARY"
    _set_rollout_state(
        rollout_payload,
        strategy_id=strategy_id,
        mode=mode,
        percentage=requested,
        reason=f"ROLLOUT_{requested}:{payload.reason}",
    )

    auto_rollback_triggered = False
    auto_rollback_reason = []
    if before_row.get("health_score", 0) < _AUTO_ROLLBACK_HEALTH_THRESHOLD:
        auto_rollback_triggered = True
        auto_rollback_reason.append(f"health<{_AUTO_ROLLBACK_HEALTH_THRESHOLD}")
    if before_row.get("error_rate_pct", 0) > _AUTO_ROLLBACK_ERROR_THRESHOLD:
        auto_rollback_triggered = True
        auto_rollback_reason.append(f"error_rate>{_AUTO_ROLLBACK_ERROR_THRESHOLD}%")

    if auto_rollback_triggered:
        rollout_payload = rollout_before

    after_rows = _compose_strategy_rows(
        state["status_payload"],
        state["lifecycle_registry"],
        state["throttle_payload"],
        state["manual_controls"],
        rollout_payload,
    )
    after_row = _find_row(after_rows, strategy_id)

    if not payload.dry_run:
        _cache_set(pipeline_runtime.cache, state["keys"]["rollout"], rollout_payload)
        history = _append_action_history(
            state["action_history"],
            {
                "trace_id": trace_id,
                "action": "rollout",
                "strategy_id": strategy_id,
                "before_row": before_row,
                "after_row": after_row,
                "lifecycle_before": _deep_copy(state["lifecycle_registry"]),
                "throttle_before": _deep_copy(state["throttle_payload"]),
                "manual_before": _deep_copy(state["manual_controls"]),
                "rollout_before": rollout_before,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        _cache_set(pipeline_runtime.cache, state["keys"]["history"], history)

    create_audit_log(
        db,
        action="FUTURES_STRATEGY_ROLLOUT_APPLIED",
        entity_type="futures_strategy_control",
        entity_id=strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="critical" if auto_rollback_triggered else "warning",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "confirm_phrase": payload.confirm_phrase,
            "dry_run": payload.dry_run,
            "requested_rollout_percentage": requested,
            "precheck": precheck,
            "auto_rollback_triggered": auto_rollback_triggered,
            "auto_rollback_reason": auto_rollback_reason,
            "before_state": before_row,
            "after_state": after_row,
        },
    )

    status_value = "auto_rollback" if auto_rollback_triggered else ("dry_run" if payload.dry_run else "success")
    message = (
        f"Auto rollback tetiklendi: {'; '.join(auto_rollback_reason)}"
        if auto_rollback_triggered
        else f"Rollout %{requested} uygulandı"
    )
    return _result_payload(
        status=status_value,
        trace_id=trace_id,
        message=message,
        state_snapshot=after_row,
        extra={
            "precheck": precheck,
            "before_state": before_row,
            "after_state": after_row,
            "auto_rollback": {
                "triggered": auto_rollback_triggered,
                "reason": auto_rollback_reason,
                "thresholds": {
                    "health_score_min": _AUTO_ROLLBACK_HEALTH_THRESHOLD,
                    "error_rate_max_pct": _AUTO_ROLLBACK_ERROR_THRESHOLD,
                },
                "previous_state": before_row,
            },
        },
    )


@router.post("/strategy/{strategy_id}/rollback")
def strategy_rollback_last_action(
    strategy_id: str,
    payload: StrategyRollbackRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    trace_id = f"strategy_rollback_{uuid.uuid4().hex[:12]}"
    if str(payload.confirm_phrase or "").strip().upper() != _ROLLBACK_CONFIRM:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message=f"Rollback için onay ifadesi zorunlu: {_ROLLBACK_CONFIRM}",
            state_snapshot={"strategy_id": strategy_id},
        )

    state = _load_control_state(db, current_admin, refresh=False)
    history = list(state["action_history"] or [])
    target_index = -1
    for idx in range(len(history) - 1, -1, -1):
        if str(history[idx].get("strategy_id") or "") == strategy_id:
            target_index = idx
            break

    if target_index < 0:
        row = _find_row(state["rows"], strategy_id)
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message="Rollback için önceki aksiyon bulunamadı.",
            state_snapshot=row,
        )

    last_action = history[target_index]
    before_row = _find_row(state["rows"], strategy_id)

    lifecycle_registry = _deep_copy(last_action.get("lifecycle_before") or state["lifecycle_registry"])
    throttle_payload = _deep_copy(last_action.get("throttle_before") or state["throttle_payload"])
    manual_controls = _deep_copy(last_action.get("manual_before") or state["manual_controls"])
    rollout_payload = _deep_copy(last_action.get("rollout_before") or state["rollout_payload"])

    after_rows = _compose_strategy_rows(
        state["status_payload"],
        lifecycle_registry,
        throttle_payload,
        manual_controls,
        rollout_payload,
    )
    after_row = _find_row(after_rows, strategy_id)

    if not payload.dry_run:
        _cache_set(pipeline_runtime.cache, state["keys"]["lifecycle"], lifecycle_registry)
        _cache_set(pipeline_runtime.cache, state["keys"]["throttle"], throttle_payload)
        _cache_set(pipeline_runtime.cache, state["keys"]["manual"], manual_controls)
        _cache_set(pipeline_runtime.cache, state["keys"]["rollout"], rollout_payload)
        del history[target_index]
        _cache_set(pipeline_runtime.cache, state["keys"]["history"], history)

    create_audit_log(
        db,
        action="FUTURES_STRATEGY_ROLLBACK_LAST_ACTION",
        entity_type="futures_strategy_control",
        entity_id=strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="critical",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "confirm_phrase": payload.confirm_phrase,
            "dry_run": payload.dry_run,
            "rolled_back_action": last_action.get("action"),
            "rolled_back_trace_id": last_action.get("trace_id"),
            "before_state": before_row,
            "after_state": after_row,
        },
    )

    return _result_payload(
        status="dry_run" if payload.dry_run else "success",
        trace_id=trace_id,
        message=f"Son aksiyon rollback edildi: {last_action.get('action')}",
        state_snapshot=after_row,
        extra={
            "before_state": before_row,
            "after_state": after_row,
            "rolled_back_action": last_action.get("action"),
            "rolled_back_trace_id": last_action.get("trace_id"),
        },
    )


@router.post("/strategy/bulk-action")
def strategy_bulk_action(
    payload: StrategyBulkActionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    trace_id = f"strategy_bulk_{uuid.uuid4().hex[:12]}"
    action = str(payload.action or "").strip().lower()
    if action not in {"pause", "resume", "throttle"}:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message="Bulk action sadece pause/resume/throttle destekler.",
            state_snapshot={"strategy_ids": payload.strategy_ids},
        )

    expected_confirm = _resolve_bulk_confirm_phrase(action)
    if str(payload.confirm_phrase or "").strip().upper() != expected_confirm:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message=f"Bulk action onayı zorunlu: {expected_confirm}",
            state_snapshot={"strategy_ids": payload.strategy_ids, "action": action},
        )

    results = []
    success_count = 0
    rejected_count = 0
    for strategy_id in payload.strategy_ids:
        result = _run_strategy_action(
            action=action,
            strategy_id=strategy_id,
            payload=StrategyControlActionRequest(
                reason=f"BULK::{payload.reason}",
                confirm_phrase=None,
                throttle_level=payload.throttle_level,
                dry_run=payload.dry_run,
            ),
            current_admin=current_admin,
            db=db,
        )
        results.append({"strategy_id": strategy_id, **result})
        if result.get("status") in {"success", "dry_run"}:
            success_count += 1
        else:
            rejected_count += 1

    create_audit_log(
        db,
        action="FUTURES_STRATEGY_BULK_ACTION",
        entity_type="futures_strategy_control",
        entity_id="bulk",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="critical" if rejected_count > 0 else "warning",
        details={
            "trace_id": trace_id,
            "bulk_action": action,
            "strategy_ids": payload.strategy_ids,
            "reason": payload.reason,
            "confirm_phrase": payload.confirm_phrase,
            "dry_run": payload.dry_run,
            "success_count": success_count,
            "rejected_count": rejected_count,
        },
    )

    state_snapshot = {
        "bulk_action": action,
        "strategy_ids": payload.strategy_ids,
        "success_count": success_count,
        "rejected_count": rejected_count,
    }
    status_value = "success" if success_count > 0 else "rejected"
    return _result_payload(
        status=status_value,
        trace_id=trace_id,
        message=f"Bulk {action} tamamlandı: success={success_count}, rejected={rejected_count}",
        state_snapshot=state_snapshot,
        extra={"results": results},
    )


@router.post("/strategy/{strategy_id}/feedback-label")
def strategy_feedback_label(
    strategy_id: str,
    payload: FeedbackLabelRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    trace_id = f"feedback_{uuid.uuid4().hex[:12]}"
    state = _load_control_state(db, current_admin, refresh=False)

    alerts = _build_drift_alert_rows(state["status_payload"], state["drift_alert_state"])
    related_alert = None
    for alert in alerts:
        if str(alert.get("alert_id") or "") == str(payload.drift_alert_id) and str(alert.get("strategy_id") or "") == strategy_id:
            related_alert = alert
            break
    if not related_alert:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message="Feedback drift context eşleşmedi (strategy + drift_alert_id).",
            state_snapshot={"strategy_id": strategy_id, "drift_alert_id": payload.drift_alert_id},
        )

    feedback_payload = state["feedback_payload"]
    version_map = feedback_payload.get("version_by_strategy") or {}
    current_version = int(version_map.get(strategy_id) or 0)
    next_version = current_version + 1
    entry_id = f"fb_{uuid.uuid4().hex[:10]}"
    entry = {
        "entry_id": entry_id,
        "strategy_id": strategy_id,
        "drift_alert_id": payload.drift_alert_id,
        "corrected_label": payload.corrected_label,
        "reason_taxonomy": payload.reason_taxonomy,
        "reason": payload.reason,
        "sample_link": payload.sample_link,
        "related_data_slice": payload.related_data_slice or {},
        "dataset_version": next_version,
        "trace_id": trace_id,
        "created_by": current_admin.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if not payload.dry_run:
        items = list(feedback_payload.get("items") or [])
        items.append(entry)
        feedback_payload["items"] = items[-1000:]
        version_map[strategy_id] = next_version
        feedback_payload["version_by_strategy"] = version_map
        _cache_set(pipeline_runtime.cache, state["keys"]["feedback"], feedback_payload)

    create_audit_log(
        db,
        action="FUTURES_STRATEGY_FEEDBACK_LABEL",
        entity_type="futures_strategy_control",
        entity_id=strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "dry_run": payload.dry_run,
            "entry": entry,
            "drift_context": related_alert,
        },
    )

    return _result_payload(
        status="dry_run" if payload.dry_run else "success",
        trace_id=trace_id,
        message="Feedback label correction kaydedildi.",
        state_snapshot=entry,
        extra={"dataset_version": next_version},
    )


@router.get("/strategy/{strategy_id}/feedback")
def strategy_feedback_list(
    strategy_id: str,
    drift_alert_id: str | None = Query(default=None),
    taxonomy: str | None = Query(default=None),
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    _ = db
    state = _load_control_state(db, current_admin, refresh=False)
    rows = [item for item in (state["feedback_payload"].get("items") or []) if str(item.get("strategy_id") or "") == strategy_id]
    if drift_alert_id:
        rows = [item for item in rows if str(item.get("drift_alert_id") or "") == str(drift_alert_id)]
    if taxonomy:
        rows = [item for item in rows if str(item.get("reason_taxonomy") or "").lower() == str(taxonomy).lower()]
    rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return {
        "status": "ok",
        "strategy_id": strategy_id,
        "items": rows,
        "dataset_version": int((state["feedback_payload"].get("version_by_strategy") or {}).get(strategy_id) or 0),
    }


@router.post("/strategy/{strategy_id}/trigger-model-update")
def strategy_trigger_model_update(
    strategy_id: str,
    payload: ModelUpdateTriggerRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    trace_id = f"model_update_{uuid.uuid4().hex[:12]}"
    state = _load_control_state(db, current_admin, refresh=False)
    refreshed = _refresh_model_update_jobs(state["model_update_payload"])
    model_payload = refreshed["payload"]
    if refreshed["changed"]:
        _cache_set(pipeline_runtime.cache, state["keys"]["model_update"], model_payload)

    current_job = dict((model_payload.get("by_strategy") or {}).get(strategy_id) or {})
    if str(current_job.get("status") or "") in {"queued", "running"}:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message="Bu strategy için çalışan model update job zaten var.",
            state_snapshot=current_job,
        )

    dataset_version = payload.dataset_version
    if dataset_version is None:
        dataset_version = int((state["feedback_payload"].get("version_by_strategy") or {}).get(strategy_id) or 0)

    job_id = f"mu_{uuid.uuid4().hex[:12]}"
    job = {
        "job_id": job_id,
        "strategy_id": strategy_id,
        "status": "queued",
        "dataset_version": int(dataset_version),
        "reason": payload.reason,
        "trace_id": trace_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_admin.id,
    }

    if not payload.dry_run:
        by_strategy = model_payload.get("by_strategy") or {}
        by_strategy[strategy_id] = job
        model_payload["by_strategy"] = by_strategy
        history = list(model_payload.get("history") or [])
        history.append(job)
        model_payload["history"] = history[-500:]
        _cache_set(pipeline_runtime.cache, state["keys"]["model_update"], model_payload)

    create_audit_log(
        db,
        action="FUTURES_STRATEGY_MODEL_UPDATE_TRIGGERED",
        entity_type="futures_strategy_control",
        entity_id=strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "dataset_version": dataset_version,
            "dry_run": payload.dry_run,
            "job": job,
        },
    )

    return _result_payload(
        status="dry_run" if payload.dry_run else "success",
        trace_id=trace_id,
        message="Model update job queued.",
        state_snapshot=job,
    )


@router.get("/strategy/{strategy_id}/model-update-status")
def strategy_model_update_status(
    strategy_id: str,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    state = _load_control_state(db, current_admin, refresh=False)
    refreshed = _refresh_model_update_jobs(state["model_update_payload"])
    model_payload = refreshed["payload"]
    if refreshed["changed"]:
        _cache_set(pipeline_runtime.cache, state["keys"]["model_update"], model_payload)

    current_job = dict((model_payload.get("by_strategy") or {}).get(strategy_id) or {})
    history = [item for item in (model_payload.get("history") or []) if str(item.get("strategy_id") or "") == strategy_id]
    history.sort(key=lambda item: str(item.get("created_at") or item.get("updated_at") or ""), reverse=True)
    return {
        "status": "ok",
        "strategy_id": strategy_id,
        "current_job": current_job,
        "history": history[:50],
    }


@router.get("/strategy/{strategy_id}/timeline-export")
def strategy_timeline_export(
    strategy_id: str,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    trace_id = f"timeline_export_{uuid.uuid4().hex[:12]}"
    state = _load_control_state(db, current_admin, refresh=False)
    refreshed = _refresh_model_update_jobs(state["model_update_payload"])
    model_payload = refreshed["payload"]
    if refreshed["changed"]:
        _cache_set(pipeline_runtime.cache, state["keys"]["model_update"], model_payload)

    timeline = _build_strategy_timeline(
        strategy_id=strategy_id,
        status_payload=state["status_payload"],
        action_history=state["action_history"],
        feedback_payload=state["feedback_payload"],
        model_update_payload=model_payload,
    )

    create_audit_log(
        db,
        action="FUTURES_STRATEGY_TIMELINE_EXPORTED",
        entity_type="futures_strategy_control",
        entity_id=strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "trace_id": trace_id,
            "format": format,
            "count": len(timeline),
        },
    )

    if format == "csv":
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["event_type", "event_id", "timestamp", "message"])
        for item in timeline:
            writer.writerow([item.get("event_type"), item.get("event_id"), item.get("timestamp"), item.get("message")])
        csv_text = stream.getvalue()
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={strategy_id}_timeline.csv"},
        )

    return {
        "status": "success",
        "trace_id": trace_id,
        "message": "Timeline export hazırlandı.",
        "state_snapshot": {
            "strategy_id": strategy_id,
            "format": "json",
            "count": len(timeline),
        },
        "items": timeline,
    }


@router.get("/strategy-control/policy-suggestions")
def strategy_policy_suggestions(
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    state = _load_control_state(db, current_admin, refresh=False)
    summary = _build_policy_suggestions(state["feedback_payload"].get("items") or [])
    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "state_snapshot": {
            "rules_count": len(summary.get("rules") or []),
        },
        "summary": summary,
    }


@router.get("/strategy/{strategy_id}/rollback-snapshots")
def strategy_rollback_snapshots(
    strategy_id: str,
    limit: int = Query(default=30, ge=1, le=200),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    state = _load_control_state(db, current_admin, refresh=False)
    snapshots = _build_rollback_snapshots(state["action_history"], strategy_id)
    return {
        "status": "ok",
        "strategy_id": strategy_id,
        "items": snapshots[:limit],
        "permission_matrix": {
            "super_admin": "full",
            "admin": "request_only",
            "ops": "read_only",
        },
    }


@router.post("/strategy/{strategy_id}/rollback-request")
def strategy_rollback_request_create(
    strategy_id: str,
    payload: RollbackRequestCreateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    trace_id = f"rollback_req_{uuid.uuid4().hex[:12]}"
    state = _load_control_state(db, current_admin, refresh=False)
    snapshots = _build_rollback_snapshots(state["action_history"], strategy_id)
    snapshot = next((item for item in snapshots if str(item.get("snapshot_trace_id") or "") == str(payload.snapshot_trace_id)), None)
    if not snapshot:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message="Snapshot bulunamadı.",
            state_snapshot={"strategy_id": strategy_id, "snapshot_trace_id": payload.snapshot_trace_id},
        )

    request_id = f"apr_{uuid.uuid4().hex[:10]}"
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    request_item = {
        "request_id": request_id,
        "strategy_id": strategy_id,
        "snapshot_trace_id": payload.snapshot_trace_id,
        "status": "pending",
        "requested_by": current_admin.id,
        "requested_role": current_admin.role.value,
        "reason": payload.reason,
        "preview": {
            "action_type": snapshot.get("action_type"),
            "diff_preview": snapshot.get("diff_preview") or {},
        },
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
    }

    approvals = state["approval_requests_payload"]
    items = list(approvals.get("items") or [])
    items.append(request_item)
    approvals["items"] = items[-500:]
    _cache_set(pipeline_runtime.cache, state["keys"]["approval_requests"], approvals)

    create_audit_log(
        db,
        action="FUTURES_STRATEGY_ROLLBACK_REQUEST_CREATED",
        entity_type="futures_strategy_control",
        entity_id=request_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "request": request_item,
        },
    )

    return _result_payload(
        status="success",
        trace_id=trace_id,
        message="Rollback request oluşturuldu, super_admin onayı bekleniyor.",
        state_snapshot=request_item,
        extra={"rollback_reference": f"rollback_ref:{payload.snapshot_trace_id}"},
    )


@router.get("/strategy/approval-requests")
def strategy_approval_requests(
    status: str | None = Query(default=None),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    state = _load_control_state(db, current_admin, refresh=False)
    all_items = list(state["approval_requests_payload"].get("items") or [])
    now = datetime.now(timezone.utc)

    for item in all_items:
        if item.get("status") == "pending":
            try:
                expires = datetime.fromisoformat(str(item.get("expires_at")))
                if expires <= now:
                    item["status"] = "expired"
            except Exception:
                pass

    items = list(all_items)
    if status:
        items = [item for item in items if str(item.get("status") or "") == status]

    if current_admin.role.value != "super_admin":
        items = [item for item in items if str(item.get("requested_by") or "") == current_admin.id]

    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    _cache_set(pipeline_runtime.cache, state["keys"]["approval_requests"], {"items": all_items})
    return {
        "status": "ok",
        "items": items,
        "permission_matrix": {
            "super_admin": "full",
            "admin": "request_only",
            "ops": "read_only",
        },
    }


def _decision_approval_request(
    *,
    request_id: str,
    decision: str,
    payload: ApprovalDecisionRequest,
    current_admin: User,
    db: Session,
):
    trace_id = f"approval_decision_{uuid.uuid4().hex[:12]}"
    state = _load_control_state(db, current_admin, refresh=False)
    approvals = state["approval_requests_payload"]
    items = list(approvals.get("items") or [])

    target = None
    target_index = -1
    for index, item in enumerate(items):
        if str(item.get("request_id") or "") == str(request_id):
            target = item
            target_index = index
            break
    if not target:
        raise HTTPException(status_code=404, detail="approval_request_not_found")

    if str(target.get("status") or "") != "pending":
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message="Request pending değil.",
            state_snapshot=target,
        )

    try:
        expires = datetime.fromisoformat(str(target.get("expires_at")))
        if expires <= datetime.now(timezone.utc):
            target["status"] = "expired"
            items[target_index] = target
            approvals["items"] = items
            _cache_set(pipeline_runtime.cache, state["keys"]["approval_requests"], approvals)
            return _result_payload(
                status="rejected",
                trace_id=trace_id,
                message="Request süresi doldu (expired).",
                state_snapshot=target,
            )
    except Exception:
        pass

    if decision == "reject":
        target["status"] = "rejected"
        target["decision_reason"] = payload.reason
        target["decided_by"] = current_admin.id
        target["decided_at"] = datetime.now(timezone.utc).isoformat()
        target["decision_trace_id"] = trace_id
        items[target_index] = target
        approvals["items"] = items
        _cache_set(pipeline_runtime.cache, state["keys"]["approval_requests"], approvals)

        create_audit_log(
            db,
            action="FUTURES_STRATEGY_ROLLBACK_REQUEST_REJECTED",
            entity_type="futures_strategy_control",
            entity_id=request_id,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            severity="warning",
            details={"trace_id": trace_id, "reason": payload.reason, "request": target},
        )
        return _result_payload(
            status="success",
            trace_id=trace_id,
            message="Rollback request reddedildi.",
            state_snapshot=target,
        )

    strategy_id = str(target.get("strategy_id") or "")
    snapshot_trace = str(target.get("snapshot_trace_id") or "")
    snapshot_source = None
    for history_item in state["action_history"]:
        if str(history_item.get("strategy_id") or "") == strategy_id and str(history_item.get("trace_id") or "") == snapshot_trace:
            snapshot_source = history_item
            break
    if not snapshot_source:
        return _result_payload(
            status="rejected",
            trace_id=trace_id,
            message="Rollback snapshot kaynağı bulunamadı.",
            state_snapshot=target,
        )

    lifecycle_registry = _deep_copy(snapshot_source.get("lifecycle_before") or state["lifecycle_registry"])
    throttle_payload = _deep_copy(snapshot_source.get("throttle_before") or state["throttle_payload"])
    manual_controls = _deep_copy(snapshot_source.get("manual_before") or state["manual_controls"])
    rollout_payload = _deep_copy(snapshot_source.get("rollout_before") or state["rollout_payload"])

    _cache_set(pipeline_runtime.cache, state["keys"]["lifecycle"], lifecycle_registry)
    _cache_set(pipeline_runtime.cache, state["keys"]["throttle"], throttle_payload)
    _cache_set(pipeline_runtime.cache, state["keys"]["manual"], manual_controls)
    _cache_set(pipeline_runtime.cache, state["keys"]["rollout"], rollout_payload)

    target["status"] = "approved"
    target["decision_reason"] = payload.reason
    target["decided_by"] = current_admin.id
    target["decided_at"] = datetime.now(timezone.utc).isoformat()
    target["decision_trace_id"] = trace_id
    target["rollback_reference"] = f"rollback_ref:{snapshot_trace}"
    items[target_index] = target
    approvals["items"] = items
    _cache_set(pipeline_runtime.cache, state["keys"]["approval_requests"], approvals)

    after_rows = _compose_strategy_rows(
        state["status_payload"],
        lifecycle_registry,
        throttle_payload,
        manual_controls,
        rollout_payload,
    )
    after_row = _find_row(after_rows, strategy_id)

    create_audit_log(
        db,
        action="FUTURES_STRATEGY_ROLLBACK_APPROVED_AND_APPLIED",
        entity_type="futures_strategy_control",
        entity_id=request_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="critical",
        details={
            "trace_id": trace_id,
            "reason": payload.reason,
            "request": target,
            "after_state": after_row,
        },
    )

    return _result_payload(
        status="success",
        trace_id=trace_id,
        message="Rollback request onaylandı ve uygulandı.",
        state_snapshot=after_row,
        extra={"approval_request": target},
    )


@router.post("/strategy/approval-requests/{request_id}/approve")
def strategy_approval_request_approve(
    request_id: str,
    payload: ApprovalDecisionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return _decision_approval_request(
        request_id=request_id,
        decision="approve",
        payload=payload,
        current_admin=current_admin,
        db=db,
    )


@router.post("/strategy/approval-requests/{request_id}/reject")
def strategy_approval_request_reject(
    request_id: str,
    payload: ApprovalDecisionRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return _decision_approval_request(
        request_id=request_id,
        decision="reject",
        payload=payload,
        current_admin=current_admin,
        db=db,
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
