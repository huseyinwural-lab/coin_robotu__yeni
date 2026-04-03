import json
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db, redis_client
from core.runtime_stream import runtime_stream_hub
from deps import require_admin
from models import AlertPolicy, AuditLog, PermissionDriftEvent, SystemAlert, User, UserExchangeConnection, UserRole
from runtime_control import (
    MAX_OVERRIDE_TTL_MINUTES,
    cancel_override,
    create_override,
    flush_pipeline_queues,
    force_new_ws_session,
    force_pipeline_resync,
    get_guard_telemetry,
    get_ws_health,
    list_active_overrides,
    list_override_history,
    manual_health_check,
    reconnect_ws,
    restart_runtime_service,
)
from services.audit_service import create_audit_log
from services.live_mode_service import release_gate_view
from services.quote_asset_constraints import allowed_quote_assets

router = APIRouter(prefix="/runtime", tags=["runtime_control"])

SUPER_ADMIN_ONLY = {UserRole.SUPER_ADMIN}


class RuntimeActionRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=4, max_length=80)


class PipelineFlushRequest(RuntimeActionRequest):
    queue_type: str = Field(default="all")


class OverrideCreateRequest(BaseModel):
    override_type: str = Field(min_length=2, max_length=80)
    scope: str = Field(min_length=2, max_length=120)
    ttl_minutes: int = Field(default=30, ge=1, le=MAX_OVERRIDE_TTL_MINUTES)
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=4, max_length=80)


class OverrideCancelRequest(RuntimeActionRequest):
    pass


class HeartbeatCheckRequest(BaseModel):
    lag_threshold_seconds: float = Field(default=60, ge=1, le=3600)


class ServiceRestartRequest(RuntimeActionRequest):
    service: str = Field(default="all", pattern="^(worker|ws|all)$")


class AlertActionRequest(BaseModel):
    action: str = Field(pattern="^(ack|mute|resolve)$")
    reason: str = Field(min_length=3, max_length=300)
    mute_minutes: int = Field(default=30, ge=5, le=1440)


class AlertBulkRequest(BaseModel):
    ids: list[str] = Field(min_length=1)
    action: str = Field(pattern="^(ack|mute|resolve)$")
    reason: str = Field(min_length=3, max_length=300)
    mute_minutes: int = Field(default=30, ge=5, le=1440)


class AlertPolicyUpdateRequest(BaseModel):
    execution_quality_warning_threshold: float = Field(ge=1, le=100)
    execution_quality_critical_threshold: float = Field(ge=1, le=100)
    permission_drift_warning_per_day: int = Field(ge=1, le=100)
    permission_drift_critical_per_day: int = Field(ge=1, le=200)
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=4, max_length=80)


class AlertPolicyRollbackRequest(RuntimeActionRequest):
    pass


def _require_super_admin(current_admin: User) -> User:
    if current_admin.role not in SUPER_ADMIN_ONLY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_required")
    return current_admin


def _audit(
    db: Session,
    *,
    current_admin: User,
    action: str,
    entity_type: str,
    entity_id: str,
    severity: str,
    trace_id: str,
    details: dict,
):
    payload = dict(details)
    payload["trace_id"] = trace_id
    return create_audit_log(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity=severity,
        details=payload,
    )


def _collect_gate_details(db: Session) -> dict:
    gate = release_gate_view(db, environment="prod")
    report_path = Path("/app/artifacts/final_release_gate_report.json")
    report_payload = {}
    if report_path.exists():
        try:
            report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            report_payload = {}
    rules = _build_gate_rules()
    history = _cache_read_json("runtime:gate:history", [])
    suggested_fixes = [
        {
            "rule_id": item.get("rule_id"),
            "suggested_fix": item.get("suggested_fix"),
            "run_fix_action": item.get("run_fix_action"),
        }
        for item in rules
        if str(item.get("result") or "").upper() == "FAIL"
    ]
    return {
        "status": gate.get("status"),
        "reason_codes": gate.get("reason_codes") or [],
        "reasons": gate.get("reasons") or [],
        "metrics": gate.get("metrics") or {},
        "blocking_items": report_payload.get("blocking_items") or [],
        "final_decision": report_payload.get("final_decision"),
        "rules": rules,
        "suggested_fixes": suggested_fixes,
        "history": history[-20:],
        "fix_redirect": "/admin/execution-policies",
    }


def _cache_read_json(key: str, default):
    raw = redis_client.get(key)
    if raw is None:
        return default
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except Exception:
        return default


def _cache_write_json(key: str, payload):
    redis_client.set(key, json.dumps(payload, ensure_ascii=False))


def _append_cache_json_list(key: str, payload: dict, *, max_items: int = 50):
    rows = _cache_read_json(key, [])
    if not isinstance(rows, list):
        rows = []
    rows.append(payload)
    _cache_write_json(key, rows[-max_items:])


def _build_gate_rules() -> list[dict]:
    rules: list[dict] = []

    env_report = Path("/app/artifacts/prod_env_resolution_report.json")
    if env_report.exists():
        try:
            payload = json.loads(env_report.read_text(encoding="utf-8"))
            for row in payload.get("checks") or []:
                status = str(row.get("status") or "UNKNOWN").upper()
                rule_id = str(row.get("key") or "env_rule")
                message = f"{rule_id} resolved from {row.get('resolved_source') or 'unknown'}"
                if row.get("contains_localhost"):
                    message = f"{rule_id} localhost içeriyor"
                rules.append(
                    {
                        "rule_id": rule_id,
                        "result": "FAIL" if status == "FAIL" else "PASS",
                        "message": message,
                        "fix_hint": f"{rule_id} değerini production ortam kaynağından güncelleyin",
                        "suggested_fix": _map_gate_suggested_fix(rule_id=rule_id, message=message),
                        "run_fix_action": _map_gate_run_fix_action(rule_id=rule_id, message=message),
                    }
                )
        except Exception:
            pass

    preflight_report = Path("/app/artifacts/prod_preflight_check.json")
    if preflight_report.exists():
        try:
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            for row in payload.get("checks") or []:
                status = str(row.get("status") or "UNKNOWN").upper()
                rule_name = str(row.get("name") or "preflight_rule")
                rules.append(
                    {
                        "rule_id": rule_name,
                        "result": "FAIL" if status == "FAIL" else "PASS",
                        "message": str(row.get("detail") or rule_name),
                        "fix_hint": "Preflight kontrolünü düzeltip tekrar /runtime/gate/recheck çalıştırın",
                        "suggested_fix": _map_gate_suggested_fix(rule_id=rule_name, message=str(row.get("detail") or rule_name)),
                        "run_fix_action": _map_gate_run_fix_action(rule_id=rule_name, message=str(row.get("detail") or rule_name)),
                    }
                )
        except Exception:
            pass

    if not rules:
        rules.append(
            {
                "rule_id": "gate_rules_unavailable",
                "result": "FAIL",
                "message": "Gate kural artefaktları bulunamadı",
                "fix_hint": "CI scriptlerini çalıştırıp artefakt üretimini doğrulayın",
                "suggested_fix": "Gate scriptlerini yeniden çalıştır",
                "run_fix_action": "gate_recheck",
            }
        )

    return rules


def _map_gate_suggested_fix(*, rule_id: str, message: str) -> str:
    text = f"{rule_id} {message}".lower()
    if "db" in text or "postgres" in text or "database" in text:
        return "DB bağlantısını doğrula, gerekirse servis restart + gate re-check çalıştır"
    if "redis" in text:
        return "Redis bağlantısını doğrula, gerekirse reconnect + gate re-check çalıştır"
    return "Fix hint adımlarını uygulayıp gate re-check çalıştır"


def _map_gate_run_fix_action(*, rule_id: str, message: str) -> str:
    text = f"{rule_id} {message}".lower()
    if "db" in text or "postgres" in text or "database" in text:
        return "db_restart_then_gate_recheck"
    if "redis" in text:
        return "redis_reconnect_then_gate_recheck"
    return "gate_recheck"


def _safe_ltrim(cache, key: str, start: int, end: int):
    if hasattr(cache, "ltrim"):
        cache.ltrim(key, start, end)


def _safe_rpop(cache, key: str):
    if hasattr(cache, "rpop"):
        return cache.rpop(key)
    rows = cache.lrange(key, 0, -1) if hasattr(cache, "lrange") else []
    if not rows:
        return None
    last = rows[-1]
    cache.delete(key)
    for item in rows[:-1]:
        cache.rpush(key, item)
    return last


def _action_result(*, status: str, trace_id: str | None, message: str, state_snapshot: dict | None = None, **extra):
    payload = {
        "status": status,
        "trace_id": trace_id,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state_snapshot": state_snapshot or {},
    }
    payload.update(extra)
    return payload


@router.post("/ws/reconnect")
def runtime_ws_reconnect(payload: RuntimeActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _require_super_admin(current_admin)
    if payload.confirmation_phrase.strip().upper() != "RECONNECT WS":
        raise HTTPException(status_code=400, detail={"expected_phrase": "RECONNECT WS"})

    trace_id = str(uuid.uuid4())
    state = reconnect_ws(redis_client, actor_user_id=current_admin.id, reason=payload.reason, trace_id=trace_id)
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_WS_RECONNECT",
        entity_type="ws",
        entity_id="global",
        severity="warning",
        trace_id=trace_id,
        details={"reason": payload.reason, "state": state},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="ws reconnect request accepted",
        state_snapshot={"ws_state": state},
        audit_log_id=audit.id,
    )


@router.post("/ws/force-new-session")
def runtime_ws_force_new_session(payload: RuntimeActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _require_super_admin(current_admin)
    if payload.confirmation_phrase.strip().upper() != "FORCE NEW WS SESSION":
        raise HTTPException(status_code=400, detail={"expected_phrase": "FORCE NEW WS SESSION"})

    trace_id = str(uuid.uuid4())
    result = force_new_ws_session(redis_client, actor_user_id=current_admin.id, reason=payload.reason, trace_id=trace_id)
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_WS_FORCE_NEW_SESSION",
        entity_type="ws",
        entity_id="global",
        severity="critical",
        trace_id=trace_id,
        details={"reason": payload.reason, "result": result},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="new ws session requested",
        state_snapshot={"ws_state": result.get("state") or {}},
        result=result,
        audit_log_id=audit.id,
    )


@router.get("/ws/health")
def runtime_ws_health(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return get_ws_health(redis_client)


@router.get("/ws/execution-timeline")
def runtime_ws_execution_timeline(
    limit: int = Query(default=50, ge=1, le=200),
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    return {
        "status": "http_polling",
        "items": runtime_stream_hub.get_recent_events(limit=limit),
    }


@router.post("/pipeline/resync")
def runtime_pipeline_resync(payload: RuntimeActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _require_super_admin(current_admin)
    if payload.confirmation_phrase.strip().upper() != "FORCE PIPELINE RESYNC":
        raise HTTPException(status_code=400, detail={"expected_phrase": "FORCE PIPELINE RESYNC"})

    trace_id = str(uuid.uuid4())
    result = force_pipeline_resync(redis_client, actor_user_id=current_admin.id, reason=payload.reason, trace_id=trace_id)
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_PIPELINE_RESYNC",
        entity_type="pipeline",
        entity_id="global",
        severity="warning",
        trace_id=trace_id,
        details={"reason": payload.reason, "result": result},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="pipeline resync queued",
        state_snapshot={"pipeline": result},
        result=result,
        audit_log_id=audit.id,
    )


@router.post("/pipeline/flush")
def runtime_pipeline_flush(payload: PipelineFlushRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _require_super_admin(current_admin)
    if payload.confirmation_phrase.strip().upper() != "FLUSH PIPELINE":
        raise HTTPException(status_code=400, detail={"expected_phrase": "FLUSH PIPELINE"})

    trace_id = str(uuid.uuid4())
    result = flush_pipeline_queues(redis_client, actor_user_id=current_admin.id, reason=payload.reason, trace_id=trace_id)
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_PIPELINE_FLUSH",
        entity_type="pipeline",
        entity_id=payload.queue_type,
        severity="critical",
        trace_id=trace_id,
        details={"reason": payload.reason, "result": result},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="pipeline queue flush completed",
        state_snapshot={"queue_flush": result},
        result=result,
        audit_log_id=audit.id,
    )


@router.get("/guard/telemetry")
def runtime_guard_telemetry(limit: int = Query(default=100, ge=1, le=500), current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    return get_guard_telemetry(db, limit=limit)


@router.get("/quote-policy")
def runtime_quote_policy(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return {"allowed_quote_assets": allowed_quote_assets()}


@router.get("/state-validation")
def runtime_state_validation(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    ws = get_ws_health(redis_client)
    current_session_id = ws.get("session_id") or ws.get("state", {}).get("session_id")
    previous_session_id = _cache_read_json("runtime:state_validation:last_ws_session_id", None)
    ws_session_changed = bool(previous_session_id and current_session_id and previous_session_id != current_session_id)
    _cache_write_json("runtime:state_validation:last_ws_session_id", current_session_id)

    active_overrides = list_active_overrides(redis_client)
    override_effect_applied = len(active_overrides) > 0

    gate_state = _cache_read_json("runtime:state_validation:last_gate_state", {})
    gate_source = gate_state.get("gate_source") or "runtime_check"

    guard = get_guard_telemetry(db, limit=100)
    guard_block_visible = len(guard.get("blocked_trade_list") or []) > 0

    checks = {
        "ws_session_changed": {
            "value": ws_session_changed,
            "status": "pass" if ws_session_changed else ("warning" if previous_session_id is None else "fail"),
            "fix_action": "Fix WS",
        },
        "override_effect_applied": {
            "value": override_effect_applied,
            "status": "pass" if override_effect_applied else "warning",
            "fix_action": "Re-sync Override",
        },
        "gate_source": {
            "value": gate_source,
            "status": "pass" if gate_source == "ci_script" else "fail",
            "fix_action": "Run Gate Re-check",
        },
        "guard_block_visible": {
            "value": guard_block_visible,
            "status": "pass" if guard_block_visible else "warning",
            "fix_action": "Rebuild Guard List",
        },
    }

    any_fail = any(item["status"] == "fail" for item in checks.values())
    any_warning = any(item["status"] == "warning" for item in checks.values())

    suggestions = {
        "ws_session_changed": None if ws_session_changed else "WS reconnect veya force-new-session aksiyonunu çalıştırın.",
        "override_effect_applied": None if override_effect_applied else "Test override oluşturup aktif override state değişimini doğrulayın.",
        "gate_source": None if gate_source == "ci_script" else "Gate Re-check aksiyonunu çalıştırıp CI script sonucunu yenileyin.",
        "guard_block_visible": None if guard_block_visible else "Guard blocked trade listesi için bir block senaryosu tetikleyin.",
    }

    return {
        "overall_status": "fail" if any_fail else ("warning" if any_warning else "pass"),
        "ws_session_changed": ws_session_changed,
        "override_effect_applied": override_effect_applied,
        "gate_source": gate_source,
        "guard_block_visible": guard_block_visible,
        "checks": checks,
        "suggestions": suggestions,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/gate/recheck")
def runtime_gate_recheck(payload: RuntimeActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _require_super_admin(current_admin)
    if payload.confirmation_phrase.strip().upper() != "RECHECK RELEASE GATE":
        raise HTTPException(status_code=400, detail={"expected_phrase": "RECHECK RELEASE GATE"})

    trace_id = str(uuid.uuid4())
    scripts = [
        "/app/scripts/prod_env_resolution_report.sh",
        "/app/scripts/prod_secret_readiness_check.sh",
        "/app/scripts/preflight_prod_env_check.sh",
        "/app/scripts/final_release_gate_report.sh",
    ]
    script_results = []
    for script in scripts:
        completed = subprocess.run(["bash", script], cwd="/app", capture_output=True, text=True, check=False)
        script_results.append({"script": script, "returncode": completed.returncode})

    gate = _collect_gate_details(db)
    _cache_write_json(
        "runtime:state_validation:last_gate_state",
        {
            "gate_source": "ci_script",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "status": gate.get("status"),
            "final_decision": gate.get("final_decision"),
        },
    )
    _append_cache_json_list(
        "runtime:gate:history",
        {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "status": gate.get("status"),
            "final_decision": gate.get("final_decision"),
            "rules_count": len(gate.get("rules") or []),
        },
        max_items=50,
    )
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_RELEASE_GATE_RECHECK",
        entity_type="release_gate",
        entity_id="prod",
        severity="warning" if gate.get("status") != "PASS" else "info",
        trace_id=trace_id,
        details={"reason": payload.reason, "scripts": script_results, "gate": gate},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="release gate recheck completed",
        state_snapshot={"gate": gate},
        gate=gate,
        scripts=script_results,
        audit_log_id=audit.id,
    )


@router.get("/gate/status")
def runtime_gate_status(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    return _collect_gate_details(db)


@router.post("/override/create")
def runtime_override_create(payload: OverrideCreateRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _require_super_admin(current_admin)
    if payload.confirmation_phrase.strip().upper() != "CREATE OVERRIDE":
        raise HTTPException(status_code=400, detail={"expected_phrase": "CREATE OVERRIDE"})

    trace_id = str(uuid.uuid4())
    result = create_override(
        db,
        redis_client,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        override_type=payload.override_type,
        scope=payload.scope,
        ttl_minutes=payload.ttl_minutes,
        reason=payload.reason,
        trace_id=trace_id,
    )
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_OVERRIDE_CREATE",
        entity_type="override",
        entity_id=result.get("override_id"),
        severity="critical",
        trace_id=trace_id,
        details={"result": result},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="override created",
        state_snapshot={"override": result},
        override=result,
        max_ttl_minutes=MAX_OVERRIDE_TTL_MINUTES,
        audit_log_id=audit.id,
    )


@router.get("/override/active")
def runtime_override_active(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    rows = list_active_overrides(redis_client)
    guard = get_guard_telemetry(db, limit=500)
    impacted = guard.get("override_impacted_trades") or []
    impacted_map = {}
    for item in impacted:
        override_id = item.get("override_id")
        if not override_id:
            continue
        impacted_map[override_id] = impacted_map.get(override_id, 0) + 1

    now = datetime.now(timezone.utc)
    enriched = []
    for row in rows:
        ttl_remaining_seconds = None
        expires_at = row.get("expires_at")
        if expires_at:
            try:
                expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                ttl_remaining_seconds = max(int((expires - now).total_seconds()), 0)
            except Exception:
                ttl_remaining_seconds = None
        enriched.append(
            {
                **row,
                "ttl_remaining_seconds": ttl_remaining_seconds,
                "impacted_trades_count": impacted_map.get(row.get("override_id"), 0),
            }
        )

    return {
        "items": enriched,
        "max_ttl_minutes": MAX_OVERRIDE_TTL_MINUTES,
        "total_impacted_trades": sum(item.get("impacted_trades_count", 0) for item in enriched),
    }


@router.post("/override/{override_id}/cancel")
def runtime_override_cancel(override_id: str, payload: OverrideCancelRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _require_super_admin(current_admin)
    if payload.confirmation_phrase.strip().upper() != "CANCEL OVERRIDE":
        raise HTTPException(status_code=400, detail={"expected_phrase": "CANCEL OVERRIDE"})

    trace_id = str(uuid.uuid4())
    result = cancel_override(db, redis_client, override_id=override_id, actor_user_id=current_admin.id, reason=payload.reason, trace_id=trace_id)
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_OVERRIDE_CANCEL",
        entity_type="override",
        entity_id=override_id,
        severity="warning",
        trace_id=trace_id,
        details={"result": result},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="override cancel completed",
        state_snapshot={"override_cancel": result},
        result=result,
        audit_log_id=audit.id,
    )


@router.get("/override/history")
def runtime_override_history(limit: int = Query(default=100, ge=1, le=500), current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    rows = list_override_history(db, limit=limit)
    return {"items": rows, "count": len(rows)}


@router.post("/heartbeat/check")
def runtime_heartbeat_check(payload: HeartbeatCheckRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    trace_id = str(uuid.uuid4())
    result = manual_health_check(redis_client, lag_threshold_seconds=payload.lag_threshold_seconds)
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_HEARTBEAT_CHECK",
        entity_type="heartbeat",
        entity_id="global",
        severity="warning" if result.get("warning_triggered") else "info",
        trace_id=trace_id,
        details={
            "lag_threshold_seconds": payload.lag_threshold_seconds,
            "result": result,
        },
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="manual heartbeat check completed",
        state_snapshot={"heartbeat": result},
        heartbeat=result,
        lag_seconds=result.get("lag_seconds"),
        warning_triggered=result.get("warning_triggered"),
        audit_log_id=audit.id,
    )


@router.post("/service/restart")
def runtime_service_restart(payload: ServiceRestartRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _require_super_admin(current_admin)
    if payload.confirmation_phrase.strip().upper() != "RESTART SERVICE":
        raise HTTPException(status_code=400, detail={"expected_phrase": "RESTART SERVICE"})

    trace_id = str(uuid.uuid4())
    result = restart_runtime_service(service=payload.service)
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_SERVICE_RESTART",
        entity_type="service",
        entity_id=payload.service,
        severity="critical",
        trace_id=trace_id,
        details={"reason": payload.reason, "result": result},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="service restart scheduled",
        state_snapshot={"service_restart": result},
        result=result,
        audit_log_id=audit.id,
    )


@router.get("/exchange/monitoring")
def runtime_exchange_monitoring(current_admin: User = Depends(require_admin), db: Session = Depends(get_db), limit: int = Query(default=100, ge=1, le=500)):
    _ = current_admin
    drift_rows = db.query(PermissionDriftEvent).order_by(PermissionDriftEvent.created_at.desc()).limit(limit).all()
    connection_rows = db.query(UserExchangeConnection).order_by(UserExchangeConnection.updated_at.desc()).limit(limit).all()
    trend = {}
    for row in drift_rows:
        hour_key = (row.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:00") if row.created_at else "unknown")
        trend[hour_key] = trend.get(hour_key, 0) + 1

    return {
        "drift_details": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "exchange": row.exchange,
                "is_critical": row.is_critical,
                "old_permissions": row.old_permissions,
                "new_permissions": row.new_permissions,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in drift_rows
        ],
        "connection_details": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "exchange": row.exchange,
                "environment": row.environment,
                "market_type": row.market_type,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in connection_rows
        ],
        "trend": [{"bucket": bucket, "count": count} for bucket, count in sorted(trend.items())],
    }


@router.post("/exchange/revalidate/{connection_id}")
def runtime_exchange_revalidate(connection_id: str, payload: RuntimeActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _require_super_admin(current_admin)
    if payload.confirmation_phrase.strip().upper() != "REVALIDATE EXCHANGE":
        raise HTTPException(status_code=400, detail={"expected_phrase": "REVALIDATE EXCHANGE"})

    row = db.query(UserExchangeConnection).filter(UserExchangeConnection.id == connection_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="connection_not_found")
    snapshot = dict(row.readiness_snapshot or {})
    snapshot["revalidated_at"] = datetime.now(timezone.utc).isoformat()
    snapshot["revalidated_by"] = current_admin.id
    row.readiness_snapshot = snapshot
    db.commit()

    trace_id = str(uuid.uuid4())
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_EXCHANGE_REVALIDATE",
        entity_type="exchange_connection",
        entity_id=connection_id,
        severity="warning",
        trace_id=trace_id,
        details={"reason": payload.reason, "snapshot": snapshot},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="exchange connection revalidated",
        state_snapshot={"exchange_snapshot": snapshot},
        snapshot=snapshot,
        audit_log_id=audit.id,
    )


@router.post("/exchange/disable-key/{connection_id}")
def runtime_exchange_disable_key(connection_id: str, payload: RuntimeActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _require_super_admin(current_admin)
    if payload.confirmation_phrase.strip().upper() != "DISABLE EXCHANGE KEY":
        raise HTTPException(status_code=400, detail={"expected_phrase": "DISABLE EXCHANGE KEY"})

    row = db.query(UserExchangeConnection).filter(UserExchangeConnection.id == connection_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="connection_not_found")
    row.readiness_snapshot = {**(row.readiness_snapshot or {}), "disabled": True, "disabled_at": datetime.now(timezone.utc).isoformat()}
    db.commit()

    trace_id = str(uuid.uuid4())
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_EXCHANGE_DISABLE_KEY",
        entity_type="exchange_connection",
        entity_id=connection_id,
        severity="critical",
        trace_id=trace_id,
        details={"reason": payload.reason},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="exchange key disabled",
        state_snapshot={"connection_id": connection_id, "disabled": True},
        audit_log_id=audit.id,
    )


@router.get("/hardening/analytics")
def runtime_hardening_analytics(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    time_window_hours: int = Query(default=24, ge=1, le=720),
    event_type: str | None = Query(default=None),
):
    _ = current_admin
    since = datetime.now(timezone.utc) - timedelta(hours=time_window_hours)
    query = db.query(AuditLog).filter(AuditLog.created_at >= since, AuditLog.action.ilike("%RUNTIME%"))
    if event_type:
        query = query.filter(AuditLog.action.ilike(f"%{event_type}%"))
    rows = query.order_by(AuditLog.created_at.desc()).limit(300).all()
    return {
        "items": [
            {
                "id": row.id,
                "action": row.action,
                "actor_role": row.actor_role,
                "severity": row.severity,
                "details": row.details or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.get("/action-audit")
def runtime_action_audit(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    user_id: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    since_hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=100, ge=1, le=500),
):
    _ = current_admin
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    query = db.query(AuditLog).filter(AuditLog.created_at >= since)
    query = query.filter(AuditLog.action.ilike("%RUNTIME%") | AuditLog.action.ilike("LIVE_CONTROL_%") | AuditLog.action.ilike("ACTION_CENTER_%"))
    if user_id:
        query = query.filter(AuditLog.actor_user_id == user_id)
    if action_type:
        query = query.filter(AuditLog.action.ilike(f"%{action_type}%"))
    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": row.id,
                "action": row.action,
                "severity": row.severity,
                "actor_user_id": row.actor_user_id,
                "actor_role": row.actor_role,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "details": row.details or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.get("/action-audit/{audit_id}")
def runtime_action_audit_detail(audit_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    row = db.query(AuditLog).filter(AuditLog.id == audit_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="audit_not_found")
    return {
        "id": row.id,
        "action": row.action,
        "severity": row.severity,
        "actor_user_id": row.actor_user_id,
        "actor_role": row.actor_role,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "details": row.details or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/alerts/history")
def runtime_alert_history(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    severity: str | None = Query(default=None),
    since_hours: int = Query(default=24, ge=1, le=720),
    event_type: str | None = Query(default=None),
    status_filter: str = Query(default="all", pattern="^(all|open|ack|resolved)$"),
    limit: int = Query(default=100, ge=1, le=500),
):
    _ = current_admin
    query = db.query(SystemAlert)
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    query = query.filter(SystemAlert.created_at >= since)
    if severity:
        query = query.filter(SystemAlert.severity == severity)
    if event_type:
        query = query.filter(SystemAlert.alert_type.ilike(f"%{event_type}%"))
    if status_filter != "all":
        query = query.filter(SystemAlert.status == status_filter)
    rows = query.order_by(SystemAlert.last_triggered_at.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": row.id,
                "alert_type": row.alert_type,
                "severity": row.severity,
                "status": row.status,
                "message": row.message,
                "details": row.details or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.post("/alerts/{alert_id}/action")
def runtime_alert_action(alert_id: str, payload: AlertActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="alert_not_found")
    now = datetime.now(timezone.utc)
    details = dict(row.details or {})
    if payload.action == "ack":
        row.status = "ack"
    elif payload.action == "resolve":
        row.status = "resolved"
    elif payload.action == "mute":
        row.status = "ack"
        details["muted_until"] = (now + timedelta(minutes=payload.mute_minutes)).isoformat()
        details["muted_by"] = current_admin.id
        row.details = details
    row.updated_at = now
    db.commit()

    trace_id = str(uuid.uuid4())
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_ALERT_ACTION",
        entity_type="system_alert",
        entity_id=alert_id,
        severity="warning",
        trace_id=trace_id,
        details={"action": payload.action, "reason": payload.reason},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message=f"alert {payload.action} completed",
        state_snapshot={"alert_id": alert_id, "action": payload.action},
        alert_id=alert_id,
        action=payload.action,
        audit_log_id=audit.id,
    )


@router.post("/alerts/bulk-action")
def runtime_alert_bulk_action(payload: AlertBulkRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(SystemAlert).filter(SystemAlert.id.in_(payload.ids)).all()
    if not rows:
        raise HTTPException(status_code=404, detail="alerts_not_found")
    now = datetime.now(timezone.utc)
    for row in rows:
        details = dict(row.details or {})
        if payload.action == "ack":
            row.status = "ack"
        elif payload.action == "resolve":
            row.status = "resolved"
        elif payload.action == "mute":
            row.status = "ack"
            details["muted_until"] = (now + timedelta(minutes=payload.mute_minutes)).isoformat()
            details["muted_by"] = current_admin.id
            row.details = details
        row.updated_at = now
    db.commit()

    trace_id = str(uuid.uuid4())
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_ALERT_BULK_ACTION",
        entity_type="system_alert",
        entity_id="bulk",
        severity="warning",
        trace_id=trace_id,
        details={"ids": payload.ids, "action": payload.action, "reason": payload.reason},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message=f"bulk alert {payload.action} completed",
        state_snapshot={"count": len(rows), "action": payload.action},
        count=len(rows),
        audit_log_id=audit.id,
    )


@router.get("/alert-policy")
def runtime_alert_policy(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    row = db.query(AlertPolicy).filter(AlertPolicy.id == "global").first()
    if row is None:
        row = AlertPolicy(id="global")
        db.add(row)
        db.commit()
        db.refresh(row)
    versions = []
    raw = redis_client.lrange("runtime:alert_policy:versions", -20, -1)
    for item in raw:
        try:
            versions.append(json.loads(item.decode("utf-8") if isinstance(item, bytes) else item))
        except Exception:
            continue
    return {
        "policy": {
            "execution_quality_warning_threshold": row.execution_quality_warning_threshold,
            "execution_quality_critical_threshold": row.execution_quality_critical_threshold,
            "permission_drift_warning_per_day": row.permission_drift_warning_per_day,
            "permission_drift_critical_per_day": row.permission_drift_critical_per_day,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        },
        "versions": versions,
    }


@router.put("/alert-policy")
def runtime_alert_policy_update(payload: AlertPolicyUpdateRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _require_super_admin(current_admin)
    if payload.execution_quality_warning_threshold <= payload.execution_quality_critical_threshold:
        raise HTTPException(status_code=400, detail="warning_threshold_must_be_greater_than_critical")
    if payload.permission_drift_warning_per_day >= payload.permission_drift_critical_per_day:
        raise HTTPException(status_code=400, detail="warning_limit_must_be_lower_than_critical")
    if payload.confirmation_phrase.strip().upper() != "UPDATE ALERT POLICY":
        raise HTTPException(status_code=400, detail={"expected_phrase": "UPDATE ALERT POLICY"})

    row = db.query(AlertPolicy).filter(AlertPolicy.id == "global").first()
    if row is None:
        row = AlertPolicy(id="global")
        db.add(row)

    snapshot = {
        "execution_quality_warning_threshold": row.execution_quality_warning_threshold,
        "execution_quality_critical_threshold": row.execution_quality_critical_threshold,
        "permission_drift_warning_per_day": row.permission_drift_warning_per_day,
        "permission_drift_critical_per_day": row.permission_drift_critical_per_day,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    redis_client.rpush("runtime:alert_policy:versions", json.dumps(snapshot, ensure_ascii=False))
    _safe_ltrim(redis_client, "runtime:alert_policy:versions", -100, -1)

    row.execution_quality_warning_threshold = payload.execution_quality_warning_threshold
    row.execution_quality_critical_threshold = payload.execution_quality_critical_threshold
    row.permission_drift_warning_per_day = payload.permission_drift_warning_per_day
    row.permission_drift_critical_per_day = payload.permission_drift_critical_per_day
    db.commit()

    trace_id = str(uuid.uuid4())
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_ALERT_POLICY_UPDATE",
        entity_type="alert_policy",
        entity_id="global",
        severity="warning",
        trace_id=trace_id,
        details={"reason": payload.reason, "new_policy": payload.model_dump()},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="alert policy updated",
        state_snapshot={
            "execution_quality_warning_threshold": row.execution_quality_warning_threshold,
            "execution_quality_critical_threshold": row.execution_quality_critical_threshold,
            "permission_drift_warning_per_day": row.permission_drift_warning_per_day,
            "permission_drift_critical_per_day": row.permission_drift_critical_per_day,
        },
        audit_log_id=audit.id,
    )


@router.post("/alert-policy/rollback")
def runtime_alert_policy_rollback(request: AlertPolicyRollbackRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _require_super_admin(current_admin)
    if request.confirmation_phrase.strip().upper() != "ROLLBACK ALERT POLICY":
        raise HTTPException(status_code=400, detail={"expected_phrase": "ROLLBACK ALERT POLICY"})

    trace_id = str(uuid.uuid4())
    raw = _safe_rpop(redis_client, "runtime:alert_policy:versions")
    if not raw:
        raise HTTPException(status_code=404, detail="no_policy_version_available")
    rollback_version = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)

    row = db.query(AlertPolicy).filter(AlertPolicy.id == "global").first()
    if row is None:
        row = AlertPolicy(id="global")
        db.add(row)
    row.execution_quality_warning_threshold = float(rollback_version.get("execution_quality_warning_threshold") or row.execution_quality_warning_threshold)
    row.execution_quality_critical_threshold = float(rollback_version.get("execution_quality_critical_threshold") or row.execution_quality_critical_threshold)
    row.permission_drift_warning_per_day = int(rollback_version.get("permission_drift_warning_per_day") or row.permission_drift_warning_per_day)
    row.permission_drift_critical_per_day = int(rollback_version.get("permission_drift_critical_per_day") or row.permission_drift_critical_per_day)
    db.commit()

    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_ALERT_POLICY_ROLLBACK",
        entity_type="alert_policy",
        entity_id="global",
        severity="warning",
        trace_id=trace_id,
        details={"reason": request.reason, "rolled_back_to": rollback_version},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="alert policy rollback completed",
        state_snapshot={"rolled_back_to": rollback_version},
        rolled_back_to=rollback_version,
        audit_log_id=audit.id,
    )


@router.post("/alert-policy/test-alert")
def runtime_alert_policy_test_alert(payload: RuntimeActionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _require_super_admin(current_admin)
    if payload.confirmation_phrase.strip().upper() != "SEND TEST ALERT":
        raise HTTPException(status_code=400, detail={"expected_phrase": "SEND TEST ALERT"})

    alert = SystemAlert(
        alert_type="TEST_ALERT",
        severity="INFO",
        message=f"Manual test alert by {current_admin.email}",
        root_cause_code="manual_test",
        details={"reason": payload.reason, "created_by": current_admin.id},
        status="open",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    trace_id = str(uuid.uuid4())
    audit = _audit(
        db,
        current_admin=current_admin,
        action="RUNTIME_ALERT_POLICY_TEST_ALERT",
        entity_type="system_alert",
        entity_id=alert.id,
        severity="info",
        trace_id=trace_id,
        details={"reason": payload.reason},
    )
    return _action_result(
        status="success",
        trace_id=trace_id,
        message="test alert created",
        state_snapshot={"alert_id": alert.id, "severity": alert.severity},
        alert_id=alert.id,
        audit_log_id=audit.id,
    )
