from __future__ import annotations

import base64
import hashlib
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from models import AuditLog


EVENT_SCHEMA_VERSION = "1.0.0"
MANDATORY_FIELDS = [
    "event_id",
    "event_type",
    "timestamp",
    "correlation_id",
    "parent_event_id",
    "strategy_id",
    "symbol",
    "user_id",
    "environment",
    "payload",
    "latency",
    "decision_reason",
    "risk_flags",
    "execution_result",
]

LIFECYCLE_ORDER = ["request", "intent", "decision", "risk", "order", "execution", "fill"]

TRADING_CORRELATION_HINTS = {
    "trade",
    "strategy",
    "signal",
    "intent",
    "preview",
    "risk",
    "order",
    "execution",
    "fill",
    "position",
    "scanner",
    "bot",
    "exchange",
}

NOISE_CORRELATION_EXCLUDE_HINTS = {
    "auth",
    "login",
    "logout",
    "mfa",
    "session",
    "password",
    "forgot",
    "reset",
    "profile",
    "onboarding",
    "user_approval",
}

SEVERITY_ACTION = {
    "INFO": "observe",
    "WARNING": "filterable",
    "ERROR": "incident_candidate",
    "CRITICAL": "alert_escalate",
}


@dataclass
class NormalizedEvent:
    envelope: dict
    validation_errors: list[str]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_iso(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str) and value.strip():
        return value
    return _utcnow().isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _infer_stage(action: str, details: dict) -> str:
    raw = f"{action} {(details.get('route') or '')} {(details.get('event_type') or '')}".lower()
    if any(token in raw for token in ["fill", "filled", "partial_fill"]):
        return "fill"
    if any(token in raw for token in ["execution", "execute", "submit_order", "cancel_order"]):
        return "execution"
    if any(token in raw for token in ["order", "intent_event", "order_create"]):
        return "order"
    if any(token in raw for token in ["risk", "guard", "limit", "liquidation"]):
        return "risk"
    if any(token in raw for token in ["decision", "strategy", "signal", "selection"]):
        return "decision"
    if any(token in raw for token in ["intent", "preview", "candidate"]):
        return "intent"
    return "request"


def _normalize_event_type(action: str, details: dict) -> str:
    stage = _infer_stage(action, details)
    suffix = str(details.get("event_type") or action or "event").strip().lower().replace(" ", "_")
    if not suffix:
        suffix = "event"
    return f"{stage}.{suffix[:80]}"


def _normalize_severity(value: str | None) -> str:
    normalized = str(value or "INFO").upper()
    if normalized not in {"INFO", "WARNING", "ERROR", "CRITICAL"}:
        return "INFO"
    return normalized


def _extract_reason_codes(details: dict) -> list[str]:
    reason_codes = details.get("reason_codes") or []
    if not isinstance(reason_codes, list):
        reason_codes = [reason_codes]
    return [str(code).strip().lower() for code in reason_codes if str(code).strip()]


def _extract_correlation_id(row: AuditLog, details: dict) -> str | None:
    candidates = [
        details.get("correlation_id"),
        details.get("chain_id"),
        details.get("request_id"),
        details.get("trace_id"),
        details.get("decision_trace_id"),
        details.get("intent_id"),
        details.get("session_id"),
    ]
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _derive_environment(details: dict) -> str:
    for key in ["environment", "execution_mode", "mode", "runtime_environment"]:
        value = str(details.get(key) or "").strip()
        if value:
            return value.lower()
    return "unknown"


def _normalize_environment_value(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    aliases = {
        "production": "prod",
        "live": "prod",
        "dev": "staging",
        "development": "staging",
        "qa": "test",
    }
    normalized = aliases.get(value, value)
    return normalized if normalized in {"prod", "staging", "test", "canary"} else "test"


def _requires_correlation_tracking(row: AuditLog, normalized_event: dict) -> bool:
    payload = normalized_event.get("payload") if isinstance(normalized_event.get("payload"), dict) else {}
    raw = " ".join(
        [
            str(getattr(row, "action", "") or ""),
            str(getattr(row, "entity_type", "") or ""),
            str(payload.get("event_type") or ""),
            str(payload.get("route") or ""),
            str(normalized_event.get("event_type") or ""),
            str(normalized_event.get("lifecycle_stage") or ""),
        ]
    ).lower()

    if any(token in raw for token in NOISE_CORRELATION_EXCLUDE_HINTS):
        return False
    return any(token in raw for token in TRADING_CORRELATION_HINTS)


def normalize_audit_log_event(row: AuditLog) -> NormalizedEvent:
    details = dict(row.details or {})
    correlation_id = _extract_correlation_id(row, details)
    event_type = _normalize_event_type(row.action, details)
    stage = event_type.split(".", 1)[0]
    severity = _normalize_severity(row.severity)

    envelope = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_id": str(row.id),
        "event_type": event_type,
        "lifecycle_stage": stage,
        "timestamp": _safe_iso(row.created_at),
        "correlation_id": correlation_id,
        "parent_event_id": str(details.get("parent_event_id") or details.get("parent_audit_id") or "").strip() or None,
        "strategy_id": str(details.get("strategy_id") or details.get("strategy_code") or "").strip() or None,
        "symbol": str(details.get("symbol") or details.get("ticker") or "").upper().strip() or None,
        "user_id": str(details.get("user_id") or row.actor_user_id or "").strip() or None,
        "environment": _normalize_environment_value(getattr(row, "environment", None) or _derive_environment(details)),
        "is_test_event": bool(getattr(row, "is_test_event", details.get("is_test_event", False))),
        "previous_event_hash": getattr(row, "previous_event_hash", None),
        "event_hash": getattr(row, "event_hash", None),
        "signature_version": getattr(row, "signature_version", "v1"),
        "payload": details,
        "latency": {
            "ms": _safe_float(details.get("latency_ms") or details.get("duration_ms") or details.get("elapsed_ms")),
            "source": "details",
        },
        "decision_reason": str(details.get("decision_reason") or details.get("reason") or details.get("message") or "").strip() or None,
        "risk_flags": details.get("risk_flags") if isinstance(details.get("risk_flags"), list) else (details.get("reason_codes") or []),
        "execution_result": details.get("execution_result") or details.get("status") or details.get("result") or None,
        "severity": severity,
        "severity_action": SEVERITY_ACTION.get(severity, "observe"),
    }

    validation_errors: list[str] = []
    for key in MANDATORY_FIELDS:
        if key not in envelope:
            validation_errors.append(f"MISSING_KEY:{key}")

    if not envelope.get("correlation_id"):
        validation_errors.append("MISSING_CORRELATION_ID")
    if envelope.get("parent_event_id") == envelope.get("event_id"):
        validation_errors.append("SELF_PARENT_REFERENCE")
    if envelope.get("event_type", "").split(".", 1)[0] not in LIFECYCLE_ORDER:
        validation_errors.append("UNKNOWN_LIFECYCLE_STAGE")

    envelope["validation_errors"] = validation_errors
    envelope["is_valid"] = len(validation_errors) == 0
    return NormalizedEvent(envelope=envelope, validation_errors=validation_errors)


def _suppression_signature(event: dict) -> str:
    parts = [
        str(event.get("event_type") or ""),
        str(event.get("decision_reason") or ""),
        str(event.get("execution_result") or ""),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _apply_duplicate_suppression(events: list[dict], *, window_sec: int = 30) -> list[dict]:
    seen: dict[str, datetime] = {}
    for event in events:
        signature = _suppression_signature(event)
        timestamp = _parse_iso(event.get("timestamp"))
        event["duplicate_signature"] = signature
        event["suppressed"] = False
        if timestamp is None:
            continue
        previous = seen.get(signature)
        if previous and (timestamp - previous) <= timedelta(seconds=window_sec):
            event["suppressed"] = True
            event["suppression_reason"] = "duplicate_noise_suppressed"
        else:
            seen[signature] = timestamp
    return events


def _build_lifecycle_graph(events: list[dict]) -> dict:
    event_map = {str(event.get("event_id")): event for event in events if str(event.get("event_id") or "").strip()}
    children: dict[str, list[dict]] = defaultdict(list)
    roots: list[dict] = []
    orphans: list[dict] = []
    missing_links: list[dict] = []

    for event in events:
        event["relation_status"] = "root"
        event["is_orphan"] = False
        parent_id = str(event.get("parent_event_id") or "").strip() or None
        if not parent_id:
            roots.append(event)
            continue
        parent = event_map.get(parent_id)
        if parent is None:
            event["relation_status"] = "orphan"
            event["is_orphan"] = True
            orphans.append(event)
            missing_links.append({"event_id": event.get("event_id"), "missing_parent_event_id": parent_id})
            roots.append(event)
            continue
        event["relation_status"] = "linked"
        children[parent_id].append(event)

    stage_presence = {stage: 0 for stage in LIFECYCLE_ORDER}
    for event in events:
        stage = str(event.get("lifecycle_stage") or "")
        if stage in stage_presence:
            stage_presence[stage] += 1

    missing_critical_stages = [stage for stage in LIFECYCLE_ORDER if stage_presence.get(stage, 0) == 0]
    trace_incomplete = len(missing_critical_stages) > 0 or len(orphans) > 0
    broken_chain = trace_incomplete or len(missing_links) > 0

    for index, event in enumerate(events, start=1):
        event["causal_index"] = index

    return {
        "events": events,
        "children": {key: [item.get("event_id") for item in value] for key, value in children.items()},
        "roots": [item.get("event_id") for item in roots],
        "orphans": [item.get("event_id") for item in orphans],
        "missing_links": missing_links,
        "stage_presence": stage_presence,
        "missing_critical_stages": missing_critical_stages,
        "trace_incomplete": trace_incomplete,
        "broken_chain": broken_chain,
        "is_chain_valid": not broken_chain,
    }


def _explain_failure(graph: dict) -> dict:
    events = graph.get("events") or []
    broken = None
    for event in events:
        severity = str(event.get("severity") or "INFO").upper()
        if severity in {"ERROR", "CRITICAL"} or event.get("validation_errors"):
            broken = event
            break

    if broken is None and events:
        broken = events[-1]

    if broken is None:
        return {
            "root_cause": "insufficient_context",
            "broken_step": None,
            "upstream_cause": None,
            "downstream_impact": [],
            "missing_context": ["no_events"],
        }

    broken_index = int(broken.get("causal_index") or 1)
    upstream = None
    for event in reversed(events[: broken_index - 1]):
        if str(event.get("severity") or "").upper() in {"WARNING", "ERROR", "CRITICAL"}:
            upstream = {
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "decision_reason": event.get("decision_reason"),
            }
            break

    downstream = [
        {
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "severity": event.get("severity"),
        }
        for event in events[broken_index:]
    ]

    missing_context = []
    if graph.get("trace_incomplete"):
        missing_context.append("trace_incomplete")
    if graph.get("missing_critical_stages"):
        missing_context.append(f"missing_stages:{','.join(graph.get('missing_critical_stages') or [])}")

    return {
        "root_cause": broken.get("decision_reason") or (broken.get("validation_errors") or ["unknown"])[0],
        "broken_step": {
            "event_id": broken.get("event_id"),
            "event_type": broken.get("event_type"),
            "stage": broken.get("lifecycle_stage"),
            "severity": broken.get("severity"),
            "validation_errors": broken.get("validation_errors") or [],
        },
        "upstream_cause": upstream,
        "downstream_impact": downstream,
        "missing_context": missing_context,
    }


def _derive_pattern_tag(*, event_type: str, reason_codes: list[str], root_cause: str) -> str:
    haystack = " ".join([event_type, root_cause, *reason_codes]).lower()
    if any(token in haystack for token in ["timeout", "network", "exchange_unreachable", "exchange_http_error"]):
        return "exchange_timeout"
    if any(token in haystack for token in ["risk", "risk_gate", "liquidation", "exposure"]):
        return "risk_reject"
    if any(token in haystack for token in ["invalid_order", "min_notional", "precision", "size"]):
        return "invalid_order_size"
    if any(token in haystack for token in ["auth", "permission", "invalid_key", "session"]):
        return "auth_error"
    if any(token in haystack for token in ["validation", "missing", "schema"]):
        return "validation_failure"
    return "unknown_pattern"


def get_anomaly_reasons(events: list[dict]) -> list[str]:
    reasons: list[str] = []
    stage_presence = {stage: 0 for stage in LIFECYCLE_ORDER}
    orphan_count = 0
    for event in events:
        stage = str(event.get("lifecycle_stage") or "")
        if stage in stage_presence:
            stage_presence[stage] += 1
        if event.get("is_orphan") or str(event.get("relation_status") or "") == "orphan":
            orphan_count += 1

    missing_stages = [stage for stage, count in stage_presence.items() if count == 0]
    if len(events) >= 40:
        reasons.append("event_volume_spike")
    if len(missing_stages) >= 3:
        reasons.append("critical_stage_gap")
    if orphan_count >= 2:
        reasons.append("orphan_spike")
    return reasons


def detect_anomaly(events: list[dict]) -> bool:
    return len(get_anomaly_reasons(events)) > 0


def _build_root_cause_breakdown(graph: dict, explanation: dict) -> dict:
    events = list(graph.get("events") or [])
    broken_step = explanation.get("broken_step") or {}
    broken_event_id = str(broken_step.get("event_id") or "").strip()
    broken_event = next((row for row in events if str(row.get("event_id") or "") == broken_event_id), {})
    details = broken_event.get("payload") if isinstance(broken_event.get("payload"), dict) else {}
    reason_codes = _extract_reason_codes(details)
    missing_stages = list(graph.get("missing_critical_stages") or [])
    orphan_count = len(graph.get("orphans") or [])
    root_cause = str(explanation.get("root_cause") or "unknown")
    event_type = str(broken_step.get("event_type") or "unknown")
    pattern_tag = _derive_pattern_tag(event_type=event_type, reason_codes=reason_codes, root_cause=root_cause)

    contributing_factors = []
    if reason_codes:
        contributing_factors.extend([f"reason_code:{item}" for item in reason_codes[:5]])
    if missing_stages:
        contributing_factors.append(f"missing_stages:{','.join(missing_stages[:6])}")
    if orphan_count:
        contributing_factors.append(f"orphan_events:{orphan_count}")
    if not contributing_factors:
        contributing_factors.append("insufficient_context")

    anomaly_reasons = get_anomaly_reasons(events)
    anomaly_detected = detect_anomaly(events)

    critical_blockers = []
    for code in reason_codes:
        normalized = code.upper()
        if normalized in {
            "EXCHANGE_UNREACHABLE",
            "TIMEOUT",
            "NETWORK_ERROR",
            "RISK_GATE_BLOCKED",
            "INVALID_ORDER_SIZE",
            "AUTH_FAILED",
        }:
            critical_blockers.append(normalized)
    if missing_stages:
        critical_blockers.append("CHAIN_INCOMPLETE")

    cluster_seed = "|".join([pattern_tag, root_cause.lower(), event_type.lower(), ",".join(sorted(reason_codes))])
    cluster_id = hashlib.sha256(cluster_seed.encode("utf-8")).hexdigest()[:16]
    pattern_id = hashlib.sha256(f"pattern:{pattern_tag}".encode("utf-8")).hexdigest()[:12]
    if root_cause not in {"unknown", "insufficient_context"} and reason_codes:
        confidence = "high"
    elif root_cause not in {"unknown", "insufficient_context"}:
        confidence = "medium"
    else:
        confidence = "low"

    rca_result = {
        "failure_type": pattern_tag,
        "root_cause": root_cause,
        "contributing_factors": contributing_factors,
        "impact_scope": {
            "total_events": len(events),
            "downstream_event_count": len(explanation.get("downstream_impact") or []),
            "missing_critical_stages": missing_stages,
            "orphan_count": orphan_count,
        },
        "cluster_id": cluster_id,
        "pattern_id": pattern_id,
        "pattern_tag": pattern_tag,
        "confidence": confidence,
        "anomaly_detected": anomaly_detected,
        "anomaly_reasons": anomaly_reasons,
        "reason_codes": reason_codes,
        "critical_blockers": sorted(set(critical_blockers)),
    }
    assert "anomaly_detected" in rca_result
    assert "anomaly_reasons" in rca_result
    return rca_result


def _encode_cursor(timestamp: datetime, marker: str) -> str:
    payload = f"{timestamp.isoformat()}|{marker}"
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        ts_raw, marker = decoded.split("|", 1)
        ts = _parse_iso(ts_raw)
        if ts is None:
            return None
        return ts, marker
    except Exception:
        return None


def get_lifecycle_chain(db: Session, correlation_id: str, *, limit: int = 500, environment: str | None = None) -> dict:
    normalized = str(correlation_id or "").strip()
    if not normalized:
        raise ValueError("invalid_correlation_id")

    details_text = cast(AuditLog.details, String)
    query = db.query(AuditLog).filter(details_text.ilike(f"%{normalized}%") | (AuditLog.entity_id == normalized))
    if environment:
        query = query.filter(AuditLog.environment == str(environment).strip().lower())
    rows = query.order_by(AuditLog.created_at.asc()).limit(max(limit, 50)).all()

    normalized_events = [normalize_audit_log_event(row).envelope for row in rows]
    normalized_events = [event for event in normalized_events if event.get("correlation_id") == normalized]
    normalized_events.sort(key=lambda item: (_parse_iso(item.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc), str(item.get("event_id") or "")))
    normalized_events = _apply_duplicate_suppression(normalized_events)

    graph = _build_lifecycle_graph(normalized_events)
    explanation = _explain_failure(graph)
    breakdown = _build_root_cause_breakdown(graph, explanation)
    severity_counter = dict(Counter(str(event.get("severity") or "INFO") for event in normalized_events))

    return {
        "correlation_id": normalized,
        "environment": str(environment).strip().lower() if environment else None,
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_count": len(normalized_events),
        "events": normalized_events,
        "trace_incomplete": bool(graph.get("trace_incomplete")),
        "missing_critical_stages": graph.get("missing_critical_stages") or [],
        "broken_chain": bool(graph.get("broken_chain")),
        "severity_breakdown": severity_counter,
        "chain": graph,
        "explain_failure": explanation,
        "root_cause_breakdown": breakdown,
        "cluster_id": breakdown.get("cluster_id"),
        "pattern_tag": breakdown.get("pattern_tag"),
        "reason_codes": breakdown.get("reason_codes") or [],
        "critical_blockers": breakdown.get("critical_blockers") or [],
        "lifecycle_layers": {
            "strategy": [event for event in normalized_events if event.get("lifecycle_stage") in {"request", "intent", "decision"}],
            "risk": [event for event in normalized_events if event.get("lifecycle_stage") == "risk"],
            "execution": [event for event in normalized_events if event.get("lifecycle_stage") in {"order", "execution", "fill"}],
            "exchange": [event for event in normalized_events if str(event.get("event_type") or "").startswith("execution")],
        },
    }


def list_lifecycle_summaries(
    db: Session,
    *,
    limit: int = 100,
    q: str | None = None,
    severity: str | None = None,
    strategy_id: str | None = None,
    symbol: str | None = None,
    user_id: str | None = None,
    event_type: str | None = None,
    environment: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    payload_query: str | None = None,
    cursor: str | None = None,
    include_test_events: bool = False,
    archive_mode: bool = False,
    archive_cutoff_days: int = 7,
) -> dict:
    started_at = time.perf_counter()
    query = db.query(AuditLog)
    details_text = cast(AuditLog.details, String)
    if q:
        needle = f"%{q.strip()}%"
        query = query.filter(
            AuditLog.action.ilike(needle)
            | AuditLog.entity_id.ilike(needle)
            | details_text.ilike(needle)
        )

    if payload_query:
        search_term = payload_query.strip()
        if search_term:
            query = query.filter(
                func.to_tsvector("simple", func.coalesce(details_text, "")).op("@@")(func.plainto_tsquery("simple", search_term))
            )

    if severity:
        query = query.filter(AuditLog.severity == severity.upper())

    if strategy_id:
        query = query.filter(func.lower(func.coalesce(AuditLog.details.op("->>")("strategy_id"), "")) == strategy_id.strip().lower())
    if symbol:
        query = query.filter(func.upper(func.coalesce(AuditLog.details.op("->>")("symbol"), "")) == symbol.strip().upper())
    if user_id:
        normalized_user_id = user_id.strip()
        query = query.filter(
            or_(
                AuditLog.actor_user_id == normalized_user_id,
                func.coalesce(AuditLog.details.op("->>")("user_id"), "") == normalized_user_id,
            )
        )
    if event_type:
        normalized_event_type = event_type.strip()
        query = query.filter(
            or_(
                AuditLog.action.ilike(f"%{normalized_event_type}%"),
                func.lower(func.coalesce(AuditLog.details.op("->>")("event_type"), "")) == normalized_event_type.lower(),
            )
        )
    if environment:
        query = query.filter(AuditLog.environment == environment.strip().lower())
    if not include_test_events:
        query = query.filter(or_(AuditLog.is_test_event.is_(False), AuditLog.is_test_event.is_(None)))

    parsed_start = _parse_iso(start_time)
    parsed_end = _parse_iso(end_time)
    if parsed_start is not None:
        query = query.filter(AuditLog.created_at >= parsed_start)
    if parsed_end is not None:
        query = query.filter(AuditLog.created_at <= parsed_end)

    parsed_cursor = _decode_cursor(cursor)
    if parsed_cursor is not None:
        cursor_ts, _cursor_marker = parsed_cursor
        query = query.filter(AuditLog.created_at < cursor_ts)

    cutoff = _utcnow() - timedelta(days=max(archive_cutoff_days, 1))
    if archive_mode:
        query = query.filter(AuditLog.created_at < cutoff)
    else:
        query = query.filter(AuditLog.created_at >= cutoff)

    rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(max(limit * 40, 2000)).all()
    grouped: dict[str, list[dict]] = defaultdict(list)
    missing_correlation: list[str] = []
    missing_correlation_events: list[dict] = []

    for row in rows:
        normalized = normalize_audit_log_event(row).envelope
        correlation_id = str(normalized.get("correlation_id") or "").strip()
        if not correlation_id:
            if _requires_correlation_tracking(row, normalized):
                event_id = str(normalized.get("event_id") or "").strip()
                missing_correlation.append(event_id)
                payload = normalized.get("payload") if isinstance(normalized.get("payload"), dict) else {}
                missing_correlation_events.append(
                    {
                        "event_id": event_id,
                        "timestamp": normalized.get("timestamp"),
                        "event_type": normalized.get("event_type"),
                        "lifecycle_stage": normalized.get("lifecycle_stage"),
                        "severity": normalized.get("severity"),
                        "parent_event_id": normalized.get("parent_event_id"),
                        "relation_status": "root" if not normalized.get("parent_event_id") else "child_unlinked",
                        "route": payload.get("route"),
                        "method": payload.get("method"),
                        "error_address": payload.get("route") or "/api/audit-logs/trading-lifecycle",
                        "error_code": "MISSING_CORRELATION_ID",
                        "error_message": "Correlation ID boş veya bulunamadı",
                        "resolution_hint": "Event üretim katmanında correlation_id zorunlu hale getirilmeli",
                        "payload": payload,
                    }
                )
            continue
        grouped[correlation_id].append(normalized)

    summaries: list[dict] = []
    for correlation_id, events in grouped.items():
        events.sort(key=lambda item: (_parse_iso(item.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc), str(item.get("event_id") or "")))
        events = _apply_duplicate_suppression(events)
        graph = _build_lifecycle_graph(events)
        explanation = _explain_failure(graph)
        breakdown = _build_root_cause_breakdown(graph, explanation)
        severities = Counter(str(item.get("severity") or "INFO") for item in events)
        summaries.append(
            {
                "correlation_id": correlation_id,
                "event_count": len(events),
                "started_at": events[0].get("timestamp") if events else None,
                "ended_at": events[-1].get("timestamp") if events else None,
                "latest_event_type": events[-1].get("event_type") if events else None,
                "chain_valid": graph.get("is_chain_valid"),
                "trace_incomplete": graph.get("trace_incomplete"),
                "broken_chain": graph.get("broken_chain"),
                "orphan_count": len(graph.get("orphans") or []),
                "missing_critical_stages": graph.get("missing_critical_stages") or [],
                "severity": dict(severities),
                "has_error": severities.get("ERROR", 0) > 0 or severities.get("CRITICAL", 0) > 0,
                "pattern_tag": breakdown.get("pattern_tag"),
                "cluster_id": breakdown.get("cluster_id"),
                "reason_codes": breakdown.get("reason_codes") or [],
                "critical_blockers": breakdown.get("critical_blockers") or [],
            }
        )

    summaries.sort(key=lambda item: (item.get("ended_at") or "", item.get("correlation_id") or ""), reverse=True)
    page_limit = max(limit, 1)
    paged_items = summaries[:page_limit]
    has_more = len(summaries) > page_limit
    next_cursor = None
    if has_more and paged_items:
        cursor_ts = _parse_iso(paged_items[-1].get("ended_at")) or _utcnow()
        next_cursor = _encode_cursor(cursor_ts, str(paged_items[-1].get("correlation_id") or ""))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "total": len(summaries),
        "items": paged_items,
        "missing_correlation_event_ids": missing_correlation,
        "missing_correlation_events": missing_correlation_events[:250],
        "has_more": has_more,
        "next_cursor": next_cursor,
        "page_size": page_limit,
        "query_latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
    }


def replay_lifecycle(correlation_payload: dict, *, snapshot_id: str | None = None, run_by: str = "admin") -> dict:
    chain = correlation_payload.get("chain") or {}
    events = list(chain.get("events") or [])
    events.sort(key=lambda item: (_parse_iso(item.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc), str(item.get("event_id") or "")))

    replay_steps: list[dict] = []
    break_step = None
    for index, event in enumerate(events, start=1):
        source = f"{event.get('event_id')}|{event.get('event_type')}|{event.get('timestamp')}"
        replay_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()[:20]
        severity = str(event.get("severity") or "INFO").upper()
        status = "ok"
        if severity in {"ERROR", "CRITICAL"} or event.get("validation_errors"):
            status = "failed"
            if break_step is None:
                break_step = {
                    "step_index": index,
                    "event_id": event.get("event_id"),
                    "event_type": event.get("event_type"),
                    "reason": (event.get("validation_errors") or [event.get("decision_reason") or "unknown"])[0],
                }

        replay_steps.append(
            {
                "step_index": index,
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "parent_event_id": event.get("parent_event_id"),
                "status": status,
                "deterministic_hash": replay_hash,
            }
        )

    return {
        "correlation_id": correlation_payload.get("correlation_id"),
        "snapshot_id": snapshot_id or "snapshot:latest",
        "run_by": run_by,
        "replay_mode": "isolated",
        "isolation_mode": "isolated",
        "external_calls_disabled": True,
        "deterministic_order": True,
        "ordered": True,
        "side_effects_blocked": True,
        "step_count": len(replay_steps),
        "break_step": break_step,
        "steps": replay_steps,
        "result": "FAILED" if break_step else "SUCCESS",
    }
