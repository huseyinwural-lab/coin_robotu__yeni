from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from models import AuditLog
from services.system_alert_service import create_system_alert
from services.trading_lifecycle_debugger_service import get_lifecycle_chain


def _canonical_payload(row: AuditLog) -> dict:
    return {
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "severity": str(row.severity or "").upper(),
        "environment": str(getattr(row, "environment", "test") or "test").lower(),
        "is_test_event": bool(getattr(row, "is_test_event", False)),
        "correlation_id": str((row.details or {}).get("correlation_id") or row.entity_id or ""),
        "details": row.details or {},
        "created_at": row.created_at.isoformat() if isinstance(row.created_at, datetime) else str(row.created_at),
    }


def _compute_hash(previous_hash: str, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(f"{previous_hash}|{canonical}".encode("utf-8")).hexdigest()


def verify_trace_integrity(db: Session, *, correlation_id: str, environment: str | None = None, emit_alert: bool = True) -> dict:
    normalized_correlation_id = str(correlation_id or "").strip()
    details_text = cast(AuditLog.details, String)
    query = db.query(AuditLog).filter(details_text.ilike(f"%{normalized_correlation_id}%") | (AuditLog.entity_id == normalized_correlation_id))
    if environment:
        query = query.filter(AuditLog.environment == str(environment).strip().lower())

    rows = query.order_by(AuditLog.created_at.asc()).all()
    mismatches: list[dict] = []
    previous_hash = "GENESIS"

    for row in rows:
        expected_hash = _compute_hash(previous_hash, _canonical_payload(row))
        row_prev_hash = str(getattr(row, "previous_event_hash", "") or "GENESIS")
        row_event_hash = str(getattr(row, "event_hash", "") or "")
        hash_match = row_event_hash == expected_hash
        prev_match = row_prev_hash == previous_hash

        if not hash_match or not prev_match:
            mismatches.append(
                {
                    "event_id": row.id,
                    "expected_previous_event_hash": previous_hash,
                    "stored_previous_event_hash": row_prev_hash,
                    "expected_event_hash": expected_hash,
                    "stored_event_hash": row_event_hash,
                }
            )
        previous_hash = row_event_hash or expected_hash

    tampered = len(mismatches) > 0
    result = {
        "correlation_id": normalized_correlation_id,
        "environment": environment,
        "events_checked": len(rows),
        "tampered": tampered,
        "compromised": tampered,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }

    if tampered and emit_alert:
        create_system_alert(
            db,
            alert_type="audit_tamper_detected",
            severity="CRITICAL",
            message="Audit hash chain mismatch detected",
            details=result,
            root_cause_code="AUDIT_HASH_CHAIN_MISMATCH",
            dedupe_window_seconds=300,
        )
    return result


def compare_correlation_across_environments(
    db: Session,
    *,
    correlation_id: str,
    environments: list[str],
    limit: int = 1200,
) -> dict:
    normalized_envs = [str(item or "").strip().lower() for item in environments if str(item or "").strip()]
    normalized_envs = [env for env in normalized_envs if env in {"prod", "staging", "test", "canary"}]
    if not normalized_envs:
        normalized_envs = ["prod", "staging", "test", "canary"]

    by_environment = {}
    for environment in normalized_envs:
        lifecycle = get_lifecycle_chain(db, correlation_id, limit=limit, environment=environment)
        by_environment[environment] = {
            "correlation_id": lifecycle.get("correlation_id"),
            "event_count": lifecycle.get("event_count", 0),
            "trace_incomplete": lifecycle.get("trace_incomplete"),
            "broken_chain": lifecycle.get("broken_chain"),
            "missing_critical_stages": lifecycle.get("missing_critical_stages") or [],
            "pattern_tag": lifecycle.get("pattern_tag"),
            "critical_blockers": lifecycle.get("critical_blockers") or [],
            "events": lifecycle.get("events") or [],
        }

    return {
        "correlation_id": correlation_id,
        "environments": by_environment,
    }
