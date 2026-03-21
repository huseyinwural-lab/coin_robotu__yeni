import json
import uuid
from datetime import datetime, timezone


def _decode(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _read_json(cache, key: str, default):
    raw = _decode(cache.get(key))
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _write_json(cache, key: str, payload: dict):
    cache.set(key, json.dumps(payload, ensure_ascii=False))


def _append_ws_log(cache, event: dict):
    cache.rpush("runtime:ws:logs", json.dumps(event, ensure_ascii=False))
    if hasattr(cache, "ltrim"):
        cache.ltrim("runtime:ws:logs", -200, -1)


def reconnect_ws(cache, *, actor_user_id: str, reason: str, trace_id: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    state = _read_json(cache, "runtime:ws:state", {"session_id": str(uuid.uuid4()), "reconnect_count": 0})
    state["reconnect_count"] = int(state.get("reconnect_count") or 0) + 1
    state["last_reconnect_at"] = now
    state["last_reconnect_by"] = actor_user_id
    state["reconnect_reason"] = reason
    state["status"] = "reconnecting"
    _write_json(cache, "runtime:ws:state", state)

    event = {
        "event": "ws_reconnect_requested",
        "trace_id": trace_id,
        "actor_user_id": actor_user_id,
        "reason": reason,
        "created_at": now,
    }
    _append_ws_log(cache, event)
    return state


def force_new_ws_session(cache, *, actor_user_id: str, reason: str, trace_id: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    state = _read_json(cache, "runtime:ws:state", {})
    old_session_id = state.get("session_id")
    new_session_id = str(uuid.uuid4())

    state["session_id"] = new_session_id
    state["status"] = "new_session_requested"
    state["last_reconnect_at"] = now
    state["last_reconnect_by"] = actor_user_id
    state["reconnect_reason"] = reason
    state["reconnect_count"] = int(state.get("reconnect_count") or 0) + 1
    _write_json(cache, "runtime:ws:state", state)

    multi_state = _read_json(cache, "runtime:ws:connections", {"active": [], "history": []})
    active = list(multi_state.get("active") or [])
    active = [item for item in active if item.get("session_id") != old_session_id]
    active.append(
        {
            "session_id": new_session_id,
            "status": "active",
            "started_at": now,
            "node": "default",
        }
    )
    history = list(multi_state.get("history") or [])
    history.append(
        {
            "old_session_id": old_session_id,
            "new_session_id": new_session_id,
            "reason": reason,
            "switched_at": now,
            "actor_user_id": actor_user_id,
            "trace_id": trace_id,
        }
    )
    multi_state["active"] = active[-10:]
    multi_state["history"] = history[-100:]
    _write_json(cache, "runtime:ws:connections", multi_state)

    _append_ws_log(
        cache,
        {
            "event": "ws_force_new_session",
            "trace_id": trace_id,
            "actor_user_id": actor_user_id,
            "reason": reason,
            "old_session_id": old_session_id,
            "new_session_id": new_session_id,
            "created_at": now,
        },
    )
    return {"old_session_id": old_session_id, "new_session_id": new_session_id, "state": state}


def get_ws_health(cache) -> dict:
    state = _read_json(cache, "runtime:ws:state", {})
    logs_raw = cache.lrange("runtime:ws:logs", -50, -1)
    logs = []
    for row in logs_raw:
        raw = _decode(row)
        if not raw:
            continue
        try:
            logs.append(json.loads(raw))
        except Exception:
            continue

    multi = _read_json(cache, "runtime:ws:connections", {"active": [], "history": []})
    reconnect_reasons = [
        {
            "reason": item.get("reason"),
            "created_at": item.get("created_at"),
            "event": item.get("event"),
        }
        for item in logs
        if item.get("event") in {"ws_reconnect_requested", "ws_force_new_session"}
    ]
    reconnect_reasons = reconnect_reasons[-5:]

    inferred_last_error = None
    for item in reversed(logs):
        if item.get("error"):
            inferred_last_error = item.get("error")
            break

    return {
        "state": state,
        "session_id": state.get("session_id"),
        "reconnect_count": int(state.get("reconnect_count") or 0),
        "last_error": state.get("last_error") or inferred_last_error,
        "reconnect_reason": state.get("reconnect_reason") or (reconnect_reasons[-1]["reason"] if reconnect_reasons else None),
        "connection_logs": logs,
        "recent_reconnect_reasons": reconnect_reasons,
        "multi_connection_state": multi,
    }
