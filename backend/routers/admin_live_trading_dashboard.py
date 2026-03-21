import json
import subprocess
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin
from models import AuditLog, FailedEvent, LiveActivationConfig, PaperPosition, RiskOrchestratorPolicy, StateRebuildLog, SystemAlert, User, UserExecutionIntent, UserRole
from services.audit_service import create_audit_log
from services.execution_mode_control_service import (
    get_execution_mode,
    get_latency_thresholds,
    read_mode_snapshots,
    set_latency_thresholds,
    switch_execution_mode,
)
from services.execution_safety_service import execution_safety_snapshot, update_execution_safety_state
from services.live_trading_dashboard_service import (
    build_daily_report,
    build_execution_quality_summary,
    build_learning_summary,
    build_live_trading_summary,
    build_risk_summary,
    build_scanner_health,
    export_daily_report_csv,
)

router = APIRouter(prefix="/admin/live-trading", tags=["admin_live_trading_dashboard"])

MANAGER_ROLES = {UserRole.SUPER_ADMIN, UserRole.ADMIN}
OPS_ALLOWED_ALERT_ACTIONS = {"resolve", "mute", "fix_action"}

MODE_SWITCH_PHRASE = {
    "LIVE": "SWITCH TO LIVE",
    "PAPER": "SWITCH TO PAPER",
    "MOCK": "SWITCH TO MOCK",
}

SYSTEM_HEALTH_PHRASES = {
    "kill_on": "DISABLE TRADING",
    "kill_off": "ENABLE TRADING",
    "fallback_on": "ENABLE FALLBACK",
    "fallback_off": "DISABLE FALLBACK",
    "set_latency": "SET LATENCY THRESHOLD",
}

RISK_CONTROL_PHRASE = "UPDATE RISK CONTROLS"
RISK_OVERRIDE_PHRASE = "APPLY RISK OVERRIDE"
SNAPSHOT_PHRASE = "CAPTURE SNAPSHOT"
RESET_DAILY_PHRASE = "RESET DAILY METRICS"
RETRY_ORDERS_PHRASE = "RETRY FAILED ORDERS"
REMOVE_FAILED_ORDERS_PHRASE = "REMOVE FAILED ORDERS"
SCANNER_RESTART_PHRASE = "RESTART SCANNER"
SCANNER_TRIGGER_PHRASE = "TRIGGER MANUAL SCAN"
SCANNER_UNIVERSE_PHRASE = "UPDATE SYMBOL UNIVERSE"


class ExecutionModeSwitchRequest(BaseModel):
    mode: str = Field(pattern="^(LIVE|PAPER|MOCK)$")
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=5, max_length=80)


class SystemHealthControlRequest(BaseModel):
    action: str = Field(pattern="^(kill_on|kill_off|fallback_on|fallback_off|set_latency)$")
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=5, max_length=80)
    scan_latency_ms: float | None = None
    decision_latency_ms: float | None = None
    execution_latency_ms: float | None = None


class CriticalAlertActionRequest(BaseModel):
    action: str = Field(pattern="^(resolve|mute|escalate|fix_action)$")
    reason: str = Field(min_length=3, max_length=300)
    mute_minutes: int = Field(default=30, ge=5, le=1440)
    fix_action: str | None = Field(default=None)
    confirmation_phrase: str | None = None


class RiskControlUpdateRequest(BaseModel):
    max_loss_pct: float = Field(ge=0.1, le=100)
    account_exposure_pct: float = Field(ge=1, le=100)
    symbol_exposure_pct: float = Field(ge=1, le=100)
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=5, max_length=80)


class RiskOverrideRequest(BaseModel):
    decision: str = Field(pattern="^(force_allow|force_reject)$")
    reason: str = Field(min_length=5, max_length=300)
    ttl_minutes: int = Field(default=30, ge=5, le=240)
    confirmation_phrase: str = Field(min_length=5, max_length=80)


class SnapshotRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=5, max_length=80)


class RetryFailedOrdersRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=5, max_length=80)


class RemoveFailedOrdersRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=5, max_length=80)


class ScannerControlRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=5, max_length=80)


class ScannerSymbolUniverseRequest(BaseModel):
    action: str = Field(pattern="^(add|remove)$")
    symbols: list[str] = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=5, max_length=80)


def _require_manager(current_admin: User) -> User:
    if current_admin.role not in MANAGER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="manager_role_required")
    return current_admin


def _read_json_value(cache, key: str, default):
    raw = cache.get(key)
    if not raw:
        return default
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except Exception:
        return default


def _write_json_value(cache, key: str, value: dict):
    cache.set(key, json.dumps(value, ensure_ascii=False))


def _read_symbol_universe(cache) -> list[str]:
    payload = _read_json_value(cache, "control_layer:scanner_symbol_universe", {"symbols": []})
    return sorted(list({str(item).upper() for item in payload.get("symbols", []) if str(item).strip()}))


@router.get("/control-layer/state")
def admin_live_trading_control_state(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    mode = get_execution_mode(db, redis_client)
    snapshots = read_mode_snapshots(redis_client, limit=10)
    latency_thresholds = get_latency_thresholds(redis_client)
    kill_switch = _read_json_value(redis_client, "pipeline:kill_switch", {"active": False, "reasons": []})
    fallback = _read_json_value(redis_client, "control_layer:fallback", {"active": False})
    risk_override = _read_json_value(redis_client, "control_layer:risk_override", {"active": False})

    retry_queue_count = db.query(FailedEvent).filter(FailedEvent.status == "pending").count()
    failed_orders_count = db.query(FailedEvent).filter(FailedEvent.status.in_(["pending", "failed"])).count()
    open_positions_count = db.query(PaperPosition).filter(PaperPosition.status == "open").count()
    scanner_symbol_universe = _read_symbol_universe(redis_client)

    return {
        "server_clock": datetime.now(timezone.utc).isoformat(),
        "execution_mode": mode,
        "execution_mode_snapshots": snapshots,
        "latency_thresholds": latency_thresholds,
        "kill_switch": kill_switch,
        "fallback": fallback,
        "risk_override": risk_override,
        "retry_queue_count": retry_queue_count,
        "failed_orders_count": failed_orders_count,
        "open_positions_count": open_positions_count,
        "scanner_symbol_universe": scanner_symbol_universe,
    }


@router.get("/control-layer/action-audit")
def admin_live_trading_action_audit(
    user_id: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    since_hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=100, ge=1, le=500),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    query = db.query(AuditLog).filter(AuditLog.created_at >= since)
    query = query.filter(
        (AuditLog.action.ilike("LIVE_CONTROL_%"))
        | (AuditLog.action.ilike("EXECUTION_MODE_%"))
        | (AuditLog.action.ilike("ACTION_CENTER_%"))
    )

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


@router.get("/control-layer/action-audit/{audit_id}")
def admin_live_trading_action_audit_detail(
    audit_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    row = db.query(AuditLog).filter(AuditLog.id == audit_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audit_not_found")
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


@router.post("/control-layer/execution-mode")
def admin_live_trading_switch_execution_mode(
    payload: ExecutionModeSwitchRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _require_manager(current_admin)
    expected_phrase = MODE_SWITCH_PHRASE[payload.mode]
    if payload.confirmation_phrase.strip().upper() != expected_phrase:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_confirmation_phrase", "expected_phrase": expected_phrase},
        )

    result = switch_execution_mode(
        db,
        redis_client,
        mode=payload.mode,
        reason=payload.reason,
        actor_user_id=manager.id,
        actor_role=manager.role.value,
    )
    return {"status": "ok", **result}


@router.post("/control-layer/system-health")
def admin_live_trading_system_health_control(
    payload: SystemHealthControlRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _require_manager(current_admin)
    expected_phrase = SYSTEM_HEALTH_PHRASES[payload.action]
    if payload.confirmation_phrase.strip().upper() != expected_phrase:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_confirmation_phrase", "expected_phrase": expected_phrase},
        )

    details: dict = {"action": payload.action, "reason": payload.reason}

    if payload.action in {"kill_on", "kill_off"}:
        active = payload.action == "kill_on"
        safety_result = update_execution_safety_state(
            db,
            trading_enabled=not active,
            reason=payload.reason,
            requested_by=manager.email,
            effective_at=datetime.now(timezone.utc).isoformat(),
            actor_user_id=manager.id,
            actor_role=manager.role.value,
        )
        # Remove non-serializable config object from safety_result
        safety_result.pop("config", None)
        _write_json_value(
            redis_client,
            "pipeline:kill_switch",
            {
                "active": active,
                "reasons": [payload.reason],
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": manager.id,
            },
        )
        details["execution_safety"] = safety_result

    if payload.action in {"fallback_on", "fallback_off"}:
        _write_json_value(
            redis_client,
            "control_layer:fallback",
            {
                "active": payload.action == "fallback_on",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": manager.id,
            },
        )

    if payload.action == "set_latency":
        thresholds = set_latency_thresholds(
            redis_client,
            {
                "scan_latency_ms": payload.scan_latency_ms,
                "decision_latency_ms": payload.decision_latency_ms,
                "execution_latency_ms": payload.execution_latency_ms,
            },
        )
        details["latency_thresholds"] = thresholds

    audit_row = create_audit_log(
        db,
        action="LIVE_CONTROL_SYSTEM_HEALTH_UPDATED",
        entity_type="control_layer",
        entity_id="system_health",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="critical" if payload.action in {"kill_on", "kill_off"} else "warning",
        details=details,
    )
    snapshot = execution_safety_snapshot(db)
    # Remove non-serializable config object
    snapshot.pop("config", None)
    return {
        "status": "ok",
        "action": payload.action,
        "audit_log_id": audit_row.id,
        "execution_safety": snapshot,
        "latency_thresholds": get_latency_thresholds(redis_client),
    }


@router.get("/control-layer/critical-alerts")
def admin_live_trading_critical_alerts(
    status_filter: str = Query(default="open", pattern="^(open|ack|resolved|all)$"),
    limit: int = Query(default=50, ge=1, le=200),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    query = db.query(SystemAlert)
    if status_filter != "all":
        query = query.filter(SystemAlert.status == status_filter)
    rows = query.order_by(SystemAlert.last_triggered_at.desc()).limit(limit).all()

    items = []
    for row in rows:
        alert_history = (
            db.query(AuditLog)
            .filter((AuditLog.entity_id == row.id) | (AuditLog.entity_type == "system_alert"))
            .order_by(AuditLog.created_at.desc())
            .limit(8)
            .all()
        )
        items.append(
            {
                "id": row.id,
                "alert_type": row.alert_type,
                "severity": row.severity,
                "status": row.status,
                "message": row.message,
                "root_cause_code": row.root_cause_code,
                "entity_key": row.entity_key,
                "details": row.details or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "history": [
                    {
                        "id": item.id,
                        "action": item.action,
                        "severity": item.severity,
                        "actor_role": item.actor_role,
                        "details": item.details or {},
                        "created_at": item.created_at.isoformat() if item.created_at else None,
                    }
                    for item in alert_history
                ],
            }
        )

    return {"items": items, "count": len(items)}


@router.post("/control-layer/critical-alerts/{alert_id}/action")
def admin_live_trading_critical_alert_action(
    alert_id: str,
    payload: CriticalAlertActionRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert_not_found")

    if current_admin.role == UserRole.OPS and payload.action not in OPS_ALLOWED_ALERT_ACTIONS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops_not_allowed_for_this_action")

    if payload.action in {"escalate"}:
        _require_manager(current_admin)

    if payload.action == "fix_action" and (payload.confirmation_phrase or "").strip().upper() != "RUN ALERT FIX ACTION":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_confirmation_phrase", "expected_phrase": "RUN ALERT FIX ACTION"},
        )

    now = datetime.now(timezone.utc)
    action_result: dict = {}

    if payload.action == "resolve":
        row.status = "resolved"
        row.updated_at = now
        action_result = {"resolved": True}

    elif payload.action == "mute":
        details = dict(row.details or {})
        details["muted_until"] = (now + timedelta(minutes=payload.mute_minutes)).isoformat()
        details["muted_by"] = current_admin.id
        row.details = details
        row.status = "ack"
        row.updated_at = now
        action_result = {"muted_until": details["muted_until"]}

    elif payload.action == "escalate":
        row.severity = "CRITICAL"
        row.updated_at = now
        action_result = {"escalated": True}

    elif payload.action == "fix_action":
        fix = str(payload.fix_action or "").strip().lower()
        if fix not in {
            "reconnect-exchange",
            "restart-service",
            "cancel-stuck-orders",
            "requeue-timeout-intents",
            "flush-retry-queue",
            "force-resync-positions",
        }:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_fix_action")

        if fix == "reconnect-exchange":
            _write_json_value(
                redis_client,
                "control_layer:exchange_reconnect",
                {"requested_at": now.isoformat(), "requested_by": current_admin.id, "reason": payload.reason},
            )
            action_result = {"reconnect_requested": True}

        if fix == "restart-service":
            subprocess.Popen(["bash", "-lc", "(sleep 1; supervisorctl restart backend frontend) >> /tmp/live_control_restart.log 2>&1"], cwd="/app")
            action_result = {"restart_scheduled": True, "log": "/tmp/live_control_restart.log"}

        if fix == "cancel-stuck-orders":
            stuck_rows = (
                db.query(UserExecutionIntent)
                .filter(UserExecutionIntent.status.in_(["QUEUED", "SUBMITTED"]))
                .order_by(UserExecutionIntent.created_at.asc())
                .limit(200)
                .all()
            )
            cancelled = 0
            for intent in stuck_rows:
                intent.status = "CANCELLED"
                intent.cancelled_at = now
                cancelled += 1
            action_result = {"cancelled_intents": cancelled}

        if fix == "requeue-timeout-intents":
            timeout_rows = (
                db.query(UserExecutionIntent)
                .filter(UserExecutionIntent.status == "REJECTED", UserExecutionIntent.admin_note.ilike("%pending_timeout%"))
                .order_by(UserExecutionIntent.updated_at.asc())
                .limit(200)
                .all()
            )
            requeued = 0
            for intent in timeout_rows:
                intent.status = "QUEUED"
                intent.admin_note = "requeued_from_alert_fix_action"
                requeued += 1
            action_result = {"requeued_intents": requeued}

        if fix == "flush-retry-queue":
            queue_rows = db.query(FailedEvent).filter(FailedEvent.status == "pending").limit(500).all()
            flushed = 0
            for item in queue_rows:
                item.status = "resolved"
                item.resolved_at = now
                flushed += 1
            action_result = {"flushed_retry_queue": flushed}

        if fix == "force-resync-positions":
            rebuild = StateRebuildLog(
                rebuild_type="positions_resync",
                status="completed",
                trigger_source="control_layer_fix_action",
                details={"reason": payload.reason, "requested_by": current_admin.id},
                started_at=now,
                finished_at=now,
            )
            db.add(rebuild)
            action_result = {"positions_resync": "triggered"}

    db.commit()
    db.refresh(row)

    audit_row = create_audit_log(
        db,
        action="LIVE_CONTROL_ALERT_ACTION",
        entity_type="system_alert",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={
            "alert_id": row.id,
            "action": payload.action,
            "fix_action": payload.fix_action,
            "reason": payload.reason,
            "result": action_result,
        },
    )

    return {
        "status": "ok",
        "alert": {
            "id": row.id,
            "status": row.status,
            "severity": row.severity,
            "details": row.details or {},
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        },
        "result": action_result,
        "audit_log_id": audit_row.id,
    }


@router.get("/control-layer/scanner")
def admin_live_trading_scanner_control_state(
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    runtime = _read_json_value(redis_client, "pipeline:scanner:health", {})
    universe = _read_symbol_universe(redis_client)
    manual_trigger = _read_json_value(redis_client, "control_layer:scanner_manual_trigger", {})
    restart_state = _read_json_value(redis_client, "control_layer:scanner_restart_state", {})
    return {
        "runtime": runtime,
        "symbol_universe": universe,
        "manual_trigger": manual_trigger,
        "restart_state": restart_state,
    }


@router.post("/control-layer/scanner/restart")
def admin_live_trading_scanner_restart(
    payload: ScannerControlRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if current_admin.role not in {UserRole.OPS, *MANAGER_ROLES}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="role_not_allowed")
    if payload.confirmation_phrase.strip().upper() != SCANNER_RESTART_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_confirmation_phrase", "expected_phrase": SCANNER_RESTART_PHRASE},
        )

    restart_state = {
        "reset_at": datetime.now(timezone.utc).isoformat(),
        "reset_by": current_admin.id,
        "reason": payload.reason,
    }
    _write_json_value(redis_client, "pipeline:scanner:health", {"status": "reset", **restart_state})
    _write_json_value(redis_client, "control_layer:scanner_restart_state", restart_state)

    audit_row = create_audit_log(
        db,
        action="LIVE_CONTROL_SCANNER_RESTART",
        entity_type="scanner",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details=restart_state,
    )
    return {"status": "ok", "restart_state": restart_state, "audit_log_id": audit_row.id}


@router.post("/control-layer/scanner/manual-trigger")
def admin_live_trading_scanner_manual_trigger(
    payload: ScannerControlRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if current_admin.role not in {UserRole.OPS, *MANAGER_ROLES}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="role_not_allowed")
    if payload.confirmation_phrase.strip().upper() != SCANNER_TRIGGER_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_confirmation_phrase", "expected_phrase": SCANNER_TRIGGER_PHRASE},
        )

    trigger_payload = {
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "requested_by": current_admin.id,
        "reason": payload.reason,
        "status": "queued",
    }
    _write_json_value(redis_client, "control_layer:scanner_manual_trigger", trigger_payload)

    audit_row = create_audit_log(
        db,
        action="LIVE_CONTROL_SCANNER_MANUAL_TRIGGER",
        entity_type="scanner",
        entity_id="manual_trigger",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details=trigger_payload,
    )
    return {"status": "ok", "trigger": trigger_payload, "audit_log_id": audit_row.id}


@router.post("/control-layer/scanner/symbol-universe")
def admin_live_trading_scanner_symbol_universe(
    payload: ScannerSymbolUniverseRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _require_manager(current_admin)
    if payload.confirmation_phrase.strip().upper() != SCANNER_UNIVERSE_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_confirmation_phrase", "expected_phrase": SCANNER_UNIVERSE_PHRASE},
        )

    current = set(_read_symbol_universe(redis_client))
    symbols = {str(item).strip().upper() for item in payload.symbols if str(item).strip()}
    if payload.action == "add":
        current.update(symbols)
    else:
        current.difference_update(symbols)

    result = sorted(current)
    _write_json_value(redis_client, "control_layer:scanner_symbol_universe", {"symbols": result})

    audit_row = create_audit_log(
        db,
        action="LIVE_CONTROL_SCANNER_SYMBOL_UNIVERSE",
        entity_type="scanner",
        entity_id="symbol_universe",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={"action": payload.action, "symbols": sorted(list(symbols)), "reason": payload.reason},
    )
    return {"status": "ok", "symbol_universe": result, "audit_log_id": audit_row.id}


@router.get("/control-layer/trading-performance/open-positions")
def admin_live_trading_open_positions(
    limit: int = Query(default=100, ge=1, le=500),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.status == "open")
        .order_by(PaperPosition.updated_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "symbol": row.symbol,
                "side": row.side,
                "quantity": row.quantity,
                "entry_price": row.entry_price,
                "unrealized_pnl": row.unrealized_pnl,
                "opened_at": row.opened_at.isoformat() if row.opened_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.post("/control-layer/trading-performance/snapshot")
def admin_live_trading_capture_snapshot(
    payload: SnapshotRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _require_manager(current_admin)
    if payload.confirmation_phrase.strip().upper() != SNAPSHOT_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_confirmation_phrase", "expected_phrase": SNAPSHOT_PHRASE},
        )

    report = build_daily_report(db, redis_client)
    # Convert datetime to string for JSON serialization
    if "generated_at" in report and hasattr(report["generated_at"], "isoformat"):
        report["generated_at"] = report["generated_at"].isoformat()
    snapshot_item = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "captured_by": manager.id,
        "reason": payload.reason,
        "report": report,
    }
    redis_client.rpush("control_layer:performance_snapshots", json.dumps(snapshot_item, ensure_ascii=False, default=str))

    audit_row = create_audit_log(
        db,
        action="LIVE_CONTROL_PERFORMANCE_SNAPSHOT",
        entity_type="trading_performance",
        entity_id="daily",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="info",
        details={"reason": payload.reason, "snapshot_date": report.get("date")},
    )
    return {"status": "ok", "snapshot": snapshot_item, "audit_log_id": audit_row.id}


@router.post("/control-layer/trading-performance/reset-daily")
def admin_live_trading_reset_daily(
    payload: SnapshotRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _require_manager(current_admin)
    if payload.confirmation_phrase.strip().upper() != RESET_DAILY_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_confirmation_phrase", "expected_phrase": RESET_DAILY_PHRASE},
        )

    marker = {
        "reset_at": datetime.now(timezone.utc).isoformat(),
        "reset_by": manager.id,
        "reason": payload.reason,
    }
    _write_json_value(redis_client, "control_layer:daily_reset_marker", marker)

    audit_row = create_audit_log(
        db,
        action="LIVE_CONTROL_DAILY_RESET",
        entity_type="trading_performance",
        entity_id="daily_reset",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details=marker,
    )
    return {"status": "ok", "marker": marker, "audit_log_id": audit_row.id}


@router.post("/control-layer/risk-controls")
def admin_live_trading_update_risk_controls(
    payload: RiskControlUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _require_manager(current_admin)
    if payload.confirmation_phrase.strip().upper() != RISK_CONTROL_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_confirmation_phrase", "expected_phrase": RISK_CONTROL_PHRASE},
        )

    row = db.query(RiskOrchestratorPolicy).filter(RiskOrchestratorPolicy.id == "global").first()
    if row is None:
        row = RiskOrchestratorPolicy(id="global")
        db.add(row)

    row.daily_loss_limit_pct = payload.max_loss_pct
    row.account_max_notional_pct = payload.account_exposure_pct
    row.symbol_max_notional_pct = payload.symbol_exposure_pct
    db.commit()
    db.refresh(row)

    audit_row = create_audit_log(
        db,
        action="LIVE_CONTROL_RISK_PARAMS_UPDATED",
        entity_type="risk_orchestrator",
        entity_id="global",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="critical",
        details={
            "reason": payload.reason,
            "max_loss_pct": payload.max_loss_pct,
            "account_exposure_pct": payload.account_exposure_pct,
            "symbol_exposure_pct": payload.symbol_exposure_pct,
        },
    )
    return {
        "status": "ok",
        "risk_controls": {
            "max_loss_pct": row.daily_loss_limit_pct,
            "account_exposure_pct": row.account_max_notional_pct,
            "symbol_exposure_pct": row.symbol_max_notional_pct,
        },
        "audit_log_id": audit_row.id,
    }


@router.post("/control-layer/risk-override")
def admin_live_trading_risk_override(
    payload: RiskOverrideRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _require_manager(current_admin)
    if payload.confirmation_phrase.strip().upper() != RISK_OVERRIDE_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_confirmation_phrase", "expected_phrase": RISK_OVERRIDE_PHRASE},
        )

    override_payload = {
        "active": True,
        "decision": payload.decision,
        "reason": payload.reason,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "requested_by": manager.id,
        "ttl_minutes": payload.ttl_minutes,
    }
    _write_json_value(redis_client, "control_layer:risk_override", override_payload)
    redis_client.expire("control_layer:risk_override", payload.ttl_minutes * 60)

    audit_row = create_audit_log(
        db,
        action="LIVE_CONTROL_RISK_OVERRIDE",
        entity_type="risk_override",
        entity_id="global",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="critical",
        details=override_payload,
    )
    return {"status": "ok", "override": override_payload, "audit_log_id": audit_row.id}


@router.get("/control-layer/execution-quality/failed-orders")
def admin_live_trading_failed_orders(
    status_filter: str = Query(default="pending", pattern="^(pending|failed|resolved|all)$"),
    limit: int = Query(default=100, ge=1, le=500),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    query = db.query(FailedEvent)
    if status_filter != "all":
        query = query.filter(FailedEvent.status == status_filter)
    rows = query.order_by(FailedEvent.updated_at.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": row.id,
                "event_type": row.event_type,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "status": row.status,
                "retry_count": row.retry_count,
                "max_retry": row.max_retry,
                "error_message": row.error_message,
                "next_retry_at": row.next_retry_at.isoformat() if row.next_retry_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.post("/control-layer/execution-quality/retry")
def admin_live_trading_retry_failed_orders(
    payload: RetryFailedOrdersRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if current_admin.role == UserRole.OPS:
        allowed = True
    else:
        _require_manager(current_admin)
        allowed = True

    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="role_not_allowed")

    if payload.confirmation_phrase.strip().upper() != RETRY_ORDERS_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_confirmation_phrase", "expected_phrase": RETRY_ORDERS_PHRASE},
        )

    query = db.query(FailedEvent)
    if payload.ids:
        query = query.filter(FailedEvent.id.in_(payload.ids))
    else:
        query = query.filter(FailedEvent.status.in_(["pending", "failed"]))

    rows = query.limit(500).all()
    now = datetime.now(timezone.utc)
    results: list[dict] = []
    for row in rows:
        previous_status = row.status
        row.status = "pending"
        row.retry_count = int(row.retry_count or 0) + 1
        row.next_retry_at = now
        row.updated_at = now
        results.append(
            {
                "id": row.id,
                "order_id": row.entity_id,
                "previous_status": previous_status,
                "new_status": row.status,
                "result": "queued",
            }
        )

    db.commit()
    audit_row = create_audit_log(
        db,
        action="LIVE_CONTROL_RETRY_FAILED_ORDERS",
        entity_type="failed_event",
        entity_id="bulk_retry",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"reason": payload.reason, "retried_count": len(results), "ids": [item["id"] for item in results]},
    )

    return {
        "status": "ok",
        "retried_count": len(results),
        "results": results,
        "audit_log_id": audit_row.id,
    }


@router.post("/control-layer/execution-quality/remove")
def admin_live_trading_remove_failed_orders(
    payload: RemoveFailedOrdersRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if current_admin.role not in {UserRole.OPS, *MANAGER_ROLES}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="role_not_allowed")
    if payload.confirmation_phrase.strip().upper() != REMOVE_FAILED_ORDERS_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_confirmation_phrase", "expected_phrase": REMOVE_FAILED_ORDERS_PHRASE},
        )

    query = db.query(FailedEvent)
    if payload.ids:
        query = query.filter(FailedEvent.id.in_(payload.ids))
    else:
        query = query.filter(FailedEvent.status.in_(["pending", "failed"]))

    rows = query.limit(500).all()
    now = datetime.now(timezone.utc)
    removed: list[dict] = []
    for row in rows:
        row.status = "resolved"
        row.resolved_at = now
        row.updated_at = now
        removed.append({"id": row.id, "order_id": row.entity_id, "result": "removed"})

    db.commit()
    audit_row = create_audit_log(
        db,
        action="LIVE_CONTROL_REMOVE_FAILED_ORDERS",
        entity_type="failed_event",
        entity_id="bulk_remove",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"reason": payload.reason, "removed_count": len(removed), "ids": [item["id"] for item in removed]},
    )
    return {"status": "ok", "removed_count": len(removed), "results": removed, "audit_log_id": audit_row.id}


@router.get("/summary")
def admin_live_trading_summary(
    window: str = Query(default="1h", pattern="^(1h|6h|24h)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    try:
        return build_live_trading_summary(db, redis_client, window=window)
    except Exception as exc:
        return {
            "window": window,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "system_health": {"status": "degraded", "execution_mode": "MOCK", "kill_switch_active": False, "fallback_active": True},
            "critical_alerts": {"status": "critical", "items": [{"code": "summary_generation_failed", "message": str(exc)}]},
            "component_errors": [{"component": "summary", "error": str(exc)}],
        }


@router.get("/scanner-health")
def admin_live_trading_scanner_health(
    window: str = Query(default="1h", pattern="^(1h|6h|24h)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return build_scanner_health(db, redis_client, window=window)


@router.get("/execution-quality")
def admin_live_trading_execution_quality(
    window: str = Query(default="1h", pattern="^(1h|6h|24h)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return build_execution_quality_summary(db, window=window)


@router.get("/risk-summary")
def admin_live_trading_risk_summary(
    window: str = Query(default="1h", pattern="^(1h|6h|24h)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return build_risk_summary(db, redis_client, window=window)


@router.get("/daily-report")
def admin_live_trading_daily_report(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return build_daily_report(db, redis_client)


@router.get("/learning-summary")
def admin_live_trading_learning_summary(
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return build_learning_summary(db, window=window)


@router.get("/daily-report/export")
def admin_live_trading_daily_report_export(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    report = build_daily_report(db, redis_client)
    if format == "csv":
        content = export_daily_report_csv(report)
        filename = f"live_trading_daily_report_{report.get('date', 'latest')}.csv"
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    return report
