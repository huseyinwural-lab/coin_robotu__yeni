from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from models import PendingSignal, PaperPosition, UserDecisionTrace, UserExecutionIntent

REASON_REGISTRY_PATH = Path("/app/config/reason_codes_registry.json")
TRACE_RETENTION_DAYS = 90

_reason_registry_cache: dict[str, dict] | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fallback_reason_title(code: str) -> str:
    return code.replace("_", " ").replace("-", " ").strip().title() or "Unknown Reason"


def _load_reason_registry() -> dict[str, dict]:
    global _reason_registry_cache
    if _reason_registry_cache is not None:
        return _reason_registry_cache

    try:
        payload = json.loads(REASON_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        _reason_registry_cache = {}
        return _reason_registry_cache

    codes = payload.get("codes") or {}
    normalized: dict[str, dict] = {}
    for code, metadata in codes.items():
        if not isinstance(metadata, dict):
            continue
        normalized[str(code).upper()] = {
            "title": str(metadata.get("title") or _fallback_reason_title(str(code))),
            "description": str(metadata.get("description") or "Bu kod için açıklama bulunamadı."),
        }

    _reason_registry_cache = normalized
    return normalized


def build_reason_details(reason_codes: list[str]) -> list[dict]:
    registry = _load_reason_registry()
    details: list[dict] = []
    seen: set[str] = set()

    for item in reason_codes or []:
        code = str(item or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        metadata = registry.get(code.upper(), {})
        details.append(
            {
                "code": code,
                "title": str(metadata.get("title") or _fallback_reason_title(code)),
                "description": str(metadata.get("description") or "Bu kod için açıklama bulunamadı."),
            }
        )
    return details


def purge_expired_traces(db: Session, now: datetime | None = None) -> None:
    current = now or _now()
    db.query(UserDecisionTrace).filter(UserDecisionTrace.expires_at < current).delete(synchronize_session=False)


def record_decision_trace(
    db: Session,
    *,
    user_id: str,
    trace_scope: str,
    trace_type: str,
    entity_id: str,
    strategy_code: str | None,
    decision_status: str,
    reason_codes: list[str] | None = None,
    feature_snapshot: dict | None = None,
    context_payload: dict | None = None,
) -> UserDecisionTrace:
    current = _now()
    purge_expired_traces(db, now=current)

    normalized_codes = [str(item).strip() for item in (reason_codes or []) if str(item).strip()]
    row = UserDecisionTrace(
        id=str(uuid.uuid4()),
        user_id=user_id,
        trace_scope=str(trace_scope or "signal").lower(),
        trace_type=str(trace_type or "decision"),
        entity_id=str(entity_id),
        strategy_code=str(strategy_code) if strategy_code else None,
        decision_status=str(decision_status or "UNKNOWN").upper(),
        reason_codes=normalized_codes,
        reason_details=build_reason_details(normalized_codes),
        feature_snapshot=feature_snapshot or {},
        context_payload=context_payload or {},
        created_at=current,
        expires_at=current + timedelta(days=TRACE_RETENTION_DAYS),
    )
    db.add(row)
    db.flush()
    return row


def serialize_trace(row: UserDecisionTrace) -> dict:
    reason_codes = row.reason_codes or []
    reason_details = row.reason_details or build_reason_details(reason_codes)
    return {
        "trace_id": row.id,
        "trace_scope": row.trace_scope,
        "trace_type": row.trace_type,
        "entity_id": row.entity_id,
        "strategy_code": row.strategy_code,
        "decision_status": row.decision_status,
        "reason_codes": reason_codes,
        "reason_details": reason_details,
        "feature_snapshot": row.feature_snapshot or {},
        "context_payload": row.context_payload or {},
        "created_at": row.created_at,
        "expires_at": row.expires_at,
    }


def list_entity_trace_timeline(
    db: Session,
    *,
    user_id: str,
    trace_scope: str,
    entity_id: str,
    limit: int = 25,
) -> dict:
    current = _now()
    rows = (
        db.query(UserDecisionTrace)
        .filter(
            UserDecisionTrace.user_id == user_id,
            UserDecisionTrace.trace_scope == trace_scope.lower(),
            UserDecisionTrace.entity_id == str(entity_id),
            UserDecisionTrace.expires_at >= current,
        )
        .order_by(UserDecisionTrace.created_at.desc())
        .limit(max(limit, 1))
        .all()
    )
    timeline = [serialize_trace(row) for row in rows]
    return {
        "entity_scope": trace_scope.lower(),
        "entity_id": str(entity_id),
        "trace_count": len(timeline),
        "latest_trace": timeline[0] if timeline else None,
        "timeline": timeline,
    }


def build_strategy_explanation(
    db: Session,
    *,
    user_id: str,
    strategy_code: str,
    lookback_days: int = 30,
) -> dict:
    current = _now()
    from_ts = current - timedelta(days=max(lookback_days, 1))
    rows = (
        db.query(UserDecisionTrace)
        .filter(
            UserDecisionTrace.user_id == user_id,
            UserDecisionTrace.strategy_code == strategy_code,
            UserDecisionTrace.created_at >= from_ts,
            UserDecisionTrace.expires_at >= current,
        )
        .order_by(UserDecisionTrace.created_at.desc())
        .limit(500)
        .all()
    )

    decision_distribution = dict(Counter((row.decision_status or "UNKNOWN") for row in rows))
    reason_distribution = Counter(code for row in rows for code in (row.reason_codes or []))

    top_reason_codes: list[dict] = []
    for code, count in reason_distribution.most_common(8):
        details = build_reason_details([code])
        meta = details[0] if details else {"code": code, "title": _fallback_reason_title(code), "description": "Bu kod için açıklama bulunamadı."}
        top_reason_codes.append({**meta, "count": count})

    latest_examples = [serialize_trace(row) for row in rows[:5]]
    return {
        "strategy_code": strategy_code,
        "lookback_days": max(lookback_days, 1),
        "trace_count": len(rows),
        "decision_distribution": decision_distribution,
        "top_reason_codes": top_reason_codes,
        "latest_examples": latest_examples,
    }


def compute_trace_coverage(db: Session, *, user_id: str, window_days: int = 7) -> dict:
    current = _now()
    days = max(window_days, 1)
    from_ts = current - timedelta(days=days)

    signal_total = (
        db.query(PendingSignal)
        .filter(PendingSignal.user_id == user_id, PendingSignal.created_at >= from_ts)
        .count()
    )
    signal_traced = (
        db.query(UserDecisionTrace.entity_id)
        .filter(
            UserDecisionTrace.user_id == user_id,
            UserDecisionTrace.trace_scope == "signal",
            UserDecisionTrace.created_at >= from_ts,
            UserDecisionTrace.expires_at >= current,
        )
        .distinct()
        .count()
    )

    trade_total = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.opened_at >= from_ts)
        .count()
    )
    trade_traced = (
        db.query(UserDecisionTrace.entity_id)
        .filter(
            UserDecisionTrace.user_id == user_id,
            UserDecisionTrace.trace_scope == "trade",
            UserDecisionTrace.created_at >= from_ts,
            UserDecisionTrace.expires_at >= current,
        )
        .distinct()
        .count()
    )

    execution_total = (
        db.query(UserExecutionIntent)
        .filter(UserExecutionIntent.user_id == user_id, UserExecutionIntent.created_at >= from_ts)
        .count()
    )
    execution_traced = (
        db.query(UserDecisionTrace.entity_id)
        .filter(
            UserDecisionTrace.user_id == user_id,
            UserDecisionTrace.trace_scope == "execution",
            UserDecisionTrace.created_at >= from_ts,
            UserDecisionTrace.expires_at >= current,
        )
        .distinct()
        .count()
    )

    scopes = [
        {"scope": "signal", "total_events": signal_total, "traced_events": signal_traced},
        {"scope": "trade", "total_events": trade_total, "traced_events": trade_traced},
        {"scope": "execution", "total_events": execution_total, "traced_events": execution_traced},
    ]

    for scope in scopes:
        total = scope["total_events"]
        traced = scope["traced_events"]
        scope["coverage_pct"] = round((traced / total) * 100, 2) if total else 0.0

    overall_total = sum(scope["total_events"] for scope in scopes)
    overall_traced = sum(scope["traced_events"] for scope in scopes)

    return {
        "window_days": days,
        "generated_at": current,
        "overall_total_events": overall_total,
        "overall_traced_events": overall_traced,
        "overall_coverage_pct": round((overall_traced / overall_total) * 100, 2) if overall_total else 0.0,
        "scopes": scopes,
    }
