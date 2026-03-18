from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import AuditLog


def _window_start(last_24h: bool = True) -> datetime:
    now = datetime.now(timezone.utc)
    return now - timedelta(hours=24) if last_24h else now - timedelta(days=3650)


def _reason_from_details(details: dict | None) -> str:
    payload = dict(details or {})
    reason = str(payload.get("reason") or "").strip().upper()
    if reason:
        return reason

    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    reason_codes = readiness.get("reason_codes") if isinstance(readiness, dict) else []
    if isinstance(reason_codes, list) and reason_codes:
        return str(reason_codes[0] or "READINESS_FAIL").strip().upper()

    return "READINESS_FAIL"


def count_blocked_trades(db: Session, *, last_24h: bool = True) -> int:
    start = _window_start(last_24h)
    return (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "EXECUTION_BLOCKED",
            AuditLog.created_at >= start,
        )
        .count()
    )


def count_overrides(db: Session, *, last_24h: bool = True) -> int:
    start = _window_start(last_24h)
    return (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "EXECUTION_OVERRIDE_ENABLED",
            AuditLog.created_at >= start,
        )
        .count()
    )


def top_block_reasons(db: Session, *, last_24h: bool = True, limit: int = 5) -> list[dict]:
    start = _window_start(last_24h)
    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "EXECUTION_BLOCKED",
            AuditLog.created_at >= start,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(500)
        .all()
    )
    reason_counter = Counter(_reason_from_details(row.details or {}) for row in rows)
    return [{"reason": reason, "count": int(count)} for reason, count in reason_counter.most_common(max(limit, 1))]


def build_guard_telemetry_payload(db: Session) -> dict:
    return {
        "blocked_24h": int(count_blocked_trades(db, last_24h=True)),
        "override_24h": int(count_overrides(db, last_24h=True)),
        "top_reasons": top_block_reasons(db, last_24h=True),
    }
