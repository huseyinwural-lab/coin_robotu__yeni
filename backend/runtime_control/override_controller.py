import json
import uuid
from datetime import datetime, timedelta, timezone

from models import ManualOverrideLog

ACTIVE_OVERRIDE_KEY = "runtime:overrides:active"
MAX_OVERRIDE_TTL_MINUTES = 120


def _decode(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _read_active(cache) -> list[dict]:
    raw = _decode(cache.get(ACTIVE_OVERRIDE_KEY))
    if not raw:
        return []
    try:
        payload = json.loads(raw)
        if isinstance(payload, list):
            return payload
    except Exception:
        return []
    return []


def _write_active(cache, payload: list[dict]):
    cache.set(ACTIVE_OVERRIDE_KEY, json.dumps(payload, ensure_ascii=False))


def _cleanup_expired(items: list[dict]) -> list[dict]:
    now = datetime.now(timezone.utc)
    active = []
    for item in items:
        expires_at = item.get("expires_at")
        if not expires_at:
            active.append(item)
            continue
        try:
            expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expires >= now:
                active.append(item)
        except Exception:
            active.append(item)
    return active


def list_active_overrides(cache) -> list[dict]:
    items = _cleanup_expired(_read_active(cache))
    _write_active(cache, items)
    return items


def create_override(
    db,
    cache,
    *,
    actor_user_id: str,
    actor_role: str,
    override_type: str,
    scope: str,
    ttl_minutes: int,
    reason: str,
    trace_id: str,
) -> dict:
    ttl = max(1, min(int(ttl_minutes), MAX_OVERRIDE_TTL_MINUTES))
    now = datetime.now(timezone.utc)
    override_id = str(uuid.uuid4())
    payload = {
        "override_id": override_id,
        "type": override_type,
        "scope": scope,
        "ttl_minutes": ttl,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=ttl)).isoformat(),
        "status": "active",
        "reason": reason,
        "trace_id": trace_id,
        "actor_user_id": actor_user_id,
        "actor_role": actor_role,
    }

    active = list_active_overrides(cache)
    active.append(payload)
    _write_active(cache, active)

    db.add(
        ManualOverrideLog(
            override_id=override_id,
            admin_id=actor_user_id,
            action_type="runtime_override_create",
            reason=reason,
            payload=payload,
            timestamp=now,
        )
    )
    db.commit()
    return payload


def cancel_override(db, cache, *, override_id: str, actor_user_id: str, reason: str, trace_id: str) -> dict:
    now = datetime.now(timezone.utc)
    active = list_active_overrides(cache)
    cancelled = None
    remaining = []
    for item in active:
        if item.get("override_id") == override_id and cancelled is None:
            item["status"] = "cancelled"
            item["cancelled_at"] = now.isoformat()
            item["cancelled_by"] = actor_user_id
            item["cancel_reason"] = reason
            item["trace_id"] = trace_id
            cancelled = item
            continue
        remaining.append(item)

    _write_active(cache, remaining)
    if cancelled is None:
        return {"cancelled": False, "override_id": override_id}

    db.add(
        ManualOverrideLog(
            override_id=str(uuid.uuid4()),
            admin_id=actor_user_id,
            action_type="runtime_override_cancel",
            reason=reason,
            payload=cancelled,
            timestamp=now,
        )
    )
    db.commit()
    return {"cancelled": True, "override": cancelled}


def list_override_history(db, *, limit: int = 200) -> list[dict]:
    rows = (
        db.query(ManualOverrideLog)
        .filter(ManualOverrideLog.action_type.in_(["runtime_override_create", "runtime_override_cancel", "runtime_override_action"]))
        .order_by(ManualOverrideLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "override_id": row.override_id,
            "admin_id": row.admin_id,
            "action_type": row.action_type,
            "reason": row.reason,
            "payload": row.payload or {},
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        }
        for row in rows
    ]
