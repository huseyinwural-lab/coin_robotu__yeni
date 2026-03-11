from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from db import redis_client
from models import AuditLog


CACHE_TTL_SECONDS = 60


def _cache_key(days: int) -> str:
    return f"risk_orchestrator:analytics:{days}"


def _serialize(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _deserialize(raw: str) -> dict:
    return json.loads(raw)


def _cache_set(key: str, value: str) -> None:
    try:
        redis_client.set(key, value, ex=CACHE_TTL_SECONDS)
    except TypeError:
        redis_client.set(key, value)


def compute_risk_analytics(db: Session, *, days: int = 14) -> dict:
    cache_key = _cache_key(days)
    cached = redis_client.get(cache_key)
    if cached:
        if isinstance(cached, bytes):
            cached = cached.decode("utf-8")
        try:
            return _deserialize(cached)
        except json.JSONDecodeError:
            pass

    since = datetime.now(timezone.utc) - timedelta(days=days)
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.created_at >= since, AuditLog.action.in_(["risk_orchestrator_reject", "kill_switch_triggered"]))
        .order_by(AuditLog.created_at.asc())
        .all()
    )

    reason_counter = Counter()
    breach_by_day = defaultdict(int)
    breach_by_strategy = Counter()
    breach_by_symbol = Counter()
    duplicate_attempts = 0
    kill_switch_events = 0

    for log in logs:
        day_key = log.created_at.date().isoformat()
        breach_by_day[day_key] += 1
        details = log.details or {}
        if log.action == "kill_switch_triggered":
            kill_switch_events += 1
            continue

        reason_codes = details.get("reason_codes") or []
        for code in reason_codes:
            reason_counter[code] += 1
        if any(code in {"duplicate_decision_hash", "duplicate_intent_hash"} for code in reason_codes):
            duplicate_attempts += 1

        strategy_id = details.get("strategy_id")
        if strategy_id:
            breach_by_strategy[strategy_id] += 1
        symbol = details.get("symbol")
        if symbol:
            breach_by_symbol[symbol] += 1

    reject_logs = [log for log in logs if log.action == "risk_orchestrator_reject"]
    response = {
        "days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "risk_policy_hits": len(reject_logs),
        "kill_switch_events": kill_switch_events,
        "duplicate_intent_attempts": duplicate_attempts,
        "reject_reason_distribution": [
            {"label": label, "value": value} for label, value in reason_counter.most_common()
        ],
        "breach_by_day": [
            {"date": day, "value": breach_by_day[day]}
            for day in sorted(breach_by_day.keys())
        ],
        "breach_by_strategy": [
            {"label": label, "value": value} for label, value in breach_by_strategy.most_common()
        ],
        "breach_by_symbol": [
            {"label": label, "value": value} for label, value in breach_by_symbol.most_common()
        ],
    }

    _cache_set(cache_key, _serialize(response))
    return response
