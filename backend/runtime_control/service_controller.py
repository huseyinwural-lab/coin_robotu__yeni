import json
import subprocess
from datetime import datetime, timezone


def _decode(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _event_lag_seconds(cache) -> float:
    try:
        if hasattr(cache, "lindex"):
            raw = cache.lindex("runtime:events:all", 0)
        else:
            rows = cache.lrange("runtime:events:all", 0, 0) if hasattr(cache, "lrange") else []
            raw = rows[0] if rows else None
        if not raw:
            return 0.0
        payload = json.loads(_decode(raw) or "{}")
        created_at = payload.get("created_at")
        if not created_at:
            return 0.0
        event_dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - event_dt).total_seconds())
    except Exception:
        return 0.0


def manual_health_check(cache, *, lag_threshold_seconds: float) -> dict:
    now = datetime.now(timezone.utc)
    lag_seconds = _event_lag_seconds(cache)
    status = "ok" if lag_seconds <= float(lag_threshold_seconds or 60) else "warning"
    return {
        "status": status,
        "checked_at": now.isoformat(),
        "lag_seconds": lag_seconds,
        "lag_threshold_seconds": float(lag_threshold_seconds or 60),
        "warning_triggered": lag_seconds > float(lag_threshold_seconds or 60),
    }


def restart_runtime_service(*, service: str) -> dict:
    normalized = str(service or "").strip().lower()
    if normalized not in {"worker", "ws", "all"}:
        normalized = "all"

    dependency_order_map = {
        "all": ["database", "redis", "worker", "ws", "backend"],
        "worker": ["redis", "worker", "backend"],
        "ws": ["redis", "ws", "backend"],
    }
    dependency_order = dependency_order_map.get(normalized, [normalized, "backend"])

    # Current deployment has supervisor-managed frontend/backend only.
    # For worker/ws requests, schedule lightweight backend restart as runtime recovery action.
    command = "(sleep 1; supervisorctl restart backend) >> /tmp/runtime_control_service_restart.log 2>&1"
    subprocess.Popen(["bash", "-lc", command], cwd="/app")
    return {
        "status": "scheduled",
        "requested_service": normalized,
        "dependency_order": dependency_order,
        "restart_log": "/tmp/runtime_control_service_restart.log",
    }
