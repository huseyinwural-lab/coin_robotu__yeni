from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

from sqlalchemy.orm import Session

from models import SystemAlert
from services.alert_channel_service import DEDUP_WINDOW_SECONDS, deliver_execution_alert, dispatch_alert


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
    normalized_type = str(alert_type or "")
    normalized_entity = str(entity_key or "")
    normalized_root = str(root_cause_code or "")
    normalized_severity = str(severity or "")
    if normalized_type.startswith("execution_") and normalized_entity:
        raw = f"{normalized_type}|{normalized_entity}|{normalized_root}"
    else:
        raw = f"{normalized_type}|{normalized_severity}|{normalized_entity}|{normalized_root}"
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
    details = dict(details or {})
    grouped_window = int(details.get("group_window_seconds") or dedupe_window_seconds or DEDUP_WINDOW_SECONDS)
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
        last_triggered = existing.last_triggered_at
        if last_triggered.tzinfo is None:
            last_triggered = last_triggered.replace(tzinfo=timezone.utc)
        delta = now - last_triggered
        if delta.total_seconds() < grouped_window:
            existing.occurrences += 1
            existing.last_triggered_at = now
            existing.severity = severity
            existing.message = message or existing.message
            merged_details = dict(existing.details or {})
            merged_details.update(details or {})
            merged_details["grouped_count"] = int(existing.occurrences or 1)
            existing.details = merged_details
            existing.delivery_status = {"status": "DEDUPED", "dedupe_window_seconds": grouped_window}
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
        details={
            **details,
            "grouped_count": max(int(details.get("grouped_count") or 0), 1),
        },
        status="open",
        occurrences=1,
        last_triggered_at=now,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    if str(alert.alert_type or "").lower().startswith("execution_"):
        tier = str(alert.severity or "INFO").upper()
        if tier == "INFO" and not bool((alert.details or {}).get("is_test")):
            delivery_status = {
                "status": "SENT",
                "provider": "slack",
                "reason": "info_silent_tier",
                "escalation_tier": "silent",
                "attempt_no": int(alert.attempt_count or 0),
            }
        else:
            delivery_status = deliver_execution_alert(db, alert=alert)
    else:
        delivery_status = dispatch_alert(
            {
                "alert_id": alert.id,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "message": alert.message,
                "details": alert.details,
                "entity_key": alert.entity_key,
                "root_cause_code": alert.root_cause_code,
            },
            db=db,
        )
    alert.delivery_status = delivery_status
    db.commit()
    db.refresh(alert)
    return alert


def list_system_alerts(
    db: Session,
    *,
    status: str | None = None,
    severity: str | None = None,
    alert_type: str | None = None,
    entity_key: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 50,
) -> list[SystemAlert]:
    query = db.query(SystemAlert)
    if status:
        query = query.filter(SystemAlert.status == status)
    if severity:
        query = query.filter(SystemAlert.severity == severity)
    if alert_type:
        query = query.filter(SystemAlert.alert_type == alert_type)
    if entity_key:
        query = query.filter(SystemAlert.entity_key == entity_key)
    if date_from:
        query = query.filter(SystemAlert.created_at >= date_from)
    if date_to:
        query = query.filter(SystemAlert.created_at <= date_to)
    return query.order_by(SystemAlert.last_triggered_at.desc()).limit(limit).all()


def build_alert_timeline(db: Session, *, days: int = 14) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(SystemAlert)
        .filter(SystemAlert.created_at >= since)
        .order_by(SystemAlert.created_at.asc())
        .all()
    )
    buckets: dict[str, int] = {}
    for row in rows:
        day = row.created_at.date().isoformat()
        buckets[day] = buckets.get(day, 0) + 1
    return [{"date": day, "count": buckets[day]} for day in sorted(buckets.keys())]


def update_system_alert_status(db: Session, alert: SystemAlert, status: str) -> SystemAlert:
    alert.status = status
    alert.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return alert
