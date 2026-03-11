import hashlib
import json
import uuid
from datetime import datetime, timezone

from db import redis_client


PROCESSED_EVENTS_SET = "runtime:processed:event_ids"
RUNTIME_EVENTS_QUEUE = "runtime_events"
RUNTIME_RETRY_QUEUE = "runtime_retry_queue"
RUNTIME_DEAD_LETTER_QUEUE = "runtime_dead_letter_queue"
RUNTIME_QUARANTINE_QUEUE = "runtime_quarantine_queue"


def _canonical(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def publish_runtime_event(
    *,
    event_type: str,
    payload: dict,
    correlation_id: str,
    causation_id: str | None,
    partition_key: str,
    schema_version: str = "1.0",
) -> dict:
    event_id = str(uuid.uuid4())
    ordering = int(redis_client.incr("runtime:events:ordering"))
    envelope = {
        "event_id": event_id,
        "event_type": event_type,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "partition_key": partition_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": schema_version,
        "ordering": ordering,
        "payload": payload,
        "payload_hash": _payload_hash(payload),
    }
    raw = json.dumps(envelope, ensure_ascii=False, default=str)
    redis_client.rpush(f"runtime:events:{event_type}", raw)
    redis_client.rpush("runtime:events:all", raw)
    redis_client.rpush(RUNTIME_EVENTS_QUEUE, raw)
    return envelope


def consume_runtime_event(event_type: str, worker_name: str, timeout: int = 1) -> tuple[dict, str, str] | None:
    source = f"runtime:events:{event_type}"
    processing = f"runtime:events:{event_type}:processing:{worker_name}"
    raw = redis_client.brpoplpush(source, processing, timeout=timeout)
    if raw is None:
        return None
    return json.loads(raw), processing, raw


def ack_runtime_event(processing_queue: str, raw: str) -> None:
    redis_client.lrem(processing_queue, 1, raw)


def is_event_processed(event_id: str) -> bool:
    return bool(redis_client.sismember(PROCESSED_EVENTS_SET, event_id))


def mark_event_processed(event_id: str) -> None:
    redis_client.sadd(PROCESSED_EVENTS_SET, event_id)


def enqueue_retry_event(
    *,
    envelope: dict,
    error_message: str,
    reason_code: str,
    retry_count: int,
    max_retry: int,
    next_retry_at: str,
) -> dict:
    entry = {
        "envelope": envelope,
        "error_message": error_message,
        "reason_code": reason_code,
        "retry_count": retry_count,
        "max_retry": max_retry,
        "next_retry_at": next_retry_at,
    }
    redis_client.rpush(RUNTIME_RETRY_QUEUE, json.dumps(entry, ensure_ascii=False, default=str))
    return entry


def enqueue_quarantine_event(
    *,
    envelope: dict,
    error_message: str,
    reason_code: str,
    retry_count: int,
    max_retry: int,
) -> dict:
    entry = {
        "envelope": envelope,
        "error_message": error_message,
        "reason_code": reason_code,
        "retry_count": retry_count,
        "max_retry": max_retry,
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
    }
    raw = json.dumps(entry, ensure_ascii=False, default=str)
    redis_client.rpush(RUNTIME_DEAD_LETTER_QUEUE, raw)
    redis_client.rpush(RUNTIME_QUARANTINE_QUEUE, raw)
    return entry


def requeue_runtime_event(envelope: dict) -> None:
    raw = json.dumps(envelope, ensure_ascii=False, default=str)
    event_type = envelope.get("event_type", "")
    if event_type:
        redis_client.rpush(f"runtime:events:{event_type}", raw)
    redis_client.rpush("runtime:events:all", raw)
    redis_client.rpush(RUNTIME_EVENTS_QUEUE, raw)


def release_due_retry_events(limit: int = 200) -> int:
    raw_items = redis_client.lrange(RUNTIME_RETRY_QUEUE, 0, limit - 1)
    if not raw_items:
        return 0
    redis_client.ltrim(RUNTIME_RETRY_QUEUE, len(raw_items), -1)
    now = datetime.now(timezone.utc)
    released = 0
    deferred: list[str] = []

    for raw in raw_items:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        next_retry_at = entry.get("next_retry_at")
        if next_retry_at:
            try:
                next_dt = datetime.fromisoformat(str(next_retry_at).replace("Z", "+00:00"))
            except ValueError:
                next_dt = now
        else:
            next_dt = now

        if next_dt <= now:
            envelope = entry.get("envelope") or {}
            requeue_runtime_event(envelope)
            released += 1
        else:
            deferred.append(raw)

    if deferred:
        redis_client.rpush(RUNTIME_RETRY_QUEUE, *deferred)
    return released


def remove_quarantine_event(event_id: str) -> None:
    raw_items = redis_client.lrange(RUNTIME_QUARANTINE_QUEUE, 0, -1)
    if not raw_items:
        return
    remaining: list[str] = []
    for raw in raw_items:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        envelope = entry.get("envelope", {})
        if envelope.get("event_id") != event_id:
            remaining.append(raw)
    redis_client.delete(RUNTIME_QUARANTINE_QUEUE)
    if remaining:
        redis_client.rpush(RUNTIME_QUARANTINE_QUEUE, *remaining)
