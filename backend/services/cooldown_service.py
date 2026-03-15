from datetime import datetime, timedelta, timezone

from services.pipeline.cache_store import get_json, set_json


def _cooldown_key(scope: str, user_id: str, key: str | None = None) -> str:
    suffix = f":{key}" if key else ""
    return f"risk:cooldown:{scope}:{user_id}{suffix}"


def activate_cooldown(cache, *, scope: str, user_id: str, minutes: int, key: str | None = None, reason: str = "") -> dict:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=max(int(minutes or 0), 0))
    payload = {
        "active": minutes > 0,
        "scope": scope,
        "user_id": user_id,
        "key": key,
        "reason": reason,
        "started_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "remaining_seconds": max(int((expires_at - now).total_seconds()), 0),
    }
    set_json(cache, _cooldown_key(scope, user_id, key), payload)
    return payload


def cooldown_state(cache, *, scope: str, user_id: str, key: str | None = None) -> dict:
    payload = get_json(cache, _cooldown_key(scope, user_id, key)) or {
        "active": False,
        "remaining_seconds": 0,
        "expires_at": None,
        "reason": None,
    }
    if not payload.get("active"):
        return payload

    try:
        expires_at = datetime.fromisoformat(str(payload.get("expires_at") or ""))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        remaining = int((expires_at - now).total_seconds())
        if remaining <= 0:
            payload["active"] = False
            payload["remaining_seconds"] = 0
            payload["reason"] = payload.get("reason") or "cooldown_expired"
            set_json(cache, _cooldown_key(scope, user_id, key), payload)
            return payload
        payload["remaining_seconds"] = remaining
        return payload
    except Exception:
        payload["active"] = False
        payload["remaining_seconds"] = 0
        set_json(cache, _cooldown_key(scope, user_id, key), payload)
        return payload
