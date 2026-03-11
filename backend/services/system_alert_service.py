from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import SystemAlert


def create_system_alert(
    db: Session,
    *,
    alert_type: str,
    severity: str,
    message: str,
    details: dict | None = None,
    dedupe_window_seconds: int = 600,
) -> SystemAlert:
    now = datetime.now(timezone.utc)
    details = details or {}

    existing = (
        db.query(SystemAlert)
        .filter(SystemAlert.alert_type == alert_type, SystemAlert.status.in_(["open", "ack"]))
        .order_by(SystemAlert.last_triggered_at.desc())
        .first()
    )
    if existing and existing.last_triggered_at:
        delta = now - existing.last_triggered_at
        if delta.total_seconds() < dedupe_window_seconds:
            existing.occurrences += 1
            existing.last_triggered_at = now
            existing.severity = severity
            existing.message = message or existing.message
            existing.details = details or existing.details
            db.commit()
            db.refresh(existing)
            return existing

    alert = SystemAlert(
        alert_type=alert_type,
        severity=severity,
        message=message,
        details=details,
        status="open",
        occurrences=1,
        last_triggered_at=now,
    )
    db.add(alert)
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
