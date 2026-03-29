from __future__ import annotations

import json
import hashlib
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from db import redis_client
from models import AlertTriageAction, AuditLog, DebugIncident, FailedEvent, LiveActivationConfig, SystemAlert
from runtime_control import force_pipeline_resync, restart_runtime_service
from services.audit_service import create_audit_log
from services.execution_safety_service import update_execution_safety_state
from services.execution_microstructure_service import build_microstructure_venue_summary


OPEN_INCIDENT_STATES = {"OPEN", "INVESTIGATING", "MITIGATED"}
ANOMALY_ALERT_PREFIX = "anomaly."
MAX_SOURCE_ROWS = 1500
POLICY_KEY = "incident_intelligence:policy:v1"

DEFAULT_POLICY_CONFIG = {
    "execution": [
        {"action": "reconcile_trigger", "severity": ["ERROR", "CRITICAL"], "recurrence_min": 1, "approval_mode": "hybrid", "cooldown_seconds": 300, "retry_limit": 2},
    ],
    "risk": [
        {"action": "reduce_leverage", "severity": ["ERROR", "CRITICAL"], "recurrence_min": 1, "approval_mode": "auto", "cooldown_seconds": 600, "retry_limit": 2},
    ],
    "system": [
        {"action": "restart_worker", "severity": ["ERROR", "CRITICAL"], "recurrence_min": 1, "approval_mode": "manual", "cooldown_seconds": 600, "retry_limit": 1},
    ],
    "exchange": [
        {"action": "block_trading", "severity": ["ERROR", "CRITICAL"], "recurrence_min": 1, "approval_mode": "auto", "cooldown_seconds": 900, "retry_limit": 1},
    ],
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if isinstance(value, datetime) else None


def _json_safe(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _domain_from_text(value: str) -> str:
    raw = str(value or "").lower()
    if any(token in raw for token in ["execution", "intent", "order", "fill", "quarantine", "stuck"]):
        return "execution"
    if any(token in raw for token in ["risk", "liquidation", "leverage", "var", "cvar", "exposure"]):
        return "risk"
    if any(token in raw for token in ["exchange", "binance", "bybit", "venue"]):
        return "exchange"
    if any(token in raw for token in ["strategy", "signal", "regime"]):
        return "strategy"
    return "system"


def _severity_rank(value: str) -> int:
    return {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}.get(str(value or "INFO").upper(), 0)


def _normalize_severity(value: str) -> str:
    normalized = str(value or "INFO").upper()
    if normalized not in {"INFO", "WARNING", "ERROR", "CRITICAL"}:
        return "INFO"
    return normalized


def _owner_for_domain(domain: str) -> str:
    return {
        "execution": "ops-execution",
        "risk": "risk-control",
        "exchange": "exchange-ops",
        "strategy": "strategy-ops",
        "system": "platform-sre",
    }.get(domain, "platform-sre")


def _linked_evidence(details: dict) -> dict:
    linked_artefacts = [
        str(details.get(key)).strip()
        for key in ["artifact_id", "proof_id", "snapshot_id", "bundle_id"]
        if str(details.get(key) or "").strip()
    ]
    linked_quarantine = [
        str(details.get(key)).strip()
        for key in ["quarantine_id", "failed_event_id"]
        if str(details.get(key) or "").strip()
    ]
    linked_stuck_intents = [
        str(details.get(key)).strip()
        for key in ["intent_id", "stuck_intent_id", "execution_job_id"]
        if str(details.get(key) or "").strip()
    ]
    return {
        "linked_artefacts": sorted(set(linked_artefacts)),
        "linked_quarantine": sorted(set(linked_quarantine)),
        "linked_stuck_intents": sorted(set(linked_stuck_intents)),
    }


def _impact_from_details(domain: str, details: dict, *, severity_hint: str) -> dict:
    pnl = _safe_float(details.get("pnl") or details.get("pnl_impact") or details.get("loss_usd"), 0.0)
    exposure = _safe_float(
        details.get("exposure")
        or details.get("exposure_impact")
        or details.get("projected_exposure")
        or details.get("notional"),
        0.0,
    )
    availability = _safe_float(details.get("availability_impact") or details.get("queue_pressure") or 0.0, 0.0)
    if availability <= 0:
        availability = 1.0 if domain in {"system", "exchange"} and _severity_rank(severity_hint) >= 2 else 0.2
    if domain == "execution" and exposure <= 0:
        exposure = _safe_float(details.get("quantity"), 0.0)
    total = abs(pnl) * 0.35 + abs(exposure) * 0.25 + availability * 40.0
    return {
        "pnl": round(pnl, 6),
        "exposure": round(exposure, 6),
        "availability": round(availability, 6),
        "total_score": round(total, 6),
    }


def _severity_from_impact(impact: dict) -> str:
    total = _safe_float(impact.get("total_score"), 0.0)
    if total >= 120:
        return "CRITICAL"
    if total >= 60:
        return "ERROR"
    if total >= 20:
        return "WARNING"
    return "INFO"


def _root_cause(domain: str, source: str, details: dict, signals: dict) -> tuple[str, float]:
    raw = f"{source} {details.get('reason_code') or ''} {details.get('error_message') or ''} {details.get('message') or ''}".lower()
    if domain == "exchange":
        cause = "exchange_connectivity" if any(token in raw for token in ["timeout", "403", "auth", "network", "exchange"]) else "exchange_degradation"
    elif domain == "execution":
        cause = "execution_flow_break" if any(token in raw for token in ["retry", "reconcile", "intent", "fill", "precheck"]) else "execution_quality_drop"
    elif domain == "risk":
        cause = "risk_guard_breach"
    elif domain == "strategy":
        cause = "strategy_regime_mismatch"
    else:
        cause = "system_capacity_or_worker"
    confidence = 0.45
    if signals.get("burst_detected"):
        confidence += 0.15
    if signals.get("repeated_pattern"):
        confidence += 0.15
    if _safe_float(signals.get("z_score"), 0.0) >= 2.0:
        confidence += 0.15
    return cause, round(min(confidence, 0.95), 6)


def _suggested_actions(domain: str, root_cause: str, severity: str) -> list[str]:
    actions = []
    if domain == "execution":
        actions.extend(["retry", "inspect_reconcile"])
    elif domain == "risk":
        actions.extend(["reduce_leverage", "block_trading"])
    elif domain == "system":
        actions.extend(["restart_worker", "inspect_reconcile"])
    elif domain == "exchange":
        actions.extend(["block_trading", "inspect_reconcile"])
    else:
        actions.extend(["retry"])
    if _severity_rank(severity) >= 2 and "block_trading" not in actions:
        actions.append("block_trading")
    return list(dict.fromkeys(actions))


def _anomaly_signature(domain: str, anomaly_type: str, source: str, entity_key: str) -> str:
    raw = f"{domain}|{anomaly_type}|{source}|{entity_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_dynamic_context() -> dict:
    venue_summary = build_microstructure_venue_summary(redis_client)
    binance = (venue_summary.get("venues") or {}).get("binance") or {}
    stress = _safe_float(binance.get("liquidity_stress_score"), 0.0)
    volatility = "high" if stress >= 50 else "normal"
    regime = "stressed" if stress >= 60 else "normal"
    load = "high" if _safe_float(binance.get("venue_health_score"), 100.0) < 60 else "normal"
    return {"volatility": volatility, "load": load, "regime": regime}


def _dynamic_thresholds(context: dict) -> dict:
    multiplier = 1.0
    if context.get("volatility") == "high":
        multiplier += 0.2
    if context.get("load") == "high":
        multiplier += 0.15
    if context.get("regime") == "stressed":
        multiplier += 0.15
    return {
        "z_score": 1.5 * multiplier,
        "baseline_deviation": 1.8 * multiplier,
        "burst_count": max(2, int(round(3 * multiplier))),
        "repeat_count": max(2, int(round(3 * multiplier))),
    }


def _audit_candidates(db, since: datetime) -> list[dict]:
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.created_at >= since)
        .order_by(AuditLog.created_at.desc())
        .limit(MAX_SOURCE_ROWS)
        .all()
    )
    rows = list(reversed(rows))
    candidates = []
    for row in rows:
        details = dict(row.details or {})
        domain = _domain_from_text(f"{row.action} {row.entity_type} {' '.join(str(item) for item in details.get('reason_codes', []))}")
        source = f"audit:{row.action.lower()}"
        anomaly_type = str(details.get("reason_code") or row.action or "event").lower().replace(" ", "_")[:80]
        entity_key = (
            anomaly_type
            if domain in {"risk", "system", "exchange"}
            else str(details.get("correlation_id") or row.entity_id or row.id)
        )
        candidates.append(
            {
                "candidate_id": f"audit:{row.id}",
                "source_model": "audit_log",
                "source_id": row.id,
                "source": source,
                "domain": domain,
                "type": anomaly_type,
                "entity_key": entity_key,
                "severity_hint": _normalize_severity(row.severity),
                "details": details,
                "timestamp": row.created_at,
                "linked_events": [f"audit:{row.id}"],
                **_linked_evidence(details),
            }
        )
    return candidates


def _failed_event_candidates(db, since: datetime) -> list[dict]:
    rows = (
        db.query(FailedEvent)
        .filter(FailedEvent.created_at >= since)
        .order_by(FailedEvent.created_at.desc())
        .limit(MAX_SOURCE_ROWS)
        .all()
    )
    rows = list(reversed(rows))
    candidates = []
    for row in rows:
        payload = dict(row.payload or {})
        details = {**payload, "error_message": row.error_message, "reason_code": row.retry_reason or row.failure_class}
        domain = _domain_from_text(f"{row.event_type} {row.entity_type} {row.failure_class}")
        candidates.append(
            {
                "candidate_id": f"failed:{row.id}",
                "source_model": "failed_event",
                "source_id": row.id,
                "source": f"failed:{row.event_type}",
                "domain": domain,
                "type": str(row.failure_class or row.event_type or "failed_event").lower(),
                "entity_key": str(row.failure_class or row.event_type or row.entity_type or row.id),
                "severity_hint": "ERROR",
                "details": details,
                "timestamp": row.created_at,
                "linked_events": [f"failed:{row.id}"],
                **_linked_evidence({**details, "failed_event_id": row.id}),
            }
        )
    return candidates


def _system_alert_candidates(db, since: datetime) -> list[dict]:
    rows = (
        db.query(SystemAlert)
        .filter(SystemAlert.created_at >= since, ~SystemAlert.alert_type.like(f"{ANOMALY_ALERT_PREFIX}%"))
        .order_by(SystemAlert.created_at.desc())
        .limit(MAX_SOURCE_ROWS)
        .all()
    )
    rows = list(reversed(rows))
    candidates = []
    for row in rows:
        details = dict(row.details or {})
        domain = _domain_from_text(f"{row.alert_type} {row.entity_key} {row.root_cause_code}")
        candidates.append(
            {
                "candidate_id": f"alert:{row.id}",
                "source_model": "system_alert",
                "source_id": row.id,
                "source": f"system_alert:{row.alert_type}",
                "domain": domain,
                "type": str(row.root_cause_code or row.alert_type or "system_alert").lower(),
                "entity_key": str(row.root_cause_code or row.entity_key or row.id),
                "severity_hint": _normalize_severity(row.severity),
                "details": details,
                "timestamp": row.created_at,
                "linked_events": [f"alert:{row.id}"],
                **_linked_evidence(details),
            }
        )
    return candidates


def _window_counts(candidates: list[dict], *, now: datetime, window_minutes: int, historical_windows: int = 6) -> dict[str, list[int]]:
    window = timedelta(minutes=window_minutes)
    start = now - (window * historical_windows)
    relevant = [item for item in candidates if item.get("timestamp") and item["timestamp"] >= start]
    buckets: dict[str, list[int]] = defaultdict(lambda: [0 for _ in range(historical_windows)])
    for item in relevant:
        signature = _anomaly_signature(item["domain"], item["type"], item["source"], item["entity_key"])
        age = now - item["timestamp"]
        bucket_index = min(historical_windows - 1, max(0, int(age.total_seconds() // window.total_seconds())))
        buckets[signature][historical_windows - 1 - bucket_index] += 1
    return buckets


def _score_signature(current_count: int, history_counts: list[int], thresholds: dict) -> dict:
    baseline = history_counts[:-1] if len(history_counts) > 1 else []
    mean = statistics.mean(baseline) if baseline else 0.0
    std = statistics.pstdev(baseline) if len(baseline) > 1 else 0.0
    z_score = ((current_count - mean) / std) if std > 0 else (float(current_count) if current_count > 0 else 0.0)
    baseline_deviation = (current_count / max(mean, 1.0)) if current_count > 0 else 0.0
    burst_detected = current_count >= thresholds["burst_count"]
    repeated_pattern = sum(1 for item in baseline if item > 0) >= thresholds["repeat_count"] - 1 and current_count > 0
    return {
        "current_count": current_count,
        "mean": round(mean, 6),
        "std": round(std, 6),
        "z_score": round(z_score, 6),
        "baseline_deviation": round(baseline_deviation, 6),
        "burst_detected": burst_detected,
        "repeated_pattern": repeated_pattern,
        "is_anomaly": bool(
            current_count > 0
            and (
                z_score >= thresholds["z_score"]
                or baseline_deviation >= thresholds["baseline_deviation"]
                or burst_detected
                or repeated_pattern
            )
        ),
    }


def _upsert_anomaly_alert(db, *, latest: dict, grouped_items: list[dict], signals: dict) -> SystemAlert:
    impact = _impact_from_details(latest["domain"], latest["details"], severity_hint=latest["severity_hint"])
    severity = max(_normalize_severity(latest["severity_hint"]), _severity_from_impact(impact), key=_severity_rank)
    root_cause, confidence = _root_cause(latest["domain"], latest["source"], latest["details"], signals)
    owner = _owner_for_domain(latest["domain"])
    suggested_actions = _suggested_actions(latest["domain"], root_cause, severity)
    signature = _anomaly_signature(latest["domain"], latest["type"], latest["source"], latest["entity_key"])
    existing = (
        db.query(SystemAlert)
        .filter(SystemAlert.alert_type == f"{ANOMALY_ALERT_PREFIX}{latest['domain']}", SystemAlert.fingerprint == signature)
        .order_by(SystemAlert.last_triggered_at.desc())
        .first()
    )
    details = {
        "id": existing.id if existing else None,
        "type": latest["type"],
        "source": latest["source"],
        "domain": latest["domain"],
        "owner": owner,
        "linked_events": sorted({ref for item in grouped_items for ref in (item.get("linked_events") or [])}),
        "linked_artefacts": sorted({ref for item in grouped_items for ref in (item.get("linked_artefacts") or [])}),
        "impact": impact,
        "root_cause": root_cause,
        "confidence_score": confidence,
        "suggested_actions": suggested_actions,
        "anomaly_signals": signals,
        "linked_quarantine": sorted({ref for item in grouped_items for ref in (item.get("linked_quarantine") or [])}),
        "linked_stuck_intents": sorted({ref for item in grouped_items for ref in (item.get("linked_stuck_intents") or [])}),
        "entity_key": latest["entity_key"],
        "first_event_at": min(item["timestamp"] for item in grouped_items).isoformat(),
        "last_event_at": max(item["timestamp"] for item in grouped_items).isoformat(),
    }
    if existing:
        existing.severity = severity
        existing.message = f"{latest['domain']} anomaly: {latest['type']}"
        existing.details = details
        existing.root_cause_code = root_cause
        existing.entity_key = latest["entity_key"]
        existing.last_triggered_at = _utcnow()
        existing.occurrences = max(int(existing.occurrences or 1), len(grouped_items))
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    anomaly = SystemAlert(
        alert_type=f"{ANOMALY_ALERT_PREFIX}{latest['domain']}",
        severity=severity,
        message=f"{latest['domain']} anomaly: {latest['type']}",
        fingerprint=signature,
        entity_key=latest["entity_key"],
        root_cause_code=root_cause,
        details=details,
        status="open",
        occurrences=len(grouped_items),
        last_triggered_at=_utcnow(),
    )
    db.add(anomaly)
    db.commit()
    db.refresh(anomaly)
    anomaly.details = {**anomaly.details, "id": anomaly.id}
    db.add(anomaly)
    db.commit()
    db.refresh(anomaly)
    return anomaly


def serialize_anomaly(row: SystemAlert) -> dict:
    details = dict(row.details or {})
    return {
        "id": row.id,
        "type": details.get("type") or row.alert_type,
        "source": details.get("source") or row.alert_type,
        "domain": details.get("domain") or _domain_from_text(row.alert_type),
        "severity": _normalize_severity(row.severity),
        "state": str(row.status or "open").upper(),
        "owner": details.get("owner") or _owner_for_domain(details.get("domain") or _domain_from_text(row.alert_type)),
        "linked_events": details.get("linked_events") or [],
        "linked_artefacts": details.get("linked_artefacts") or [],
        "impact": details.get("impact") or {"pnl": 0.0, "exposure": 0.0, "availability": 0.0},
        "root_cause": details.get("root_cause") or row.root_cause_code,
        "confidence_score": details.get("confidence_score"),
        "suggested_actions": details.get("suggested_actions") or [],
        "linked_quarantine": details.get("linked_quarantine") or [],
        "linked_stuck_intents": details.get("linked_stuck_intents") or [],
        "signals": details.get("anomaly_signals") or {},
        "created_at": _safe_iso(row.created_at),
        "updated_at": _safe_iso(row.updated_at),
    }


def _upsert_incident_from_anomaly(db, anomaly: SystemAlert) -> DebugIncident:
    anomaly_payload = serialize_anomaly(anomaly)
    existing = (
        db.query(DebugIncident)
        .filter(DebugIncident.fingerprint == anomaly.fingerprint, DebugIncident.status.in_(list(OPEN_INCIDENT_STATES)))
        .order_by(DebugIncident.last_seen_at.desc())
        .first()
    )
    details = {
        "owner": anomaly_payload["owner"],
        "state": existing.status if existing else "OPEN",
        "anomaly_id": anomaly_payload["id"],
        "domain": anomaly_payload["domain"],
        "source": anomaly_payload["source"],
        "type": anomaly_payload["type"],
        "linked_events": anomaly_payload["linked_events"],
        "linked_artefacts": anomaly_payload["linked_artefacts"],
        "impact": anomaly_payload["impact"],
        "root_cause": anomaly_payload["root_cause"],
        "confidence_score": anomaly_payload["confidence_score"],
        "suggested_actions": anomaly_payload["suggested_actions"],
        "linked_quarantine": anomaly_payload["linked_quarantine"],
        "linked_stuck_intents": anomaly_payload["linked_stuck_intents"],
    }
    if existing:
        existing.severity = anomaly_payload["severity"]
        existing.root_cause = anomaly_payload["root_cause"]
        existing.last_seen_at = _utcnow()
        existing.occurrence_count = max(int(existing.occurrence_count or 1), int(anomaly.occurrences or 1))
        existing.details = {**dict(existing.details or {}), **details}
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    incident = DebugIncident(
        incident_id=str(uuid.uuid4()),
        title=f"{anomaly_payload['domain'].upper()} incident: {anomaly_payload['type']}",
        severity=anomaly_payload["severity"],
        tags=[anomaly_payload["domain"], "incident-intelligence", anomaly_payload["type"]],
        linked_correlation_id=str((anomaly_payload.get("linked_events") or [anomaly.entity_key or anomaly.id])[0]),
        source_event_id=anomaly_payload["id"],
        fingerprint=anomaly.fingerprint,
        cluster_id=anomaly_payload["domain"],
        root_cause=anomaly_payload["root_cause"],
        status="OPEN",
        auto_created=True,
        dedupe_window_seconds=300,
        occurrence_count=max(int(anomaly.occurrences or 1), 1),
        last_seen_at=_utcnow(),
        created_by=anomaly_payload["owner"],
        details=details,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def _auto_remediation_action(incident: DebugIncident) -> dict | None:
    policy = _policy_for_incident(incident)
    if not policy or str(policy.get("approval_mode") or "manual") != "auto":
        return None
    return {"action": policy.get("action"), "status": "queued", "approval_mode": "auto"}


def _read_policy_config() -> dict:
    raw = redis_client.get(POLICY_KEY)
    if not raw:
        return DEFAULT_POLICY_CONFIG
    raw = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        payload = json.loads(raw)
    except Exception:
        return DEFAULT_POLICY_CONFIG
    if not isinstance(payload, dict):
        return DEFAULT_POLICY_CONFIG
    merged = {**DEFAULT_POLICY_CONFIG}
    merged.update(payload)
    return merged


def get_incident_policy_config() -> dict:
    return _read_policy_config()


def update_incident_policy_config(payload: dict) -> dict:
    merged = {**DEFAULT_POLICY_CONFIG, **dict(payload or {})}
    redis_client.set(POLICY_KEY, json.dumps(merged, ensure_ascii=False))
    return merged


def _policy_for_incident(incident: DebugIncident) -> dict | None:
    details = dict(incident.details or {})
    domain = str(details.get("domain") or "system")
    severity = _normalize_severity(incident.severity)
    recurrence = int(incident.occurrence_count or 1)
    policies = list((_read_policy_config().get(domain) or []))
    for policy in policies:
        if severity not in set(policy.get("severity") or []):
            continue
        if recurrence < int(policy.get("recurrence_min") or 1):
            continue
        return policy
    return None


def execute_incident_action(
    db,
    *,
    incident_id: str,
    action: str,
    actor_user_id: str,
    actor_role: str,
    mode: str = "manual",
) -> dict:
    incident = db.query(DebugIncident).filter(DebugIncident.incident_id == incident_id).first()
    if incident is None:
        raise ValueError("incident_not_found")
    details = dict(incident.details or {})
    normalized_action = str(action or "").strip().lower()
    rollback_payload = None
    result = {"status": "executed", "action": normalized_action, "mode": mode}
    if normalized_action == "restart_worker":
        result["connector_result"] = restart_runtime_service(service="worker")
    elif normalized_action == "block_trading":
        safety = update_execution_safety_state(
            db,
            trading_enabled=False,
            reason=f"incident:{incident_id}",
            requested_by=actor_user_id,
            effective_at=_utcnow().isoformat(),
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
        rollback_payload = {"trading_enabled": True}
        result["connector_result"] = _json_safe(safety)
    elif normalized_action == "reduce_leverage":
        config = db.query(LiveActivationConfig).filter(LiveActivationConfig.id == "global").first()
        if config is None:
            config = LiveActivationConfig(id="global")
            db.add(config)
            db.flush()
        previous = int(config.leverage_cap or 1)
        config.leverage_cap = max(1, previous - 1)
        db.commit()
        db.refresh(config)
        rollback_payload = {"leverage_cap": previous}
        result["connector_result"] = {"previous_leverage_cap": previous, "current_leverage_cap": config.leverage_cap}
    elif normalized_action == "reconcile_trigger":
        result["connector_result"] = _json_safe(force_pipeline_resync(redis_client, actor_user_id=actor_user_id, reason=f"incident:{incident_id}", trace_id=str(uuid.uuid4())))
    else:
        raise ValueError("invalid_incident_action")

    history = list(details.get("remediation_history") or [])
    history.append({**_json_safe(result), "executed_at": _utcnow().isoformat(), "rollback_payload": _json_safe(rollback_payload)})
    details["remediation_history"] = history
    incident.details = details
    incident.status = "MITIGATED" if normalized_action in {"block_trading", "reduce_leverage", "restart_worker", "reconcile_trigger"} else incident.status
    db.add(incident)
    create_audit_log(
        db,
        action="INCIDENT_ACTION_EXECUTED",
        entity_type="incident_intelligence",
        entity_id=incident_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        details={"action": normalized_action, "mode": mode, "rollback_payload": rollback_payload},
        commit=False,
    )
    db.commit()
    db.refresh(incident)
    return {"incident": serialize_incident_intelligence(incident), "action_result": result}


def rollback_incident_action(db, *, incident_id: str, actor_user_id: str, actor_role: str) -> dict:
    incident = db.query(DebugIncident).filter(DebugIncident.incident_id == incident_id).first()
    if incident is None:
        raise ValueError("incident_not_found")
    details = dict(incident.details or {})
    history = list(details.get("remediation_history") or [])
    if not history:
        raise ValueError("rollback_not_available")
    latest = history[-1]
    rollback_payload = dict(latest.get("rollback_payload") or {})
    if not rollback_payload:
        raise ValueError("rollback_not_available")
    if "trading_enabled" in rollback_payload:
        update_execution_safety_state(
            db,
            trading_enabled=bool(rollback_payload.get("trading_enabled")),
            reason=f"incident_rollback:{incident_id}",
            requested_by=actor_user_id,
            effective_at=_utcnow().isoformat(),
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
    if "leverage_cap" in rollback_payload:
        config = db.query(LiveActivationConfig).filter(LiveActivationConfig.id == "global").first()
        if config is None:
            config = LiveActivationConfig(id="global")
            db.add(config)
            db.flush()
        config.leverage_cap = int(rollback_payload.get("leverage_cap") or config.leverage_cap or 1)
        db.commit()
    details.setdefault("rollback_history", []).append({"rolled_back_at": _utcnow().isoformat(), "rollback_payload": rollback_payload})
    incident.details = details
    db.add(incident)
    create_audit_log(
        db,
        action="INCIDENT_ACTION_ROLLED_BACK",
        entity_type="incident_intelligence",
        entity_id=incident_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        details={"rollback_payload": rollback_payload},
        commit=False,
    )
    db.commit()
    db.refresh(incident)
    return {"incident": serialize_incident_intelligence(incident), "rollback_payload": rollback_payload}


def run_incident_intelligence_cycle(
    db,
    *,
    window_minutes: int = 60,
    create_incidents: bool = True,
    run_auto_remediation: bool = True,
) -> dict:
    now = _utcnow()
    since = now - timedelta(minutes=max(window_minutes, 5) * 6)
    current_since = now - timedelta(minutes=max(window_minutes, 5))
    context = _build_dynamic_context()
    thresholds = _dynamic_thresholds(context)
    candidates = [
        * _audit_candidates(db, since),
        * _failed_event_candidates(db, since),
        * _system_alert_candidates(db, since),
    ]
    grouped: dict[str, list[dict]] = defaultdict(list)
    for candidate in candidates:
        signature = _anomaly_signature(candidate["domain"], candidate["type"], candidate["source"], candidate["entity_key"])
        grouped[signature].append(candidate)
    bucket_counts = _window_counts(candidates, now=now, window_minutes=max(window_minutes, 5))

    anomalies = []
    incidents = []
    remediation_events = []
    for signature, items in grouped.items():
        current_items = [item for item in items if item["timestamp"] >= current_since]
        if not current_items:
            continue
        signals = _score_signature(len(current_items), bucket_counts.get(signature) or [len(current_items)], thresholds)
        latest = max(current_items, key=lambda row: row["timestamp"])
        if not signals["is_anomaly"] and _severity_rank(latest["severity_hint"]) < 2:
            continue
        anomaly = _upsert_anomaly_alert(db, latest=latest, grouped_items=current_items, signals=signals)
        anomalies.append(serialize_anomaly(anomaly))
        if create_incidents and _severity_rank(anomaly.severity) >= 1:
            incident = _upsert_incident_from_anomaly(db, anomaly)
            incidents.append(serialize_incident_intelligence(incident))
            if run_auto_remediation:
                action = _auto_remediation_action(incident)
                if action:
                    executed = execute_incident_action(
                        db,
                        incident_id=incident.incident_id,
                        action=str(action.get("action") or ""),
                        actor_user_id="system",
                        actor_role="system",
                        mode="auto",
                    )
                    remediation_events.append({"incident_id": incident.incident_id, **(executed.get("action_result") or {})})
    return {
        "generated_at": now.isoformat(),
        "context": context,
        "thresholds": thresholds,
        "anomalies": anomalies,
        "incidents": incidents,
        "auto_remediation": remediation_events,
    }


def serialize_incident_intelligence(row: DebugIncident) -> dict:
    details = dict(row.details or {})
    return {
        "incident_id": row.incident_id,
        "title": row.title,
        "severity": _normalize_severity(row.severity),
        "state": str(row.status or "OPEN").upper(),
        "owner": details.get("owner") or row.created_by,
        "evidence": {
            "linked_events": details.get("linked_events") or [],
            "linked_artefacts": details.get("linked_artefacts") or [],
            "linked_quarantine": details.get("linked_quarantine") or [],
            "linked_stuck_intents": details.get("linked_stuck_intents") or [],
        },
        "impact": details.get("impact") or {},
        "root_cause": details.get("root_cause") or row.root_cause,
        "confidence_score": details.get("confidence_score"),
        "suggested_actions": details.get("suggested_actions") or [],
        "remediation_history": details.get("remediation_history") or [],
        "created_at": _safe_iso(row.created_at),
        "updated_at": _safe_iso(row.updated_at),
        "resolved_at": _safe_iso(row.closed_at),
    }


def list_intelligence_anomalies(db, *, limit: int = 100, state: str | None = None, domain: str | None = None, severity: str | None = None) -> list[dict]:
    query = db.query(SystemAlert).filter(SystemAlert.alert_type.like(f"{ANOMALY_ALERT_PREFIX}%"))
    if state:
        query = query.filter(SystemAlert.status == str(state).lower())
    if severity:
        query = query.filter(SystemAlert.severity == _normalize_severity(severity))
    rows = query.order_by(SystemAlert.last_triggered_at.desc()).limit(max(1, min(limit, 300))).all()
    anomalies = [serialize_anomaly(row) for row in rows]
    if domain:
        anomalies = [item for item in anomalies if item["domain"] == domain]
    return anomalies


def list_intelligence_incidents(db, *, limit: int = 100, state: str | None = None) -> list[dict]:
    query = db.query(DebugIncident)
    if state:
        query = query.filter(DebugIncident.status == str(state).upper())
    rows = query.order_by(DebugIncident.last_seen_at.desc()).limit(max(1, min(limit, 300))).all()
    return [serialize_incident_intelligence(row) for row in rows]


def _load_linked_event(ref: str, db) -> dict | None:
    kind, _, value = str(ref or "").partition(":")
    if not kind or not value:
        return None
    if kind == "audit":
        row = db.query(AuditLog).filter(AuditLog.id == value).first()
        if row is None:
            return None
        return {"kind": "raw_event", "id": ref, "timestamp": _safe_iso(row.created_at), "payload": dict(row.details or {}), "source": row.action}
    if kind == "failed":
        row = db.query(FailedEvent).filter(FailedEvent.id == value).first()
        if row is None:
            return None
        return {"kind": "raw_event", "id": ref, "timestamp": _safe_iso(row.created_at), "payload": dict(row.payload or {}), "source": row.event_type}
    if kind == "alert":
        row = db.query(SystemAlert).filter(SystemAlert.id == value).first()
        if row is None:
            return None
        return {"kind": "raw_event", "id": ref, "timestamp": _safe_iso(row.created_at), "payload": dict(row.details or {}), "source": row.alert_type}
    return None


def build_incident_timeline(db, incident_id: str) -> dict:
    incident = db.query(DebugIncident).filter(DebugIncident.incident_id == incident_id).first()
    if incident is None:
        raise ValueError("incident_not_found")
    details = dict(incident.details or {})
    anomaly_id = str(details.get("anomaly_id") or "").strip()
    anomaly = db.query(SystemAlert).filter(SystemAlert.id == anomaly_id).first() if anomaly_id else None
    chain = []
    for ref in details.get("linked_events") or []:
        node = _load_linked_event(ref, db)
        if node:
            chain.append(node)
    if anomaly:
        chain.append({"kind": "anomaly", "id": anomaly.id, "timestamp": _safe_iso(anomaly.created_at), "payload": serialize_anomaly(anomaly)})
    chain.append({"kind": "incident", "id": incident.incident_id, "timestamp": _safe_iso(incident.created_at), "payload": serialize_incident_intelligence(incident)})
    triage_rows = []
    if anomaly:
        triage_rows = db.query(AlertTriageAction).filter(AlertTriageAction.alert_id == anomaly.id).order_by(AlertTriageAction.created_at.asc()).all()
    for row in triage_rows:
        chain.append({
            "kind": "remediation",
            "id": row.id,
            "timestamp": _safe_iso(row.created_at),
            "payload": {"action_type": row.action_type, "note": row.note, "details": row.details or {}},
        })
    for item in details.get("remediation_history") or []:
        chain.append({"kind": "remediation", "id": str(uuid.uuid4()), "timestamp": item.get("executed_at"), "payload": item})
    if incident.status in {"RESOLVED", "FALSE_POSITIVE"}:
        chain.append({"kind": "resolution", "id": incident.incident_id, "timestamp": _safe_iso(incident.closed_at or incident.updated_at), "payload": {"state": incident.status}})
    return {"incident_id": incident_id, "chain": chain}


def update_incident_intelligence_state(db, *, incident_id: str, state: str, owner: str | None = None, note: str | None = None) -> dict:
    incident = db.query(DebugIncident).filter(DebugIncident.incident_id == incident_id).first()
    if incident is None:
        raise ValueError("incident_not_found")
    normalized_state = str(state or "OPEN").upper()
    if normalized_state not in {"OPEN", "INVESTIGATING", "MITIGATED", "RESOLVED", "FALSE_POSITIVE"}:
        raise ValueError("invalid_incident_state")
    incident.status = normalized_state
    if normalized_state in {"RESOLVED", "FALSE_POSITIVE"}:
        incident.closed_at = _utcnow()
    details = dict(incident.details or {})
    if owner:
        details["owner"] = owner
    if note:
        history = list(details.get("resolution_notes") or [])
        history.append({"note": note, "at": _utcnow().isoformat(), "state": normalized_state})
        details["resolution_notes"] = history
    details["state"] = normalized_state
    incident.details = details
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return serialize_incident_intelligence(incident)


def build_incident_kpis(db, *, days: int = 7) -> dict:
    since = _utcnow() - timedelta(days=max(1, days))
    rows = db.query(DebugIncident).filter(DebugIncident.created_at >= since).all()
    anomalies = db.query(SystemAlert).filter(SystemAlert.alert_type.like(f"{ANOMALY_ALERT_PREFIX}%"), SystemAlert.created_at >= since).all()
    mttd_values = []
    for anomaly in anomalies:
        details = dict(anomaly.details or {})
        first_event_at = _parse_iso(details.get("first_event_at"))
        if first_event_at and anomaly.created_at:
            mttd_values.append(max((anomaly.created_at - first_event_at).total_seconds(), 0.0))
    mttr_values = []
    for row in rows:
        if row.closed_at and row.created_at:
            mttr_values.append(max((row.closed_at - row.created_at).total_seconds(), 0.0))
    repeat_count = len([row for row in rows if int(row.occurrence_count or 0) > 1])
    return {
        "days": days,
        "incident_count": len(rows),
        "mttd_seconds": round((sum(mttd_values) / len(mttd_values)) if mttd_values else 0.0, 4),
        "mttr_seconds": round((sum(mttr_values) / len(mttr_values)) if mttr_values else 0.0, 4),
        "repeat_incident_rate": round((repeat_count / len(rows)) if rows else 0.0, 6),
    }


def build_weekly_incident_summary(db) -> dict:
    payload = build_incident_kpis(db, days=7)
    incidents = list_intelligence_incidents(db, limit=50)
    root_causes = Counter(item.get("root_cause") or "unknown" for item in incidents)
    domains = Counter((item.get("evidence") or {}).get("domain", item.get("title", "unknown")).split()[0].lower() for item in incidents)
    return {
        "generated_at": _utcnow().isoformat(),
        "kpis": payload,
        "top_root_causes": root_causes.most_common(10),
        "top_domains": domains.most_common(10),
        "top_incidents": incidents[:10],
    }


def build_correlation_graph(db, *, limit: int = 60) -> dict:
    incidents = list_intelligence_incidents(db, limit=limit)
    anomalies = list_intelligence_anomalies(db, limit=limit)
    nodes = []
    edges = []
    for anomaly in anomalies:
        nodes.append({"id": f"anomaly:{anomaly['id']}", "type": "anomaly", "domain": anomaly["domain"], "severity": anomaly["severity"]})
        for ref in anomaly.get("linked_events") or []:
            nodes.append({"id": ref, "type": "event"})
            edges.append({"source": ref, "target": f"anomaly:{anomaly['id']}", "relation": "triggers"})
    for incident in incidents:
        nodes.append({"id": f"incident:{incident['incident_id']}", "type": "incident", "severity": incident["severity"]})
        anomaly_id = (incident.get("evidence") or {}).get("anomaly_id")
        if anomaly_id:
            edges.append({"source": f"anomaly:{anomaly_id}", "target": f"incident:{incident['incident_id']}", "relation": "opens"})
    deduped_nodes = {item["id"]: item for item in nodes}
    return {"nodes": list(deduped_nodes.values()), "edges": edges}


def build_incident_predictions(db, *, days: int = 14) -> dict:
    since = _utcnow() - timedelta(days=max(1, days))
    rows = db.query(DebugIncident).filter(DebugIncident.created_at >= since).all()
    grouped: dict[str, list[DebugIncident]] = defaultdict(list)
    for row in rows:
        grouped[str(row.fingerprint or row.root_cause or row.incident_id)].append(row)
    predictions = []
    for fingerprint, items in grouped.items():
        if len(items) < 2:
            continue
        items = sorted(items, key=lambda row: row.created_at)
        risk_trend = "rising" if len(items) >= 3 else "watch"
        predictions.append(
            {
                "fingerprint": fingerprint,
                "recurrence_count": len(items),
                "predicted_risk": "HIGH" if len(items) >= 3 else "MEDIUM",
                "risk_trend": risk_trend,
                "last_seen_at": _safe_iso(items[-1].last_seen_at),
                "root_cause": items[-1].root_cause,
            }
        )
    return {"generated_at": _utcnow().isoformat(), "items": predictions}
