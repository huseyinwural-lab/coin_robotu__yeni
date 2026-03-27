from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from model_domains.security_branding import AuthRiskEvent, SuspiciousActivityAlert
from models import User


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_suspicious_activity_tables(db: Session) -> None:
    for model in (AuthRiskEvent, SuspiciousActivityAlert):
        try:
            model.__table__.create(bind=db.bind, checkfirst=True)
        except Exception:
            continue


def create_risk_event(
    db: Session,
    *,
    user: User,
    action_name: str,
    risk_level: str,
    risk_reasons: list[str],
    requires_step_up: bool,
    ip_address: str | None,
    country_iso: str | None,
    device_fingerprint: str | None,
    metadata: dict | None = None,
) -> AuthRiskEvent:
    ensure_suspicious_activity_tables(db)
    row = AuthRiskEvent(
        user_id=user.id,
        action_name=str(action_name or "login")[:120],
        risk_level=str(risk_level or "low")[:20],
        risk_reasons=list(risk_reasons or []),
        requires_step_up=bool(requires_step_up),
        ip_address=str(ip_address or "")[:120] or None,
        country_iso=str(country_iso or "")[:10] or None,
        device_fingerprint=str(device_fingerprint or "")[:160] or None,
        metadata_json=dict(metadata or {}),
    )
    db.add(row)
    db.flush()
    return row


def maybe_create_suspicious_alert(
    db: Session,
    *,
    user: User,
    risk_event: AuthRiskEvent,
) -> SuspiciousActivityAlert | None:
    reasons = set(risk_event.risk_reasons or [])
    should_alert = bool(
        risk_event.risk_level in {"high", "critical"}
        or {"country_change", "high_amount"}.intersection(reasons)
        or len(reasons) >= 3
    )
    if not should_alert:
        return None

    alert = SuspiciousActivityAlert(
        user_id=user.id,
        risk_event_id=risk_event.id,
        alert_type="risk_event",
        severity="high" if risk_event.risk_level in {"high", "critical"} else "medium",
        status="open",
        title="suspicious_activity_detected",
        details_json={
            "risk_level": risk_event.risk_level,
            "risk_reasons": list(risk_event.risk_reasons or []),
            "action_name": risk_event.action_name,
            "ip_address": risk_event.ip_address,
            "country_iso": risk_event.country_iso,
            "device_fingerprint": risk_event.device_fingerprint,
            "detected_at": _now().isoformat(),
        },
    )
    db.add(alert)
    db.flush()
    return alert


def list_open_suspicious_alerts(db: Session, *, limit: int = 100) -> list[SuspiciousActivityAlert]:
    ensure_suspicious_activity_tables(db)
    return (
        db.query(SuspiciousActivityAlert)
        .filter(SuspiciousActivityAlert.status == "open")
        .order_by(SuspiciousActivityAlert.created_at.desc())
        .limit(max(1, min(int(limit or 100), 500)))
        .all()
    )


def resolve_suspicious_alert(
    db: Session,
    *,
    alert_id: str,
    resolver_user_id: str,
    note: str | None,
) -> SuspiciousActivityAlert | None:
    ensure_suspicious_activity_tables(db)
    row = db.query(SuspiciousActivityAlert).filter(SuspiciousActivityAlert.id == alert_id).first()
    if row is None:
        return None
    row.status = "resolved"
    row.resolved_by_user_id = resolver_user_id
    row.resolved_note = str(note or "")[:1000] or None
    row.resolved_at = _now()
    db.flush()
    return row
