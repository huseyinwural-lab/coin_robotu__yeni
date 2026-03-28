from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from db import redis_client
from models import ExecutionIntent, ExecutionIntentEvent, FailedEvent
from services.admin_exchange_credentials_service import execution_credentials_for_adapter
from services.artifact_service import write_signed_artifact
from services.audit_service import create_audit_log
from services.failed_event_service import upsert_failed_event
from services.runtime_event_bus_service import (
    RUNTIME_DEAD_LETTER_QUEUE,
    RUNTIME_EVENTS_QUEUE,
    RUNTIME_QUARANTINE_QUEUE,
    RUNTIME_RETRY_QUEUE,
    publish_runtime_event,
)
from services.runtime_ops_service import (
    dismiss_quarantined_event,
    mark_quarantined_failed,
    replay_quarantined_event,
)


TRUE_VALUES = {"1", "true", "yes", "on"}
HARD_BLOCK_REASON_CODES = {
    "TESTNET_TRADING_DISABLED",
    "MARKET_DATA_MISSING",
    "MARKET_DATA_STALE",
    "KILL_SWITCH_ACTIVE",
    "BYBIT_TESTNET_CREDENTIALS_MISSING",
    "BYBIT_AUTH_PROBE_FAIL",
    "BYBIT_CONNECTIVITY_FAIL",
    "BYBIT_ORDER_SMOKE_FAIL",
    "BYBIT_ORDER_SMOKE_AUTH_FAIL",
    "ORDERBOOK_INVALID",
    "EXCHANGE_CONNECTION_UNHEALTHY",
    "EXECUTION_PROOF_REAL_METRIC_MISSING",
    "EXECUTION_PROOF_MOCKED_PATHS",
    "READINESS_BLOCKING_FAILURE",
}
HARD_BLOCK_STEP_KEYS = {
    "market_data_present",
    "orderbook_sync",
    "exchange_connection_ready",
    "venue_connectivity_bybit",
    "venue_orderbook_bybit",
    "proof_quality",
    "kill_switch",
}
INTENT_ALLOWED_TRANSITIONS = {
    "CREATED": {"SUBMITTED", "FAILED", "QUARANTINED", "CANCELLED"},
    "SUBMITTED": {"ACKED", "FAILED", "QUARANTINED", "CANCELLED"},
    "ACKED": {"FILLED", "FAILED", "QUARANTINED", "CANCELLED"},
    "FILLED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
    "QUARANTINED": {"SUBMITTED", "FAILED", "CANCELLED"},
}
INTENT_STUCK_TIMEOUT_ENV = {
    "CREATED": "EXECUTION_INTENT_CREATED_TIMEOUT_SEC",
    "SUBMITTED": "EXECUTION_INTENT_SUBMITTED_TIMEOUT_SEC",
    "ACKED": "EXECUTION_INTENT_ACKED_TIMEOUT_SEC",
}
INTENT_STUCK_TIMEOUT_DEFAULTS = {
    "CREATED": 60,
    "SUBMITTED": 120,
    "ACKED": 300,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_bool(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in TRUE_VALUES


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_code(raw: str | None) -> str:
    return str(raw or "").strip().upper()


def _unique_codes(items: list[str]) -> list[str]:
    deduped = {_normalize_code(item) for item in items if str(item or "").strip()}
    return sorted(deduped)


def _safe_redis_get_json(key: str) -> dict | None:
    try:
        raw = redis_client.get(key)
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _safe_redis_set_json(key: str, payload: dict, ttl_sec: int) -> None:
    try:
        redis_client.setex(key, max(int(ttl_sec), 1), json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        return


def _resolve_bybit_testnet_credentials(db: Session) -> dict:
    adapter_credentials = execution_credentials_for_adapter(db)
    bybit = dict((adapter_credentials or {}).get("bybit") or {})
    return {
        "api_key": bybit.get("testnet_key") or os.environ.get("BYBIT_TESTNET_API_KEY"),
        "api_secret": bybit.get("testnet_secret") or os.environ.get("BYBIT_TESTNET_API_SECRET"),
        "base_url": bybit.get("testnet_base_url") or os.environ.get("BYBIT_TESTNET_BASE_URL"),
    }


def _bybit_signature(*, api_secret: str, timestamp_ms: str, api_key: str, recv_window: str, payload: str) -> str:
    raw = f"{timestamp_ms}{api_key}{recv_window}{payload}"
    return hmac.new(api_secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def _bybit_signed_post(
    *,
    base_url: str,
    endpoint: str,
    payload: dict,
    api_key: str,
    api_secret: str,
    recv_window: str = "5000",
    timeout_sec: float = 10.0,
) -> dict:
    timestamp_ms = str(int(_utcnow().timestamp() * 1000))
    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    signature = _bybit_signature(
        api_secret=api_secret,
        timestamp_ms=timestamp_ms,
        api_key=api_key,
        recv_window=recv_window,
        payload=compact,
    )
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": signature,
        "X-BAPI-TIMESTAMP": timestamp_ms,
        "X-BAPI-RECV-WINDOW": recv_window,
        "Content-Type": "application/json",
    }
    response = httpx.post(f"{base_url}{endpoint}", content=compact, headers=headers, timeout=timeout_sec)
    try:
        body = response.json()
    except Exception:
        body = {"retCode": -1, "retMsg": "invalid_json", "raw": response.text}
    return {"http_status": response.status_code, "body": body}


def _fetch_bybit_mark_price(base_url: str, symbol: str, timeout_sec: float = 8.0) -> float | None:
    response = httpx.get(
        f"{base_url}/v5/market/tickers",
        params={"category": "linear", "symbol": symbol},
        timeout=timeout_sec,
    )
    if response.status_code != 200:
        raise RuntimeError(f"bybit_market_ticker_http_{response.status_code}")
    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"bybit_market_ticker_non_json_http_{response.status_code}") from exc
    rows = ((data.get("result") or {}).get("list") or [])
    if not rows:
        return None
    mark_price = rows[0].get("markPrice")
    try:
        return float(mark_price)
    except (TypeError, ValueError):
        return None


def run_bybit_testnet_order_smoke(db: Session, *, force_refresh: bool = False) -> dict:
    cache_key = "execution_safety:bybit:order_smoke"
    if not force_refresh:
        cached = _safe_redis_get_json(cache_key)
        if cached:
            return cached

    if not _to_bool(os.environ.get("TESTNET_TRADING_ENABLED")):
        result = {
            "status": "FAIL",
            "reason_code": "TESTNET_TRADING_DISABLED",
            "detail": "TESTNET_TRADING_ENABLED=false",
            "checked_at": _utcnow().isoformat(),
        }
        _safe_redis_set_json(cache_key, result, ttl_sec=30)
        return result

    credentials = _resolve_bybit_testnet_credentials(db)
    api_key = str(credentials.get("api_key") or "").strip()
    api_secret = str(credentials.get("api_secret") or "").strip()
    base_url = str(credentials.get("base_url") or "").strip()
    if not api_key or not api_secret or not base_url:
        result = {
            "status": "FAIL",
            "reason_code": "BYBIT_TESTNET_CREDENTIALS_MISSING",
            "detail": "Missing BYBIT_TESTNET_API_KEY/BYBIT_TESTNET_API_SECRET/BYBIT_TESTNET_BASE_URL",
            "checked_at": _utcnow().isoformat(),
        }
        _safe_redis_set_json(cache_key, result, ttl_sec=60)
        return result

    smoke_enabled = _to_bool(os.environ.get("EXECUTION_SAFETY_BYBIT_ORDER_SMOKE_ENABLED", "true"))
    if not smoke_enabled:
        result = {
            "status": "FAIL",
            "reason_code": "BYBIT_ORDER_SMOKE_FAIL",
            "detail": "EXECUTION_SAFETY_BYBIT_ORDER_SMOKE_ENABLED=false",
            "checked_at": _utcnow().isoformat(),
        }
        _safe_redis_set_json(cache_key, result, ttl_sec=60)
        return result

    symbol = str(os.environ.get("BYBIT_TESTNET_SMOKE_SYMBOL") or "BTCUSDT").upper()
    qty = str(os.environ.get("BYBIT_TESTNET_SMOKE_QTY") or "0.001")

    try:
        mark_price = _fetch_bybit_mark_price(base_url, symbol)
        limit_price = round(max((mark_price or 1.0) * 0.2, 1.0), 2)
        create_payload = {
            "category": "linear",
            "symbol": symbol,
            "side": "Buy",
            "orderType": "Limit",
            "qty": qty,
            "price": f"{limit_price:.2f}",
            "timeInForce": "GTC",
            "orderLinkId": f"safety-smoke-{uuid.uuid4().hex[:20]}",
            "reduceOnly": False,
        }
        create_result = _bybit_signed_post(
            base_url=base_url,
            endpoint="/v5/order/create",
            payload=create_payload,
            api_key=api_key,
            api_secret=api_secret,
            timeout_sec=10,
        )
        body = create_result.get("body") or {}
        ret_code = _safe_int(body.get("retCode"), -1)
        ret_msg = str(body.get("retMsg") or "")
        auth_fail_codes = {10003, 10004, 10005, 10010}

        if create_result.get("http_status") != 200 or ret_code in auth_fail_codes:
            result = {
                "status": "FAIL",
                "reason_code": "BYBIT_ORDER_SMOKE_AUTH_FAIL",
                "detail": ret_msg or "auth_or_signature_failure",
                "http_status": create_result.get("http_status"),
                "ret_code": ret_code,
                "checked_at": _utcnow().isoformat(),
            }
            _safe_redis_set_json(cache_key, result, ttl_sec=60)
            return result

        if ret_code != 0:
            result = {
                "status": "FAIL",
                "reason_code": "BYBIT_ORDER_SMOKE_FAIL",
                "detail": ret_msg or "order_create_failed",
                "http_status": create_result.get("http_status"),
                "ret_code": ret_code,
                "checked_at": _utcnow().isoformat(),
            }
            _safe_redis_set_json(cache_key, result, ttl_sec=60)
            return result

        order_id = ((body.get("result") or {}).get("orderId") or "").strip()
        cancel_payload = {
            "category": "linear",
            "symbol": symbol,
            "orderId": order_id,
        }
        cancel_result = _bybit_signed_post(
            base_url=base_url,
            endpoint="/v5/order/cancel",
            payload=cancel_payload,
            api_key=api_key,
            api_secret=api_secret,
            timeout_sec=10,
        )
        cancel_body = cancel_result.get("body") or {}

        result = {
            "status": "PASS",
            "reason_code": "BYBIT_ORDER_SMOKE_PASS",
            "detail": "order_create_cancel_success",
            "order_id": order_id,
            "symbol": symbol,
            "ret_code": ret_code,
            "cancel_ret_code": _safe_int(cancel_body.get("retCode"), -1),
            "checked_at": _utcnow().isoformat(),
        }
        _safe_redis_set_json(cache_key, result, ttl_sec=90)
        return result
    except Exception as exc:
        result = {
            "status": "FAIL",
            "reason_code": "BYBIT_CONNECTIVITY_FAIL",
            "detail": str(exc),
            "checked_at": _utcnow().isoformat(),
        }
        _safe_redis_set_json(cache_key, result, ttl_sec=60)
        return result


def _artifact_s3_config() -> dict:
    return {
        "bucket": os.environ.get("EXECUTION_SAFETY_S3_BUCKET"),
        "region": os.environ.get("EXECUTION_SAFETY_S3_REGION"),
        "access_key": os.environ.get("EXECUTION_SAFETY_AWS_ACCESS_KEY_ID"),
        "secret_key": os.environ.get("EXECUTION_SAFETY_AWS_SECRET_ACCESS_KEY"),
    }


def persist_execution_safety_artifact(payload: dict) -> dict:
    local_artifact = write_signed_artifact(
        payload,
        artifact_type="execution_safety_gate",
        filename_prefix="execution_safety_gate",
    )
    entry = dict(local_artifact.get("entry") or {})
    artifact_path = str(local_artifact.get("path") or "")
    config = _artifact_s3_config()
    if not all(config.values()):
        return {
            "status": "LOCAL_ONLY",
            "local_path": artifact_path,
            "entry": entry,
            "reason": "missing_s3_credentials",
        }

    file_name = Path(artifact_path).name
    object_key = f"execution-safety/{_utcnow().strftime('%Y/%m/%d')}/{file_name}"
    try:
        client = boto3.client(
            "s3",
            region_name=config["region"],
            aws_access_key_id=config["access_key"],
            aws_secret_access_key=config["secret_key"],
        )
        with Path(artifact_path).open("rb") as handle:
            client.put_object(
                Bucket=config["bucket"],
                Key=object_key,
                Body=handle.read(),
                ContentType="application/json",
                Metadata={
                    "artifact-type": "execution_safety_gate",
                    "artifact-id": str(entry.get("artifact_id") or ""),
                },
            )
        return {
            "status": "S3_UPLOADED",
            "local_path": artifact_path,
            "entry": entry,
            "bucket": config["bucket"],
            "region": config["region"],
            "s3_key": object_key,
            "s3_uri": f"s3://{config['bucket']}/{object_key}",
        }
    except (ClientError, BotoCoreError, OSError) as exc:
        return {
            "status": "LOCAL_ONLY",
            "local_path": artifact_path,
            "entry": entry,
            "reason": "s3_upload_failed",
            "error": str(exc),
        }


def _gate_state_from_readiness(readiness_state: str, hard_blockers: list[str]) -> str:
    if hard_blockers:
        return "BLOCKED"
    state = _normalize_code(readiness_state)
    if state == "READY":
        return "READY"
    if state in {"WARNING", "UNKNOWN", "DEGRADED"}:
        return "DEGRADED"
    return "BLOCKED"


def _collect_gate_codes(validator: dict, bybit_smoke: dict) -> tuple[list[str], list[str], list[dict]]:
    reason_codes = [_normalize_code(code) for code in (validator.get("reason_codes") or []) if code]
    warnings = [_normalize_code(code) for code in (validator.get("warnings") or []) if code]
    blockers_detail: list[dict] = []

    for failure in validator.get("blocking_failures") or []:
        step_key = _normalize_code(failure.get("step_key"))
        reason_code = _normalize_code(failure.get("reason_code"))
        if reason_code or step_key:
            blockers_detail.append(
                {
                    "step_key": step_key,
                    "reason_code": reason_code or "READINESS_BLOCKING_FAILURE",
                    "message": str(failure.get("reason") or failure.get("message") or "blocking_failure"),
                }
            )

    for code in reason_codes:
        if code in HARD_BLOCK_REASON_CODES:
            blockers_detail.append({"step_key": "READINESS", "reason_code": code, "message": "validator_reason_code"})

    if str(bybit_smoke.get("status") or "").upper() != "PASS":
        blockers_detail.append(
            {
                "step_key": "BYBIT_ORDER_SMOKE",
                "reason_code": _normalize_code(bybit_smoke.get("reason_code") or "BYBIT_ORDER_SMOKE_FAIL"),
                "message": str(bybit_smoke.get("detail") or "order_smoke_failed"),
            }
        )

    for failure in validator.get("blocking_failures") or []:
        step_key = _normalize_code(failure.get("step_key"))
        if step_key in {item.upper() for item in HARD_BLOCK_STEP_KEYS}:
            reason_code = _normalize_code(failure.get("reason_code") or "READINESS_BLOCKING_FAILURE")
            blockers_detail.append(
                {
                    "step_key": step_key,
                    "reason_code": reason_code,
                    "message": str(failure.get("reason") or failure.get("message") or "hard_block_step_failure"),
                }
            )

    execution_proof = dict(validator.get("execution_proof") or {})
    real_metric_count = _safe_int(execution_proof.get("real_metric_count"), 0)
    has_mocked_paths = bool(execution_proof.get("has_mocked_paths"))
    if has_mocked_paths:
        blockers_detail.append(
            {
                "step_key": "PROOF_QUALITY",
                "reason_code": "EXECUTION_PROOF_MOCKED_PATHS",
                "message": "execution_proof_has_mocked_paths",
            }
        )
    if real_metric_count <= 0:
        blockers_detail.append(
            {
                "step_key": "PROOF_QUALITY",
                "reason_code": "EXECUTION_PROOF_REAL_METRIC_MISSING",
                "message": "real_metric_count<=0",
            }
        )

    if not _to_bool(os.environ.get("TESTNET_TRADING_ENABLED")):
        blockers_detail.append(
            {
                "step_key": "EXECUTION_MODE",
                "reason_code": "TESTNET_TRADING_DISABLED",
                "message": "TESTNET_TRADING_ENABLED=false",
            }
        )

    hard_blockers = _unique_codes([item.get("reason_code") for item in blockers_detail])
    soft_warnings = _unique_codes(warnings)
    return hard_blockers, soft_warnings, blockers_detail


def get_execution_safety_gate(db: Session, *, user_id: str | None = None, force_refresh: bool = False) -> dict:
    from core.readiness.go_live_validator import evaluate_go_live_readiness
    from services.pipeline.runtime import pipeline_runtime

    cache = pipeline_runtime.cache if pipeline_runtime else None
    validator = evaluate_go_live_readiness(db, cache, user_id=user_id)
    bybit_smoke = run_bybit_testnet_order_smoke(db, force_refresh=force_refresh)
    hard_blockers, soft_warnings, blockers_detail = _collect_gate_codes(validator, bybit_smoke)

    gate_state = _gate_state_from_readiness(str(validator.get("readiness_state") or "UNKNOWN"), hard_blockers)
    execution_allowed = gate_state in {"READY", "DEGRADED"} and len(hard_blockers) == 0

    gate_payload = {
        "gate_state": gate_state,
        "execution_allowed": execution_allowed,
        "hard_blockers": hard_blockers,
        "soft_warnings": soft_warnings,
        "hard_blockers_detail": blockers_detail,
        "readiness_state": validator.get("readiness_state"),
        "readiness_score": validator.get("score"),
        "go_live_allowed": bool(validator.get("go_live_allowed")),
        "validator_reason_codes": sorted(set(validator.get("reason_codes") or [])),
        "bybit_order_smoke": bybit_smoke,
        "checked_at": _utcnow().isoformat(),
    }

    artifact_input = {
        "schema_version": "1.0",
        "proof_type": "execution_safety_gate_snapshot",
        "created_at": gate_payload["checked_at"],
        "gate": gate_payload,
        "validator": {
            "execution_mode": validator.get("execution_mode"),
            "execution_allowed": bool(validator.get("execution_allowed")),
            "readiness_state": validator.get("readiness_state"),
            "score": validator.get("score"),
        },
    }
    artifact_metadata = persist_execution_safety_artifact(artifact_input)

    return {
        **gate_payload,
        "artifact": artifact_metadata,
    }


def _intent_state_from_event(current_state: str, event: ExecutionIntentEvent) -> tuple[str, str | None]:
    event_type = _normalize_code(event.event_type)
    event_status = _normalize_code(event.event_status)

    target = current_state
    if event_type in {"EXECUTION_ORDER_SUBMISSION_REQUESTED", "EXECUTION_ORDER_SUBMITTED"}:
        target = "SUBMITTED"
    elif event_type in {"EXECUTION_ORDER_ACKED", "EXECUTION_ORDER_ACCEPTED"} or event_status in {
        "NEW",
        "SUBMITTED",
        "ACCEPTED",
        "PARTIALLY_FILLED",
        "PARTIAL_FILL",
    }:
        target = "ACKED"
    elif event_type in {"EXECUTION_ORDER_FILLED", "EXECUTION_ORDER_FINALIZED"} and event_status == "FILLED":
        target = "FILLED"
    elif event_status in {"FAILED", "REJECTED", "ERROR"}:
        target = "FAILED"
    elif event_status in {"CANCELLED", "CANCELED", "EXPIRED"}:
        target = "CANCELLED"
    elif "QUARANTINE" in event_type:
        target = "QUARANTINED"

    allowed = INTENT_ALLOWED_TRANSITIONS.get(current_state, set())
    if target != current_state and target not in allowed:
        return current_state, f"invalid_transition:{current_state}->{target}"
    return target, None


def _intent_timeout_config() -> dict[str, int]:
    values: dict[str, int] = {}
    for state, env_key in INTENT_STUCK_TIMEOUT_ENV.items():
        values[state] = _safe_int(os.environ.get(env_key), INTENT_STUCK_TIMEOUT_DEFAULTS[state])
    return values


def _quarantine_stuck_intent(db: Session, intent_row: dict, *, timeout_sec: int) -> None:
    entity_id = str(intent_row.get("intent_id") or "")
    if not entity_id:
        return
    now = _utcnow()
    next_retry = now + timedelta(seconds=15)
    payload = {
        "intent_id": entity_id,
        "symbol": intent_row.get("symbol"),
        "state": intent_row.get("state"),
        "age_seconds": intent_row.get("age_seconds"),
        "timeout_sec": timeout_sec,
        "state_path": intent_row.get("state_path") or [],
    }
    upsert_failed_event(
        db,
        event_type="execution.intent.stuck",
        entity_type="execution_intent",
        entity_id=entity_id,
        payload=payload,
        error_message="intent_state_timeout",
        status="quarantined",
        retry_count=0,
        max_retry=_safe_int(os.environ.get("EXECUTION_QUARANTINE_MAX_RETRY"), 5),
        next_retry_at=next_retry,
        failure_class="state_timeout",
        dead_letter_reason="intent_timeout",
        retry_reason="automatic_quarantine",
        error_details={"timeout_sec": timeout_sec},
    )


def get_execution_intent_state_machine_snapshot(
    db: Session,
    *,
    limit: int = 100,
    include_events: bool = False,
    auto_quarantine_stuck: bool = True,
) -> dict:
    capped_limit = min(max(int(limit or 1), 1), 250)
    intents = db.query(ExecutionIntent).order_by(ExecutionIntent.created_at.desc()).limit(capped_limit).all()
    timeout_config = _intent_timeout_config()
    now = _utcnow()

    rows: list[dict] = []
    state_counts: dict[str, int] = {state: 0 for state in INTENT_ALLOWED_TRANSITIONS}
    stuck_count = 0

    for intent in intents:
        events = (
            db.query(ExecutionIntentEvent)
            .filter(ExecutionIntentEvent.intent_id == intent.intent_id)
            .order_by(ExecutionIntentEvent.created_at.asc())
            .all()
        )

        state = "CREATED"
        state_path = ["CREATED"]
        violations: list[str] = []
        last_transition_at = _as_utc(intent.created_at)

        for event in events:
            next_state, violation = _intent_state_from_event(state, event)
            if violation:
                violations.append(violation)
            if next_state != state:
                state = next_state
                state_path.append(state)
                last_transition_at = _as_utc(event.created_at) or last_transition_at
            else:
                last_transition_at = _as_utc(event.created_at) or last_transition_at

        state_counts[state] = state_counts.get(state, 0) + 1
        anchor = last_transition_at or _as_utc(intent.created_at) or now
        age_seconds = max((now - anchor).total_seconds(), 0)
        timeout_sec = timeout_config.get(state)
        is_stuck = timeout_sec is not None and age_seconds > timeout_sec
        if is_stuck:
            stuck_count += 1

        row_payload = {
            "intent_id": intent.intent_id,
            "symbol": intent.symbol,
            "strategy_id": intent.strategy_id,
            "state": state,
            "state_path": state_path,
            "violations": violations,
            "is_stuck": is_stuck,
            "age_seconds": round(age_seconds, 2),
            "last_transition_at": anchor.isoformat() if anchor else None,
            "created_at": _as_utc(intent.created_at).isoformat() if _as_utc(intent.created_at) else None,
            "order_id": intent.order_id,
            "rejection_reason": intent.rejection_reason,
        }

        if include_events:
            row_payload["events"] = [
                {
                    "event_type": event.event_type,
                    "event_status": event.event_status,
                    "created_at": _as_utc(event.created_at).isoformat() if _as_utc(event.created_at) else None,
                    "external_order_id": event.external_order_id,
                }
                for event in events
            ]

        rows.append(row_payload)
        if is_stuck and auto_quarantine_stuck:
            _quarantine_stuck_intent(db, row_payload, timeout_sec=timeout_sec or 0)

    return {
        "total": len(rows),
        "stuck_count": stuck_count,
        "state_counts": state_counts,
        "timeouts": timeout_config,
        "items": rows,
    }


def _queue_metrics() -> dict:
    metrics = {
        "redis_available": True,
        "runtime_events_queue": 0,
        "runtime_retry_queue": 0,
        "runtime_dead_letter_queue": 0,
        "runtime_quarantine_queue": 0,
    }
    try:
        metrics["runtime_events_queue"] = int(redis_client.llen(RUNTIME_EVENTS_QUEUE))
        metrics["runtime_retry_queue"] = int(redis_client.llen(RUNTIME_RETRY_QUEUE))
        metrics["runtime_dead_letter_queue"] = int(redis_client.llen(RUNTIME_DEAD_LETTER_QUEUE))
        metrics["runtime_quarantine_queue"] = int(redis_client.llen(RUNTIME_QUARANTINE_QUEUE))
    except Exception as exc:
        metrics["redis_available"] = False
        metrics["error"] = str(exc)
    return metrics


def get_runtime_quarantine_snapshot(db: Session, *, limit: int = 200) -> dict:
    capped_limit = min(max(int(limit or 1), 1), 500)
    rows = (
        db.query(FailedEvent)
        .filter(FailedEvent.entity_type.in_(["runtime_event", "execution_intent"]))
        .order_by(FailedEvent.updated_at.desc())
        .limit(capped_limit)
        .all()
    )

    summary: dict[str, int] = {}
    items: list[dict] = []
    for row in rows:
        status_key = f"{row.entity_type}:{row.status}"
        summary[status_key] = summary.get(status_key, 0) + 1
        payload = dict(row.payload or {})
        items.append(
            {
                "id": row.id,
                "event_id": row.entity_id,
                "entity_type": row.entity_type,
                "event_type": row.event_type,
                "status": row.status,
                "retry_count": row.retry_count,
                "max_retry": row.max_retry,
                "error_message": row.error_message,
                "failure_class": row.failure_class,
                "reason_code": payload.get("reason_code") or payload.get("state") or "unknown",
                "next_retry_at": _as_utc(row.next_retry_at).isoformat() if _as_utc(row.next_retry_at) else None,
                "resolved_at": _as_utc(row.resolved_at).isoformat() if _as_utc(row.resolved_at) else None,
                "updated_at": _as_utc(row.updated_at).isoformat() if _as_utc(row.updated_at) else None,
                "created_at": _as_utc(row.created_at).isoformat() if _as_utc(row.created_at) else None,
                "payload": payload,
            }
        )

    return {
        "total": len(items),
        "summary": summary,
        "queue_metrics": _queue_metrics(),
        "items": items,
    }


def apply_runtime_quarantine_action(
    db: Session,
    *,
    event_id: str,
    action: str,
    actor_user_id: str,
    actor_role: str,
) -> dict:
    row = db.query(FailedEvent).filter(FailedEvent.id == event_id).first()
    if row is None:
        row = db.query(FailedEvent).filter(FailedEvent.entity_id == event_id).first()
    if row is None:
        raise ValueError("quarantine_event_not_found")

    normalized = str(action or "").strip().lower()
    if normalized not in {"replay", "dismiss", "mark_failed"}:
        raise ValueError("invalid_action")

    if row.entity_type == "runtime_event":
        if normalized == "replay":
            row = replay_quarantined_event(db, row)
        elif normalized == "dismiss":
            row = dismiss_quarantined_event(db, row)
        else:
            row = mark_quarantined_failed(db, row)
    else:
        if normalized == "replay":
            payload = dict(row.payload or {})
            intent_id = str(payload.get("intent_id") or row.entity_id)
            publish_runtime_event(
                event_type="execution.order.submission_requested",
                payload={"intent_id": intent_id, "source": "execution_readiness_quarantine_replay"},
                correlation_id=intent_id,
                causation_id=row.id,
                partition_key=f"intent::{intent_id}",
            )
            row.status = "retrying"
            row.retry_count = int(row.retry_count or 0) + 1
            row.next_retry_at = _utcnow() + timedelta(seconds=15)
            row.updated_at = _utcnow()
            db.commit()
            db.refresh(row)
        elif normalized == "dismiss":
            row.status = "resolved"
            row.resolved_at = _utcnow()
            row.updated_at = _utcnow()
            db.commit()
            db.refresh(row)
        else:
            row.status = "dead"
            row.dead_letter_reason = row.dead_letter_reason or "manual_mark_failed"
            row.updated_at = _utcnow()
            db.commit()
            db.refresh(row)

    create_audit_log(
        db,
        action=f"execution_quarantine_{normalized}",
        entity_type="failed_event",
        entity_id=row.id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        details={"event_id": event_id, "action": normalized, "entity_type": row.entity_type},
    )

    payload = dict(row.payload or {})
    return {
        "id": row.id,
        "event_id": row.entity_id,
        "entity_type": row.entity_type,
        "status": row.status,
        "retry_count": row.retry_count,
        "max_retry": row.max_retry,
        "next_retry_at": _as_utc(row.next_retry_at).isoformat() if _as_utc(row.next_retry_at) else None,
        "resolved_at": _as_utc(row.resolved_at).isoformat() if _as_utc(row.resolved_at) else None,
        "payload": payload,
    }


def build_execution_incident_package(
    db: Session,
    *,
    user_id: str | None = None,
    include_events: bool = False,
) -> dict:
    gate_snapshot = get_execution_safety_gate(db, user_id=user_id, force_refresh=False)
    intents_snapshot = get_execution_intent_state_machine_snapshot(
        db,
        limit=200,
        include_events=include_events,
        auto_quarantine_stuck=True,
    )
    quarantine_snapshot = get_runtime_quarantine_snapshot(db, limit=200)

    package_id = str(uuid.uuid4())
    generated_at = _utcnow().isoformat()
    package_payload = {
        "schema_version": "1.0",
        "package_type": "execution_incident_package",
        "package_id": package_id,
        "generated_at": generated_at,
        "gate_snapshot": gate_snapshot,
        "intents_snapshot": intents_snapshot,
        "quarantine_snapshot": quarantine_snapshot,
        "artifact_links": {
            "gate_artifact_local": ((gate_snapshot.get("artifact") or {}).get("local_path")),
            "gate_artifact_s3": ((gate_snapshot.get("artifact") or {}).get("s3_uri")),
        },
    }

    incident_artifact = write_signed_artifact(
        package_payload,
        artifact_type="execution_incident_package",
        filename_prefix="execution_incident_package",
    )
    package_payload["package_artifact"] = {
        "artifact_id": incident_artifact.get("artifact_id"),
        "path": incident_artifact.get("path"),
        "entry": incident_artifact.get("entry"),
    }
    return package_payload
