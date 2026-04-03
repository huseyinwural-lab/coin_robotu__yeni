import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin
from models import AdminControl, AuditLog, SystemAlert, User, UserExecutionIntent, UserRole
from core.process_guard import spawn_shell_and_reap
from services.audit_service import create_audit_log
from services.execution_safety_service import execution_safety_snapshot, update_execution_safety_state

router = APIRouter(prefix="/admin/action-center", tags=["admin_action_center"])


MANAGER_ROLES = {UserRole.SUPER_ADMIN, UserRole.ADMIN}
RESTART_CONFIRM_PHRASE = "RESTART SERVICES"
ALERTS_CLEAR_CONFIRM_PHRASE = "CLEAR ALL ALERTS"
BULK_ACK_CONFIRM_PHRASE = "ACK SELECTED ALERTS"
AUTO_CLOSE_CONFIRM_PHRASE = "RUN AUTO CLOSE"


class ActionCenterKillSwitchToggleRequest(BaseModel):
    active: bool
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=5, max_length=80)
    requested_by: str | None = None


class ActionCenterRestartServicesRequest(BaseModel):
    targets: list[str] = Field(default_factory=lambda: ["backend", "frontend"])
    reason: str = Field(min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=5, max_length=80)


class ActionCenterClearAllAlertsRequest(BaseModel):
    status_filter: str = Field(default="open")
    reason: str = Field(default="dashboard_clear_all_alerts", min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=5, max_length=80)


class ActionCenterBulkAckRequest(BaseModel):
    ids: list[str] = Field(min_length=1)
    reason: str = Field(default="dashboard_bulk_ack", min_length=3, max_length=300)
    confirmation_phrase: str = Field(min_length=5, max_length=80)


class ActionCenterCloseNextActionsRequest(BaseModel):
    ack_open_alerts: bool = True
    reject_stale_approvals: bool = True
    stale_days: int = Field(default=30, ge=1, le=365)
    retry_timeout_rejections: bool = True
    clear_kill_switch: bool = False
    reason: str = Field(default="dashboard_auto_close", min_length=5, max_length=300)
    confirmation_phrase: str = Field(min_length=5, max_length=80)


def _require_manager(current_admin: User) -> User:
    if current_admin.role not in MANAGER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_or_admin_required")
    return current_admin


def _normalize_restart_targets(targets: list[str]) -> list[str]:
    resolved: list[str] = []
    allowed = {"backend", "frontend"}

    for item in targets:
        token = str(item or "").strip().lower()
        if not token:
            continue
        if token in {"all", "system", "services"}:
            resolved.extend(["backend", "frontend"])
            continue
        if token in allowed:
            resolved.append(token)

    normalized = sorted(set(resolved))
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_restart_targets")
    return normalized


def _build_alert_recommendation(alert_row: SystemAlert) -> dict:
    root_code = str(alert_row.root_cause_code or "").lower()
    alert_type = str(alert_row.alert_type or "").lower()

    if "timeout" in root_code or "pending_timeout" in root_code:
        return {
            "title": "Intent timeout / queue sıkışması",
            "description": "Runtime Recovery ekranında timeout olmuş intent'leri inceleyip requeue edin.",
            "runbook_link": "/admin/runtime/recovery",
            "suggested_action": {
                "action_key": "auto_close_run",
                "action_label": "Auto-Close Run Now",
                "reason_hint": "timeout_alert_auto_close",
            },
        }
    if "exchange" in root_code or "exchange" in alert_type:
        return {
            "title": "Exchange bağlantı problemi",
            "description": "Exchange health ve API izinlerini kontrol edin, ardından test order çalıştırın.",
            "runbook_link": "/admin/exchanges",
            "suggested_action": {
                "action_key": "restart_services",
                "action_label": "Restart Services",
                "reason_hint": "exchange_alert_service_restart",
            },
        }
    if "risk" in alert_type:
        return {
            "title": "Risk policy ihlali",
            "description": "Risk orchestrator ve exposure limitlerini doğrulayıp anomalileri temizleyin.",
            "runbook_link": "/admin/risk-orchestrator",
            "suggested_action": {
                "action_key": "go_risk_orchestrator",
                "action_label": "Risk Orchestrator Aç",
                "reason_hint": "risk_alert_review",
            },
        }
    return {
        "title": "Genel operasyon incelemesi",
        "description": "Audit log ve anomaly timeline üzerinden root cause zincirini takip edin.",
        "runbook_link": "/admin/anomaly-timeline",
        "suggested_action": {
            "action_key": "go_audit_logs",
            "action_label": "Audit Logs Aç",
            "reason_hint": "generic_alert_triage",
        },
    }


def _serialize_alert_row(row: SystemAlert) -> dict:
    details = row.details or {}
    source = str(details.get("source") or row.entity_key or details.get("module") or "unknown")
    recommendation = _build_alert_recommendation(row)
    return {
        "id": row.id,
        "alert_type": row.alert_type,
        "severity": row.severity,
        "message": row.message,
        "status": row.status,
        "occurrences": int(row.occurrences or 0),
        "root_cause_code": row.root_cause_code,
        "entity_key": row.entity_key,
        "source": source,
        "details": details,
        "delivery_status": row.delivery_status or {},
        "last_triggered_at": row.last_triggered_at.isoformat() if row.last_triggered_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "recommendation": recommendation,
    }


def _serialize_audit_row(row: AuditLog) -> dict:
    return {
        "id": row.id,
        "action": row.action,
        "severity": row.severity,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "actor_user_id": row.actor_user_id,
        "actor_role": row.actor_role,
        "details": row.details or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _kill_switch_payload() -> dict:
    raw = redis_client.get("pipeline:kill_switch")
    if not raw:
        return {"active": False, "reasons": []}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        payload = json.loads(raw) if isinstance(raw, str) else {}
        return payload if isinstance(payload, dict) else {"active": False, "reasons": []}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"active": False, "reasons": []}


@router.get("/alerts")
def action_center_alerts(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    status_filter: str = Query(default="open"),
    severity: str | None = Query(default=None),
    alert_type: str | None = Query(default=None),
    source: str | None = Query(default=None),
    window_hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=200, ge=1, le=500),
):
    _ = current_admin
    status_value = None if status_filter == "all" else status_filter
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    query = db.query(SystemAlert).filter(SystemAlert.created_at >= since)
    if status_value:
        query = query.filter(SystemAlert.status == status_value)
    if severity:
        query = query.filter(SystemAlert.severity == severity)
    if alert_type:
        query = query.filter(SystemAlert.alert_type == alert_type)

    rows = query.order_by(SystemAlert.last_triggered_at.desc()).limit(limit).all()

    needle = str(source or "").strip().lower()
    if needle:
        rows = [
            row
            for row in rows
            if needle in str((row.details or {}).get("source") or "").lower()
            or needle in str(row.entity_key or "").lower()
            or needle in str((row.details or {}).get("module") or "").lower()
        ]

    return {
        "items": [_serialize_alert_row(row) for row in rows],
        "filters": {
            "status_filter": status_filter,
            "severity": severity,
            "alert_type": alert_type,
            "source": source,
            "window_hours": window_hours,
            "limit": limit,
        },
    }


@router.get("/alerts/{alert_id}/detail")
def action_center_alert_detail(
    alert_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    row = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert_not_found")

    response = _serialize_alert_row(row)
    response["audit_log_link"] = "/admin/audit-logs"
    return response


@router.post("/alerts/bulk-ack")
def action_center_bulk_ack_alerts(
    payload: ActionCenterBulkAckRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _require_manager(current_admin)

    phrase = str(payload.confirmation_phrase or "").strip().upper()
    if phrase != BULK_ACK_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_confirmation_phrase",
                "expected_phrase": BULK_ACK_CONFIRM_PHRASE,
            },
        )

    rows = db.query(SystemAlert).filter(SystemAlert.id.in_(payload.ids)).all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alerts_not_found")

    now = datetime.now(timezone.utc)
    acked_ids: list[str] = []
    for row in rows:
        if row.status == "ack":
            continue
        row.status = "ack"
        row.updated_at = now
        acked_ids.append(row.id)

    db.commit()
    audit_entry = create_audit_log(
        db,
        action="ACTION_CENTER_ALERTS_BULK_ACK",
        entity_type="system_alert",
        entity_id="bulk",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={
            "acked_count": len(acked_ids),
            "ids": acked_ids,
            "reason": payload.reason,
            "expected_phrase": BULK_ACK_CONFIRM_PHRASE,
        },
    )

    return {
        "status": "ok",
        "acked_count": len(acked_ids),
        "ids": acked_ids,
        "audit_log_id": audit_entry.id,
    }


@router.post("/alerts/clear-all")
def action_center_clear_all_alerts(
    payload: ActionCenterClearAllAlertsRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _require_manager(current_admin)

    phrase = str(payload.confirmation_phrase or "").strip().upper()
    if phrase != ALERTS_CLEAR_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_confirmation_phrase",
                "expected_phrase": ALERTS_CLEAR_CONFIRM_PHRASE,
            },
        )

    status_value = None if payload.status_filter == "all" else payload.status_filter
    query = db.query(SystemAlert)
    if status_value:
        query = query.filter(SystemAlert.status == status_value)
    rows = query.all()

    now = datetime.now(timezone.utc)
    acked_ids: list[str] = []
    for row in rows:
        if row.status == "ack":
            continue
        row.status = "ack"
        row.updated_at = now
        acked_ids.append(row.id)

    db.commit()
    audit_entry = create_audit_log(
        db,
        action="ACTION_CENTER_ALERTS_CLEAR_ALL",
        entity_type="system_alert",
        entity_id="global",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="warning",
        details={
            "acked_count": len(acked_ids),
            "status_filter": payload.status_filter,
            "reason": payload.reason,
        },
    )

    return {
        "status": "ok",
        "acked_count": len(acked_ids),
        "ids": acked_ids,
        "audit_log_id": audit_entry.id,
    }


@router.post("/global-kill-switch/toggle")
def action_center_toggle_global_kill_switch(
    payload: ActionCenterKillSwitchToggleRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _require_manager(current_admin)

    expected_phrase = "DISABLE TRADING" if payload.active else "ENABLE TRADING"
    phrase = str(payload.confirmation_phrase or "").strip().upper()
    if phrase != expected_phrase:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_confirmation_phrase",
                "expected_phrase": expected_phrase,
            },
        )

    snapshot = update_execution_safety_state(
        db,
        trading_enabled=not payload.active,
        reason=payload.reason,
        requested_by=payload.requested_by or manager.email,
        effective_at=datetime.now(timezone.utc).isoformat(),
        actor_user_id=manager.id,
        actor_role=manager.role.value,
    )

    if payload.active:
        redis_client.set(
            "pipeline:kill_switch",
            json.dumps(
                {
                    "triggered": True,
                    "active": True,
                    "reasons": [payload.reason],
                    "triggered_by": manager.id,
                    "triggered_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
        )
    else:
        redis_client.set(
            "pipeline:kill_switch",
            json.dumps(
                {
                    "triggered": False,
                    "active": False,
                    "reasons": ["cleared_by_action_center"],
                    "cleared_by": manager.id,
                    "cleared_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
        )

    audit_entry = create_audit_log(
        db,
        action="ACTION_CENTER_KILL_SWITCH_TOGGLE",
        entity_type="kill_switch",
        entity_id="global",
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="critical" if payload.active else "warning",
        details={
            "active": payload.active,
            "reason": payload.reason,
            "expected_phrase": expected_phrase,
            "snapshot_reason_code": snapshot.get("reason_code"),
            "trading_enabled": bool(snapshot.get("trading_enabled")),
        },
    )

    current = execution_safety_snapshot(db)
    return {
        "status": "ok",
        "kill_switch_active": bool(payload.active),
        "trading_enabled": bool(current.get("trading_enabled")),
        "reason_code": snapshot.get("reason_code"),
        "current_total_exposure": current.get("current_total_exposure"),
        "current_active_positions": current.get("current_active_positions"),
        "audit_log_id": audit_entry.id,
    }


@router.post("/restart-services")
def action_center_restart_services(
    payload: ActionCenterRestartServicesRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _require_manager(current_admin)

    phrase = str(payload.confirmation_phrase or "").strip().upper()
    if phrase != RESTART_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_confirmation_phrase",
                "expected_phrase": RESTART_CONFIRM_PHRASE,
            },
        )

    targets = _normalize_restart_targets(payload.targets)
    services_arg = " ".join(targets)
    command = f"(sleep 1; supervisorctl restart {services_arg}) >> /tmp/action_center_restart.log 2>&1"
    spawn_shell_and_reap(command=command, cwd="/app")

    operation_id = f"restart-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    audit_entry = create_audit_log(
        db,
        action="ACTION_CENTER_RESTART_SERVICES_REQUESTED",
        entity_type="system_service",
        entity_id=operation_id,
        actor_user_id=manager.id,
        actor_role=manager.role.value,
        severity="critical",
        details={
            "targets": targets,
            "reason": payload.reason,
            "operation_id": operation_id,
            "restart_log": "/tmp/action_center_restart.log",
        },
    )

    return {
        "status": "scheduled",
        "operation_id": operation_id,
        "targets": targets,
        "restart_log": "/tmp/action_center_restart.log",
        "audit_log_id": audit_entry.id,
    }


@router.get("/incident-history")
def action_center_incident_history(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=5, le=100),
):
    _ = current_admin
    audit_rows = (
        db.query(AuditLog)
        .filter(
            (AuditLog.action.ilike("ACTION_CENTER_%"))
            | (AuditLog.entity_type.in_(["kill_switch", "system_alert", "execution_safety_state", "system_service"]))
            | (AuditLog.severity == "critical")
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    alert_rows = (
        db.query(SystemAlert)
        .filter(SystemAlert.status.in_(["open", "ack", "resolved"]))
        .order_by(SystemAlert.updated_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "audit_events": [_serialize_audit_row(row) for row in audit_rows],
        "recent_alerts": [_serialize_alert_row(row) for row in alert_rows],
    }


@router.get("/close-next-actions/latest")
def close_next_actions_latest(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    row = (
        db.query(AuditLog)
        .filter(AuditLog.action == "ACTION_CENTER_CLOSE_NEXT_ACTIONS")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    if row is None:
        return {"found": False}
    return {"found": True, "item": _serialize_audit_row(row)}


@router.get("/summary")
def action_center_summary(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=30)

    pending_approvals = db.query(User).filter(User.role == UserRole.USER, User.approval_status == "pending").count()
    stale_pending_approvals = (
        db.query(User)
        .filter(User.role == UserRole.USER, User.approval_status == "pending", User.approval_requested_at <= stale_cutoff)
        .count()
    )
    open_alerts = db.query(SystemAlert).filter(SystemAlert.status == "open").count()
    queued_intents = db.query(UserExecutionIntent).filter(UserExecutionIntent.status == "QUEUED").count()
    rejected_intents = db.query(UserExecutionIntent).filter(UserExecutionIntent.status == "REJECTED").count()
    rejected_rows = db.query(UserExecutionIntent).filter(UserExecutionIntent.status == "REJECTED").all()
    timeout_rejected_intents = sum(
        1 for row in rejected_rows if "pending_timeout" in [str(item) for item in (row.reject_reason_codes or [])]
    )

    kill_switch = _kill_switch_payload()
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()

    return {
        "pending_approvals": pending_approvals,
        "stale_pending_approvals": stale_pending_approvals,
        "open_alerts": open_alerts,
        "queued_intents": queued_intents,
        "rejected_intents": rejected_intents,
        "timeout_rejected_intents": timeout_rejected_intents,
        "kill_switch_active": bool(kill_switch.get("active")),
        "kill_switch_reasons": kill_switch.get("reasons") or [],
        "emergency_mode": bool(control.emergency_mode) if control else False,
        "disable_futures": bool(control.disable_futures) if control else False,
        "generated_at": now.isoformat(),
    }


@router.post("/close-next-actions")
def close_next_actions(
    payload: ActionCenterCloseNextActionsRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    manager = _require_manager(current_admin)

    phrase = str(payload.confirmation_phrase or "").strip().upper()
    if phrase != AUTO_CLOSE_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_confirmation_phrase",
                "expected_phrase": AUTO_CLOSE_CONFIRM_PHRASE,
            },
        )

    ack_open_alerts = bool(payload.ack_open_alerts)
    reject_stale_approvals = bool(payload.reject_stale_approvals)
    stale_days = int(payload.stale_days)
    retry_timeout_rejections = bool(payload.retry_timeout_rejections)
    clear_kill_switch = bool(payload.clear_kill_switch)

    acked_alerts = 0
    rejected_approvals = 0
    retried_intents = 0

    if ack_open_alerts:
        alerts = db.query(SystemAlert).filter(SystemAlert.status == "open").all()
        now = datetime.now(timezone.utc)
        for alert in alerts:
            alert.status = "ack"
            alert.updated_at = now
        acked_alerts = len(alerts)

    if reject_stale_approvals:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(stale_days, 1))
        stale_users = (
            db.query(User)
            .filter(
                User.role == UserRole.USER,
                User.approval_status == "pending",
                User.approval_requested_at <= cutoff,
            )
            .all()
        )
        now = datetime.now(timezone.utc)
        for user in stale_users:
            user.approval_status = "rejected"
            user.is_active = False
            user.approved_at = None
            user.disabled_at = now
        rejected_approvals = len(stale_users)

    if retry_timeout_rejections:
        timeout_rows = [
            row
            for row in db.query(UserExecutionIntent).filter(UserExecutionIntent.status == "REJECTED").all()
            if "pending_timeout" in [str(item) for item in (row.reject_reason_codes or [])]
        ]
        now = datetime.now(timezone.utc)
        for row in timeout_rows:
            row.status = "QUEUED"
            row.submitted_at = now
            row.approved_at = None
            row.released_at = None
            row.cancelled_at = None
            row.admin_user_id = manager.id
            row.admin_note = "requeued_by_action_center"
            row.reject_reason_codes = []
        retried_intents = len(timeout_rows)

    if clear_kill_switch:
        redis_client.set(
            "pipeline:kill_switch",
            json.dumps(
                {
                    "triggered": False,
                    "active": False,
                    "reasons": ["cleared_by_action_center"],
                    "cleared_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
        )
        control = db.query(AdminControl).filter(AdminControl.id == "global").first()
        if control:
            control.emergency_mode = False
            control.disable_futures = False

    db.commit()
    audit_entry = create_audit_log(
        db,
        action="ACTION_CENTER_CLOSE_NEXT_ACTIONS",
        entity_type="admin_action_center",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=manager.role.value,
        severity="warning",
        details={
            "acked_alerts": acked_alerts,
            "rejected_approvals": rejected_approvals,
            "retried_intents": retried_intents,
            "clear_kill_switch": clear_kill_switch,
            "stale_days": stale_days,
            "reason": payload.reason,
            "expected_phrase": AUTO_CLOSE_CONFIRM_PHRASE,
        },
    )
    return {
        "status": "completed",
        "acked_alerts": acked_alerts,
        "rejected_approvals": rejected_approvals,
        "retried_intents": retried_intents,
        "clear_kill_switch": clear_kill_switch,
        "audit_log_id": audit_entry.id,
    }
