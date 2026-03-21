import json
from collections import Counter
from datetime import datetime, timezone

from models import UserExecutionIntent

PIPELINE_QUEUE_KEYS = [
    "runtime:events:all",
    "runtime:execution:queue",
    "runtime:retry:queue",
    "pipeline:events:queue",
    "pipeline:retry:queue",
]


def flush_pipeline_queues(cache, *, actor_user_id: str, reason: str, trace_id: str) -> dict:
    removed = {}
    for key in PIPELINE_QUEUE_KEYS:
        if hasattr(cache, "llen"):
            size_before = cache.llen(key)
        else:
            size_before = len(cache.lrange(key, 0, -1)) if hasattr(cache, "lrange") else 0
        if size_before > 0:
            cache.delete(key)
        removed[key] = int(size_before)

    event = {
        "event": "pipeline_queue_flushed",
        "trace_id": trace_id,
        "actor_user_id": actor_user_id,
        "reason": reason,
        "removed": removed,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    cache.rpush("runtime:pipeline:events", json.dumps(event, ensure_ascii=False))
    if hasattr(cache, "ltrim"):
        cache.ltrim("runtime:pipeline:events", -200, -1)
    return {"removed": removed}


def force_pipeline_resync(cache, *, actor_user_id: str, reason: str, trace_id: str) -> dict:
    payload = {
        "event": "pipeline_force_resync",
        "trace_id": trace_id,
        "actor_user_id": actor_user_id,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "queued",
    }
    cache.set("runtime:pipeline:resync:last", json.dumps(payload, ensure_ascii=False))
    cache.rpush("runtime:pipeline:events", json.dumps(payload, ensure_ascii=False))
    if hasattr(cache, "ltrim"):
        cache.ltrim("runtime:pipeline:events", -200, -1)
    return payload


def get_guard_telemetry(db, *, limit: int = 100) -> dict:
    rows = (
        db.query(UserExecutionIntent)
        .filter(UserExecutionIntent.status == "REJECTED")
        .order_by(UserExecutionIntent.updated_at.desc())
        .limit(limit)
        .all()
    )

    blocked_trades = []
    reason_counter: Counter[str] = Counter()
    override_impacted: list[dict] = []

    for row in rows:
        reason_codes = row.reject_reason_codes or []
        reason_text = reason_codes[0] if reason_codes else (row.admin_note or "unknown")
        reason_counter[reason_text] += 1
        blocked_item = {
            "id": row.id,
            "intent_token": row.intent_token,
            "symbol": row.symbol,
            "status": row.status,
            "reason_codes": reason_codes,
            "admin_note": row.admin_note,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "override_id": row.override_id,
        }
        blocked_trades.append(blocked_item)
        if row.override_id:
            override_impacted.append(
                {
                    "override_id": row.override_id,
                    "execution_intent_id": row.id,
                    "symbol": row.symbol,
                    "updated_at": blocked_item["updated_at"],
                }
            )

    return {
        "blocked_trade_list": blocked_trades,
        "top_reasons": [{"reason": key, "count": count} for key, count in reason_counter.most_common(12)],
        "override_impacted_trades": override_impacted,
    }
