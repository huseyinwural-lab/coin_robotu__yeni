from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import mean
import logging

from sqlalchemy.orm import Session

from models import (
    AuditLog,
    User,
    UserKycDocument,
    UserOnboardingDecisionLog,
    UserOnboardingProfile,
    UserOnboardingWorkflowCase,
    UserOnboardingWorkflowStepLog,
    UserRole,
)
from services.observability_service import _window_observations


logger = logging.getLogger("onboarding_observability")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(item) for item in values)
    rank = max(0, min(len(ordered) - 1, int(round((percentile / 100) * (len(ordered) - 1)))))
    return float(ordered[rank])


def _safe_rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 2)


def _reject_bucket(reason: str) -> str:
    value = str(reason or "").strip()
    if not value:
        return "unknown"
    if ":" in value:
        return value.split(":", 1)[0].strip().lower() or "unknown"
    return value[:80].lower()


def build_onboarding_observability_summary(db: Session, *, days: int = 30) -> dict:
    now = _utcnow()
    window_days = max(1, int(days or 30))
    cutoff = now - timedelta(days=window_days)

    users = db.query(User).filter(User.role == UserRole.USER, User.created_at >= cutoff).all()
    user_ids = [row.id for row in users]
    signup_count = len(users)

    docs_user_ids: set[str] = set()
    if user_ids:
        docs_rows = (
            db.query(UserKycDocument.user_id)
            .filter(UserKycDocument.user_id.in_(user_ids), UserKycDocument.uploaded_at >= cutoff)
            .all()
        )
        docs_user_ids = {str(row[0]) for row in docs_rows if row and row[0]}

    profiles = []
    if user_ids:
        profiles = db.query(UserOnboardingProfile).filter(UserOnboardingProfile.user_id.in_(user_ids)).all()
    profile_map = {str(row.user_id): row for row in profiles}

    kyc_started_count = 0
    kyc_verified_count = 0
    for uid in user_ids:
        profile = profile_map.get(str(uid))
        kyc_status = str(getattr(profile, "kyc_status", "pending") or "pending").lower()
        has_started = str(uid) in docs_user_ids or kyc_status in {"verified", "rejected"}
        if has_started:
            kyc_started_count += 1
        if kyc_status == "verified":
            kyc_verified_count += 1

    approved_count = len([row for row in users if str(row.approval_status) == "approved"])
    activated_count = len([row for row in users if str(row.approval_status) == "approved" and bool(row.is_active)])

    decision_logs = db.query(UserOnboardingDecisionLog).filter(UserOnboardingDecisionLog.created_at >= cutoff).all()
    total_decisions = len(decision_logs)
    approved_decisions = len([row for row in decision_logs if str(row.decision) == "approved"])
    rejected_logs = [row for row in decision_logs if str(row.decision) == "rejected"]

    approval_rate = _safe_rate(approved_decisions, total_decisions)
    avg_approval_minutes_values = [
        (row.approved_at - row.created_at).total_seconds() / 60
        for row in users
        if row.approved_at is not None and row.created_at is not None and str(row.approval_status) == "approved"
    ]
    avg_approval_time = round(float(mean(avg_approval_minutes_values)), 2) if avg_approval_minutes_values else 0.0

    reject_distribution_counter = Counter(_reject_bucket(row.reason) for row in rejected_logs)
    reject_distribution = [
        {"reason": reason, "count": int(count), "ratio": _safe_rate(count, len(rejected_logs))}
        for reason, count in reject_distribution_counter.most_common()
    ]

    workflow_cases = db.query(UserOnboardingWorkflowCase).filter(UserOnboardingWorkflowCase.created_at >= cutoff).all()
    workflow_case_count = len(workflow_cases)
    breached_cases = len([row for row in workflow_cases if int(row.escalation_count or 0) > 0 or bool(row.supervisor_queue)])
    sla_breach_rate = _safe_rate(breached_cases, workflow_case_count)

    workflow_log_count = (
        db.query(UserOnboardingWorkflowStepLog)
        .filter(UserOnboardingWorkflowStepLog.created_at >= cutoff)
        .count()
    )
    decision_audit_count = (
        db.query(AuditLog)
        .filter(AuditLog.created_at >= cutoff, AuditLog.action == "onboarding_decision_committed")
        .count()
    )

    reconcile_mismatch_reasons: list[str] = []
    if int(decision_audit_count) != int(total_decisions):
        reconcile_mismatch_reasons.append("decision_audit_count_mismatch")
    if workflow_case_count > 0 and workflow_log_count == 0:
        reconcile_mismatch_reasons.append("workflow_log_missing")
    status = "degraded" if reconcile_mismatch_reasons else "ok"

    minutes = max(5, min(window_days * 24 * 60, 1440))
    obs_rows = _window_observations(minutes)
    onboarding_latencies = [
        float(row.get("duration_ms") or 0)
        for row in obs_rows
        if "/api/admin/onboarding" in str(row.get("path") or "")
        or "/api/admin/user-approvals" in str(row.get("path") or "")
    ]
    if not onboarding_latencies:
        onboarding_latencies = [float(row.get("duration_ms") or 0) for row in obs_rows]

    p50_ms = round(_percentile(onboarding_latencies, 50), 2)
    p95_ms = round(_percentile(onboarding_latencies, 95), 2)
    p99_ms = round(_percentile(onboarding_latencies, 99), 2)

    threshold_warning_ms = 2000
    threshold_error_ms = 5000
    telemetry_status = "healthy"
    if p95_ms >= threshold_error_ms:
        telemetry_status = "error"
        logger.error("onboarding_observability_latency_threshold_exceeded", extra={"p95_ms": p95_ms, "threshold_ms": threshold_error_ms})
    elif p95_ms >= threshold_warning_ms:
        telemetry_status = "warning"
        logger.warning("onboarding_observability_latency_warning", extra={"p95_ms": p95_ms, "threshold_ms": threshold_warning_ms})

    funnel = {
        "signup": int(signup_count),
        "kyc_started": int(kyc_started_count),
        "kyc_verified": int(kyc_verified_count),
        "approved": int(approved_count),
        "activated": int(activated_count),
    }
    drop_off_rate = _safe_rate(max(signup_count - activated_count, 0), signup_count)

    return {
        "status": status,
        "window": {"days": window_days, "from": cutoff.isoformat(), "to": now.isoformat()},
        "kpis": {
            "approval_rate": approval_rate,
            "avg_approval_time": avg_approval_time,
            "reject_distribution": reject_distribution,
            "funnel": funnel,
            "drop_off_rate": drop_off_rate,
            "sla_breach_rate": sla_breach_rate,
        },
        "reconcile": {
            "decision_logs": int(total_decisions),
            "decision_audit_logs": int(decision_audit_count),
            "workflow_cases": int(workflow_case_count),
            "workflow_logs": int(workflow_log_count),
            "mismatch_reasons": reconcile_mismatch_reasons,
        },
        "telemetry": {
            "percentiles_ms": {"p50": p50_ms, "p95": p95_ms, "p99": p99_ms},
            "thresholds_ms": {"warning": threshold_warning_ms, "error": threshold_error_ms},
            "status": telemetry_status,
        },
    }
