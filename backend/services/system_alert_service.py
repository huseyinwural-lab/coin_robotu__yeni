from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

from sqlalchemy.orm import Session

from models import SystemAlert
from services.alert_channel_service import DEDUP_WINDOW_SECONDS, dispatch_alert


def _extract_entity_key(details: dict) -> str | None:
    for key in ["strategy_id", "symbol", "account_id", "artifact_id", "intent_id", "exchange_order_id"]:
        value = details.get(key)
        if value:
            return str(value)
    return None


def _extract_state_key(details: dict) -> str | None:
    for key in ["state", "status", "event_state", "state_code"]:
        value = details.get(key)
        if value:
            return str(value)
    return None


def _compute_fingerprint(alert_type: str, severity: str, entity_key: str | None, root_cause_code: str | None) -> str:
    raw = f"{alert_type}|{severity}|{entity_key or ''}|{root_cause_code or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_system_alert(
    db: Session,
    *,
    alert_type: str,
    severity: str,
    message: str,
    details: dict | None = None,
    dedupe_window_seconds: int = DEDUP_WINDOW_SECONDS,
    entity_key: str | None = None,
    root_cause_code: str | None = None,
    state_key: str | None = None,
) -> SystemAlert:
    now = datetime.now(timezone.utc)
    details = details or {}
    entity_key = entity_key or _extract_entity_key(details)
    state_key = state_key or _extract_state_key(details)

    fingerprint = _compute_fingerprint(alert_type, severity, entity_key, root_cause_code)

    existing = (
        db.query(SystemAlert)
        .filter(SystemAlert.fingerprint == fingerprint)
        .order_by(SystemAlert.last_triggered_at.desc())
        .first()
    )

    if existing and existing.status in {"ack", "resolved"}:
        if state_key == existing.state_key:
            return existing

    if existing and existing.status in {"open", "ack"} and existing.last_triggered_at:
        delta = now - existing.last_triggered_at
        if delta.total_seconds() < dedupe_window_seconds:
            existing.occurrences += 1
            existing.last_triggered_at = now
            existing.severity = severity
            existing.message = message or existing.message
            existing.details = details or existing.details
            existing.delivery_status = {"status": "DEDUPED", "dedupe_window_seconds": dedupe_window_seconds}
            db.commit()
            db.refresh(existing)
            return existing

    alert = SystemAlert(
        alert_type=alert_type,
        severity=severity,
        message=message,
        fingerprint=fingerprint,
        entity_key=entity_key,
        root_cause_code=root_cause_code,
        state_key=state_key,
        details=details,
        status="open",
        occurrences=1,
        last_triggered_at=now,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    delivery_status = dispatch_alert(
        {
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "details": alert.details,
            "entity_key": alert.entity_key,
            "root_cause_code": alert.root_cause_code,
        }
    )
    alert.delivery_status = delivery_status
    db.commit()
    db.refresh(alert)
    return alert


def list_system_alerts(db: Session, status: str | None = None, limit: int = 50) -> list[SystemAlert]:
    query = db.query(SystemAlert)
    if status:
        query = query.filter(SystemAlert.status == status)
    return query.order_by(SystemAlert.last_triggered_at.desc()).limit(limit).all()


def update_system_alert_status(db: Session, alert: SystemAlert, status: str) -> SystemAlert:
    alert.status = status
    alert.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return alert
