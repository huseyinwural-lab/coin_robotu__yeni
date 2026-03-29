from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from models import AuditLog, ExecutionIntent, ExecutionIntentEvent, FailedEvent, LiveActivationConfig
from services.audit_service import create_audit_log
from services.execution_safety_core_service import (
    apply_runtime_quarantine_action,
    batch_recover_stuck_intents,
    build_execution_incident_package,
    get_gate_failure_trends,
    get_manual_intervention_audit_trail,
    get_order_reconciliation_summary,
    get_execution_safety_gate,
    persist_execution_safety_artifact,
    run_bybit_testnet_order_smoke,
)
from services.failed_event_service import upsert_failed_event
from services.runtime_event_bus_service import publish_runtime_event


SAFETY_HARD_BLOCKERS = {
    "release_gate_blocked",
    "permission_check_failed",
    "balance_unverified",
    "execution_path_closed",
    "testnet_disabled_while_live_unvalidated",
    "stale_market_data",
    "stale_exchange_data",
    "missing_required_proof",
    "critical_dependency_unhealthy",
}
CANONICAL_INTENT_STATES = {
    "CREATED",
    "SUBMITTED",
    "ACKED",
    "PARTIALLY_FILLED",
    "FILLED",
    "FAILED",
    "CANCELED",
    "RECONCILING",
    "RECONCILED",
}
INTENT_TRANSITIONS = {
    "CREATED": {"SUBMITTED", "FAILED", "CANCELED"},
    "SUBMITTED": {"ACKED", "FAILED", "CANCELED"},
    "ACKED": {"PARTIALLY_FILLED", "FILLED", "FAILED", "CANCELED", "RECONCILING"},
    "PARTIALLY_FILLED": {"PARTIALLY_FILLED", "FILLED", "FAILED", "CANCELED", "RECONCILING"},
    "FILLED": {"RECONCILING"},
    "FAILED": set(),
    "CANCELED": set(),
    "RECONCILING": {"RECONCILED", "FAILED"},
    "RECONCILED": set(),
}
STATE_TIMEOUT_ENV = {
    "CREATED": "EXECUTION_INTENT_CREATED_TIMEOUT_SEC",
    "SUBMITTED": "EXECUTION_INTENT_SUBMITTED_TIMEOUT_SEC",
    "ACKED": "EXECUTION_INTENT_ACKED_TIMEOUT_SEC",
    "PARTIALLY_FILLED": "EXECUTION_INTENT_PARTIALLY_FILLED_TIMEOUT_SEC",
    "RECONCILING": "EXECUTION_INTENT_RECONCILING_TIMEOUT_SEC",
}
STATE_TIMEOUT_DEFAULT = {
    "CREATED": 60,
    "SUBMITTED": 120,
    "ACKED": 300,
    "PARTIALLY_FILLED": 300,
    "RECONCILING": 180,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _canonical_intent_state(value: Any) -> str:
    raw = _normalize_code(value)
    if raw in {"", "PENDING"}:
        return "CREATED"
    if raw == "CANCELLED":
        return "CANCELED"
    if raw in CANONICAL_INTENT_STATES:
        return raw
    return "CREATED"


def _default_environment_policy() -> dict:
    now = _utcnow().isoformat()
    return {
        "testnet": {
            "enable_flag": True,
            "validation_status": "UNVERIFIED",
            "last_verified_at": None,
            "verification_evidence": {},
            "path_open": False,
            "updated_at": now,
        },
        "staging": {
            "enable_flag": True,
            "validation_status": "UNVERIFIED",
            "last_verified_at": None,
            "verification_evidence": {},
            "path_open": False,
            "updated_at": now,
        },
        "live": {
            "enable_flag": False,
            "validation_status": "UNVERIFIED",
            "last_verified_at": None,
            "verification_evidence": {},
            "path_open": False,
            "updated_at": now,
        },
    }


def _get_or_create_environment_policy(db: Session) -> tuple[LiveActivationConfig, dict]:
    row = db.query(LiveActivationConfig).filter(LiveActivationConfig.id == "global").first()
    if row is None:
        row = LiveActivationConfig(id="global")
        db.add(row)
        db.commit()
        db.refresh(row)

    policy = dict(getattr(row, "environment_policy", {}) or {})
    if not policy:
        policy = _default_environment_policy()
        row.environment_policy = policy
        row.updated_at = _utcnow()
        db.commit()
        db.refresh(row)
    for env_name, env_payload in _default_environment_policy().items():
        if env_name not in policy:
            policy[env_name] = env_payload
        else:
            for key, value in env_payload.items():
                if key not in policy[env_name]:
                    policy[env_name][key] = value
    return row, policy


def get_unified_environment_policy(db: Session) -> dict:
    row, policy = _get_or_create_environment_policy(db)
    return {
        "policy_id": row.id,
        "updated_at": _as_utc(row.updated_at).isoformat() if _as_utc(row.updated_at) else None,
        "environments": policy,
    }


def update_unified_environment_policy(
    db: Session,
    *,
    environment: str,
    enable_flag: bool,
    validation_status: str,
    path_open: bool,
    verification_evidence: dict,
    actor_user_id: str,
    actor_role: str,
) -> dict:
    normalized_env = str(environment or "").strip().lower()
    if normalized_env not in {"testnet", "staging", "live"}:
        raise ValueError("invalid_environment")

    row, policy = _get_or_create_environment_policy(db)
    old_payload = dict(policy.get(normalized_env) or {})
    policy[normalized_env] = {
        "enable_flag": bool(enable_flag),
        "validation_status": str(validation_status or "UNVERIFIED").strip().upper(),
        "last_verified_at": _utcnow().isoformat(),
        "verification_evidence": dict(verification_evidence or {}),
        "path_open": bool(path_open),
        "updated_at": _utcnow().isoformat(),
    }
    row.environment_policy = policy
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="execution_safety_environment_policy_updated",
        entity_type="live_activation_config",
        entity_id=row.id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning" if normalized_env == "live" else "info",
        details={
            "environment": normalized_env,
            "previous": old_payload,
            "current": policy[normalized_env],
        },
    )
    return get_unified_environment_policy(db)


def _map_blockers(
    *,
    base_gate: dict,
    bybit_smoke: dict,
    policy: dict,
    config_row: LiveActivationConfig,
    correlation_coverage_ok: bool,
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    if (base_gate.get("gate_state") or "").upper() == "BLOCKED" or (base_gate.get("hard_blockers") or []):
        blockers.append("release_gate_blocked")

    if not bool(getattr(config_row, "trading_permission_ready", False)):
        blockers.append("permission_check_failed")

    reason_codes = [_normalize_code(code) for code in (base_gate.get("validator_reason_codes") or [])]
    if any("BALANCE" in code for code in reason_codes):
        blockers.append("balance_unverified")

    if not correlation_coverage_ok:
        blockers.append("missing_required_proof")

    live_policy = dict((policy.get("live") or {}))
    testnet_policy = dict((policy.get("testnet") or {}))
    if not bool(live_policy.get("path_open", False)):
        blockers.append("execution_path_closed")
    if bool(live_policy.get("path_open", False)) and (
        not bool(testnet_policy.get("enable_flag", False))
        or str(testnet_policy.get("validation_status") or "").upper() != "VALIDATED"
    ):
        blockers.append("testnet_disabled_while_live_unvalidated")

    if any(code in {"MARKET_DATA_MISSING", "MARKET_DATA_STALE"} for code in reason_codes):
        blockers.append("stale_market_data")

    bybit_status = _normalize_code(bybit_smoke.get("status"))
    if bybit_status != "PASS":
        blockers.append("stale_exchange_data")

    artifact = dict(base_gate.get("artifact") or {})
    if not artifact.get("local_path"):
        blockers.append("missing_required_proof")
    if str(artifact.get("status") or "") not in {"LOCAL_ONLY", "S3_UPLOADED"}:
        blockers.append("critical_dependency_unhealthy")

    if bool(getattr(config_row, "kill_switch_enabled", False)):
        blockers.append("critical_dependency_unhealthy")

    if bybit_status == "PASS" and str(base_gate.get("gate_state") or "").upper() in {"DEGRADED", "WARNING"}:
        warnings.append("exchange_ready_but_readiness_degraded")
    if (base_gate.get("soft_warnings") or []):
        warnings.extend([str(item).lower() for item in (base_gate.get("soft_warnings") or [])])

    unique_blockers = sorted({item for item in blockers if item in SAFETY_HARD_BLOCKERS})
    unique_warnings = sorted({item for item in warnings if item})
    return unique_blockers, unique_warnings


def _has_correlation_spine_for_recent_intents(db: Session, *, limit: int = 25) -> bool:
    intents = db.query(ExecutionIntent).order_by(ExecutionIntent.created_at.desc()).limit(limit).all()
    if not intents:
        return True
    for intent in intents:
        if not str(intent.correlation_id or "").strip():
            return False
        events = (
            db.query(ExecutionIntentEvent)
            .filter(ExecutionIntentEvent.intent_id == intent.intent_id)
            .order_by(ExecutionIntentEvent.created_at.asc())
            .limit(5)
            .all()
        )
        for event in events:
            payload = dict(event.payload or {})
            request_id = str(payload.get("request_id") or "").strip()
            session_id = str(payload.get("session_id") or "").strip()
            execution_id = str(payload.get("execution_id") or "").strip()
            if not all([request_id, session_id, execution_id]):
                return False
    return True


def evaluate_execution_safety_gate(
    db: Session,
    *,
    force_refresh: bool = False,
    user_id: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
    correlation_id: str | None = None,
) -> dict:
    gate = get_execution_safety_gate(db, user_id=user_id, force_refresh=force_refresh)
    _, policy = _get_or_create_environment_policy(db)
    config_row = db.query(LiveActivationConfig).filter(LiveActivationConfig.id == "global").first()
    bybit_smoke = run_bybit_testnet_order_smoke(db, force_refresh=force_refresh)

    correlation_ok = _has_correlation_spine_for_recent_intents(db, limit=20)
    blockers, warnings = _map_blockers(
        base_gate=gate,
        bybit_smoke=bybit_smoke,
        policy=policy,
        config_row=config_row or LiveActivationConfig(id="global"),
        correlation_coverage_ok=correlation_ok,
    )

    score = float(gate.get("readiness_score") or 0.0)
    state = "READY" if score >= 85 else "DEGRADED"
    if blockers:
        state = "BLOCKED"

    cid = str(correlation_id or gate.get("correlation_id") or uuid.uuid4())
    payload = {
        "state": state,
        "score": round(score, 2),
        "blockers": blockers,
        "warnings": warnings,
        "evaluated_at": _utcnow().isoformat(),
        "correlation_id": cid,
        "request_id": str(request_id or cid),
        "session_id": str(session_id or "execution-safety-session"),
        "execution_authority": "ALLOW" if state in {"READY", "DEGRADED"} and not blockers else "DENY",
        "environment_policy": policy,
        "legacy_gate": gate,
    }
    return payload


def _intent_state_from_event(current_state: str, event: ExecutionIntentEvent) -> tuple[str, str | None]:
    event_type = _normalize_code(event.event_type)
    event_status = _canonical_intent_state(event.event_status)
    target = current_state

    if event_type in {"EXECUTION_ORDER_SUBMISSION_REQUESTED", "EXECUTION_ORDER_SUBMITTED"}:
        target = "SUBMITTED"
    elif event_type in {"EXECUTION_ORDER_ACKED", "EXECUTION_ORDER_ACCEPTED"}:
        target = "ACKED"
    elif event_type in {"EXECUTION_ORDER_PARTIALLY_FILLED"} or event_status == "PARTIALLY_FILLED":
        target = "PARTIALLY_FILLED"
    elif event_type in {"EXECUTION_ORDER_FILLED", "EXECUTION_ORDER_FINALIZED"} or event_status == "FILLED":
        target = "FILLED"
    elif event_type in {"EXECUTION_RECONCILE_STARTED"} or event_status == "RECONCILING":
        target = "RECONCILING"
    elif event_type in {"EXECUTION_RECONCILED"} or event_status == "RECONCILED":
        target = "RECONCILED"
    elif event_status in {"FAILED"}:
        target = "FAILED"
    elif event_status in {"CANCELED"}:
        target = "CANCELED"

    allowed = INTENT_TRANSITIONS.get(current_state, set())
    if target != current_state and target not in allowed:
        return current_state, f"invalid_transition:{current_state}->{target}"
    return target, None


def _state_timeouts() -> dict[str, int]:
    import os

    result: dict[str, int] = {}
    for state, env_key in STATE_TIMEOUT_ENV.items():
        result[state] = _safe_int(os.environ.get(env_key), STATE_TIMEOUT_DEFAULT[state])
    return result


def _recommended_recovery_action(state: str) -> str:
    if state in {"CREATED", "SUBMITTED"}:
        return "retry"
    if state in {"ACKED", "PARTIALLY_FILLED"}:
        return "reconcile"
    if state in {"RECONCILING"}:
        return "reconcile"
    return "quarantine"


def get_execution_safety_intents(
    db: Session,
    *,
    limit: int = 100,
    include_events: bool = False,
    auto_quarantine_stuck: bool = True,
) -> dict:
    capped_limit = min(max(int(limit or 1), 1), 300)
    intents = db.query(ExecutionIntent).order_by(ExecutionIntent.created_at.desc()).limit(capped_limit).all()
    timeouts = _state_timeouts()
    now = _utcnow()

    items: list[dict] = []
    state_counts = {state: 0 for state in CANONICAL_INTENT_STATES}
    stuck_count = 0

    for intent in intents:
        events = (
            db.query(ExecutionIntentEvent)
            .filter(ExecutionIntentEvent.intent_id == intent.intent_id)
            .order_by(ExecutionIntentEvent.created_at.asc())
            .all()
        )
        state = _canonical_intent_state(intent.status)
        state_path = [state]
        timeline: list[dict] = []
        violations: list[str] = []
        last_at = _as_utc(intent.created_at) or now

        for event in events:
            next_state, violation = _intent_state_from_event(state, event)
            timeline.append(
                {
                    "event_type": event.event_type,
                    "event_status": event.event_status,
                    "from_state": state,
                    "to_state": next_state,
                    "created_at": _as_utc(event.created_at).isoformat() if _as_utc(event.created_at) else None,
                }
            )
            if violation:
                violations.append(violation)
            if next_state != state:
                state = next_state
                state_path.append(state)
            last_at = _as_utc(event.created_at) or last_at

        state_counts[state] = state_counts.get(state, 0) + 1
        timeout_sec = timeouts.get(state)
        age_seconds = max((now - last_at).total_seconds(), 0)
        is_stuck = timeout_sec is not None and age_seconds > timeout_sec
        recovery_action = _recommended_recovery_action(state) if is_stuck else None

        if is_stuck:
            stuck_count += 1
            if auto_quarantine_stuck:
                upsert_failed_event(
                    db,
                    event_type="execution.intent.stuck",
                    entity_type="execution_intent",
                    entity_id=intent.intent_id,
                    payload={
                        "intent_id": intent.intent_id,
                        "correlation_id": intent.correlation_id,
                        "state": state,
                        "reason_code": "intent_state_timeout",
                        "failure_stage": state,
                    },
                    error_message="intent_state_timeout",
                    status="quarantined",
                    retry_count=0,
                    max_retry=5,
                    correlation_id=intent.correlation_id,
                    next_retry_at=_utcnow() + timedelta(seconds=20),
                )

        row = {
            "intent_id": intent.intent_id,
            "strategy_id": intent.strategy_id,
            "symbol": intent.symbol,
            "state": state,
            "state_path": state_path,
            "is_stuck": is_stuck,
            "recommended_recovery": recovery_action,
            "age_seconds": round(age_seconds, 2),
            "timeout_seconds": timeout_sec,
            "created_at": _as_utc(intent.created_at).isoformat() if _as_utc(intent.created_at) else None,
            "correlation_id": intent.correlation_id,
            "violations": violations,
            "timeline": timeline,
        }
        if include_events:
            row["events"] = [
                {
                    "id": event.id,
                    "event_type": event.event_type,
                    "event_status": event.event_status,
                    "external_order_id": event.external_order_id,
                    "payload": event.payload,
                    "created_at": _as_utc(event.created_at).isoformat() if _as_utc(event.created_at) else None,
                }
                for event in events
            ]
        items.append(row)

    return {
        "total": len(items),
        "stuck_count": stuck_count,
        "state_counts": state_counts,
        "timeouts": timeouts,
        "items": items,
    }


def get_execution_safety_quarantine(db: Session, *, limit: int = 200) -> dict:
    capped_limit = min(max(int(limit or 1), 1), 500)
    rows = (
        db.query(FailedEvent)
        .filter(FailedEvent.entity_type.in_(["runtime_event", "execution_intent"]))
        .order_by(FailedEvent.updated_at.desc())
        .limit(capped_limit)
        .all()
    )
    items: list[dict] = []
    for row in rows:
        payload = dict(row.payload or {})
        items.append(
            {
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
                "entity_id": row.entity_id,
            }
        )
    return {"total": len(items), "items": items}


def apply_execution_safety_quarantine_action(
    db: Session,
    *,
    quarantine_id: str,
    action: str,
    actor_user_id: str,
    actor_role: str,
) -> dict:
    action_map = {
        "replay": "replay",
        "reprocess": "replay",
        "manual_resolve": "dismiss",
        "mark_failed": "mark_failed",
        "dismiss": "dismiss",
    }
    mapped = action_map.get(str(action or "").strip().lower())
    if mapped is None:
        raise ValueError("invalid_action")
    result = apply_runtime_quarantine_action(
        db,
        event_id=quarantine_id,
        action=mapped,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )
    result["requested_action"] = action
    return result


def create_execution_attempt_artifact(
    db: Session,
    *,
    intent_id: str,
    execution_id: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
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
    failures = (
        db.query(FailedEvent)
        .filter(FailedEvent.entity_type == "execution_intent", FailedEvent.entity_id == intent_id)
        .order_by(FailedEvent.created_at.asc())
        .all()
    )

    order_events = [
        {
            "event_type": event.event_type,
            "event_status": event.event_status,
            "external_order_id": event.external_order_id,
            "payload": event.payload,
            "created_at": _as_utc(event.created_at).isoformat() if _as_utc(event.created_at) else None,
        }
        for event in events
    ]
    ack_fill = [row for row in order_events if _normalize_code(row.get("event_status")) in {"ACKED", "PARTIALLY_FILLED", "FILLED"}]
    reconcile_events = [
        row
        for row in order_events
        if _normalize_code(row.get("event_type")) in {"EXECUTION_RECONCILE_STARTED", "EXECUTION_RECONCILED"}
        or _normalize_code(row.get("event_status")) in {"RECONCILING", "RECONCILED"}
    ]

    payload = {
        "schema_version": "1.0",
        "proof_type": "execution_attempt_artifact",
        "created_at": _utcnow().isoformat(),
        "signal_snapshot": {
            "symbol": intent.symbol,
            "side": intent.side,
            "order_type": intent.order_type,
            "quantity": intent.quantity,
            "price_reference": intent.price_reference,
        },
        "decision_snapshot": {
            "decision_hash": intent.decision_hash,
            "context_hash": intent.context_hash,
            "intent_hash": intent.intent_hash,
            "status": intent.status,
        },
        "risk_snapshot": {"strategy_id": intent.strategy_id, "strategy_version_id": intent.strategy_version_id},
        "order_request": order_events[0] if order_events else {},
        "order_response": order_events[-1] if order_events else {},
        "exchange_ack_or_fill_evidence": ack_fill,
        "reconcile_result": reconcile_events[-1] if reconcile_events else {},
        "failure_trace": [
            {
                "quarantine_id": row.id,
                "reason": row.error_message,
                "failure_class": row.failure_class,
                "created_at": _as_utc(row.created_at).isoformat() if _as_utc(row.created_at) else None,
            }
            for row in failures
        ],
        "retry_trace": [
            {
                "quarantine_id": row.id,
                "retry_count": row.retry_count,
                "status": row.status,
                "next_retry_at": _as_utc(row.next_retry_at).isoformat() if _as_utc(row.next_retry_at) else None,
            }
            for row in failures
        ],
        "correlation_spine": {
            "request_id": str(request_id or ((order_events[0].get("payload") or {}).get("request_id") if order_events else "")),
            "intent_id": intent.intent_id,
            "order_id": str((order_events[-1].get("external_order_id") if order_events else "") or ""),
            "execution_id": str(execution_id or ((order_events[-1].get("payload") or {}).get("execution_id") if order_events else "")),
            "session_id": str(session_id or ((order_events[0].get("payload") or {}).get("session_id") if order_events else "")),
            "correlation_id": intent.correlation_id,
        },
    }

    artifact = persist_execution_safety_artifact(payload)
    return {
        "intent_id": intent.intent_id,
        "artifact": artifact,
        "component_counts": {
            "events": len(order_events),
            "ack_fill_evidence": len(ack_fill),
            "reconcile_events": len(reconcile_events),
            "failure_trace": len(failures),
        },
    }


def apply_intent_recovery_action(
    db: Session,
    *,
    intent_id: str,
    action: str,
    actor_user_id: str,
    actor_role: str,
) -> dict:
    intent = db.query(ExecutionIntent).filter(ExecutionIntent.intent_id == intent_id).first()
    if intent is None:
        raise ValueError("intent_not_found")

    normalized = str(action or "").strip().lower()
    if normalized not in {"retry", "cancel", "reconcile", "quarantine"}:
        raise ValueError("invalid_action")

    if normalized == "retry":
        publish_runtime_event(
            event_type="execution.order.submission_requested",
            payload={"intent_id": intent.intent_id, "source": "execution_safety_recovery_retry"},
            correlation_id=intent.correlation_id,
            causation_id=f"recovery::{intent.intent_id}",
            partition_key=f"intent::{intent.intent_id}",
        )
        intent.status = "SUBMITTED"
        db.add(
            ExecutionIntentEvent(
                intent_id=intent.intent_id,
                event_type="EXECUTION_RECOVERY_RETRY_REQUESTED",
                event_status="SUBMITTED",
                payload={"source": "execution_safety_recovery"},
            )
        )
    elif normalized == "cancel":
        intent.status = "CANCELED"
        db.add(
            ExecutionIntentEvent(
                intent_id=intent.intent_id,
                event_type="EXECUTION_RECOVERY_CANCEL_REQUESTED",
                event_status="CANCELED",
                payload={"source": "execution_safety_recovery"},
            )
        )
    elif normalized == "reconcile":
        intent.status = "RECONCILING"
        db.add(
            ExecutionIntentEvent(
                intent_id=intent.intent_id,
                event_type="EXECUTION_RECONCILE_STARTED",
                event_status="RECONCILING",
                payload={"source": "execution_safety_recovery"},
            )
        )
        db.add(
            ExecutionIntentEvent(
                intent_id=intent.intent_id,
                event_type="EXECUTION_RECONCILED",
                event_status="RECONCILED",
                payload={"source": "execution_safety_recovery"},
            )
        )
        intent.status = "RECONCILED"
    else:
        upsert_failed_event(
            db,
            event_type="execution.intent.manual_quarantine",
            entity_type="execution_intent",
            entity_id=intent.intent_id,
            payload={
                "intent_id": intent.intent_id,
                "correlation_id": intent.correlation_id,
                "reason_code": "manual_quarantine",
                "failure_stage": _canonical_intent_state(intent.status),
            },
            correlation_id=intent.correlation_id,
            error_message="manual_quarantine_requested",
            status="quarantined",
            retry_count=0,
            max_retry=5,
        )

    db.commit()
    db.refresh(intent)

    create_audit_log(
        db,
        action=f"execution_intent_recovery_{normalized}",
        entity_type="execution_intent",
        entity_id=intent.intent_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        details={"action": normalized, "new_status": intent.status, "correlation_id": intent.correlation_id},
    )

    artifact = create_execution_attempt_artifact(db, intent_id=intent.intent_id)
    return {
        "intent_id": intent.intent_id,
        "status": intent.status,
        "action": normalized,
        "correlation_id": intent.correlation_id,
        "artifact": artifact,
    }


def get_execution_recovery_overview(db: Session) -> dict:
    intents = get_execution_safety_intents(db, limit=150, include_events=False, auto_quarantine_stuck=False)
    quarantine = get_execution_safety_quarantine(db, limit=150)
    recent_replays = (
        db.query(AuditLog)
        .filter(
            AuditLog.action.in_(
                [
                    "execution_quarantine_replay",
                    "execution_quarantine_dismiss",
                    "execution_quarantine_mark_failed",
                    "execution_intent_recovery_retry",
                    "execution_intent_recovery_cancel",
                    "execution_intent_recovery_reconcile",
                    "execution_intent_recovery_quarantine",
                ]
            )
        )
        .order_by(AuditLog.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "active_stuck_intents": intents.get("stuck_count"),
        "quarantined_events": quarantine.get("total"),
        "replay_history": [
            {
                "id": row.id,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "actor_user_id": row.actor_user_id,
                "created_at": _as_utc(row.created_at).isoformat() if _as_utc(row.created_at) else None,
                "details": row.details,
            }
            for row in recent_replays
        ],
    }


def get_execution_observability_snapshot(db: Session, *, user_id: str | None = None) -> dict:
    gate = evaluate_execution_safety_gate(db, user_id=user_id, force_refresh=False)
    intents = get_execution_safety_intents(db, limit=100, include_events=False, auto_quarantine_stuck=False)
    quarantine = get_execution_safety_quarantine(db, limit=100)
    recovery = get_execution_recovery_overview(db)
    return {
        "current_gate_state": gate,
        "blockers": gate.get("blockers") or [],
        "active_stuck_intents": intents.get("stuck_count"),
        "quarantined_events": quarantine.get("total"),
        "replay_history": recovery.get("replay_history") or [],
        "recent_execution_attempts": intents.get("items")[:20],
        "intent_lifecycle_timeline": [
            {"intent_id": item.get("intent_id"), "state_path": item.get("state_path"), "timeline": item.get("timeline")}
            for item in intents.get("items")[:20]
        ],
        "artifact_manifest": {
            "last_gate_artifact": ((gate.get("legacy_gate") or {}).get("artifact") or {}),
            "policy": gate.get("environment_policy") or {},
        },
    }


def get_execution_reconciliation_summary(db: Session, *, limit: int = 500) -> dict:
    return get_order_reconciliation_summary(db, limit=limit)


def get_execution_gate_trends(*, days: int = 14) -> dict:
    return get_gate_failure_trends(days=days)


def get_execution_intervention_audit(db: Session, *, limit: int = 120) -> dict:
    return get_manual_intervention_audit_trail(db, limit=limit)


def batch_execution_recovery(
    db: Session,
    *,
    action: str,
    limit: int,
    actor_user_id: str,
    actor_role: str,
) -> dict:
    action_map = {
        "retry": "replay",
        "cancel": "dismiss",
        "reconcile": "replay",
        "quarantine": "mark_failed",
    }
    mapped = action_map.get(str(action or "").strip().lower())
    if not mapped:
        raise ValueError("invalid_action")
    return batch_recover_stuck_intents(
        db,
        action=mapped,
        limit=limit,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )


def export_execution_incident_package(db: Session, *, include_events: bool = False, user_id: str | None = None) -> dict:
    return build_execution_incident_package(db, include_events=include_events, user_id=user_id)
