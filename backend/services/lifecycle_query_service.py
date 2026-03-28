from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from models import AuditLog, LifecycleSavedQuery
from services.trading_lifecycle_debugger_service import normalize_audit_log_event


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _encode_cursor(ts: datetime, marker: str) -> str:
    payload = f"{ts.isoformat()}|{marker}"
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        ts_raw, marker = decoded.split("|", 1)
        ts = _parse_iso(ts_raw)
        if ts is None:
            return None
        return ts, marker
    except Exception:
        return None


def search_lifecycle_events(
    db: Session,
    *,
    page_size: int = 100,
    cursor: str | None = None,
    q: str | None = None,
    payload_query: str | None = None,
    severity: str | None = None,
    strategy_id: str | None = None,
    symbol: str | None = None,
    user_id: str | None = None,
    event_type: str | None = None,
    environment: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    include_test_events: bool = False,
    archive_mode: bool = False,
    archive_cutoff_days: int = 7,
) -> dict:
    started = time.perf_counter()
    page_size = max(20, min(page_size, 300))
    details_text = cast(AuditLog.details, String)
    query = db.query(AuditLog)

    if q:
        needle = f"%{q.strip()}%"
        query = query.filter(
            or_(
                AuditLog.action.ilike(needle),
                AuditLog.entity_id.ilike(needle),
                details_text.ilike(needle),
            )
        )

    if payload_query:
        search_term = payload_query.strip()
        if search_term:
            query = query.filter(
                func.to_tsvector("simple", func.coalesce(details_text, "")).op("@@")(func.plainto_tsquery("simple", search_term))
            )
    if severity:
        query = query.filter(AuditLog.severity == severity.upper())
    if strategy_id:
        query = query.filter(func.lower(func.coalesce(AuditLog.details.op("->>")("strategy_id"), "")) == strategy_id.strip().lower())
    if symbol:
        query = query.filter(func.upper(func.coalesce(AuditLog.details.op("->>")("symbol"), "")) == symbol.strip().upper())
    if user_id:
        normalized_user_id = user_id.strip()
        query = query.filter(
            or_(
                AuditLog.actor_user_id == normalized_user_id,
                func.coalesce(AuditLog.details.op("->>")("user_id"), "") == normalized_user_id,
            )
        )
    if event_type:
        normalized_event_type = event_type.strip()
        query = query.filter(
            or_(
                AuditLog.action.ilike(f"%{normalized_event_type}%"),
                func.lower(func.coalesce(AuditLog.details.op("->>")("event_type"), "")) == normalized_event_type.lower(),
            )
        )
    if environment:
        query = query.filter(AuditLog.environment == environment.strip().lower())
    if not include_test_events:
        query = query.filter(or_(AuditLog.is_test_event.is_(False), AuditLog.is_test_event.is_(None)))

    parsed_start = _parse_iso(start_time)
    parsed_end = _parse_iso(end_time)
    if parsed_start is not None:
        query = query.filter(AuditLog.created_at >= parsed_start)
    if parsed_end is not None:
        query = query.filter(AuditLog.created_at <= parsed_end)

    parsed_cursor = _decode_cursor(cursor)
    if parsed_cursor is not None:
        cursor_ts, cursor_marker = parsed_cursor
        query = query.filter(
            or_(
                AuditLog.created_at < cursor_ts,
                (AuditLog.created_at == cursor_ts) & (AuditLog.id < cursor_marker),
            )
        )

    cutoff = _utcnow() - timedelta(days=max(archive_cutoff_days, 1))
    if archive_mode:
        query = query.filter(AuditLog.created_at < cutoff)
    else:
        query = query.filter(AuditLog.created_at >= cutoff)

    rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(page_size + 1).all()
    has_more = len(rows) > page_size
    visible_rows = rows[:page_size]

    items = [normalize_audit_log_event(row).envelope for row in visible_rows]
    next_cursor = None
    if has_more and visible_rows:
        tail = visible_rows[-1]
        next_cursor = _encode_cursor(tail.created_at, tail.id)

    return {
        "items": items,
        "page_size": page_size,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "query_latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def list_saved_queries(db: Session, *, user_id: str, limit: int = 50) -> list[dict]:
    rows = (
        db.query(LifecycleSavedQuery)
        .filter(LifecycleSavedQuery.user_id == user_id)
        .order_by(LifecycleSavedQuery.updated_at.desc())
        .limit(max(limit, 1))
        .all()
    )
    return [
        {
            "id": row.id,
            "name": row.name,
            "params": row.params or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


def create_saved_query(db: Session, *, user_id: str, name: str, params: dict) -> dict:
    row = LifecycleSavedQuery(
        user_id=user_id,
        name=str(name).strip(),
        params=json.loads(json.dumps(params or {})),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "name": row.name,
        "params": row.params or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def delete_saved_query(db: Session, *, user_id: str, query_id: str) -> bool:
    row = (
        db.query(LifecycleSavedQuery)
        .filter(LifecycleSavedQuery.id == query_id, LifecycleSavedQuery.user_id == user_id)
        .first()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
