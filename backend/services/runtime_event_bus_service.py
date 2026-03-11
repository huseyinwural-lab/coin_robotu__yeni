import hashlib
import json
import uuid
from datetime import datetime, timezone

from db import redis_client


PROCESSED_EVENTS_SET = "runtime:processed:event_ids"


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
