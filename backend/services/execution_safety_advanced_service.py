from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from models import ExecutionIntent, ExecutionIntentEvent, FailedEvent
from services.admin_exchange_credentials_service import execution_credentials_for_adapter
from services.artifact_service import write_signed_artifact
from services.audit_service import create_audit_log
from services.execution_safety_namespace_service import (
    apply_execution_safety_quarantine_action,
    apply_intent_recovery_action,
    create_execution_attempt_artifact,
    evaluate_execution_safety_gate,
)
from services.failed_event_service import upsert_failed_event


REQUIRED_SPINE_FIELDS = ["request_id", "intent_id", "order_id", "execution_id", "session_id", "correlation_id"]
CRITICAL_STAGES = {
    "order_submit",
    "exchange_ack_fill_ingestion",
    "reconcile_execution",
    "artifact_finalize",
    "lifecycle_transition_persist",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_state(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw == "CANCELLED":
        return "CANCELED"
    return raw


@dataclass
class ContextEnvelope:
    request_id: str
    intent_id: str
    order_id: str
    execution_id: str
    session_id: str
    correlation_id: str

    def as_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "intent_id": self.intent_id,
            "order_id": self.order_id,
            "execution_id": self.execution_id,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
        }


def _build_context_envelope(
    *,
    intent_id: str,
    correlation_id: str,
    order_id: str | None = None,
    request_id: str | None = None,
    execution_id: str | None = None,
    session_id: str | None = None,
) -> ContextEnvelope:
    return ContextEnvelope(
        request_id=str(request_id or f"req-{uuid.uuid4().hex}"),
        intent_id=str(intent_id),
        order_id=str(order_id or f"ord-{uuid.uuid4().hex[:20]}"),
        execution_id=str(execution_id or f"exe-{uuid.uuid4().hex[:20]}"),
        session_id=str(session_id or f"ses-{uuid.uuid4().hex[:20]}"),
        correlation_id=str(correlation_id),
    )


def _enforce_correlation_envelope(
    db: Session,
    *,
    envelope: dict,
    stage: str,
    actor_user_id: str,
    actor_role: str,
    intent_id: str | None = None,
) -> tuple[bool, dict]:
    missing = [field for field in REQUIRED_SPINE_FIELDS if not str(envelope.get(field) or "").strip()]
    if not missing:
        return True, {"status": "ok"}

    reason_code = "correlation_spine_missing"
    details = {"missing_fields": missing, "stage": stage, "envelope": envelope}
    if stage in CRITICAL_STAGES:
        target_intent_id = str(intent_id or envelope.get("intent_id") or "unknown")
        upsert_failed_event(
            db,
            event_type=f"execution.correlation.{stage}",
            entity_type="execution_intent",
            entity_id=target_intent_id,
            payload={
                "intent_id": target_intent_id,
                "correlation_id": envelope.get("correlation_id"),
                "reason_code": reason_code,
                "failure_stage": stage,
                "missing_fields": missing,
            },
            error_message=reason_code,
            status="quarantined",
            retry_count=0,
            max_retry=3,
            correlation_id=str(envelope.get("correlation_id") or ""),
            failure_class="correlation_violation",
            dead_letter_reason=reason_code,
        )
        create_audit_log(
            db,
            action="execution_correlation_violation_quarantined",
            entity_type="execution_intent",
            entity_id=target_intent_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            severity="warning",
            details=details,
        )
        return False, {"status": "quarantined", **details}

    create_audit_log(
        db,
        action="execution_correlation_violation_blocked",
        entity_type="execution_intent",
        entity_id=str(intent_id or envelope.get("intent_id") or "unknown"),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        details=details,
    )
    return False, {"status": "blocked", **details}


def _resolve_bybit_credentials(db: Session) -> tuple[str, str, str]:
    cfg = execution_credentials_for_adapter(db)
    bybit = dict((cfg or {}).get("bybit") or {})
    api_key = str(bybit.get("testnet_key") or os.environ.get("BYBIT_TESTNET_API_KEY") or "").strip()
    api_secret = str(bybit.get("testnet_secret") or os.environ.get("BYBIT_TESTNET_API_SECRET") or "").strip()
    base_url = str(bybit.get("testnet_base_url") or os.environ.get("BYBIT_TESTNET_BASE_URL") or "https://api-testnet.bybit.com").strip()
    return api_key, api_secret, base_url


def _bybit_sign(secret: str, timestamp: str, api_key: str, recv_window: str, payload: str) -> str:
    raw = f"{timestamp}{api_key}{recv_window}{payload}"
    return hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def _bybit_private_post(db: Session, endpoint: str, payload: dict) -> dict:
    api_key, api_secret, base_url = _resolve_bybit_credentials(db)
    if not api_key or not api_secret:
        return {"ok": False, "reason": "missing_exchange_credentials"}
    recv_window = "5000"
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    ts = str(int(_utcnow().timestamp() * 1000))
    sign = _bybit_sign(api_secret, ts, api_key, recv_window, body)
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": sign,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": recv_window,
        "Content-Type": "application/json",
    }
    response = httpx.post(f"{base_url}{endpoint}", headers=headers, content=body, timeout=15)
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text}
    ret_code = _safe_int(data.get("retCode"), -1)
    return {
        "ok": response.status_code == 200 and ret_code == 0,
        "http_status": response.status_code,
        "data": data,
        "base_url": base_url,
    }


def _bybit_private_get(db: Session, endpoint: str, params: dict) -> dict:
    api_key, api_secret, base_url = _resolve_bybit_credentials(db)
    if not api_key or not api_secret:
        return {"ok": False, "reason": "missing_exchange_credentials"}
    recv_window = "5000"
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    ts = str(int(_utcnow().timestamp() * 1000))
    sign = _bybit_sign(api_secret, ts, api_key, recv_window, query)
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": sign,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": recv_window,
    }
    response = httpx.get(f"{base_url}{endpoint}", params=params, headers=headers, timeout=15)
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text}
    ret_code = _safe_int(data.get("retCode"), -1)
    return {
        "ok": response.status_code == 200 and ret_code == 0,
        "http_status": response.status_code,
        "data": data,
        "base_url": base_url,
    }


def _extract_external_order_id(events: list[ExecutionIntentEvent]) -> str | None:
    for event in reversed(events):
        oid = str(event.external_order_id or "").strip()
        if oid:
            return oid
        payload = dict(event.payload or {})
        oid = str(payload.get("orderId") or payload.get("order_id") or "").strip()
        if oid:
            return oid
    return None


def _append_intent_event(db: Session, *, intent_id: str, event_type: str, event_status: str, payload: dict, external_order_id: str | None = None) -> None:
    db.add(
        ExecutionIntentEvent(
            id=str(uuid.uuid4()),
            intent_id=intent_id,
            event_type=event_type,
            event_status=_normalize_state(event_status),
            external_order_id=external_order_id,
            payload=payload,
        )
    )


def get_intent_timeline(db: Session, *, intent_id: str) -> dict:
    intent = db.query(ExecutionIntent).filter(ExecutionIntent.intent_id == intent_id).first()
    if intent is None:
        raise ValueError("intent_not_found")
    events = (
        db.query(ExecutionIntentEvent)
        .filter(ExecutionIntentEvent.intent_id == intent_id)
        .order_by(ExecutionIntentEvent.created_at.asc())
        .all()
    )
    return {
        "intent_id": intent.intent_id,
        "correlation_id": intent.correlation_id,
        "current_status": _normalize_state(intent.status),
        "timeline": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "event_status": _normalize_state(event.event_status),
                "external_order_id": event.external_order_id,
                "payload": event.payload,
                "created_at": _as_utc(event.created_at).isoformat() if _as_utc(event.created_at) else None,
            }
            for event in events
        ],
    }


def get_quarantine_detail(db: Session, *, quarantine_id: str) -> dict:
    row = db.query(FailedEvent).filter(FailedEvent.id == quarantine_id).first()
    if row is None:
        raise ValueError("quarantine_event_not_found")
    payload = dict(row.payload or {})
    return {
        "quarantine_id": row.id,
        "correlation_id": row.correlation_id or payload.get("correlation_id"),
        "intent_id": payload.get("intent_id") or (row.entity_id if row.entity_type == "execution_intent" else None),
        "reason": payload.get("reason_code") or row.dead_letter_reason or row.error_message,
        "failure_stage": payload.get("failure_stage") or payload.get("state") or row.event_type,
        "retry_count": row.retry_count,
        "max_retry": row.max_retry,
        "first_seen_at": _as_utc(row.created_at).isoformat() if _as_utc(row.created_at) else None,
        "last_seen_at": _as_utc(row.updated_at).isoformat() if _as_utc(row.updated_at) else None,
        "payload_snapshot": payload,
        "error_snapshot": {
            "error_message": row.error_message,
            "error_details": row.error_details,
            "failure_class": row.failure_class,
        },
        "status": row.status,
        "entity_type": row.entity_type,
        "event_type": row.event_type,
    }


def reconcile_intent_with_exchange(
    db: Session,
    *,
    intent_id: str,
    actor_type: str,
    actor_id: str,
    reason: str,
    stage: str = "reconcile_execution",
) -> dict:
    intent = db.query(ExecutionIntent).filter(ExecutionIntent.intent_id == intent_id).first()
    if intent is None:
        raise ValueError("intent_not_found")

    events = (
        db.query(ExecutionIntentEvent)
        .filter(ExecutionIntentEvent.intent_id == intent_id)
        .order_by(ExecutionIntentEvent.created_at.asc())
        .all()
    )
    external_order_id = _extract_external_order_id(events)
    context = _build_context_envelope(
        intent_id=intent.intent_id,
        correlation_id=str(intent.correlation_id or f"corr-{uuid.uuid4().hex[:16]}"),
        order_id=external_order_id or "",
    )
    ok, envelope_result = _enforce_correlation_envelope(
        db,
        envelope=context.as_dict(),
        stage=stage,
        actor_user_id=actor_id,
        actor_role=actor_type,
        intent_id=intent.intent_id,
    )
    if not ok:
        db.commit()
        raise ValueError("correlation_envelope_missing")

    before_state = _normalize_state(intent.status)
    intent.status = "RECONCILING"
    _append_intent_event(
        db,
        intent_id=intent.intent_id,
        event_type="EXECUTION_RECONCILE_STARTED",
        event_status="RECONCILING",
        payload={"reason": reason, **context.as_dict()},
        external_order_id=external_order_id,
    )
    db.flush()

    order_snapshot = None
    execution_snapshot = None
    exchange_state = "UNKNOWN"
    detected_fill_qty = 0.0
    detected_avg_price = 0.0
    mismatch_flags: list[str] = []
    resolution_action = "manual_review"
    resolution_reason = "exchange_data_unavailable"

    if external_order_id:
        order_resp = _bybit_private_get(
            db,
            "/v5/order/realtime",
            {"category": "linear", "symbol": intent.symbol, "orderId": external_order_id},
        )
        exec_resp = _bybit_private_get(
            db,
            "/v5/execution/list",
            {"category": "linear", "symbol": intent.symbol, "orderId": external_order_id, "limit": 50},
        )
        if order_resp.get("ok"):
            rows = (((order_resp.get("data") or {}).get("result") or {}).get("list") or [])
            order_snapshot = rows[0] if rows else {}
            exchange_state = str(order_snapshot.get("orderStatus") or "UNKNOWN").upper()
        if exec_resp.get("ok"):
            fills = (((exec_resp.get("data") or {}).get("result") or {}).get("list") or [])
            execution_snapshot = fills
            fill_qty_total = sum(_safe_float(item.get("execQty"), 0.0) for item in fills)
            detected_fill_qty = round(fill_qty_total, 8)
            if fills:
                weighted = sum(_safe_float(item.get("execPrice"), 0.0) * _safe_float(item.get("execQty"), 0.0) for item in fills)
                detected_avg_price = weighted / fill_qty_total if fill_qty_total > 0 else 0.0
        if not order_resp.get("ok") and not exec_resp.get("ok"):
            mismatch_flags.append("exchange_unreachable")
            resolution_reason = "exchange_unreachable"
        else:
            local_states = {_normalize_state(evt.event_status) for evt in events}
            if len([evt for evt in events if (evt.external_order_id or "") == external_order_id]) > 1:
                mismatch_flags.append("duplicate_order_detection")
            if exchange_state in {"FILLED"} and "FILLED" not in local_states:
                mismatch_flags.append("missing_fill_detection")
            if exchange_state in {"NEW", "PARTIALLYFILLED", "PARTIALLY_FILLED"} and "FILLED" in local_states:
                mismatch_flags.append("ghost_fill_detection")
            if "PARTIALLY_FILLED" in local_states and detected_fill_qty <= 0:
                mismatch_flags.append("partial_fill_mismatch_detection")
            if "SUBMITTED" in local_states and exchange_state in {"UNKNOWN", ""}:
                mismatch_flags.append("late_ack_detection")
            if exchange_state not in {"UNKNOWN", ""} and not external_order_id:
                mismatch_flags.append("order_exists_exchange_local_missing")
            if "SUBMITTED" in local_states and exchange_state in {"UNKNOWN", ""}:
                mismatch_flags.append("local_submitted_exchange_no_trace")
            if "CANCELED" in local_states and exchange_state == "FILLED":
                mismatch_flags.append("canceled_locally_filled_remotely")

            if not mismatch_flags:
                resolution_action = "mark_reconciled"
                resolution_reason = "exchange_state_consistent"
                intent.status = "RECONCILED"
            else:
                resolution_action = "manual_review"
                resolution_reason = ";".join(sorted(set(mismatch_flags)))
    else:
        mismatch_flags.append("local_submitted_exchange_no_trace")
        resolution_reason = "missing_external_order_id"

    result = {
        "intent_id": intent.intent_id,
        "correlation_id": intent.correlation_id,
        "exchange_order_id": external_order_id,
        "local_order_id": intent.order_id,
        "detected_exchange_state": exchange_state,
        "detected_fill_qty": detected_fill_qty,
        "detected_avg_price": round(detected_avg_price, 8),
        "mismatch_flags": sorted(set(mismatch_flags)),
        "resolution_action": resolution_action,
        "resolution_reason": resolution_reason,
        "reconciled_at": _utcnow().isoformat(),
        "order_snapshot": order_snapshot,
        "execution_snapshot": execution_snapshot,
    }

    _append_intent_event(
        db,
        intent_id=intent.intent_id,
        event_type="EXECUTION_RECONCILE_RESULT",
        event_status="RECONCILED" if resolution_action == "mark_reconciled" else "FAILED",
        payload={**result, **context.as_dict()},
        external_order_id=external_order_id,
    )
    if resolution_action == "mark_reconciled":
        _append_intent_event(
            db,
            intent_id=intent.intent_id,
            event_type="EXECUTION_RECONCILED",
            event_status="RECONCILED",
            payload={"resolution_reason": resolution_reason, **context.as_dict()},
            external_order_id=external_order_id,
        )
    else:
        intent.status = before_state

    db.commit()
    db.refresh(intent)

    artifact = create_execution_attempt_artifact(
        db,
        intent_id=intent.intent_id,
        request_id=context.request_id,
        session_id=context.session_id,
        execution_id=context.execution_id,
    )
    create_audit_log(
        db,
        action="execution_reconcile_completed",
        entity_type="execution_intent",
        entity_id=intent.intent_id,
        actor_user_id=actor_id,
        actor_role=actor_type,
        severity="warning" if mismatch_flags else "info",
        details={
            "actor_type": actor_type,
            "actor_id": actor_id,
            "action": "reconcile",
            "target_type": "execution_intent",
            "target_id": intent.intent_id,
            "reason": reason,
            "before_state": before_state,
            "after_state": _normalize_state(intent.status),
            "correlation_id": intent.correlation_id,
            "reconcile_result": result,
        },
    )
    return {
        "intent_id": intent.intent_id,
        "before_state": before_state,
        "after_state": _normalize_state(intent.status),
        "reconcile_result": result,
        "artifact": artifact,
    }


def get_intent_reconcile(db: Session, *, intent_id: str) -> dict:
    intent = db.query(ExecutionIntent).filter(ExecutionIntent.intent_id == intent_id).first()
    if intent is None:
        raise ValueError("intent_not_found")
    event = (
        db.query(ExecutionIntentEvent)
        .filter(ExecutionIntentEvent.intent_id == intent_id, ExecutionIntentEvent.event_type == "EXECUTION_RECONCILE_RESULT")
        .order_by(ExecutionIntentEvent.created_at.desc())
        .first()
    )
    return {
        "intent_id": intent.intent_id,
        "correlation_id": intent.correlation_id,
        "current_status": _normalize_state(intent.status),
        "latest_reconcile": (event.payload if event else {}),
        "latest_reconcile_at": _as_utc(event.created_at).isoformat() if event and _as_utc(event.created_at) else None,
    }


def get_artifact_by_intent(db: Session, *, intent_id: str) -> dict:
    return create_execution_attempt_artifact(db, intent_id=intent_id)


def _record_acceptance_artifact(payload: dict) -> dict:
    artifact = write_signed_artifact(
        payload,
        artifact_type="execution_testnet_acceptance",
        filename_prefix="execution_testnet_acceptance",
    )
    return {
        "artifact_id": artifact.get("artifact_id"),
        "path": artifact.get("path"),
        "entry": artifact.get("entry"),
    }


def _create_acceptance_intent(db: Session, *, symbol: str, qty: float, correlation_id: str, acceptance_run_id: str, mode: str) -> ExecutionIntent:
    intent = ExecutionIntent(
        intent_id=f"accept-{uuid.uuid4().hex[:20]}",
        strategy_id="execution_safety_acceptance",
        strategy_version_id="acceptance_v1",
        account_id="acceptance",
        symbol=symbol,
        side="BUY",
        order_type="LIMIT" if mode == "ack_mode" else "MARKET",
        quantity=qty,
        price_reference={"source": "acceptance", "mode": mode},
        decision_hash=uuid.uuid4().hex,
        context_hash=uuid.uuid4().hex,
        intent_hash=uuid.uuid4().hex,
        correlation_id=correlation_id,
        status="CREATED",
        metadata={"acceptance_run_id": acceptance_run_id, "mode": mode},
    )
    db.add(intent)
    db.flush()
    return intent


def _submit_acceptance_order(db: Session, *, symbol: str, qty: float, mode: str) -> dict:
    if mode == "ack_mode":
        mark_resp = httpx.get(
            f"{_resolve_bybit_credentials(db)[2]}/v5/market/tickers",
            params={"category": "linear", "symbol": symbol},
            timeout=12,
        )
        mark_price = 1000.0
        if mark_resp.status_code == 200:
            try:
                rows = (((mark_resp.json() or {}).get("result") or {}).get("list") or [])
                if rows:
                    mark_price = _safe_float(rows[0].get("markPrice"), 1000.0)
            except Exception:
                pass
        price = max(mark_price * 0.15, 1)
        payload = {
            "category": "linear",
            "symbol": symbol,
            "side": "Buy",
            "orderType": "Limit",
            "qty": str(qty),
            "price": f"{price:.2f}",
            "timeInForce": "GTC",
            "orderLinkId": f"accept-ack-{uuid.uuid4().hex[:20]}",
        }
    else:
        payload = {
            "category": "linear",
            "symbol": symbol,
            "side": "Buy",
            "orderType": "Market",
            "qty": str(qty),
            "orderLinkId": f"accept-fill-{uuid.uuid4().hex[:20]}",
        }
    return _bybit_private_post(db, "/v5/order/create", payload)


def _run_single_acceptance_mode(
    db: Session,
    *,
    acceptance_run_id: str,
    correlation_id: str,
    symbol: str,
    qty: float,
    mode: str,
    requested_by: str,
) -> dict:
    intent = _create_acceptance_intent(
        db,
        symbol=symbol,
        qty=qty,
        correlation_id=correlation_id,
        acceptance_run_id=acceptance_run_id,
        mode=mode,
    )
    envelope = _build_context_envelope(intent_id=intent.intent_id, correlation_id=correlation_id)
    ok, context_result = _enforce_correlation_envelope(
        db,
        envelope=envelope.as_dict(),
        stage="order_submit",
        actor_user_id=requested_by,
        actor_role="system",
        intent_id=intent.intent_id,
    )
    if not ok:
        db.commit()
        raise ValueError("correlation_envelope_missing")

    _append_intent_event(
        db,
        intent_id=intent.intent_id,
        event_type="EXECUTION_ORDER_SUBMISSION_REQUESTED",
        event_status="SUBMITTED",
        payload={
            "acceptance_run_id": acceptance_run_id,
            "mode": mode,
            **envelope.as_dict(),
        },
    )
    intent.status = "SUBMITTED"
    db.commit()

    submit = _submit_acceptance_order(db, symbol=symbol, qty=qty, mode=mode)
    if not submit.get("ok"):
        _append_intent_event(
            db,
            intent_id=intent.intent_id,
            event_type="EXECUTION_ORDER_FINALIZED",
            event_status="FAILED",
            payload={"acceptance_run_id": acceptance_run_id, "mode": mode, "submit": submit, **envelope.as_dict()},
        )
        intent.status = "FAILED"
        db.commit()
        failure_payload = {
            "schema_version": "1.0",
            "proof_type": "execution_testnet_acceptance_failure",
            "acceptance_run_id": acceptance_run_id,
            "mode": mode,
            "correlation_id": correlation_id,
            "intent_id": intent.intent_id,
            "failure_reason": "order_submit_failed",
            "submit": submit,
        }
        acceptance_artifact = _record_acceptance_artifact(failure_payload)
        create_audit_log(
            db,
            action="execution_testnet_acceptance_failed",
            entity_type="execution_intent",
            entity_id=intent.intent_id,
            actor_user_id=requested_by,
            actor_role="system",
            severity="warning",
            details={
                "actor_type": "system",
                "actor_id": requested_by,
                "action": "acceptance_failure",
                "target_type": "execution_intent",
                "target_id": intent.intent_id,
                "reason": "order_submit_failed",
                "before_state": "SUBMITTED",
                "after_state": "FAILED",
                "correlation_id": correlation_id,
            },
        )
        return {
            "mode": mode,
            "status": "FAILED",
            "reason_code": "order_submit_failed",
            "intent_id": intent.intent_id,
            "exchange_evidence": submit,
            "reconcile_result": {},
            "artifact_manifest": acceptance_artifact,
            "timeline": get_intent_timeline(db, intent_id=intent.intent_id),
        }

    order_id = str((((submit.get("data") or {}).get("result") or {}).get("orderId") or "")).strip()
    _append_intent_event(
        db,
        intent_id=intent.intent_id,
        event_type="EXECUTION_ORDER_SUBMITTED",
        event_status="SUBMITTED",
        external_order_id=order_id,
        payload={"acceptance_run_id": acceptance_run_id, "mode": mode, "submit": submit, **envelope.as_dict()},
    )

    realtime = _bybit_private_get(
        db,
        "/v5/order/realtime",
        {"category": "linear", "symbol": symbol, "orderId": order_id},
    )
    status = "ACKED"
    if realtime.get("ok"):
        rows = (((realtime.get("data") or {}).get("result") or {}).get("list") or [])
        if rows:
            order_status = _normalize_state(rows[0].get("orderStatus"))
            if order_status in {"FILLED"}:
                status = "FILLED"
            elif order_status in {"PARTIALLY_FILLED", "PARTIALLYFILLED"}:
                status = "PARTIALLY_FILLED"
            else:
                status = "ACKED"
    else:
        status = "FAILED"

    _append_intent_event(
        db,
        intent_id=intent.intent_id,
        event_type="EXECUTION_ORDER_ACKED" if status != "FAILED" else "EXECUTION_ORDER_FINALIZED",
        event_status=status,
        external_order_id=order_id,
        payload={"acceptance_run_id": acceptance_run_id, "mode": mode, "realtime": realtime, **envelope.as_dict()},
    )
    intent.status = status
    db.commit()

    reconcile = reconcile_intent_with_exchange(
        db,
        intent_id=intent.intent_id,
        actor_type="system",
        actor_id=requested_by,
        reason=f"acceptance_{mode}",
    )
    artifact = create_execution_attempt_artifact(
        db,
        intent_id=intent.intent_id,
        request_id=envelope.request_id,
        session_id=envelope.session_id,
        execution_id=envelope.execution_id,
    )
    acceptance_payload = {
        "schema_version": "1.0",
        "proof_type": "execution_testnet_acceptance_step",
        "acceptance_run_id": acceptance_run_id,
        "mode": mode,
        "correlation_id": correlation_id,
        "intent_id": intent.intent_id,
        "exchange_evidence": {"submit": submit, "realtime": realtime},
        "reconcile_result": reconcile,
        "artifact": artifact,
    }
    acceptance_artifact = _record_acceptance_artifact(acceptance_payload)
    create_audit_log(
        db,
        action="execution_testnet_acceptance_step_completed",
        entity_type="execution_intent",
        entity_id=intent.intent_id,
        actor_user_id=requested_by,
        actor_role="system",
        severity="info" if status != "FAILED" else "warning",
        details={
            "actor_type": "system",
            "actor_id": requested_by,
            "action": f"acceptance_{mode}",
            "target_type": "execution_intent",
            "target_id": intent.intent_id,
            "reason": f"acceptance_{mode}",
            "before_state": "SUBMITTED",
            "after_state": status,
            "correlation_id": correlation_id,
        },
    )
    return {
        "mode": mode,
        "status": "PASS" if status in {"ACKED", "PARTIALLY_FILLED", "FILLED"} else "FAILED",
        "reason_code": "acceptance_success" if status in {"ACKED", "PARTIALLY_FILLED", "FILLED"} else "acceptance_ack_missing",
        "intent_id": intent.intent_id,
        "exchange_evidence": {"submit": submit, "realtime": realtime},
        "reconcile_result": reconcile,
        "artifact_manifest": acceptance_artifact,
        "timeline": get_intent_timeline(db, intent_id=intent.intent_id),
    }


def run_testnet_acceptance(
    db: Session,
    *,
    symbol: str = "BTCUSDT",
    qty: float = 0.001,
    requested_by: str,
) -> dict:
    acceptance_run_id = f"acceptance-{uuid.uuid4().hex[:16]}"
    correlation_id = f"corr-acceptance-{uuid.uuid4().hex[:16]}"
    started_at = _utcnow().isoformat()

    gate = evaluate_execution_safety_gate(
        db,
        force_refresh=True,
        correlation_id=correlation_id,
        request_id=f"req-{acceptance_run_id}",
        session_id=f"session-{acceptance_run_id}",
    )
    if str(gate.get("state") or "").upper() == "BLOCKED":
        blocked_payload = {
            "schema_version": "1.0",
            "proof_type": "execution_testnet_acceptance_blocked",
            "acceptance_run_id": acceptance_run_id,
            "correlation_id": correlation_id,
            "symbol": symbol,
            "qty": qty,
            "started_at": started_at,
            "finished_at": _utcnow().isoformat(),
            "gate": gate,
            "reason_code": "acceptance_blocked_by_hard_gate",
        }
        run_artifact = _record_acceptance_artifact(blocked_payload)
        create_audit_log(
            db,
            action="execution_testnet_acceptance_blocked",
            entity_type="execution_acceptance_run",
            entity_id=acceptance_run_id,
            actor_user_id=requested_by,
            actor_role="system",
            severity="warning",
            details={
                "actor_type": "system",
                "actor_id": requested_by,
                "action": "acceptance_blocked",
                "target_type": "execution_acceptance_run",
                "target_id": acceptance_run_id,
                "reason": "hard_gate_block",
                "before_state": "STARTED",
                "after_state": "BLOCKED",
                "correlation_id": correlation_id,
                "blockers": gate.get("blockers") or [],
            },
        )
        return {
            "acceptance_run_id": acceptance_run_id,
            "correlation_id": correlation_id,
            "final_verdict": "BLOCKED",
            "reason_code": "acceptance_blocked_by_hard_gate",
            "gate": gate,
            "artefact_manifest": {"run": run_artifact},
            "audit_record": {"action": "execution_testnet_acceptance_blocked", "entity_id": acceptance_run_id},
        }

    ack_result = _run_single_acceptance_mode(
        db,
        acceptance_run_id=acceptance_run_id,
        correlation_id=correlation_id,
        symbol=symbol,
        qty=qty,
        mode="ack_mode",
        requested_by=requested_by,
    )
    fill_result = None
    if ack_result.get("status") == "PASS":
        fill_result = _run_single_acceptance_mode(
            db,
            acceptance_run_id=acceptance_run_id,
            correlation_id=correlation_id,
            symbol=symbol,
            qty=qty,
            mode="fill_mode",
            requested_by=requested_by,
        )

    final_status = "PASS" if ack_result.get("status") == "PASS" and (fill_result and fill_result.get("status") == "PASS") else "FAILED"
    summary_payload = {
        "schema_version": "1.0",
        "proof_type": "execution_testnet_acceptance_run_summary",
        "acceptance_run_id": acceptance_run_id,
        "correlation_id": correlation_id,
        "symbol": symbol,
        "qty": qty,
        "started_at": started_at,
        "finished_at": _utcnow().isoformat(),
        "steps": {
            "ack_mode": ack_result,
            "fill_mode": fill_result,
        },
        "final_verdict": final_status,
    }
    run_artifact = _record_acceptance_artifact(summary_payload)
    create_audit_log(
        db,
        action="execution_testnet_acceptance_run_completed",
        entity_type="execution_acceptance_run",
        entity_id=acceptance_run_id,
        actor_user_id=requested_by,
        actor_role="system",
        severity="info" if final_status == "PASS" else "warning",
        details={
            "actor_type": "system",
            "actor_id": requested_by,
            "action": "acceptance_run",
            "target_type": "execution_acceptance_run",
            "target_id": acceptance_run_id,
            "reason": "testnet_acceptance",
            "before_state": "STARTED",
            "after_state": final_status,
            "correlation_id": correlation_id,
        },
    )
    return {
        "acceptance_run_id": acceptance_run_id,
        "correlation_id": correlation_id,
        "final_verdict": final_status,
        "acceptance_summary": {
            "symbol": symbol,
            "qty": qty,
            "ack_mode": ack_result.get("status"),
            "fill_mode": fill_result.get("status") if fill_result else "SKIPPED",
        },
        "intent_timeline": {
            "ack_mode": ack_result.get("timeline"),
            "fill_mode": fill_result.get("timeline") if fill_result else None,
        },
        "exchange_evidence": {
            "ack_mode": ack_result.get("exchange_evidence"),
            "fill_mode": fill_result.get("exchange_evidence") if fill_result else None,
        },
        "reconcile_result": {
            "ack_mode": ack_result.get("reconcile_result"),
            "fill_mode": fill_result.get("reconcile_result") if fill_result else None,
        },
        "artefact_manifest": {
            "ack_mode": ack_result.get("artifact_manifest"),
            "fill_mode": fill_result.get("artifact_manifest") if fill_result else None,
            "run": run_artifact,
        },
        "audit_record": {
            "action": "execution_testnet_acceptance_run_completed",
            "entity_id": acceptance_run_id,
        },
    }


def _acceptance_manifest_items(limit: int = 50) -> list[dict]:
    manifest = Path("/app/artifacts/manifests/execution_testnet_acceptance_manifest.jsonl")
    if not manifest.exists():
        return []
    rows: list[dict] = []
    with manifest.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return rows[:limit]


def get_latest_testnet_acceptance() -> dict:
    items = _acceptance_manifest_items(limit=1)
    return {"latest": items[0] if items else None}


def get_testnet_acceptance_history(limit: int = 50) -> dict:
    return {"items": _acceptance_manifest_items(limit=limit), "total": len(_acceptance_manifest_items(limit=5000))}


def _select_bulk_targets(db: Session, *, action: str, selection_mode: str, intent_ids: list[str], quarantine_ids: list[str], filters: dict) -> list[dict]:
    mode = str(selection_mode or "explicit_ids").strip().lower()
    targets: list[dict] = []

    if mode == "explicit_ids":
        for intent_id in intent_ids:
            targets.append({"target_type": "intent", "target_id": intent_id})
        for quarantine_id in quarantine_ids:
            targets.append({"target_type": "quarantine", "target_id": quarantine_id})
        return targets

    if mode == "by_state":
        states = {str(item).strip().upper() for item in (filters.get("states") or [])}
        rows = db.query(ExecutionIntent).all()
        for row in rows:
            if _normalize_state(row.status) in states:
                targets.append({"target_type": "intent", "target_id": row.intent_id})
        return targets

    if mode == "by_failure_stage":
        stages = {str(item).strip() for item in (filters.get("failure_stages") or [])}
        rows = db.query(FailedEvent).all()
        for row in rows:
            payload = dict(row.payload or {})
            stage = payload.get("failure_stage") or payload.get("state") or row.event_type
            if stage in stages:
                targets.append({"target_type": "quarantine", "target_id": row.id})
        return targets

    if mode == "by_age_window":
        minutes = _safe_int(filters.get("age_minutes"), 30)
        cutoff = _utcnow() - timedelta(minutes=max(minutes, 1))
        for row in db.query(ExecutionIntent).all():
            created_at = _as_utc(row.created_at)
            if created_at and created_at <= cutoff:
                targets.append({"target_type": "intent", "target_id": row.intent_id})
        return targets

    if mode == "by_reason_code":
        reasons = {str(item).strip() for item in (filters.get("reason_codes") or [])}
        for row in db.query(FailedEvent).all():
            payload = dict(row.payload or {})
            code = payload.get("reason_code") or row.dead_letter_reason
            if code in reasons:
                targets.append({"target_type": "quarantine", "target_id": row.id})
        return targets

    if mode == "by_retry_exhaustion":
        exhausted = bool(filters.get("exhausted", True))
        for row in db.query(FailedEvent).all():
            is_exhausted = int(row.retry_count or 0) >= int(row.max_retry or 0)
            if is_exhausted == exhausted:
                targets.append({"target_type": "quarantine", "target_id": row.id})
        return targets

    if mode == "by_environment":
        env = str(filters.get("environment") or "").lower().strip()
        for row in db.query(ExecutionIntent).all():
            if str((row.metadata or {}).get("environment") or "testnet").lower() == env:
                targets.append({"target_type": "intent", "target_id": row.intent_id})
        return targets

    return targets


def run_bulk_recovery(
    db: Session,
    *,
    action: str,
    selection_mode: str,
    intent_ids: list[str],
    quarantine_ids: list[str],
    filters: dict,
    reason: str,
    requested_by: str,
) -> dict:
    if action not in {"bulk_retry", "bulk_cancel", "bulk_reconcile"}:
        raise ValueError("invalid_bulk_action")

    targets = _select_bulk_targets(
        db,
        action=action,
        selection_mode=selection_mode,
        intent_ids=intent_ids,
        quarantine_ids=quarantine_ids,
        filters=filters,
    )
    results: list[dict] = []

    for item in targets:
        target_type = item["target_type"]
        target_id = item["target_id"]
        before_state = None
        after_state = None
        error = None
        result_payload = None

        try:
            if target_type == "intent":
                intent = db.query(ExecutionIntent).filter(ExecutionIntent.intent_id == target_id).first()
                if intent is None:
                    raise ValueError("intent_not_found")
                before_state = _normalize_state(intent.status)

                if action == "bulk_retry":
                    if before_state not in {"CREATED", "SUBMITTED", "ACKED", "PARTIALLY_FILLED", "RECONCILING"}:
                        raise ValueError("non_retryable_intent")
                    result_payload = apply_intent_recovery_action(
                        db,
                        intent_id=target_id,
                        action="retry",
                        actor_user_id=requested_by,
                        actor_role="user",
                    )
                elif action == "bulk_cancel":
                    if before_state in {"FILLED", "FAILED", "CANCELED", "RECONCILED"}:
                        raise ValueError("non_cancelable_intent")
                    latest_order_event = (
                        db.query(ExecutionIntentEvent)
                        .filter(ExecutionIntentEvent.intent_id == target_id)
                        .order_by(ExecutionIntentEvent.created_at.desc())
                        .first()
                    )
                    latest_order_id = str((latest_order_event.external_order_id if latest_order_event else "") or "").strip()
                    if latest_order_id:
                        cancel_resp = _bybit_private_post(
                            db,
                            "/v5/order/cancel",
                            {
                                "category": "linear",
                                "symbol": intent.symbol,
                                "orderId": latest_order_id,
                            },
                        )
                        if not cancel_resp.get("ok"):
                            raise ValueError("exchange_cancel_failed")
                    result_payload = apply_intent_recovery_action(
                        db,
                        intent_id=target_id,
                        action="cancel",
                        actor_user_id=requested_by,
                        actor_role="user",
                    )
                else:
                    result_payload = reconcile_intent_with_exchange(
                        db,
                        intent_id=target_id,
                        actor_type="user",
                        actor_id=requested_by,
                        reason=reason or "bulk_reconcile",
                    )

                db.refresh(intent)
                after_state = _normalize_state(intent.status)
            else:
                before = get_quarantine_detail(db, quarantine_id=target_id)
                before_state = str(before.get("status"))
                if action == "bulk_reconcile":
                    raise ValueError("bulk_reconcile_not_supported_for_quarantine")
                q_action = "replay" if action == "bulk_retry" else "manual_resolve"
                result_payload = apply_execution_safety_quarantine_action(
                    db,
                    quarantine_id=target_id,
                    action=q_action,
                    actor_user_id=requested_by,
                    actor_role="user",
                )
                after_state = str(result_payload.get("status"))
        except Exception as exc:
            error = str(exc)

        item_result = {
            "target_type": target_type,
            "target_id": target_id,
            "before_state": before_state,
            "attempted_action": action,
            "result": "success" if error is None else "failed",
            "error": error,
            "after_state": after_state,
            "payload": result_payload,
        }
        results.append(item_result)

        create_audit_log(
            db,
            action="execution_bulk_recovery_item",
            entity_type=target_type,
            entity_id=target_id,
            actor_user_id=requested_by,
            actor_role="user",
            severity="warning" if error else "info",
            details={
                "actor_type": "user",
                "actor_id": requested_by,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "reason": reason,
                "before_state": before_state,
                "after_state": after_state,
                "correlation_id": ((result_payload or {}).get("correlation_id") if isinstance(result_payload, dict) else None),
                "error": error,
            },
        )

    return {
        "action": action,
        "selection_mode": selection_mode,
        "requested_by": requested_by,
        "reason": reason,
        "total": len(results),
        "success_count": len([row for row in results if row["result"] == "success"]),
        "failed_count": len([row for row in results if row["result"] == "failed"]),
        "items": results,
    }
