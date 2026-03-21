from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from db import redis_client
from services.pipeline.cache_store import get_json, incr_counter, set_json


DEFAULT_ALERT_POLICY = {
    "warning_threshold": 0.1,
    "critical_threshold": 0.2,
    "smart_mute_window_seconds": 300,
    "smart_mute_trigger_count": 3,
    "smart_mute_duration_seconds": 900,
    "notifications_enabled": True,
    "notify_min_severity": "warning",
    "webhook_urls": [],
}

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}
ALLOWED_NOTIFY_SEVERITY = {"warning", "critical"}


def _policy_key() -> str:
    return "scanner:anomaly:alert-policy"


def _pattern_mute_key(payload_hash: str) -> str:
    return f"scanner:anomaly:mute:pattern:{payload_hash}"


def _pattern_hit_counter_key(user_id: str, payload_hash: str) -> str:
    return f"scanner:anomaly:pattern-hits:{user_id}:{payload_hash}"


def _pattern_mute_index_key() -> str:
    return "scanner:anomaly:mute:pattern:index"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_webhook_urls(values: list[str] | None) -> list[str]:
    urls: list[str] = []
    for raw in values or []:
        candidate = str(raw or "").strip()
        if not candidate:
            continue
        if not (candidate.startswith("http://") or candidate.startswith("https://")):
            continue
        urls.append(candidate[:500])
    deduped = list(dict.fromkeys(urls))
    return deduped[:5]


def _normalize_policy(raw: dict | None) -> dict:
    merged = {**DEFAULT_ALERT_POLICY, **(raw or {})}
    warning = float(merged.get("warning_threshold") or DEFAULT_ALERT_POLICY["warning_threshold"])
    critical = float(merged.get("critical_threshold") or DEFAULT_ALERT_POLICY["critical_threshold"])
    if critical < warning:
        critical = warning

    notify_min = str(merged.get("notify_min_severity") or "warning").lower()
    if notify_min not in ALLOWED_NOTIFY_SEVERITY:
        notify_min = "warning"

    return {
        "warning_threshold": max(0.01, min(0.99, warning)),
        "critical_threshold": max(0.01, min(0.99, critical)),
        "smart_mute_window_seconds": int(max(30, min(3600, int(merged.get("smart_mute_window_seconds") or 300)))),
        "smart_mute_trigger_count": int(max(2, min(20, int(merged.get("smart_mute_trigger_count") or 3)))),
        "smart_mute_duration_seconds": int(max(60, min(86400, int(merged.get("smart_mute_duration_seconds") or 900)))),
        "notifications_enabled": bool(merged.get("notifications_enabled", True)),
        "notify_min_severity": notify_min,
        "webhook_urls": _sanitize_webhook_urls(merged.get("webhook_urls") or []),
    }


def get_anomaly_alert_policy() -> dict:
    raw = get_json(redis_client, _policy_key())
    policy = _normalize_policy(raw)
    updated_at = (raw or {}).get("updated_at") or _now_utc().isoformat()
    return {
        **policy,
        "updated_at": updated_at,
    }


def save_anomaly_alert_policy(policy_payload: dict) -> dict:
    normalized = _normalize_policy(policy_payload)
    updated_at = _now_utc().isoformat()
    document = {**normalized, "updated_at": updated_at}
    set_json(redis_client, _policy_key(), document)
    return document


def evaluate_anomaly_severity(*, fail_ratio: float, policy: dict) -> str:
    critical = float(policy.get("critical_threshold") or DEFAULT_ALERT_POLICY["critical_threshold"])
    warning = float(policy.get("warning_threshold") or DEFAULT_ALERT_POLICY["warning_threshold"])
    if fail_ratio >= critical:
        return "critical"
    if fail_ratio >= warning:
        return "warning"
    return "info"


def should_notify(*, severity: str, policy: dict) -> bool:
    if not bool(policy.get("notifications_enabled", True)):
        return False
    min_level = str(policy.get("notify_min_severity") or "warning")
    return SEVERITY_ORDER.get(str(severity).lower(), 0) >= SEVERITY_ORDER.get(min_level, 1)


def dispatch_generic_webhooks(*, payload: dict, policy: dict) -> dict:
    urls = policy.get("webhook_urls") or []
    sent = 0
    failed = 0
    failures: list[dict] = []
    for url in urls:
        try:
            response = httpx.post(str(url), json=payload, timeout=4)
            if 200 <= response.status_code < 300:
                sent += 1
            else:
                failed += 1
                failures.append({"url": url, "status_code": response.status_code})
        except Exception as exc:
            failed += 1
            failures.append({"url": url, "error": str(exc)[:180]})
    return {
        "attempted": len(urls),
        "sent": sent,
        "failed": failed,
        "failures": failures,
    }


def get_pattern_mute_state(payload_hash: str) -> dict | None:
    raw = get_json(redis_client, _pattern_mute_key(payload_hash))
    if not raw:
        return None
    mute_until_raw = raw.get("mute_until")
    if not mute_until_raw:
        return None
    try:
        mute_until = datetime.fromisoformat(str(mute_until_raw))
        if mute_until.tzinfo is None:
            mute_until = mute_until.replace(tzinfo=timezone.utc)
    except Exception:
        return None
    if _now_utc() >= mute_until:
        return None
    return {
        "payload_hash": str(raw.get("payload_hash") or payload_hash),
        "mute_until": mute_until,
        "reason": str(raw.get("reason") or "pattern_muted"),
        "created_at": str(raw.get("created_at") or ""),
    }


def mute_pattern(*, payload_hash: str, duration_seconds: int, reason: str, actor_user_id: str | None = None) -> dict:
    now = _now_utc()
    mute_until = now + timedelta(seconds=int(duration_seconds))
    state = {
        "payload_hash": payload_hash,
        "duration_seconds": int(duration_seconds),
        "reason": reason,
        "actor_user_id": actor_user_id,
        "created_at": now.isoformat(),
        "mute_until": mute_until.isoformat(),
    }
    key = _pattern_mute_key(payload_hash)
    set_json(redis_client, key, state)
    index_key = _pattern_mute_index_key()
    raw_index = get_json(redis_client, index_key)
    index = raw_index if isinstance(raw_index, list) else []
    normalized_index = [str(item) for item in index if str(item).strip()]
    if payload_hash not in normalized_index:
        normalized_index.insert(0, payload_hash)
    set_json(redis_client, index_key, normalized_index[:500])
    try:
        if hasattr(redis_client, "expire"):
            redis_client.expire(key, int(duration_seconds) + 60)
    except Exception:
        pass
    return {
        "payload_hash": payload_hash,
        "duration_seconds": int(duration_seconds),
        "mute_until": mute_until,
        "reason": reason,
    }


def record_pattern_hit(*, user_id: str, payload_hash: str, window_seconds: int) -> int:
    key = _pattern_hit_counter_key(user_id, payload_hash)
    count = int(incr_counter(redis_client, key, 1))
    try:
        if hasattr(redis_client, "expire"):
            redis_client.expire(key, int(window_seconds))
    except Exception:
        pass
    return count


def list_active_pattern_mutes(*, limit: int = 50) -> list[dict]:
    keys: list[str] = []
    raw_index = get_json(redis_client, _pattern_mute_index_key())
    index = raw_index if isinstance(raw_index, list) else []
    if index:
        keys = [_pattern_mute_key(str(payload_hash)) for payload_hash in index]

    try:
        if not keys and hasattr(redis_client, "keys"):
            raw_keys = redis_client.keys("scanner:anomaly:mute:pattern:*")
            keys = [item.decode("utf-8") if isinstance(item, bytes) else str(item) for item in raw_keys]
    except Exception:
        keys = []

    now = _now_utc()
    records: list[dict] = []
    for key in keys:
        raw = get_json(redis_client, key)
        if not raw:
            continue
        mute_until_raw = raw.get("mute_until")
        if not mute_until_raw:
            continue
        try:
            mute_until = datetime.fromisoformat(str(mute_until_raw))
            if mute_until.tzinfo is None:
                mute_until = mute_until.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if mute_until <= now:
            continue
        records.append(
            {
                "payload_hash": str(raw.get("payload_hash") or key.split(":")[-1]),
                "mute_until": mute_until,
                "duration_seconds": int(raw.get("duration_seconds") or 0),
                "reason": str(raw.get("reason") or "pattern_muted"),
            }
        )
    records.sort(key=lambda row: row["mute_until"], reverse=True)
    return records[: max(1, int(limit))]
