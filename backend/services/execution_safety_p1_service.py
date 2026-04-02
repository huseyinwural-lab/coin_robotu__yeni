from __future__ import annotations

import csv
import io
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx
from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import AuditLog, ExecutionIntent, ExecutionIntentEvent, FailedEvent, StrategyDefinition, StrategyVersion
from services.audit_service import create_audit_log


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


def _normalize_state(value: Any) -> str:
    state = str(value or "").strip().upper()
    return "CANCELED" if state == "CANCELLED" else state


def _window_delta(window: str) -> timedelta:
    normalized = str(window or "7d").strip().lower()
    if normalized == "30d":
        return timedelta(days=30)
    return timedelta(days=7)


AUTO_REMEDIATION_POLICY_FILE = Path("/app/artifacts/manifests/execution_safety_auto_remediation_policy.json")
ACTION_MAP_PLAYBOOK_TO_QUICK = {
    "bulk_retry": "retry",
    "bulk_reconcile": "reconcile",
    "bulk_cancel": "cancel",
    "escalate": "escalate",
}


def _normalize_iso_z(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        candidate = _as_utc(value)
    elif value is not None:
        try:
            candidate = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            candidate = _as_utc(candidate)
        except Exception:
            candidate = None
    else:
        candidate = None
    if not candidate:
        candidate = _utcnow()
    return candidate.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_pagination(page: int, page_size: int) -> tuple[int, int]:
    safe_page = max(int(page or 1), 1)
    safe_page_size = min(max(int(page_size or 200), 1), 2000)
    return safe_page, safe_page_size


def _paginate_rows(rows: list[dict], *, page: int = 1, page_size: int = 200) -> tuple[list[dict], dict]:
    safe_page, safe_page_size = _normalize_pagination(page, page_size)
    total_items = len(rows)
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    paginated = rows[start:end]
    total_pages = (total_items + safe_page_size - 1) // safe_page_size if total_items else 1
    return paginated, {
        "page": safe_page,
        "page_size": safe_page_size,
        "total_items": total_items,
        "total_pages": total_pages,
    }


def _csv_bytes_iterator(columns: list[str], rows: Iterable[dict]) -> Iterable[bytes]:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    yield buffer.getvalue().encode("utf-8")
    buffer.seek(0)
    buffer.truncate(0)

    for row in rows:
        writer.writerow({column: row.get(column) for column in columns})
        yield buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)


def _read_manifest(path: str, *, window: str) -> list[dict]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    cutoff = _utcnow() - _window_delta(window)
    rows: list[dict] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            created_at_raw = row.get("created_at")
            try:
                created_at = datetime.fromisoformat(str(created_at_raw).replace("Z", "+00:00"))
            except Exception:
                continue
            created_at = _as_utc(created_at)
            if not created_at or created_at < cutoff:
                continue
            row["_created_at"] = created_at
            rows.append(row)
    return rows


def analytics_gate_failures(*, window: str = "7d", page: int = 1, page_size: int = 200) -> dict:
    rows = _read_manifest("/app/artifacts/manifests/execution_safety_gate_manifest.jsonl", window=window)
    ready = 0
    degraded = 0
    blocked = 0
    timeseries: dict[str, dict[str, int]] = {}

    for row in rows:
        payload = dict(row.get("payload") or {})
        gate = dict(payload.get("gate") or payload)
        state = _normalize_state(gate.get("gate_state") or gate.get("state") or "UNKNOWN")
        day_key = row["_created_at"].strftime("%Y-%m-%d")
        bucket = timeseries.setdefault(day_key, {"ready": 0, "degraded": 0, "blocked": 0, "total": 0})
        bucket["total"] += 1
        if state == "READY":
            ready += 1
            bucket["ready"] += 1
        elif state == "BLOCKED":
            blocked += 1
            bucket["blocked"] += 1
        else:
            degraded += 1
            bucket["degraded"] += 1

    total = ready + degraded + blocked
    timeseries_rows = [
        {
            "date": day,
            "ready": payload["ready"],
            "degraded": payload["degraded"],
            "blocked": payload["blocked"],
            "total": payload["total"],
        }
        for day, payload in sorted(timeseries.items())
    ]
    paginated_rows, pagination = _paginate_rows(timeseries_rows, page=page, page_size=page_size)

    return {
        "window": window,
        "total_evaluations": total,
        "blocked_count": blocked,
        "degraded_count": degraded,
        "ready_count": ready,
        "failure_rate": round((blocked / total) if total else 0.0, 4),
        "timeseries": paginated_rows,
        "pagination": pagination,
    }


def analytics_blockers(*, window: str = "7d", page: int = 1, page_size: int = 200) -> dict:
    rows = _read_manifest("/app/artifacts/manifests/execution_safety_gate_manifest.jsonl", window=window)
    counts: dict[str, int] = {}
    distribution_by_day: dict[str, dict[str, int]] = {}
    for row in rows:
        payload = dict(row.get("payload") or {})
        gate = dict(payload.get("gate") or payload)
        blockers = gate.get("hard_blockers") or gate.get("blockers") or []
        day_key = row["_created_at"].strftime("%Y-%m-%d")
        bucket = distribution_by_day.setdefault(day_key, {})
        for blocker in blockers:
            code = str(blocker or "unknown")
            counts[code] = counts.get(code, 0) + 1
            bucket[code] = bucket.get(code, 0) + 1

    top = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    distribution_rows = [
        {"date": day, "blockers": payload}
        for day, payload in sorted(distribution_by_day.items())
    ]
    paginated_distribution, pagination = _paginate_rows(distribution_rows, page=page, page_size=page_size)

    return {
        "window": window,
        "top_blockers": [{"code": code, "count": count} for code, count in top[:20]],
        "distribution": paginated_distribution,
        "pagination": pagination,
    }


def analytics_recovery(db: Session, *, window: str = "7d", page: int = 1, page_size: int = 200) -> dict:
    cutoff = _utcnow() - _window_delta(window)
    audit_rows = (
        db.query(AuditLog)
        .filter(AuditLog.created_at >= cutoff)
        .filter(AuditLog.action.in_(["execution_bulk_recovery_item", "execution_quarantine_recovery_action", "execution_reconcile_completed"]))
        .all()
    )
    retry_total = 0
    retry_success = 0
    reconcile_total = 0
    reconcile_success = 0
    for row in audit_rows:
        details = dict(row.details or {})
        action = str(details.get("action") or row.action)
        error = details.get("error")
        if "retry" in action:
            retry_total += 1
            if not error:
                retry_success += 1
        if "reconcile" in action:
            reconcile_total += 1
            if not error:
                reconcile_success += 1

    quarantines = db.query(FailedEvent).filter(FailedEvent.created_at >= cutoff).all()
    resolved = [row for row in quarantines if row.resolved_at]
    avg_recovery_time_sec = 0.0
    if resolved:
        avg_recovery_time_sec = sum(
            max(((_as_utc(row.resolved_at) or _utcnow()) - (_as_utc(row.created_at) or _utcnow())).total_seconds(), 0)
            for row in resolved
        ) / len(resolved)

    intents_total = db.query(ExecutionIntent).filter(ExecutionIntent.created_at >= cutoff).count()
    metrics = {
        "window": window,
        "retry_success_rate": round((retry_success / retry_total) if retry_total else 0.0, 4),
        "reconcile_success_rate": round((reconcile_success / reconcile_total) if reconcile_total else 0.0, 4),
        "quarantine_rate": round((len(quarantines) / intents_total) if intents_total else 0.0, 4),
        "avg_recovery_time_sec": round(avg_recovery_time_sec, 2),
    }
    metric_rows = [{
        "window": metrics["window"],
        "retry_success_rate": metrics["retry_success_rate"],
        "reconcile_success_rate": metrics["reconcile_success_rate"],
        "quarantine_rate": metrics["quarantine_rate"],
        "avg_recovery_time_sec": metrics["avg_recovery_time_sec"],
    }]
    _, pagination = _paginate_rows(metric_rows, page=page, page_size=page_size)
    return {**metrics, "pagination": pagination}


def _severity_level_from_score(score: float) -> str:
    if score >= 0.7:
        return "HIGH"
    if score >= 0.3:
        return "MEDIUM"
    return "LOW"


def _infer_blocker_type(reason: str, anomaly_type: str) -> str:
    reason_raw = str(reason or "").lower()
    anomaly_raw = str(anomaly_type or "").upper()
    if "permission" in reason_raw:
        return "permission_error"
    if "timeout" in reason_raw:
        return "timeout"
    if "missing_fill" in reason_raw or "missing fill" in reason_raw:
        return "missing_fill"
    if "late_ack" in reason_raw or "late ack" in reason_raw:
        return "late_ack"
    if "correlation" in reason_raw or anomaly_raw == "CORRELATION_BREACH":
        return "correlation_violation"
    if anomaly_raw == "FALSE_ALLOW":
        return "false_allow"
    if anomaly_raw == "FALSE_READY":
        return "false_ready"
    return "generic"


def _derive_mismatch_severity(anomaly_type: str) -> str:
    normalized = str(anomaly_type or "").upper()
    if normalized in {"FALSE_ALLOW", "CORRELATION_BREACH"}:
        return "HIGH"
    if normalized in {"FALSE_READY"}:
        return "MEDIUM"
    return "LOW"


def _calculate_severity(
    *,
    blocker_type: str,
    mismatch_severity: str,
    retry_count: int,
    failure_stage: str,
    time_stuck_seconds: float,
    correlation_complete: bool,
) -> dict:
    blocker_weight = {
        "permission_error": 0.28,
        "correlation_violation": 0.26,
        "missing_fill": 0.21,
        "late_ack": 0.19,
        "timeout": 0.18,
        "false_allow": 0.2,
        "false_ready": 0.16,
        "generic": 0.12,
    }.get(blocker_type, 0.12)
    mismatch_weight = {"HIGH": 0.22, "MEDIUM": 0.14, "LOW": 0.06}.get(str(mismatch_severity).upper(), 0.06)
    stage_weight = {
        "CORRELATION": 0.2,
        "RISK": 0.12,
        "ORDER_SUBMIT": 0.18,
        "RECONCILE": 0.16,
        "ACK": 0.12,
        "UNKNOWN": 0.08,
    }.get(str(failure_stage or "UNKNOWN").upper(), 0.08)

    safe_retry = max(int(retry_count or 0), 0)
    retry_weight = min(safe_retry, 5) * 0.045
    stuck_weight = min(max(float(time_stuck_seconds or 0.0), 0.0) / 3600.0, 1.0) * 0.12
    correlation_weight = 0.0 if correlation_complete else 0.16

    severity_score = min(max(0.05 + blocker_weight + mismatch_weight + stage_weight + retry_weight + stuck_weight + correlation_weight, 0.0), 1.0)
    severity_level = _severity_level_from_score(severity_score)
    priority = 1 if severity_level == "HIGH" else 2 if severity_level == "MEDIUM" else 3
    impact = "execution_blocked" if severity_level == "HIGH" else "execution_risk" if severity_level == "MEDIUM" else "monitor"

    return {
        "severity_score": round(severity_score, 4),
        "severity_level": severity_level,
        "impact": impact,
        "priority": priority,
        "severity_explanation": [
            f"blocker_type={blocker_type}",
            f"mismatch_severity={mismatch_severity}",
            f"retry_count={safe_retry}",
            f"failure_stage={failure_stage or 'UNKNOWN'}",
            f"time_stuck_seconds={round(float(time_stuck_seconds or 0.0), 2)}",
            f"correlation_complete={str(bool(correlation_complete)).lower()}",
        ],
    }


def _build_recommended_actions(*, anomaly_type: str, severity_level: str, reconcile_result: str, failure_reason: str) -> list[dict]:
    normalized_type = str(anomaly_type or "").upper()
    normalized_reason = str(failure_reason or "").lower()
    normalized_reconcile = str(reconcile_result or "").lower()
    sev = str(severity_level or "LOW").upper()

    action_map: dict[str, dict] = {}

    def add_action(action: str, confidence: float, reason: str):
        bounded_confidence = min(max(confidence + (0.05 if sev == "HIGH" else 0.0), 0.0), 0.99)
        current = action_map.get(action)
        candidate = {"action": action, "confidence": round(bounded_confidence, 2), "reason": reason}
        if not current or candidate["confidence"] > current["confidence"]:
            action_map[action] = candidate

    if "late_ack" in normalized_reason or normalized_type in {"FALSE_READY", "FALSE_ALLOW"}:
        add_action("bulk_reconcile", 0.82, "late_ack_detected")
    if "missing fill" in normalized_reason or "missing_fill" in normalized_reason:
        add_action("bulk_reconcile", 0.86, "missing_fill_detected")
    if "timeout" in normalized_reason:
        add_action("bulk_retry", 0.74, "timeout_detected")
    if "permission" in normalized_reason:
        add_action("escalate", 0.9, "permission_error_detected")
    if normalized_type == "CORRELATION_BREACH":
        add_action("escalate", 0.92, "correlation_chain_breach")
        add_action("bulk_cancel", 0.66, "preventive_cancel_recommended")
    if "mismatch" in normalized_reconcile:
        add_action("bulk_reconcile", 0.78, "reconcile_mismatch_detected")

    if not action_map:
        fallback_action = "bulk_reconcile" if sev == "HIGH" else "bulk_retry"
        add_action(fallback_action, 0.58, "default_safe_recovery")

    ranked = sorted(action_map.values(), key=lambda item: item["confidence"], reverse=True)
    return ranked[:3]


def _enrich_anomaly_item(item: dict) -> dict:
    blocker_type = _infer_blocker_type(item.get("reason", ""), item.get("type", ""))
    mismatch_severity = str(item.get("mismatch_severity") or _derive_mismatch_severity(item.get("type", ""))).upper()
    retry_count = int(item.get("retry_count") or 0)
    failure_stage = str(item.get("failure_stage") or "UNKNOWN").upper()
    time_stuck_seconds = float(item.get("time_stuck_seconds") or 0.0)
    correlation_complete = bool(item.get("correlation_complete", bool(item.get("correlation_id") and item.get("intent_id"))))

    severity_payload = _calculate_severity(
        blocker_type=blocker_type,
        mismatch_severity=mismatch_severity,
        retry_count=retry_count,
        failure_stage=failure_stage,
        time_stuck_seconds=time_stuck_seconds,
        correlation_complete=correlation_complete,
    )
    recommended_actions = _build_recommended_actions(
        anomaly_type=str(item.get("type") or ""),
        severity_level=severity_payload["severity_level"],
        reconcile_result=str(item.get("reconcile_result") or ""),
        failure_reason=str(item.get("reason") or ""),
    )

    return {
        **item,
        "blocker_type": blocker_type,
        "mismatch_severity": mismatch_severity,
        "severity_score": severity_payload["severity_score"],
        "severity_level": severity_payload["severity_level"],
        "impact": severity_payload["impact"],
        "priority": severity_payload["priority"],
        "severity_explanation": severity_payload["severity_explanation"],
        "recommended_actions": recommended_actions,
        "severity": severity_payload["severity_level"],
        "risk_score": severity_payload["severity_score"],
    }


def _analytics_csv_payload(dataset: str, payload: dict) -> tuple[list[str], list[dict], str]:
    normalized_dataset = str(dataset or "").strip().lower()
    if normalized_dataset == "gate_failures":
        columns = ["timestamp", "blocked_count", "ready_count", "degraded_count", "total_count"]
        rows = [
            {
                "timestamp": f"{item.get('date')}T00:00:00Z",
                "blocked_count": item.get("blocked", 0),
                "ready_count": item.get("ready", 0),
                "degraded_count": item.get("degraded", 0),
                "total_count": item.get("total", 0),
            }
            for item in (payload.get("timeseries") or [])
        ]
        return columns, rows, "execution_safety_gate_failures.csv"

    if normalized_dataset == "blockers":
        columns = ["timestamp", "blocker_code", "count"]
        rows: list[dict] = []
        for day_row in payload.get("distribution") or []:
            day = day_row.get("date")
            blockers = dict(day_row.get("blockers") or {})
            for code, count in sorted(blockers.items()):
                rows.append(
                    {
                        "timestamp": f"{day}T00:00:00Z",
                        "blocker_code": code,
                        "count": count,
                    }
                )
        if not rows:
            rows = [
                {
                    "timestamp": "",
                    "blocker_code": item.get("code", "unknown"),
                    "count": item.get("count", 0),
                }
                for item in (payload.get("top_blockers") or [])
            ]
        return columns, rows, "execution_safety_blockers.csv"

    if normalized_dataset == "recovery":
        columns = ["timestamp", "retry_success_rate", "reconcile_success_rate", "quarantine_rate", "avg_recovery_time_sec"]
        rows = [
            {
                "timestamp": _normalize_iso_z(_utcnow()),
                "retry_success_rate": payload.get("retry_success_rate", 0),
                "reconcile_success_rate": payload.get("reconcile_success_rate", 0),
                "quarantine_rate": payload.get("quarantine_rate", 0),
                "avg_recovery_time_sec": payload.get("avg_recovery_time_sec", 0),
            }
        ]
        return columns, rows, "execution_safety_recovery.csv"

    raise ValueError("unsupported_analytics_dataset")


def stream_analytics_csv(dataset: str, payload: dict) -> tuple[Iterable[bytes], str]:
    columns, rows, filename = _analytics_csv_payload(dataset, payload)
    return _csv_bytes_iterator(columns, rows), filename


def _default_auto_remediation_policy() -> dict:
    return {
        "global_default_enabled": False,
        "low_auto_retry_max_retry_count": 1,
        "high_requires_manual_confirmation": True,
        "tenants": {},
        "updated_at": _normalize_iso_z(_utcnow()),
    }


def get_auto_remediation_policy() -> dict:
    if not AUTO_REMEDIATION_POLICY_FILE.exists():
        policy = _default_auto_remediation_policy()
        AUTO_REMEDIATION_POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTO_REMEDIATION_POLICY_FILE.write_text(json.dumps(policy, indent=2), encoding="utf-8")
        return policy
    try:
        payload = json.loads(AUTO_REMEDIATION_POLICY_FILE.read_text(encoding="utf-8"))
    except Exception:
        payload = _default_auto_remediation_policy()

    normalized = _default_auto_remediation_policy()
    normalized.update({
        "global_default_enabled": bool(payload.get("global_default_enabled", False)),
        "low_auto_retry_max_retry_count": min(max(int(payload.get("low_auto_retry_max_retry_count", 1)), 0), 10),
        "high_requires_manual_confirmation": bool(payload.get("high_requires_manual_confirmation", True)),
        "tenants": dict(payload.get("tenants") or {}),
    })
    normalized["updated_at"] = _normalize_iso_z(payload.get("updated_at") if isinstance(payload, dict) else None)
    return normalized


def _save_auto_remediation_policy(policy: dict) -> dict:
    normalized = {
        "global_default_enabled": bool(policy.get("global_default_enabled", False)),
        "low_auto_retry_max_retry_count": min(max(int(policy.get("low_auto_retry_max_retry_count", 1)), 0), 10),
        "high_requires_manual_confirmation": bool(policy.get("high_requires_manual_confirmation", True)),
        "tenants": dict(policy.get("tenants") or {}),
        "updated_at": _normalize_iso_z(_utcnow()),
    }
    AUTO_REMEDIATION_POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTO_REMEDIATION_POLICY_FILE.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return normalized


def update_auto_remediation_policy(*, global_default_enabled: bool | None = None, low_auto_retry_max_retry_count: int | None = None, high_requires_manual_confirmation: bool | None = None) -> dict:
    policy = get_auto_remediation_policy()
    if global_default_enabled is not None:
        policy["global_default_enabled"] = bool(global_default_enabled)
    if low_auto_retry_max_retry_count is not None:
        policy["low_auto_retry_max_retry_count"] = min(max(int(low_auto_retry_max_retry_count), 0), 10)
    if high_requires_manual_confirmation is not None:
        policy["high_requires_manual_confirmation"] = bool(high_requires_manual_confirmation)
    return _save_auto_remediation_policy(policy)


def set_auto_remediation_tenant_opt_in(*, tenant_id: str, enabled: bool) -> dict:
    normalized_tenant = str(tenant_id or "").strip().lower()
    if not normalized_tenant:
        raise ValueError("tenant_id_required")
    policy = get_auto_remediation_policy()
    tenants = dict(policy.get("tenants") or {})
    tenants[normalized_tenant] = {
        "enabled": bool(enabled),
        "updated_at": _normalize_iso_z(_utcnow()),
    }
    policy["tenants"] = tenants
    return _save_auto_remediation_policy(policy)


def _action_guard_for_intent(*, intent_id: str | None, intent_status: str | None) -> dict:
    base_actions = ["retry", "reconcile", "cancel", "escalate"]
    if not intent_id:
        return {
            "intent_mutable": False,
            "reason": "missing_intent",
            "allowed_actions": [],
            "blocked_actions": base_actions,
        }

    # ExecutionIntent modeli platform genelinde immutable listener ile korunuyor.
    return {
        "intent_mutable": False,
        "reason": "execution_intent_immutable",
        "intent_status": str(intent_status or "UNKNOWN").upper(),
        "allowed_actions": ["escalate"],
        "blocked_actions": ["retry", "reconcile", "cancel"],
    }


def _auto_remediation_decision(*, item: dict, policy: dict) -> dict:
    severity = str(item.get("severity_level") or item.get("severity") or "LOW").upper()
    retry_count = int(item.get("retry_count") or 0)
    tenant_id = str(item.get("tenant_id") or "default").strip().lower()
    tenant_cfg = dict((policy.get("tenants") or {}).get(tenant_id) or {})
    tenant_enabled = bool(tenant_cfg.get("enabled", bool(policy.get("global_default_enabled", False))))
    low_retry_threshold = int(policy.get("low_auto_retry_max_retry_count", 1))

    if severity == "HIGH":
        return {
            "tenant_id": tenant_id,
            "eligible": False,
            "recommended_action": None,
            "mode": "manual",
            "reason": "high_manual_required",
            "policy_snapshot": {
                "tenant_enabled": tenant_enabled,
                "retry_threshold": low_retry_threshold,
            },
        }

    if severity == "MEDIUM":
        return {
            "tenant_id": tenant_id,
            "eligible": False,
            "recommended_action": "retry",
            "mode": "manual",
            "reason": "medium_manual_recommended",
            "policy_snapshot": {
                "tenant_enabled": tenant_enabled,
                "retry_threshold": low_retry_threshold,
            },
        }

    if not tenant_enabled:
        return {
            "tenant_id": tenant_id,
            "eligible": False,
            "recommended_action": "retry",
            "mode": "manual",
            "reason": "tenant_not_opted_in",
            "policy_snapshot": {
                "tenant_enabled": tenant_enabled,
                "retry_threshold": low_retry_threshold,
            },
        }

    if retry_count <= low_retry_threshold:
        return {
            "tenant_id": tenant_id,
            "eligible": True,
            "recommended_action": "retry",
            "mode": "auto",
            "reason": f"low_retry_threshold_match({retry_count}<={low_retry_threshold})",
            "policy_snapshot": {
                "tenant_enabled": tenant_enabled,
                "retry_threshold": low_retry_threshold,
            },
        }

    return {
        "tenant_id": tenant_id,
        "eligible": False,
        "recommended_action": "retry",
        "mode": "manual",
        "reason": f"retry_threshold_exceeded({retry_count}>{low_retry_threshold})",
        "policy_snapshot": {
            "tenant_enabled": tenant_enabled,
            "retry_threshold": low_retry_threshold,
        },
    }


def get_operator_center_snapshot(db: Session, *, window: str = "7d", limit: int = 10) -> dict:
    capped_limit = min(max(int(limit or 10), 1), 50)
    anomalies_payload = detect_false_decisions(db, window=window)
    anomalies = list(anomalies_payload.get("items") or [])
    top_risky_intents = sorted(anomalies, key=lambda item: float(item.get("severity_score") or 0.0), reverse=True)[:capped_limit]

    blockers_payload = analytics_blockers(window=window, page=1, page_size=20)
    recent_failures = (
        db.query(FailedEvent)
        .order_by(FailedEvent.created_at.desc())
        .limit(10)
        .all()
    )
    recent_failure_rows = [
        {
            "failure_id": row.id,
            "entity_id": row.entity_id,
            "failure_class": row.failure_class,
            "status": row.status,
            "retry_count": row.retry_count,
            "reason": row.error_message,
            "created_at": _normalize_iso_z(row.created_at),
        }
        for row in recent_failures
    ]

    action_rollup: dict[str, dict] = {}
    for anomaly in top_risky_intents:
        for recommendation in anomaly.get("recommended_actions") or []:
            action = str(recommendation.get("action") or "unknown")
            bucket = action_rollup.setdefault(action, {"action": action, "count": 0, "avg_confidence": 0.0})
            bucket["count"] += 1
            bucket["avg_confidence"] += float(recommendation.get("confidence") or 0.0)

    recommended_actions = []
    for _, action_row in action_rollup.items():
        count = max(int(action_row["count"]), 1)
        recommended_actions.append(
            {
                "action": action_row["action"],
                "count": action_row["count"],
                "avg_confidence": round(float(action_row["avg_confidence"]) / count, 2),
            }
        )

    recommended_actions.sort(key=lambda item: (-item["count"], -item["avg_confidence"]))

    cutoff = _utcnow() - _window_delta(window)
    intervention_audits = (
        db.query(AuditLog)
        .filter(AuditLog.created_at >= cutoff)
        .filter(AuditLog.action == "execution_bulk_recovery_item")
        .all()
    )
    action_totals = len(intervention_audits)
    action_successes = len([row for row in intervention_audits if not (dict(row.details or {}).get("error"))])
    success_ratio = round((action_successes / action_totals), 4) if action_totals else 0.0

    action_daily: dict[str, dict] = {}
    for row in intervention_audits:
        day = (_as_utc(row.created_at) or _utcnow()).strftime("%Y-%m-%d")
        bucket = action_daily.setdefault(day, {"total": 0, "success": 0})
        bucket["total"] += 1
        if not (dict(row.details or {}).get("error")):
            bucket["success"] += 1
    action_success_series = [
        {
            "date": day,
            "total_actions": payload["total"],
            "successful_actions": payload["success"],
            "success_ratio": round((payload["success"] / payload["total"]) if payload["total"] else 0.0, 4),
        }
        for day, payload in sorted(action_daily.items())
    ]

    intervention_latencies: list[float] = []
    mtti_daily: dict[str, list[float]] = {}
    recent_failed_for_mtti = (
        db.query(FailedEvent)
        .filter(FailedEvent.created_at >= cutoff)
        .order_by(FailedEvent.created_at.desc())
        .limit(200)
        .all()
    )
    for failed_row in recent_failed_for_mtti:
        first_action = (
            db.query(AuditLog)
            .filter(AuditLog.action == "execution_bulk_recovery_item")
            .filter(AuditLog.created_at >= failed_row.created_at)
            .filter(AuditLog.entity_id.in_([str(failed_row.entity_id), str(failed_row.id)]))
            .order_by(AuditLog.created_at.asc())
            .first()
        )
        if not first_action:
            continue
        latency = max(((_as_utc(first_action.created_at) or _utcnow()) - (_as_utc(failed_row.created_at) or _utcnow())).total_seconds(), 0.0)
        intervention_latencies.append(latency)
        day = (_as_utc(failed_row.created_at) or _utcnow()).strftime("%Y-%m-%d")
        mtti_daily.setdefault(day, []).append(latency)
    mean_time_to_intervention = round(sum(intervention_latencies) / len(intervention_latencies), 2) if intervention_latencies else 0.0
    mtti_series = [
        {
            "date": day,
            "mean_time_to_intervention_sec": round(sum(values) / len(values), 2),
            "sample_count": len(values),
        }
        for day, values in sorted(mtti_daily.items())
    ]

    return {
        "window": window,
        "generated_at": _normalize_iso_z(_utcnow()),
        "total_anomalies": anomalies_payload.get("total_anomalies", 0),
        "top_risky_intents": top_risky_intents,
        "blocker_breakdown": blockers_payload.get("top_blockers") or [],
        "recommended_actions": recommended_actions[:6],
        "recent_failures": recent_failure_rows,
        "auto_remediation_policy": get_auto_remediation_policy(),
        "ops_metrics": {
            "mean_time_to_intervention_sec": mean_time_to_intervention,
            "action_success_ratio": success_ratio,
            "mtti_series": mtti_series,
            "action_success_series": action_success_series,
        },
    }


def get_correlation_drilldown(db: Session, *, intent_id: str, limit: int = 120) -> dict:
    normalized_intent = str(intent_id or "").strip()
    if not normalized_intent:
        raise ValueError("intent_id_required")

    intent_row = db.query(ExecutionIntent).filter(ExecutionIntent.intent_id == normalized_intent).first()
    if not intent_row:
        raise ValueError("intent_not_found")

    event_rows = (
        db.query(ExecutionIntentEvent)
        .filter(ExecutionIntentEvent.intent_id == normalized_intent)
        .order_by(ExecutionIntentEvent.created_at.asc())
        .limit(min(max(int(limit or 120), 1), 500))
        .all()
    )
    failed_rows = (
        db.query(FailedEvent)
        .filter((FailedEvent.entity_id == normalized_intent) | (FailedEvent.correlation_id == intent_row.correlation_id))
        .order_by(FailedEvent.created_at.asc())
        .limit(80)
        .all()
    )

    events = [
        {
            "event_id": row.id,
            "event_type": row.event_type,
            "event_status": row.event_status,
            "external_order_id": row.external_order_id,
            "created_at": _normalize_iso_z(row.created_at),
            "payload": row.payload or {},
        }
        for row in event_rows
    ]
    failed_events = [
        {
            "failure_id": row.id,
            "failure_class": row.failure_class,
            "status": row.status,
            "reason": row.error_message,
            "retry_count": row.retry_count,
            "created_at": _normalize_iso_z(row.created_at),
        }
        for row in failed_rows
    ]

    timeline = [
        {
            "at": entry["created_at"],
            "type": "INTENT_EVENT",
            "status": entry["event_status"],
            "title": entry["event_type"],
        }
        for entry in events
    ]
    timeline.extend(
        {
            "at": entry["created_at"],
            "type": "FAILED_EVENT",
            "status": entry["status"],
            "title": entry["failure_class"],
        }
        for entry in failed_events
    )
    timeline.sort(key=lambda item: item.get("at") or "")

    return {
        "intent_id": normalized_intent,
        "correlation_id": intent_row.correlation_id,
        "intent": {
            "status": intent_row.status,
            "symbol": intent_row.symbol,
            "side": intent_row.side,
            "quantity": intent_row.quantity,
            "created_at": _normalize_iso_z(intent_row.created_at),
        },
        "chain_links": {
            "intent": "/api/execution-safety/intents?limit=100",
            "events": f"/api/execution-safety/intents/{normalized_intent}/timeline",
            "artifact": f"/api/execution-safety/artifacts/{normalized_intent}",
            "reconcile": f"/api/execution-safety/intents/{normalized_intent}/reconcile",
            "quarantine": "/api/execution-safety/quarantine?limit=200",
        },
        "events": events,
        "failed_events": failed_events,
        "timeline": timeline,
    }


def detect_false_decisions(
    db: Session,
    *,
    window: str = "7d",
    severity: str | None = None,
    anomaly_type: str | None = None,
    page: int = 1,
    page_size: int = 200,
) -> dict:
    rows = _read_manifest("/app/artifacts/manifests/execution_safety_gate_manifest.jsonl", window=window)
    items: list[dict] = []

    for row in rows:
        payload = dict(row.get("payload") or {})
        gate = dict(payload.get("gate") or payload)
        state = _normalize_state(gate.get("gate_state") or gate.get("state") or "UNKNOWN")
        blockers = gate.get("hard_blockers") or gate.get("blockers") or []
        execution_allowed = bool(gate.get("execution_allowed") or payload.get("execution_allowed"))
        decision_type = None
        reason = None
        risk = 0.0
        if state == "READY" and blockers:
            decision_type = "FALSE_READY"
            reason = "blocker_present_but_ready"
            risk = 0.88
        elif execution_allowed and blockers:
            decision_type = "FALSE_ALLOW"
            reason = "blocker_present_but_allowed"
            risk = 0.93
        if decision_type:
            correlation_id = (payload.get("gate") or {}).get("correlation_id") or payload.get("correlation_id")
            intent_id = (payload.get("gate") or {}).get("intent_id") or payload.get("intent_id")
            event_ts = row.get("created_at")
            event_dt = _utcnow()
            if isinstance(event_ts, str) and event_ts:
                try:
                    event_dt = _as_utc(datetime.fromisoformat(event_ts.replace("Z", "+00:00"))) or _utcnow()
                except Exception:
                    event_dt = _utcnow()
            age_seconds = max((_utcnow() - (event_dt or _utcnow())).total_seconds(), 0.0)
            items.append(
                {
                    "intent_id": intent_id,
                    "correlation_id": correlation_id,
                    "tenant_id": str(payload.get("tenant_id") or payload.get("account_id") or "default").strip().lower(),
                    "type": decision_type,
                    "reason": reason,
                    "risk_score": risk,
                    "severity": "HIGH" if risk >= 0.9 else "MEDIUM",
                    "requires_manual_intervention": True,
                    "detected_at": row.get("created_at"),
                    "retry_count": int(payload.get("retry_count") or 0),
                    "failure_stage": str(payload.get("failure_stage") or "RISK").upper(),
                    "time_stuck_seconds": round(age_seconds, 2),
                    "correlation_complete": bool(correlation_id and intent_id),
                    "reconcile_result": str(payload.get("reconcile_result") or ""),
                }
            )

    cutoff = _utcnow() - _window_delta(window)
    corr_failures = (
        db.query(FailedEvent)
        .filter(FailedEvent.created_at >= cutoff)
        .filter(FailedEvent.failure_class == "correlation_violation")
        .all()
    )
    for row in corr_failures:
        event_dt = _as_utc(row.created_at) or _utcnow()
        items.append(
            {
                "intent_id": row.entity_id,
                "correlation_id": row.correlation_id,
                "tenant_id": str((row.payload or {}).get("tenant_id") or (row.payload or {}).get("account_id") or "default").strip().lower(),
                "type": "CORRELATION_BREACH",
                "reason": row.error_message,
                "risk_score": 0.91,
                "severity": "HIGH",
                "requires_manual_intervention": True,
                "detected_at": _normalize_iso_z(row.created_at),
                "retry_count": row.retry_count,
                "failure_stage": str((row.error_details or {}).get("failure_stage") or "CORRELATION").upper(),
                "time_stuck_seconds": round(max((_utcnow() - event_dt).total_seconds(), 0.0), 2),
                "correlation_complete": bool(row.correlation_id and row.entity_id),
                "reconcile_result": str((row.error_details or {}).get("reconcile_result") or ""),
            }
        )

    unresolved_correlation_ids = {
        str(item.get("correlation_id"))
        for item in items
        if not item.get("intent_id") and item.get("correlation_id")
    }
    if unresolved_correlation_ids:
        mapping_rows = (
            db.query(ExecutionIntent.intent_id, ExecutionIntent.correlation_id, ExecutionIntent.status, ExecutionIntent.account_id)
            .filter(ExecutionIntent.correlation_id.in_(list(unresolved_correlation_ids)))
            .all()
        )
        correlation_to_intent = {row.correlation_id: row.intent_id for row in mapping_rows if row.correlation_id and row.intent_id}
        for item in items:
            if not item.get("intent_id") and item.get("correlation_id"):
                item["intent_id"] = correlation_to_intent.get(str(item.get("correlation_id")))

    intent_ids = [str(item.get("intent_id")) for item in items if item.get("intent_id")]
    intent_status_map: dict[str, str] = {}
    intent_account_map: dict[str, str] = {}
    if intent_ids:
        intent_rows = (
            db.query(ExecutionIntent.intent_id, ExecutionIntent.status, ExecutionIntent.account_id)
            .filter(ExecutionIntent.intent_id.in_(list(set(intent_ids))))
            .all()
        )
        intent_status_map = {row.intent_id: str(row.status or "UNKNOWN").upper() for row in intent_rows if row.intent_id}
        intent_account_map = {row.intent_id: str(row.account_id or "default").strip().lower() for row in intent_rows if row.intent_id}

    policy = get_auto_remediation_policy()
    enriched_items: list[dict] = []
    for item in items:
        intent_id = str(item.get("intent_id") or "").strip() or None
        if intent_id and not item.get("tenant_id"):
            item["tenant_id"] = intent_account_map.get(intent_id, "default")
        intent_status = intent_status_map.get(intent_id) if intent_id else None
        item["intent_status"] = intent_status

        enriched = _enrich_anomaly_item(item)
        action_guard = _action_guard_for_intent(intent_id=intent_id, intent_status=intent_status)
        enriched["action_guard"] = action_guard
        enriched["allowed_actions"] = list(action_guard.get("allowed_actions") or [])
        enriched["blocked_actions"] = list(action_guard.get("blocked_actions") or [])
        enriched["playbook_primary_action"] = None
        for recommendation in enriched.get("recommended_actions") or []:
            mapped_action = ACTION_MAP_PLAYBOOK_TO_QUICK.get(str(recommendation.get("action") or "").strip().lower())
            if mapped_action:
                enriched["playbook_primary_action"] = mapped_action
                break
        enriched["auto_remediation"] = _auto_remediation_decision(item=enriched, policy=policy)
        enriched_items.append(enriched)

    items = enriched_items

    if severity:
        items = [item for item in items if str(item.get("severity_level") or item.get("severity") or "").upper() == str(severity).upper()]
    if anomaly_type:
        items = [item for item in items if str(item.get("type") or "").upper() == str(anomaly_type).upper()]

    items.sort(
        key=lambda item: (
            int(item.get("priority") or 99),
            -float(item.get("severity_score") or 0.0),
            str(item.get("detected_at") or ""),
        )
    )
    paginated_items, pagination = _paginate_rows(items, page=page, page_size=page_size)

    return {
        "window": window,
        "total_anomalies": len(items),
        "items": paginated_items,
        "pagination": pagination,
    }


def _bybit_market_read(symbol: str) -> dict:
    load_dotenv("/app/backend/.env", override=True)
    base_url = str(os.environ.get("BYBIT_LIVE_BASE_URL") or "https://api-live.bybit.com").strip()
    try:
        ticker_resp = httpx.get(
            f"{base_url}/v5/market/tickers",
            params={"category": "linear", "symbol": symbol},
            timeout=10,
        )
        book_resp = httpx.get(
            f"{base_url}/v5/market/orderbook",
            params={"category": "linear", "symbol": symbol, "limit": 5},
            timeout=10,
        )
        ticker_data = ticker_resp.json() if ticker_resp.status_code == 200 else {}
        book_data = book_resp.json() if book_resp.status_code == 200 else {}
        mark_price = _safe_float((((ticker_data.get("result") or {}).get("list") or [{}])[0]).get("markPrice"), 0.0)
        bid = _safe_float((((book_data.get("result") or {}).get("b") or [[0]])[0])[0], 0.0)
        ask = _safe_float((((book_data.get("result") or {}).get("a") or [[0]])[0])[0], 0.0)
        return {
            "ok": ticker_resp.status_code == 200 and book_resp.status_code == 200 and mark_price > 0,
            "mark_price": mark_price,
            "best_bid": bid,
            "best_ask": ask,
            "degrade_mode": not (ticker_resp.status_code == 200 and book_resp.status_code == 200),
            "http_status": {"ticker": ticker_resp.status_code, "orderbook": book_resp.status_code},
            "base_url": base_url,
        }
    except Exception as exc:
        return {
            "ok": False,
            "mark_price": 0.0,
            "best_bid": 0.0,
            "best_ask": 0.0,
            "degrade_mode": True,
            "error": str(exc),
            "base_url": base_url,
        }


def _create_simulation_events(db: Session, *, intent_id: str, mode: str, payload: dict) -> None:
    db.add(
        ExecutionIntentEvent(
            id=str(uuid.uuid4()),
            intent_id=intent_id,
            event_type="EXECUTION_SIMULATION_SIGNAL",
            event_status="CREATED",
            payload={"mode": mode, **payload},
        )
    )
    db.add(
        ExecutionIntentEvent(
            id=str(uuid.uuid4()),
            intent_id=intent_id,
            event_type="EXECUTION_SIMULATION_DECISION",
            event_status="SUBMITTED",
            payload={"mode": mode, **payload},
        )
    )
    db.add(
        ExecutionIntentEvent(
            id=str(uuid.uuid4()),
            intent_id=intent_id,
            event_type="EXECUTION_SIMULATION_RISK",
            event_status="ACKED",
            payload={"mode": mode, **payload},
        )
    )


def _ensure_simulation_strategy_seed(db: Session, *, requested_by: str) -> tuple[str, str]:
    strategy_id = "execution_safety_simulation"
    strategy_version_id = "execution_safety_simulation_v1"

    strategy = db.query(StrategyDefinition).filter(StrategyDefinition.strategy_id == strategy_id).first()
    if not strategy:
        strategy = StrategyDefinition(
            strategy_id=strategy_id,
            name="Execution Safety Simulation",
            code="execution_safety_simulation",
            description="Synthetic strategy for execution safety dry-run/shadow simulation",
            owner_type="system",
            owner_name="execution-safety",
            category="execution_safety",
            tags=["simulation", "dry-run", "shadow"],
            created_by=requested_by,
            status="active",
            active_version_id=strategy_version_id,
        )
        db.add(strategy)
    elif not strategy.active_version_id:
        strategy.active_version_id = strategy_version_id

    version = db.query(StrategyVersion).filter(StrategyVersion.version_id == strategy_version_id).first()
    if not version:
        version = StrategyVersion(
            version_id=strategy_version_id,
            strategy_id=strategy_id,
            version_number=1,
            config_json={
                "engine": "execution_safety_p1",
                "mode": "simulation",
                "supports": ["dry-run", "shadow"],
            },
            config_schema_version="1.0",
            created_by=requested_by,
            version_hash=uuid.uuid4().hex,
        )
        db.add(version)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        strategy = db.query(StrategyDefinition).filter(StrategyDefinition.strategy_id == strategy_id).first()
        version = db.query(StrategyVersion).filter(StrategyVersion.version_id == strategy_version_id).first()
        if not strategy or not version:
            raise

    return strategy_id, strategy_version_id


def run_execution_simulation(
    db: Session,
    *,
    mode: str,
    symbol: str = "BTCUSDT",
    qty: float = 0.001,
    side: str = "BUY",
    requested_by: str,
) -> dict:
    normalized_mode = str(mode or "dry-run").strip().lower()
    if normalized_mode not in {"dry-run", "shadow"}:
        raise ValueError("invalid_mode")

    market = _bybit_market_read(symbol)
    mark = market.get("mark_price") or 0.0
    if mark <= 0:
        mark = 1000.0
    spread = max((market.get("best_ask") or mark) - (market.get("best_bid") or mark), 0.0)
    slippage = round(min(max(spread / mark if mark else 0.001, 0.0005), 0.01), 6)
    expected_fill = mark * (1 + slippage if str(side).upper() == "BUY" else 1 - slippage)
    expected_pnl = round((expected_fill - mark) * qty * (1 if str(side).upper() == "BUY" else -1), 4)
    notional = round(expected_fill * qty, 4)
    confidence = 0.88 if market.get("ok") else 0.62

    strategy_id, strategy_version_id = _ensure_simulation_strategy_seed(db, requested_by=requested_by)

    correlation_id = f"sim-{normalized_mode}-{uuid.uuid4().hex[:16]}"
    intent_id = f"sim-intent-{uuid.uuid4().hex[:16]}"
    intent = ExecutionIntent(
        intent_id=intent_id,
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        account_id="simulation",
        symbol=symbol,
        side=str(side).upper(),
        order_type="MARKET",
        quantity=qty,
        price_reference={"mode": normalized_mode, "mark_price": mark},
        decision_hash=uuid.uuid4().hex,
        context_hash=uuid.uuid4().hex,
        intent_hash=uuid.uuid4().hex,
        correlation_id=correlation_id,
        status="RECONCILED" if normalized_mode == "shadow" else "ACKED",
        metadata={"simulation_mode": normalized_mode, "degrade_mode": bool(market.get("degrade_mode"))},
    )
    db.add(intent)
    db.flush()

    _create_simulation_events(
        db,
        intent_id=intent_id,
        mode=normalized_mode,
        payload={
            "request_id": f"req-{uuid.uuid4().hex[:16]}",
            "execution_id": f"exe-{uuid.uuid4().hex[:16]}",
            "session_id": f"ses-{uuid.uuid4().hex[:16]}",
            "correlation_id": correlation_id,
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "expected_fill_price": expected_fill,
        },
    )
    db.commit()

    create_audit_log(
        db,
        action=f"execution_simulation_{normalized_mode}",
        entity_type="execution_intent",
        entity_id=intent_id,
        actor_user_id=requested_by,
        actor_role="user",
        severity="info",
        details={
            "actor_type": "user",
            "actor_id": requested_by,
            "action": normalized_mode,
            "target_type": "execution_intent",
            "target_id": intent_id,
            "reason": "simulation_run",
            "before_state": "CREATED",
            "after_state": intent.status,
            "correlation_id": correlation_id,
        },
    )

    return {
        "mode": normalized_mode,
        "symbol": symbol,
        "qty": qty,
        "side": str(side).upper(),
        "expected_fill_price": round(expected_fill, 4),
        "expected_slippage": slippage,
        "expected_pnl": expected_pnl,
        "risk_exposure": {
            "notional": notional,
            "max_drawdown_estimate": round(notional * 0.015, 4),
            "leverage_assumed": 1,
        },
        "divergence_from_real_market": {
            "mark_price": round(mark, 4),
            "abs_diff": round(abs(expected_fill - mark), 6),
            "pct_diff": round(abs(expected_fill - mark) / mark if mark else 0.0, 6),
        },
        "degrade_mode": bool(market.get("degrade_mode")),
        "confidence": round(confidence, 2),
        "intent_id": intent_id,
        "correlation_id": correlation_id,
    }
