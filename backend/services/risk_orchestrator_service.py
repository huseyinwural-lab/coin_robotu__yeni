from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import RLock
from time import monotonic
from typing import Iterable
from uuid import uuid4

import sqlalchemy as sa
from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import (
    AdminControl,
    AuditLog,
    ExecutionMetric,
    ExecutionIntent,
    ExecutionIntentEvent,
    Position,
    RiskOrchestratorApprovalRequest,
    RiskOrchestratorAutoTriggerLog,
    RiskOrchestratorDecisionTrace,
    RiskOrchestratorInterventionLog,
    RiskOrchestratorManualOverride,
    RiskOrchestratorPolicy,
    RiskOrchestratorPolicyChangeRequest,
    RiskOrchestratorPolicySimulation,
    RiskOrchestratorPolicyVersion,
    SystemAlert,
    User,
)
from services.audit_service import create_audit_log
from services.execution_safety_service import execution_safety_snapshot, update_execution_safety_state
from services.runtime_execution_service import map_decision_to_intent
from services.system_alert_service import create_system_alert


def _now() -> datetime:
    return datetime.now(timezone.utc)


POLICY_FIELDS = [
    "reference_equity_usd",
    "account_max_notional_pct",
    "symbol_max_notional_pct",
    "strategy_max_concurrent_positions",
    "strategy_cooldown_seconds",
    "max_order_frequency_per_min",
    "max_order_burst_per_10s",
    "daily_loss_limit_pct",
    "duplicate_suppression_window_seconds",
]

RISK_SCORE_WEIGHTS = {
    "exposure": 0.35,
    "reject_rate": 0.20,
    "daily_loss_proximity": 0.20,
    "concurrent_impact": 0.15,
    "volatility": 0.10,
}

APPROVAL_TIMEOUT_MINUTES = 10
OVERRIDE_EXPIRY_ALERT_MINUTES = 5
OVERRIDE_ACTIVE_LIMIT = 12
OVERRIDE_TOTAL_NOTIONAL_LIMIT = 200.0
APPROVER_PENDING_LIMIT = 8
STUCK_APPROVAL_MINUTES = 4
QUEUE_CACHE_TTL_SECONDS = 5
DASHBOARD_CACHE_TTL_SECONDS = 8
GOVERNANCE_QUORUM_WEIGHT = 3
GOVERNANCE_MIN_DISTINCT_APPROVERS = 2
GOVERNANCE_ROLE_WEIGHTS = {
    "super_admin": 2,
    "admin": 1,
    "ops": 1,
}

_cache_lock = RLock()
_queue_cache: dict[tuple, dict] = {}
_dashboard_cache: dict[tuple, dict] = {}
_inflight_operation_lock = RLock()
_inflight_operations: set[str] = set()


def _clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    return max(min_value, min(max_value, value))


def _role_value(raw_role: str | object | None) -> str:
    if raw_role is None:
        return "admin"
    return str(raw_role.value if hasattr(raw_role, "value") else raw_role)


def _cache_get(cache_store: dict[tuple, dict], key: tuple):
    with _cache_lock:
        item = cache_store.get(key)
        if not item:
            return None
        if float(item.get("expires_at") or 0) <= monotonic():
            cache_store.pop(key, None)
            return None
        return deepcopy(item.get("value"))


def _cache_set(cache_store: dict[tuple, dict], key: tuple, value, ttl_seconds: int) -> None:
    with _cache_lock:
        cache_store[key] = {
            "value": deepcopy(value),
            "expires_at": monotonic() + ttl_seconds,
        }


def _invalidate_operational_cache() -> None:
    with _cache_lock:
        _queue_cache.clear()
        _dashboard_cache.clear()


@contextmanager
def _operation_guard(lock_key: str):
    with _inflight_operation_lock:
        if lock_key in _inflight_operations:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="operation_in_progress")
        _inflight_operations.add(lock_key)
    try:
        yield
    finally:
        with _inflight_operation_lock:
            _inflight_operations.discard(lock_key)


def _predictive_risk_signal(db: Session) -> dict:
    now_ts = _now()
    recent_window_start = now_ts - timedelta(minutes=15)
    previous_window_start = now_ts - timedelta(minutes=30)

    recent_breaches = (
        db.query(SystemAlert)
        .filter(
            SystemAlert.alert_type.in_(["risk_orchestrator_breach", "daily_loss_limit_hit", "exposure_limit_breach"]),
            SystemAlert.created_at >= recent_window_start,
        )
        .count()
    )
    previous_breaches = (
        db.query(SystemAlert)
        .filter(
            SystemAlert.alert_type.in_(["risk_orchestrator_breach", "daily_loss_limit_hit", "exposure_limit_breach"]),
            SystemAlert.created_at >= previous_window_start,
            SystemAlert.created_at < recent_window_start,
        )
        .count()
    )

    pending_critical = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(
            RiskOrchestratorApprovalRequest.state.in_(["pending", "assigned"]),
            RiskOrchestratorApprovalRequest.classification == "CRITICAL",
        )
        .count()
    )
    pending_total = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(RiskOrchestratorApprovalRequest.state.in_(["pending", "assigned"]))
        .count()
    )
    queue_pressure_pct = (pending_critical / max(pending_total, 1)) * 100 if pending_total else 0

    vol_recent = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.created_at >= recent_window_start)
        .order_by(ExecutionMetric.created_at.desc())
        .limit(80)
        .all()
    )
    vol_previous = (
        db.query(ExecutionMetric)
        .filter(
            ExecutionMetric.created_at >= previous_window_start,
            ExecutionMetric.created_at < recent_window_start,
        )
        .order_by(ExecutionMetric.created_at.desc())
        .limit(80)
        .all()
    )
    avg_recent_vol = (
        sum(float(item.volatility_pct or 0) for item in vol_recent) / max(len(vol_recent), 1)
        if vol_recent
        else 0.0
    )
    avg_previous_vol = (
        sum(float(item.volatility_pct or 0) for item in vol_previous) / max(len(vol_previous), 1)
        if vol_previous
        else avg_recent_vol
    )
    volatility_acceleration_pct = ((avg_recent_vol - avg_previous_vol) / max(avg_previous_vol, 1)) * 100

    breach_trend_pct = (
        ((recent_breaches - previous_breaches) / max(previous_breaches, 1)) * 100
        if previous_breaches
        else (100.0 if recent_breaches >= 3 else recent_breaches * 20.0)
    )

    predictive_score = _clamp(
        (max(0.0, breach_trend_pct) * 0.45)
        + (queue_pressure_pct * 0.35)
        + (max(0.0, volatility_acceleration_pct) * 0.20),
        0,
        100,
    )

    return {
        "predictive_score": round(predictive_score, 2),
        "recent_breach_count": recent_breaches,
        "previous_breach_count": previous_breaches,
        "breach_trend_pct": round(breach_trend_pct, 2),
        "pending_critical": pending_critical,
        "pending_total": pending_total,
        "queue_pressure_pct": round(queue_pressure_pct, 2),
        "avg_recent_volatility": round(avg_recent_vol, 2),
        "avg_previous_volatility": round(avg_previous_vol, 2),
        "volatility_acceleration_pct": round(volatility_acceleration_pct, 2),
    }


def _governance_policy() -> dict:
    return {
        "enabled": True,
        "quorum_weight": GOVERNANCE_QUORUM_WEIGHT,
        "min_distinct_approvers": GOVERNANCE_MIN_DISTINCT_APPROVERS,
        "role_weights": deepcopy(GOVERNANCE_ROLE_WEIGHTS),
    }


def _governance_vote_progress(context_payload: dict | None) -> dict:
    payload = context_payload or {}
    votes = payload.get("governance_votes") or []
    approved_votes = [item for item in votes if (item.get("decision") or "").lower() == "approve"]
    unique_voters = {str(item.get("actor_id")) for item in votes if item.get("actor_id")}
    total_weight = sum(int(item.get("weight") or 0) for item in votes)
    return {
        "votes": votes,
        "approved_vote_count": len(approved_votes),
        "total_weight": total_weight,
        "distinct_voter_count": len(unique_voters),
        "quorum_weight": int(payload.get("governance_policy", {}).get("quorum_weight") or GOVERNANCE_QUORUM_WEIGHT),
        "min_distinct_approvers": int(
            payload.get("governance_policy", {}).get("min_distinct_approvers") or GOVERNANCE_MIN_DISTINCT_APPROVERS
        ),
    }


def _classification_from_score(score: float) -> str:
    if score <= 40:
        return "SAFE"
    if score <= 70:
        return "WARNING"
    return "CRITICAL"


def _approval_flow_from_classification(classification: str) -> dict:
    if classification == "SAFE":
        return {
            "requires_double_confirm": False,
            "requires_second_approval": False,
            "default_blocked": False,
            "rule_path": "SAFE_DIRECT_APPLY",
        }
    if classification == "WARNING":
        return {
            "requires_double_confirm": True,
            "requires_second_approval": False,
            "default_blocked": False,
            "rule_path": "WARNING_DOUBLE_CONFIRM",
        }
    return {
        "requires_double_confirm": True,
        "requires_second_approval": True,
        "default_blocked": True,
        "rule_path": "CRITICAL_BLOCK_OR_4_EYES_OVERRIDE",
    }


def _current_policy_version(policy: RiskOrchestratorPolicy) -> int:
    return int(getattr(policy, "policy_version", 1) or 1)


def _approval_ui_link(approval_id: str) -> str:
    return f"/admin/risk-orchestrator?tab=approvals&approval_id={approval_id}"


def _emit_approval_event(
    db: Session,
    *,
    event_type: str,
    request: RiskOrchestratorApprovalRequest,
    actor_id: str | None,
    reason: str,
    extra: dict | None = None,
    severity: str = "INFO",
) -> None:
    details = {
        "request_id": request.approval_id,
        "risk_score": float(request.risk_score or 0),
        "classification": request.classification,
        "actor": actor_id,
        "reason": reason,
        "link_to_ui": _approval_ui_link(request.approval_id),
        "state": request.state,
        "assigned_to": request.assigned_to,
        "requested_by": request.requested_by,
    }
    if extra:
        details.update(extra)

    create_system_alert(
        db,
        alert_type=event_type,
        severity=severity,
        message=f"Approval event: {event_type}",
        details=details,
        entity_key=request.approval_id,
        root_cause_code=event_type,
        state_key=f"approval_event_{event_type}_{request.approval_id}",
    )


def _eligible_approvers(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(
            User.is_active.is_(True),
            User.role.in_(["super_admin", "admin", "ops"]),
        )
        .order_by(User.created_at.asc())
        .all()
    )


def _approver_pending_count(db: Session, *, approver_id: str) -> int:
    return (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(
            RiskOrchestratorApprovalRequest.state.in_(["pending", "assigned"]),
            RiskOrchestratorApprovalRequest.assigned_to == approver_id,
        )
        .count()
    )


def _select_auto_assignee(
    db: Session,
    *,
    requested_by: str,
    classification: str,
    exclude_ids: set[str] | None = None,
    allow_requester_fallback: bool = True,
) -> User | None:
    excluded = exclude_ids or set()
    candidates = [item for item in _eligible_approvers(db) if item.id != requested_by and item.id not in excluded]
    if not candidates:
        if not allow_requester_fallback:
            return None
        fallback = db.query(User).filter(User.id == requested_by, User.is_active.is_(True)).first()
        if fallback is None:
            return None
        if (
            _approver_pending_count(db, approver_id=fallback.id) >= APPROVER_PENDING_LIMIT
            and classification != "CRITICAL"
        ):
            return None
        return fallback

    role_priority = ["super_admin", "admin", "ops"]
    if classification == "CRITICAL":
        role_priority = ["super_admin", "admin", "ops"]
    elif classification == "WARNING":
        role_priority = ["admin", "super_admin", "ops"]

    role_ordered: list[User] = []
    for role in role_priority:
        role_ordered.extend([item for item in candidates if str(item.role.value if hasattr(item.role, "value") else item.role) == role])

    if not role_ordered:
        role_ordered = candidates

    scored: list[tuple[int, datetime, User]] = []
    for candidate in role_ordered:
        pending_count = _approver_pending_count(db, approver_id=candidate.id)
        if pending_count >= APPROVER_PENDING_LIMIT and classification != "CRITICAL":
            continue
        last_assigned = (
            db.query(RiskOrchestratorApprovalRequest)
            .filter(RiskOrchestratorApprovalRequest.assigned_to == candidate.id)
            .order_by(RiskOrchestratorApprovalRequest.assigned_at.desc())
            .first()
        )
        assigned_at = last_assigned.assigned_at if last_assigned and last_assigned.assigned_at else datetime.fromtimestamp(0, tz=timezone.utc)
        scored.append((pending_count, assigned_at, candidate))

    if not scored:
        fallback_scored: list[tuple[int, datetime, User]] = []
        for candidate in role_ordered:
            pending_count = _approver_pending_count(db, approver_id=candidate.id)
            last_assigned = (
                db.query(RiskOrchestratorApprovalRequest)
                .filter(RiskOrchestratorApprovalRequest.assigned_to == candidate.id)
                .order_by(RiskOrchestratorApprovalRequest.assigned_at.desc())
                .first()
            )
            assigned_at = last_assigned.assigned_at if last_assigned and last_assigned.assigned_at else datetime.fromtimestamp(0, tz=timezone.utc)
            fallback_scored.append((pending_count, assigned_at, candidate))
        if not fallback_scored:
            return None
        fallback_scored.sort(key=lambda item: (item[0], item[1]))
        return fallback_scored[0][2]

    scored.sort(key=lambda item: (item[0], item[1]))
    return scored[0][2]


def _ensure_critical_queue_ownership(
    db: Session,
    *,
    request: RiskOrchestratorApprovalRequest,
    actor_id: str | None,
) -> RiskOrchestratorApprovalRequest:
    if request.classification != "CRITICAL":
        return request
    if request.state not in {"pending", "assigned"}:
        return request

    should_reassign = request.assigned_to is None
    if request.assigned_to:
        assigned_user = (
            db.query(User)
            .filter(User.id == request.assigned_to)
            .first()
        )
        pending_count = _approver_pending_count(db, approver_id=request.assigned_to)
        if assigned_user is None or not assigned_user.is_active or pending_count > (APPROVER_PENDING_LIMIT + 2):
            should_reassign = True

    if not should_reassign:
        return request

    selected = _select_auto_assignee(
        db,
        requested_by=request.requested_by,
        classification=request.classification,
        exclude_ids={request.assigned_to} if request.assigned_to else None,
        allow_requester_fallback=True,
    )
    if selected is None:
        selected = db.query(User).filter(User.id == request.requested_by, User.is_active.is_(True)).first()

    if selected is None:
        create_system_alert(
            db,
            alert_type="approval_owner_unresolved",
            severity="CRITICAL",
            message="Critical approval request owner could not be resolved",
            details={
                "request_id": request.approval_id,
                "requested_by": request.requested_by,
                "state": request.state,
            },
            entity_key=request.approval_id,
            root_cause_code="critical_owner_unresolved",
            state_key=f"approval_owner_unresolved_{request.approval_id}",
        )
        db.commit()
        return request

    if request.assigned_to == selected.id and request.state == "assigned":
        return request

    return _assign_approval_request(
        db,
        request=request,
        assignee_id=selected.id,
        actor_id=actor_id,
        auto_assigned=True,
        allow_over_capacity=True,
    )


def _assign_approval_request(
    db: Session,
    *,
    request: RiskOrchestratorApprovalRequest,
    assignee_id: str,
    actor_id: str | None,
    auto_assigned: bool,
    allow_over_capacity: bool = False,
) -> RiskOrchestratorApprovalRequest:
    pending_count = _approver_pending_count(db, approver_id=assignee_id)
    if pending_count >= APPROVER_PENDING_LIMIT and not allow_over_capacity:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approver_pending_limit_reached")

    request.assigned_to = assignee_id
    request.assigned_at = _now()
    request.auto_assigned = auto_assigned
    request.last_activity_at = _now()
    request.state = "assigned"
    request.updated_at = _now()
    db.commit()
    _invalidate_operational_cache()
    db.refresh(request)

    if pending_count >= APPROVER_PENDING_LIMIT and allow_over_capacity:
        create_system_alert(
            db,
            alert_type="approval_bottleneck",
            severity="WARNING",
            message="Critical request assigned over approver pending limit",
            details={
                "request_id": request.approval_id,
                "assigned_to": assignee_id,
                "pending_count": pending_count,
                "pending_limit": APPROVER_PENDING_LIMIT,
            },
            entity_key=request.approval_id,
            root_cause_code="critical_over_capacity_assignment",
            state_key=f"approval_bottleneck_over_capacity_{request.approval_id}",
        )

    _emit_approval_event(
        db,
        event_type="approval_assigned",
        request=request,
        actor_id=actor_id,
        reason="auto_assigned" if auto_assigned else "manual_assigned",
        extra={"assigned_to": assignee_id},
        severity="INFO",
    )
    db.commit()
    _invalidate_operational_cache()
    return request


def _policy_payload(policy: RiskOrchestratorPolicy) -> dict:
    return {
        "reference_equity_usd": float(policy.reference_equity_usd),
        "account_max_notional_pct": float(policy.account_max_notional_pct),
        "symbol_max_notional_pct": float(policy.symbol_max_notional_pct),
        "strategy_max_concurrent_positions": int(policy.strategy_max_concurrent_positions),
        "strategy_cooldown_seconds": int(policy.strategy_cooldown_seconds),
        "max_order_frequency_per_min": int(policy.max_order_frequency_per_min),
        "max_order_burst_per_10s": int(policy.max_order_burst_per_10s),
        "daily_loss_limit_pct": float(policy.daily_loss_limit_pct),
        "duplicate_suppression_window_seconds": int(policy.duplicate_suppression_window_seconds),
    }


def _normalize_policy_payload(payload: dict) -> dict:
    return {
        "reference_equity_usd": float(payload.get("reference_equity_usd") or 0),
        "account_max_notional_pct": float(payload.get("account_max_notional_pct") or 0),
        "symbol_max_notional_pct": float(payload.get("symbol_max_notional_pct") or 0),
        "strategy_max_concurrent_positions": int(payload.get("strategy_max_concurrent_positions") or 0),
        "strategy_cooldown_seconds": int(payload.get("strategy_cooldown_seconds") or 0),
        "max_order_frequency_per_min": int(payload.get("max_order_frequency_per_min") or 0),
        "max_order_burst_per_10s": int(payload.get("max_order_burst_per_10s") or 0),
        "daily_loss_limit_pct": float(payload.get("daily_loss_limit_pct") or 0),
        "duplicate_suppression_window_seconds": int(payload.get("duplicate_suppression_window_seconds") or 0),
    }


def _policy_diff(baseline: dict, candidate: dict) -> dict:
    changed: dict[str, dict] = {}
    critical_fields: list[str] = []
    loosened: list[str] = []
    tightened: list[str] = []

    risk_loosen_fields = {
        "account_max_notional_pct",
        "symbol_max_notional_pct",
        "strategy_max_concurrent_positions",
        "max_order_frequency_per_min",
        "max_order_burst_per_10s",
        "daily_loss_limit_pct",
    }

    for field in POLICY_FIELDS:
        before = baseline.get(field)
        after = candidate.get(field)
        if before == after:
            continue
        changed[field] = {"before": before, "after": after}
        if field in {
            "account_max_notional_pct",
            "symbol_max_notional_pct",
            "strategy_max_concurrent_positions",
            "daily_loss_limit_pct",
        }:
            critical_fields.append(field)

        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            if field in {"strategy_cooldown_seconds", "duplicate_suppression_window_seconds"}:
                if after < before:
                    loosened.append(field)
                elif after > before:
                    tightened.append(field)
            elif field in risk_loosen_fields:
                if after > before:
                    loosened.append(field)
                elif after < before:
                    tightened.append(field)

    risk_score = len(loosened) + (2 if "daily_loss_limit_pct" in loosened else 0)
    result_status = "safe"
    if risk_score >= 3:
        result_status = "critical"
    elif risk_score > 0:
        result_status = "warning"

    return {
        "changed_fields": changed,
        "critical_fields": critical_fields,
        "loosened_constraints": loosened,
        "tightened_constraints": tightened,
        "result_status": result_status,
        "metrics": {
            "changed_field_count": len(changed),
            "loosened_count": len(loosened),
            "tightened_count": len(tightened),
            "risk_score": risk_score,
        },
    }


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _jsonify(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        # Exclude SQLAlchemy model objects (like 'config' key from execution_safety_snapshot)
        return {key: _jsonify(item) for key, item in value.items() if key != "config" and not hasattr(item, "__table__")}
    if isinstance(value, (list, tuple, set)):
        return [_jsonify(item) for item in value]
    # Handle SQLAlchemy model objects by skipping them
    if hasattr(value, "__table__"):
        return None
    return value


def _maintain_override_health(db: Session) -> None:
    now_ts = _now()
    soon_ts = now_ts + timedelta(minutes=OVERRIDE_EXPIRY_ALERT_MINUTES)
    rows = (
        db.query(RiskOrchestratorManualOverride)
        .filter(RiskOrchestratorManualOverride.status == "active")
        .all()
    )

    touched = False
    for row in rows:
        if row.expires_at is None:
            continue
        if row.expires_at <= now_ts:
            row.status = "inactive"
            row.deactivated_at = now_ts
            row.updated_at = now_ts
            touched = True
            continue

        if row.expires_at <= soon_ts:
            create_system_alert(
                db,
                alert_type="risk_override_expiry_soon",
                severity="WARNING",
                message=f"Override yaklaşan süre nedeniyle auto-disable edildi: {row.override_id}",
                details={
                    "override_id": row.override_id,
                    "target_key": row.target_key,
                    "expires_at": row.expires_at.isoformat(),
                },
                entity_key=row.override_id,
                root_cause_code="override_expiry_soon",
                state_key=f"risk_override_expiry_soon_{row.override_id}",
            )
            row.status = "inactive"
            row.deactivated_at = now_ts
            row.updated_at = now_ts
            touched = True

    if touched:
        db.commit()


def _active_overrides(db: Session) -> list[RiskOrchestratorManualOverride]:
    _maintain_override_health(db)
    now_ts = _now()
    return (
        db.query(RiskOrchestratorManualOverride)
        .filter(
            RiskOrchestratorManualOverride.status == "active",
            or_(
                RiskOrchestratorManualOverride.expires_at.is_(None),
                RiskOrchestratorManualOverride.expires_at > now_ts,
            ),
        )
        .all()
    )


def _compute_risk_score(
    db: Session,
    *,
    baseline_policy: dict,
    candidate_policy: dict,
    diff_summary: dict,
) -> dict:
    now_ts = _now()
    changed = diff_summary.get("changed_fields") or {}
    critical_fields = set(diff_summary.get("critical_fields") or [])
    loosened_constraints = set(diff_summary.get("loosened_constraints") or [])

    account_before = float(baseline_policy.get("account_max_notional_pct") or 0)
    account_after = float(candidate_policy.get("account_max_notional_pct") or 0)
    symbol_before = float(baseline_policy.get("symbol_max_notional_pct") or 0)
    symbol_after = float(candidate_policy.get("symbol_max_notional_pct") or 0)
    concurrent_before = float(baseline_policy.get("strategy_max_concurrent_positions") or 1)
    concurrent_after = float(candidate_policy.get("strategy_max_concurrent_positions") or 1)

    account_delta = max(0.0, ((account_after - max(account_before, 0.1)) / max(account_before, 0.1)) * 100)
    symbol_delta = max(0.0, ((symbol_after - max(symbol_before, 0.1)) / max(symbol_before, 0.1)) * 100)
    concurrent_delta = max(0.0, ((concurrent_after - max(concurrent_before, 1.0)) / max(concurrent_before, 1.0)) * 100)
    exposure_component = _clamp((account_delta * 0.4) + (symbol_delta * 0.35) + (concurrent_delta * 0.25))

    recent_rejects = (
        db.query(AuditLog)
        .filter(AuditLog.action == "risk_orchestrator_reject", AuditLog.created_at >= now_ts - timedelta(minutes=30))
        .count()
    )
    previous_rejects = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "risk_orchestrator_reject",
            AuditLog.created_at >= now_ts - timedelta(minutes=60),
            AuditLog.created_at < now_ts - timedelta(minutes=30),
        )
        .count()
    )
    if previous_rejects == 0:
        reject_spike_pct = 100.0 if recent_rejects >= 5 else float(recent_rejects) * 20.0
    else:
        reject_spike_pct = ((recent_rejects - previous_rejects) / max(previous_rejects, 1)) * 100
    reject_rate_component = _clamp(max(0.0, reject_spike_pct))

    candidate_equity = max(float(candidate_policy.get("reference_equity_usd") or 0), 1.0)
    candidate_daily_loss = max(float(candidate_policy.get("daily_loss_limit_pct") or 1), 0.1)
    loss_abs = (
        db.query(Position)
        .filter(Position.status.in_(["open", "OPEN"]), Position.unrealized_pnl < 0)
        .all()
    )
    total_loss_usd = abs(sum(float(item.unrealized_pnl or 0) for item in loss_abs))
    loss_pct = (total_loss_usd / candidate_equity) * 100
    proximity = (loss_pct / candidate_daily_loss) * 100
    daily_loss_component = _clamp(proximity)

    open_by_strategy = build_status_snapshot(db).get("open_intents_by_strategy") or []
    max_open_strategy = max([int(item.get("open_count") or 0) for item in open_by_strategy], default=0)
    concurrent_limit = max(int(candidate_policy.get("strategy_max_concurrent_positions") or 1), 1)
    concurrent_ratio = (max_open_strategy / concurrent_limit) * 100
    concurrent_component = _clamp(concurrent_ratio)

    recent_vol = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.created_at >= now_ts - timedelta(hours=1))
        .order_by(ExecutionMetric.created_at.desc())
        .limit(100)
        .all()
    )
    if recent_vol:
        avg_volatility = sum(float(item.volatility_pct or 0) for item in recent_vol) / max(len(recent_vol), 1)
    else:
        avg_volatility = 10.0
    volatility_component = _clamp(avg_volatility * 2.0)

    weighted = (
        exposure_component * RISK_SCORE_WEIGHTS["exposure"]
        + reject_rate_component * RISK_SCORE_WEIGHTS["reject_rate"]
        + daily_loss_component * RISK_SCORE_WEIGHTS["daily_loss_proximity"]
        + concurrent_component * RISK_SCORE_WEIGHTS["concurrent_impact"]
        + volatility_component * RISK_SCORE_WEIGHTS["volatility"]
    )

    active_breaches = (
        db.query(SystemAlert)
        .filter(
            SystemAlert.alert_type.in_(["risk_orchestrator_breach", "daily_loss_limit_hit", "exposure_limit_breach"]),
            SystemAlert.created_at >= now_ts - timedelta(minutes=30),
            SystemAlert.status.notin_(["resolved", "RESOLVED"]),
        )
        .count()
    )
    active_breach_penalty = _clamp(active_breaches * 8, 0, 25)

    active_overrides = _active_overrides(db)
    total_override_notional = sum(float((item.override_value or {}).get("max_notional_pct") or 0) for item in active_overrides)
    override_abuse_penalty = 0.0
    if len(active_overrides) > OVERRIDE_ACTIVE_LIMIT:
        override_abuse_penalty += min(20, (len(active_overrides) - OVERRIDE_ACTIVE_LIMIT) * 2)
    if total_override_notional > OVERRIDE_TOTAL_NOTIONAL_LIMIT:
        override_abuse_penalty += min(20, (total_override_notional - OVERRIDE_TOTAL_NOTIONAL_LIMIT) * 0.2)

    critical_loosen_count = len(critical_fields.intersection(loosened_constraints))
    critical_change_penalty = min(45.0, critical_loosen_count * 14.0)
    broad_change_penalty = 10.0 if len(changed) >= 6 else 0.0
    predictive_signal = _predictive_risk_signal(db)
    predictive_penalty = round(float(predictive_signal.get("predictive_score") or 0) * 0.18, 2)

    final_score = _clamp(
        weighted
        + active_breach_penalty
        + override_abuse_penalty
        + critical_change_penalty
        + broad_change_penalty
        + predictive_penalty
    )
    classification = _classification_from_score(final_score)

    if active_breaches > 0 and classification == "SAFE":
        classification = "WARNING"
        final_score = max(final_score, 45)

    if override_abuse_penalty >= 15 and classification != "CRITICAL":
        classification = "WARNING"
        final_score = max(final_score, 55)

    return {
        "risk_score": round(final_score, 2),
        "classification": classification,
        "components": {
            "exposure": round(exposure_component, 2),
            "reject_rate": round(reject_rate_component, 2),
            "daily_loss_proximity": round(daily_loss_component, 2),
            "concurrent_impact": round(concurrent_component, 2),
            "volatility": round(volatility_component, 2),
            "active_breach_penalty": round(active_breach_penalty, 2),
            "override_abuse_penalty": round(override_abuse_penalty, 2),
            "critical_change_penalty": round(critical_change_penalty, 2),
            "broad_change_penalty": round(broad_change_penalty, 2),
            "predictive_penalty": predictive_penalty,
            "predictive_signal": predictive_signal,
            "recent_rejects": recent_rejects,
            "previous_rejects": previous_rejects,
            "active_breaches": active_breaches,
            "active_override_count": len(active_overrides),
            "active_override_total_notional_pct": round(total_override_notional, 2),
            "changed_field_count": len(changed),
        },
    }


def _ensure_active_override_scope(override: RiskOrchestratorManualOverride) -> bool:
    if override.status != "active":
        return False
    if override.expires_at is None:
        return True
    return override.expires_at > _now()


def _match_override(override: RiskOrchestratorManualOverride, *, symbol: str | None, strategy_id: str) -> bool:
    target = (override.target_key or "").upper()
    symbol_key = (symbol or "").upper()
    strategy_key = (strategy_id or "").upper()
    scope = (override.override_type or "").lower()

    if scope in {"symbol", "symbol_exposure"}:
        return bool(symbol_key and target == symbol_key)
    if scope in {"strategy", "strategy_exposure"}:
        return bool(strategy_key and target == strategy_key)
    if scope == "block_adds":
        return (
            target in {"ALL", "GLOBAL"}
            or target == f"SYMBOL:{symbol_key}"
            or target == f"STRATEGY:{strategy_key}"
            or (symbol_key and target == symbol_key)
            or (strategy_key and target == strategy_key)
        )
    return False


def get_or_create_policy(db: Session) -> RiskOrchestratorPolicy:
    policy = db.query(RiskOrchestratorPolicy).filter(RiskOrchestratorPolicy.id == "global").first()
    if policy is not None:
        return policy

    policy = RiskOrchestratorPolicy(id="global")
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def update_policy(db: Session, *, payload: dict) -> RiskOrchestratorPolicy:
    policy = get_or_create_policy(db)
    policy.reference_equity_usd = float(payload.get("reference_equity_usd", policy.reference_equity_usd))
    policy.account_max_notional_pct = float(payload.get("account_max_notional_pct", policy.account_max_notional_pct))
    policy.symbol_max_notional_pct = float(payload.get("symbol_max_notional_pct", policy.symbol_max_notional_pct))
    policy.strategy_max_concurrent_positions = int(
        payload.get("strategy_max_concurrent_positions", policy.strategy_max_concurrent_positions)
    )
    policy.strategy_cooldown_seconds = int(payload.get("strategy_cooldown_seconds", policy.strategy_cooldown_seconds))
    policy.max_order_frequency_per_min = int(payload.get("max_order_frequency_per_min", policy.max_order_frequency_per_min))
    policy.max_order_burst_per_10s = int(payload.get("max_order_burst_per_10s", policy.max_order_burst_per_10s))
    policy.daily_loss_limit_pct = float(payload.get("daily_loss_limit_pct", policy.daily_loss_limit_pct))
    policy.duplicate_suppression_window_seconds = int(
        payload.get("duplicate_suppression_window_seconds", policy.duplicate_suppression_window_seconds)
    )
    policy.policy_version = int(getattr(policy, "policy_version", 1) or 1)
    db.commit()
    db.refresh(policy)
    return policy


def simulate_policy_change(db: Session, *, actor_id: str, actor_role: str, candidate_payload: dict) -> dict:
    policy = get_or_create_policy(db)
    baseline = _policy_payload(policy)
    candidate = _normalize_policy_payload(candidate_payload)
    diff = _policy_diff(baseline, candidate)
    risk_gate = _compute_risk_score(
        db,
        baseline_policy=baseline,
        candidate_policy=candidate,
        diff_summary=diff,
    )
    approval_flow = _approval_flow_from_classification(risk_gate["classification"])
    snapshot = build_status_snapshot(db)

    simulation_metrics = {
        **diff["metrics"],
        "baseline_policy_version": _current_policy_version(policy),
        "risk_score": risk_gate["risk_score"],
        "classification": risk_gate["classification"],
        "score_components": risk_gate["components"],
        "approval_flow": approval_flow,
    }

    simulation = RiskOrchestratorPolicySimulation(
        simulation_id=f"ro-sim-{uuid4().hex[:18]}",
        actor_id=actor_id,
        actor_role=actor_role,
        baseline_policy=baseline,
        candidate_policy=candidate,
        result_status=diff["result_status"],
        diff_summary=diff,
        impacted_strategies=[row["key"] for row in snapshot["open_intents_by_strategy"][:10]],
        impacted_symbols=[row["key"] for row in snapshot["open_intents_by_symbol"][:10]],
        metrics=simulation_metrics,
    )
    db.add(simulation)
    db.commit()
    db.refresh(simulation)
    return {
        "simulation_id": simulation.simulation_id,
        "result_status": simulation.result_status,
        "baseline_policy": simulation.baseline_policy,
        "candidate_policy": simulation.candidate_policy,
        "diff_summary": simulation.diff_summary,
        "impacted_strategies": simulation.impacted_strategies,
        "impacted_symbols": simulation.impacted_symbols,
        "metrics": simulation.metrics,
        "risk_score": risk_gate["risk_score"],
        "classification": risk_gate["classification"],
        "approval_flow": approval_flow,
        "created_at": simulation.created_at,
    }


def apply_policy_from_simulation(
    db: Session,
    *,
    simulation_id: str,
    actor_id: str,
    actor_role: str,
    reason_note: str,
    double_confirmed: bool,
    apply_with_override: bool,
    approval_note: str | None,
    request_key: str | None,
    expected_policy_version: int | None,
    flow_type: str = "apply",
    force_resolution: bool = False,
    approval_finalization: bool = False,
) -> dict:
    simulation = (
        db.query(RiskOrchestratorPolicySimulation)
        .filter(RiskOrchestratorPolicySimulation.simulation_id == simulation_id)
        .first()
    )
    if simulation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="simulation_not_found")

    computed_request_key = request_key or f"{flow_type}:{simulation_id}:{actor_id}"
    existing_approval = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(RiskOrchestratorApprovalRequest.request_key == computed_request_key)
        .first()
    )
    if existing_approval is not None and existing_approval.state in {"pending", "assigned", "approved", "rejected", "expired"}:
        return {
            "status": existing_approval.state,
            "flow_type": existing_approval.flow_type,
            "simulation_id": simulation_id,
            "risk_score": existing_approval.risk_score,
            "classification": existing_approval.classification,
            "rule_path": "CRITICAL_BLOCK_OR_4_EYES_OVERRIDE",
            "policy": None,
            "approval_request_id": existing_approval.approval_id,
            "decision_trace_id": existing_approval.final_decision_trace_id,
            "message": "idempotent_replay_existing_approval_state",
        }

    existing_trace = (
        db.query(RiskOrchestratorDecisionTrace)
        .filter(RiskOrchestratorDecisionTrace.request_key == computed_request_key)
        .order_by(RiskOrchestratorDecisionTrace.created_at.desc())
        .first()
    )
    if existing_trace is not None and existing_trace.decision_state in {"applied", "blocked", "pending", "assigned", "rejected", "expired"}:
        return {
            "status": existing_trace.decision_state,
            "flow_type": existing_trace.flow_type,
            "simulation_id": existing_trace.simulation_id,
            "risk_score": float(existing_trace.risk_score or 0),
            "classification": existing_trace.classification,
            "rule_path": existing_trace.rule_path,
            "policy": get_or_create_policy(db) if existing_trace.decision_state == "applied" else None,
            "approval_request_id": None,
            "decision_trace_id": existing_trace.trace_id,
            "message": "idempotent_replay_existing_decision_trace",
        }

    current_policy = get_or_create_policy(db)
    current_version = _current_policy_version(current_policy)
    baseline_version = int((simulation.metrics or {}).get("baseline_policy_version") or current_version)

    if expected_policy_version is not None and current_version != int(expected_policy_version):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="stale_policy_data")
    if current_version != baseline_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="stale_simulation_requires_resimulate")

    candidate_policy = simulation.candidate_policy or {}
    diff_payload = simulation.diff_summary or _policy_diff(_policy_payload(current_policy), candidate_policy)
    risk_gate = {
        "risk_score": float((simulation.metrics or {}).get("risk_score") or 0),
        "classification": (simulation.metrics or {}).get("classification") or "SAFE",
        "components": (simulation.metrics or {}).get("score_components") or {},
    }
    approval_flow = _approval_flow_from_classification(risk_gate["classification"])
    if force_resolution:
        approval_flow = {
            "requires_double_confirm": False,
            "requires_second_approval": False,
            "default_blocked": False,
            "rule_path": "FORCE_OVERRIDE_APPLY",
        }
    elif approval_finalization:
        approval_flow = {
            "requires_double_confirm": False,
            "requires_second_approval": False,
            "default_blocked": False,
            "rule_path": "CRITICAL_4_EYES_FINALIZE",
        }

    if approval_flow["requires_double_confirm"] and not double_confirmed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="double_confirmation_required")

    if approval_flow["default_blocked"] and not apply_with_override:
        trace = RiskOrchestratorDecisionTrace(
            trace_id=f"ro-trace-{uuid4().hex[:18]}",
            flow_type=flow_type,
            simulation_id=simulation_id,
            classification=risk_gate["classification"],
            risk_score=float(risk_gate["risk_score"]),
            rule_path="CRITICAL_BLOCK_DEFAULT",
            decision_state="blocked",
            requested_by=actor_id,
            approver_id=None,
            request_key=computed_request_key,
            reason_note=reason_note,
            approval_note=approval_note,
            payload={
                "score_components": risk_gate["components"],
                "approval_flow": approval_flow,
                "apply_with_override": False,
            },
        )
        db.add(trace)
        create_system_alert(
            db,
            alert_type="critical_block",
            severity="CRITICAL",
            message="Critical policy change blocked by risk gate",
            details={
                "request_id": computed_request_key,
                "risk_score": float(risk_gate["risk_score"]),
                "classification": risk_gate["classification"],
                "actor": actor_id,
                "reason": reason_note,
                "link_to_ui": "/admin/risk-orchestrator?tab=risk-gate",
            },
            entity_key=computed_request_key,
            root_cause_code="critical_block",
            state_key=f"critical_block_{computed_request_key}",
        )
        db.commit()
        _invalidate_operational_cache()
        return {
            "status": "blocked",
            "flow_type": flow_type,
            "simulation_id": simulation_id,
            "risk_score": float(risk_gate["risk_score"]),
            "classification": risk_gate["classification"],
            "rule_path": "CRITICAL_BLOCK_DEFAULT",
            "policy": None,
            "approval_request_id": None,
            "decision_trace_id": trace.trace_id,
            "message": "critical_policy_blocked_use_apply_with_override_and_4eyes",
        }

    if approval_flow["requires_second_approval"]:
        actor_role_value = _role_value(actor_role)
        approval_request = RiskOrchestratorApprovalRequest(
            approval_id=f"ro-appr-{uuid4().hex[:18]}",
            request_key=computed_request_key,
            flow_type=flow_type,
            simulation_id=simulation_id,
            classification=risk_gate["classification"],
            priority=risk_gate["classification"],
            risk_score=float(risk_gate["risk_score"]),
            state="pending",
            requested_by=actor_id,
            requested_role=actor_role,
            reason_note=reason_note,
            override_used=apply_with_override,
            expires_at=_now() + timedelta(minutes=APPROVAL_TIMEOUT_MINUTES),
            last_activity_at=_now(),
            context_payload={
                "approval_flow": approval_flow,
                "score_components": risk_gate["components"],
                "approval_note": approval_note,
                "governance_policy": _governance_policy(),
                "governance_votes": [
                    {
                        "actor_id": actor_id,
                        "actor_role": actor_role_value,
                        "weight": int(GOVERNANCE_ROLE_WEIGHTS.get(actor_role_value, 1)),
                        "decision": "proposed",
                        "note": reason_note,
                        "voted_at": _now().isoformat(),
                    }
                ],
            },
        )
        trace = RiskOrchestratorDecisionTrace(
            trace_id=f"ro-trace-{uuid4().hex[:18]}",
            flow_type=flow_type,
            simulation_id=simulation_id,
            classification=risk_gate["classification"],
            risk_score=float(risk_gate["risk_score"]),
            rule_path="CRITICAL_PENDING_4_EYES",
            decision_state="pending",
            requested_by=actor_id,
            approver_id=None,
            request_key=computed_request_key,
            reason_note=reason_note,
            approval_note=approval_note,
            payload={
                "approval_id": approval_request.approval_id,
                "score_components": risk_gate["components"],
            },
        )
        db.add(approval_request)
        db.add(trace)
        try:
            db.commit()
        except sa.exc.IntegrityError:
            db.rollback()
            existing = (
                db.query(RiskOrchestratorApprovalRequest)
                .filter(RiskOrchestratorApprovalRequest.request_key == computed_request_key)
                .first()
            )
            if existing is not None:
                return {
                    "status": existing.state,
                    "flow_type": existing.flow_type,
                    "simulation_id": existing.simulation_id,
                    "risk_score": float(existing.risk_score or 0),
                    "classification": existing.classification,
                    "rule_path": "CRITICAL_PENDING_4_EYES",
                    "policy": None,
                    "approval_request_id": existing.approval_id,
                    "decision_trace_id": existing.final_decision_trace_id,
                    "message": "idempotent_replay_existing_approval_state",
                }
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="approval_request_idempotency_conflict")

        _invalidate_operational_cache()

        _emit_approval_event(
            db,
            event_type="approval_requested",
            request=approval_request,
            actor_id=actor_id,
            reason=reason_note,
            extra={"rule_path": "CRITICAL_PENDING_4_EYES"},
            severity="WARNING",
        )
        approval_request = _ensure_critical_queue_ownership(db, request=approval_request, actor_id=actor_id)

        return {
            "status": approval_request.state,
            "flow_type": flow_type,
            "simulation_id": simulation_id,
            "risk_score": float(risk_gate["risk_score"]),
            "classification": risk_gate["classification"],
            "rule_path": "CRITICAL_PENDING_4_EYES",
            "policy": None,
            "approval_request_id": approval_request.approval_id,
            "decision_trace_id": trace.trace_id,
            "message": "waiting_for_second_approval",
        }

    current_policy = get_or_create_policy(db)
    previous_payload = _policy_payload(current_policy)

    change_request = RiskOrchestratorPolicyChangeRequest(
        request_id=f"ro-cr-{uuid4().hex[:18]}",
        status="applied",
        requested_by=actor_id,
        requested_role=actor_role,
        approved_by=actor_id,
        approval_note=approval_note,
        reason_note=reason_note,
        payload=candidate_policy,
        simulation_id=simulation.simulation_id,
        critical_fields=diff_payload.get("critical_fields") or [],
        double_confirmed=bool(double_confirmed),
        decided_at=_now(),
    )
    db.add(change_request)

    updated_policy = update_policy(db, payload=candidate_policy)
    updated_policy.policy_version = int(getattr(updated_policy, "policy_version", 1) or 1) + 1

    final_diff_payload = _policy_diff(previous_payload, _policy_payload(updated_policy))
    version = RiskOrchestratorPolicyVersion(
        version_id=f"ro-pv-{uuid4().hex[:18]}",
        version_no=updated_policy.policy_version,
        policy_payload=_policy_payload(updated_policy),
        diff_payload=final_diff_payload,
        changed_by=actor_id,
        changed_role=actor_role,
        reason_note=reason_note,
        simulation_id=simulation.simulation_id,
        approval_request_id=change_request.request_id,
    )

    trace = RiskOrchestratorDecisionTrace(
        trace_id=f"ro-trace-{uuid4().hex[:18]}",
        flow_type=flow_type,
        simulation_id=simulation.simulation_id,
        classification=risk_gate["classification"],
        risk_score=float(risk_gate["risk_score"]),
        rule_path=approval_flow["rule_path"],
        decision_state="applied",
        requested_by=actor_id,
        approver_id=actor_id,
        request_key=computed_request_key,
        reason_note=reason_note,
        approval_note=approval_note,
        payload={
            "score_components": risk_gate["components"],
            "change_request_id": change_request.request_id,
            "version_id": version.version_id,
            "approval_flow": approval_flow,
            "apply_with_override": apply_with_override,
        },
    )

    db.add(version)
    db.add(trace)
    db.commit()
    db.refresh(updated_policy)
    db.refresh(version)
    db.refresh(trace)
    _invalidate_operational_cache()

    create_audit_log(
        db,
        action="risk_orchestrator_policy_applied",
        entity_type="risk_orchestrator_policy",
        entity_id=updated_policy.id,
        actor_user_id=actor_id,
        actor_role=actor_role,
        details={
            "simulation_id": simulation.simulation_id,
            "change_request_id": change_request.request_id,
            "version_id": version.version_id,
            "reason_note": reason_note,
            "risk_score": risk_gate["risk_score"],
            "classification": risk_gate["classification"],
            "rule_path": approval_flow["rule_path"],
        },
        severity="high",
    )

    return {
        "status": "applied",
        "flow_type": flow_type,
        "simulation_id": simulation.simulation_id,
        "risk_score": float(risk_gate["risk_score"]),
        "classification": risk_gate["classification"],
        "rule_path": approval_flow["rule_path"],
        "policy": updated_policy,
        "approval_request_id": None,
        "decision_trace_id": trace.trace_id,
        "message": "policy_applied",
    }


def _expire_stale_approval_requests(db: Session) -> None:
    now_ts = _now()
    rows = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(
            RiskOrchestratorApprovalRequest.state.in_(["pending", "assigned"]),
            RiskOrchestratorApprovalRequest.expires_at <= now_ts,
        )
        .all()
    )
    if not rows:
        return
    for row in rows:
        row.state = "expired"
        row.rejected_at = now_ts
        row.expired_at = now_ts
        row.updated_at = now_ts
        row.last_activity_at = now_ts
        row.second_approver_note = "SLA breach auto-reject"

        trace = RiskOrchestratorDecisionTrace(
            trace_id=f"ro-trace-{uuid4().hex[:18]}",
            flow_type=row.flow_type,
            simulation_id=row.simulation_id,
            classification=row.classification,
            risk_score=float(row.risk_score or 0),
            rule_path="FORCED_AUTO_REJECT_SLA_BREACH",
            decision_state="expired",
            requested_by=row.requested_by,
            approver_id=None,
            request_key=row.request_key,
            reason_note=row.reason_note,
            approval_note="SLA breach auto-reject",
            payload={"approval_id": row.approval_id, "reason": "sla_breach"},
        )
        db.add(trace)
        row.final_decision_trace_id = trace.trace_id

        _emit_approval_event(
            db,
            event_type="approval_expired",
            request=row,
            actor_id=None,
            reason="sla_breach_auto_reject",
            extra={"forced_resolution": "auto_reject"},
            severity="CRITICAL",
        )

    db.commit()
    _invalidate_operational_cache()


def process_approval_escalations(db: Session) -> dict:
    now_ts = _now()
    _expire_stale_approval_requests(db)

    rows = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(
            RiskOrchestratorApprovalRequest.state.in_(["pending", "assigned"]),
            RiskOrchestratorApprovalRequest.classification == "CRITICAL",
        )
        .all()
    )

    warning_count = 0
    critical_count = 0
    stuck_count = 0
    changed = False

    for row in rows:
        previous_assignee = row.assigned_to
        row = _ensure_critical_queue_ownership(db, request=row, actor_id=None)
        if row.assigned_to != previous_assignee:
            changed = True

        elapsed = (now_ts - row.created_at).total_seconds()

        if elapsed >= 8 * 60 and row.critical_escalated_at is None:
            row.critical_escalated_at = now_ts
            row.escalation_count = int(row.escalation_count or 0) + 1
            row.last_activity_at = now_ts
            row.updated_at = now_ts
            changed = True
            _emit_approval_event(
                db,
                event_type="approval_expiring",
                request=row,
                actor_id=None,
                reason="critical_escalation_8m",
                extra={"sla_stage": "critical", "elapsed_seconds": int(elapsed)},
                severity="CRITICAL",
            )
            critical_count += 1

        elif elapsed >= 5 * 60 and row.warning_escalated_at is None:
            row.warning_escalated_at = now_ts
            row.escalation_count = int(row.escalation_count or 0) + 1
            row.last_activity_at = now_ts
            row.updated_at = now_ts
            changed = True
            _emit_approval_event(
                db,
                event_type="approval_expiring",
                request=row,
                actor_id=None,
                reason="warning_escalation_5m",
                extra={"sla_stage": "warning", "elapsed_seconds": int(elapsed)},
                severity="WARNING",
            )
            warning_count += 1

        inactivity_seconds = (now_ts - (row.last_activity_at or row.created_at)).total_seconds()
        if inactivity_seconds >= STUCK_APPROVAL_MINUTES * 60:
            create_system_alert(
                db,
                alert_type="approval_stuck",
                severity="WARNING",
                message="Approval request seems stuck",
                details={
                    "request_id": row.approval_id,
                    "classification": row.classification,
                    "assigned_to": row.assigned_to,
                    "inactive_seconds": int(inactivity_seconds),
                },
                entity_key=row.approval_id,
                root_cause_code="approval_stuck",
                state_key=f"approval_stuck_{row.approval_id}",
            )
            changed = True
            stuck_count += 1

    if rows and changed:
        db.commit()
        _invalidate_operational_cache()

    return {
        "warning_escalations": warning_count,
        "critical_escalations": critical_count,
        "stuck_detected": stuck_count,
    }


def list_policy_approval_requests(db: Session, *, state: str | None = None, limit: int = 50) -> list[RiskOrchestratorApprovalRequest]:
    process_approval_escalations(db)
    query = db.query(RiskOrchestratorApprovalRequest)
    if state:
        query = query.filter(RiskOrchestratorApprovalRequest.state == state)
    return query.order_by(RiskOrchestratorApprovalRequest.created_at.desc()).limit(limit).all()


def list_policy_queue(
    db: Session,
    *,
    actor_id: str,
    scope: str = "all",
    state: str | None = None,
    critical_first: bool = True,
    limit: int = 100,
    page: int = 1,
) -> list[RiskOrchestratorApprovalRequest]:
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, min(200, int(limit or 100)))
    cache_key = (actor_id, scope, state or "", str(bool(critical_first)), safe_limit, safe_page)
    cached_ids = _cache_get(_queue_cache, cache_key)
    if cached_ids is not None:
        rows = (
            db.query(RiskOrchestratorApprovalRequest)
            .filter(RiskOrchestratorApprovalRequest.approval_id.in_(cached_ids))
            .all()
        )
        by_id = {row.approval_id: row for row in rows}
        return [by_id[item_id] for item_id in cached_ids if item_id in by_id]

    process_approval_escalations(db)
    query = db.query(RiskOrchestratorApprovalRequest)

    if scope == "my":
        query = query.filter(RiskOrchestratorApprovalRequest.assigned_to == actor_id)
    elif scope == "unassigned":
        query = query.filter(RiskOrchestratorApprovalRequest.assigned_to.is_(None))

    if state:
        query = query.filter(RiskOrchestratorApprovalRequest.state == state)

    if critical_first:
        query = query.order_by(
            sa.case((RiskOrchestratorApprovalRequest.classification == "CRITICAL", 0), else_=1),
            RiskOrchestratorApprovalRequest.expires_at.asc(),
        )
    else:
        query = query.order_by(RiskOrchestratorApprovalRequest.created_at.desc())

    rows = query.offset((safe_page - 1) * safe_limit).limit(safe_limit).all()
    _cache_set(
        _queue_cache,
        cache_key,
        [row.approval_id for row in rows],
        QUEUE_CACHE_TTL_SECONDS,
    )
    return rows


def approve_policy_approval_request(
    db: Session,
    *,
    approval_id: str,
    actor_id: str,
    actor_role: str,
    decision_note: str,
) -> dict:
    _expire_stale_approval_requests(db)
    request = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(RiskOrchestratorApprovalRequest.approval_id == approval_id)
        .with_for_update()
        .first()
    )
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval_request_not_found")

    if request.state not in {"pending", "assigned"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="approval_request_not_pending")
    if request.requested_by == actor_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="same_user_second_approval_blocked")
    if request.assigned_to and request.assigned_to != actor_id and _role_value(actor_role) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="approval_owned_by_another_actor")

    payload = deepcopy(request.context_payload or {})
    governance_policy = payload.get("governance_policy") or _governance_policy()
    payload["governance_policy"] = governance_policy
    votes = list(payload.get("governance_votes") or [])
    actor_role_value = _role_value(actor_role)

    if any(str(item.get("actor_id")) == actor_id for item in votes):
        progress = _governance_vote_progress(payload)
        request.context_payload = payload
        request.last_activity_at = _now()
        request.updated_at = _now()
        db.commit()
        return {
            "approval_request": request,
            "apply_result": {
                "status": request.state,
                "flow_type": request.flow_type,
                "simulation_id": request.simulation_id,
                "risk_score": float(request.risk_score or 0),
                "classification": request.classification,
                "rule_path": "CRITICAL_GOVERNANCE_VOTE_DUPLICATE",
                "policy": None,
                "approval_request_id": request.approval_id,
                "decision_trace_id": request.final_decision_trace_id,
                "message": "vote_already_recorded",
                "governance": progress,
            },
        }

    votes.append(
        {
            "actor_id": actor_id,
            "actor_role": actor_role_value,
            "weight": int(GOVERNANCE_ROLE_WEIGHTS.get(actor_role_value, 1)),
            "decision": "approve",
            "note": decision_note,
            "voted_at": _now().isoformat(),
        }
    )
    payload["governance_votes"] = votes
    progress = _governance_vote_progress(payload)
    request.context_payload = payload
    request.second_approver_id = actor_id
    request.second_approver_note = decision_note
    request.last_activity_at = _now()
    request.updated_at = _now()

    quorum_weight = int(progress.get("quorum_weight") or GOVERNANCE_QUORUM_WEIGHT)
    min_approvers = int(progress.get("min_distinct_approvers") or GOVERNANCE_MIN_DISTINCT_APPROVERS)
    quorum_reached = (
        int(progress.get("total_weight") or 0) >= quorum_weight
        and int(progress.get("distinct_voter_count") or 0) >= min_approvers
    )

    if not quorum_reached:
        request.state = "pending"
        pending_trace = RiskOrchestratorDecisionTrace(
            trace_id=f"ro-trace-{uuid4().hex[:18]}",
            flow_type=request.flow_type,
            simulation_id=request.simulation_id,
            classification=request.classification,
            risk_score=float(request.risk_score or 0),
            rule_path="CRITICAL_GOVERNANCE_QUORUM_PENDING",
            decision_state="pending",
            requested_by=request.requested_by,
            approver_id=actor_id,
            request_key=request.request_key,
            reason_note=request.reason_note,
            approval_note=decision_note,
            payload={
                "approval_id": request.approval_id,
                "governance": progress,
            },
        )
        db.add(pending_trace)
        _emit_approval_event(
            db,
            event_type="approval_vote_collected",
            request=request,
            actor_id=actor_id,
            reason="governance_vote_collected",
            extra={"governance": progress},
            severity="INFO",
        )
        db.commit()
        _invalidate_operational_cache()
        db.refresh(request)
        return {
            "approval_request": request,
            "apply_result": {
                "status": "pending",
                "flow_type": request.flow_type,
                "simulation_id": request.simulation_id,
                "risk_score": float(request.risk_score or 0),
                "classification": request.classification,
                "rule_path": "CRITICAL_GOVERNANCE_QUORUM_PENDING",
                "policy": None,
                "approval_request_id": request.approval_id,
                "decision_trace_id": pending_trace.trace_id,
                "message": "quorum_waiting_additional_votes",
                "governance": progress,
            },
        }

    apply_result = apply_policy_from_simulation(
        db,
        simulation_id=request.simulation_id,
        actor_id=request.requested_by,
        actor_role=request.requested_role,
        reason_note=request.reason_note,
        double_confirmed=True,
        apply_with_override=bool(request.override_used),
        approval_note=request.second_approver_note,
        request_key=f"{request.request_key}:finalize",
        expected_policy_version=None,
        flow_type=request.flow_type,
        approval_finalization=True,
    )
    if apply_result.get("status") != "applied":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="approval_finalize_not_applied")

    request.state = "approved"
    request.approved_at = _now()
    request.final_decision_trace_id = apply_result.get("decision_trace_id")
    request.updated_at = _now()
    request.last_activity_at = _now()

    trace = RiskOrchestratorDecisionTrace(
        trace_id=f"ro-trace-{uuid4().hex[:18]}",
        flow_type=request.flow_type,
        simulation_id=request.simulation_id,
        classification=request.classification,
        risk_score=float(request.risk_score or 0),
        rule_path="CRITICAL_4_EYES_APPROVED",
        decision_state="approved",
        requested_by=request.requested_by,
        approver_id=actor_id,
        request_key=request.request_key,
        reason_note=request.reason_note,
        approval_note=decision_note,
        payload={
            "approval_id": request.approval_id,
            "apply_result": {
                "status": apply_result.get("status"),
                "decision_trace_id": apply_result.get("decision_trace_id"),
            },
            "governance": progress,
        },
    )
    db.add(trace)
    _emit_approval_event(
        db,
        event_type="approval_approved",
        request=request,
        actor_id=actor_id,
        reason=decision_note,
        extra={"governance": progress},
        severity="INFO",
    )
    db.commit()
    _invalidate_operational_cache()
    db.refresh(request)

    return {
        "approval_request": request,
        "apply_result": {
            **apply_result,
            "governance": progress,
        },
    }


def reject_policy_approval_request(
    db: Session,
    *,
    approval_id: str,
    actor_id: str,
    actor_role: str,
    decision_note: str,
) -> RiskOrchestratorApprovalRequest:
    _expire_stale_approval_requests(db)
    request = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(RiskOrchestratorApprovalRequest.approval_id == approval_id)
        .with_for_update()
        .first()
    )
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval_request_not_found")

    if request.state not in {"pending", "assigned"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="approval_request_not_pending")
    if request.requested_by == actor_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="same_user_second_approval_blocked")
    if request.assigned_to and request.assigned_to != actor_id and actor_role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="approval_owned_by_another_actor")

    request.state = "rejected"
    request.second_approver_id = actor_id
    request.second_approver_note = decision_note
    request.rejected_at = _now()
    request.last_activity_at = _now()
    request.updated_at = _now()

    trace = RiskOrchestratorDecisionTrace(
        trace_id=f"ro-trace-{uuid4().hex[:18]}",
        flow_type=request.flow_type,
        simulation_id=request.simulation_id,
        classification=request.classification,
        risk_score=float(request.risk_score or 0),
        rule_path="CRITICAL_4_EYES_REJECTED",
        decision_state="rejected",
        requested_by=request.requested_by,
        approver_id=actor_id,
        request_key=request.request_key,
        reason_note=request.reason_note,
        approval_note=decision_note,
        payload={"approval_id": request.approval_id},
    )
    db.add(trace)
    request.final_decision_trace_id = trace.trace_id
    _emit_approval_event(
        db,
        event_type="approval_rejected",
        request=request,
        actor_id=actor_id,
        reason=decision_note,
        severity="WARNING",
    )
    db.commit()
    _invalidate_operational_cache()
    db.refresh(request)
    return request


def assign_policy_approval_request(
    db: Session,
    *,
    approval_id: str,
    actor_id: str,
    assignee_id: str | None,
    auto_assign: bool,
) -> RiskOrchestratorApprovalRequest:
    _expire_stale_approval_requests(db)
    request = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(RiskOrchestratorApprovalRequest.approval_id == approval_id)
        .with_for_update()
        .first()
    )
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval_request_not_found")
    if request.state not in {"pending", "assigned"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="approval_request_not_assignable")

    selected_assignee_id = assignee_id
    if auto_assign:
        selected = _select_auto_assignee(
            db,
            requested_by=request.requested_by,
            classification=request.classification,
            exclude_ids={request.assigned_to} if request.assigned_to else None,
        )
        if selected is None:
            request = _ensure_critical_queue_ownership(db, request=request, actor_id=actor_id)
            if request.assigned_to:
                return request
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no_eligible_auto_assignee")
        selected_assignee_id = selected.id

    if not selected_assignee_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assignee_required")

    return _assign_approval_request(
        db,
        request=request,
        assignee_id=selected_assignee_id,
        actor_id=actor_id,
        auto_assigned=auto_assign,
    )


def force_apply_approval_request(
    db: Session,
    *,
    approval_id: str,
    actor_id: str,
    actor_role: str,
    reason_note: str,
) -> dict:
    if _role_value(actor_role) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_required_for_force_apply")

    _expire_stale_approval_requests(db)
    request = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(RiskOrchestratorApprovalRequest.approval_id == approval_id)
        .with_for_update()
        .first()
    )
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval_request_not_found")
    if request.state == "expired":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="expired_request_force_apply_forbidden")
    if request.state not in {"pending", "assigned"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="approval_request_not_force_applicable")

    result = apply_policy_from_simulation(
        db,
        simulation_id=request.simulation_id,
        actor_id=request.requested_by,
        actor_role=request.requested_role,
        reason_note=request.reason_note,
        double_confirmed=True,
        apply_with_override=True,
        approval_note=f"force_apply:{reason_note}",
        request_key=f"{request.request_key}:force_apply",
        expected_policy_version=None,
        flow_type=request.flow_type,
        force_resolution=True,
    )
    if result.get("status") != "applied":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="force_apply_finalize_not_applied")

    request.force_applied = True
    request.state = "approved"
    request.second_approver_id = actor_id
    request.second_approver_note = f"force_apply:{reason_note}"
    request.approved_at = _now()
    request.last_activity_at = _now()
    request.updated_at = _now()

    request.final_decision_trace_id = result.get("decision_trace_id")
    request.updated_at = _now()
    db.commit()
    _invalidate_operational_cache()

    _emit_approval_event(
        db,
        event_type="force_override",
        request=request,
        actor_id=actor_id,
        reason=reason_note,
        severity="CRITICAL",
    )
    db.commit()
    _invalidate_operational_cache()
    return result


def build_decision_intelligence(db: Session, *, trace_id: str) -> dict:
    trace = (
        db.query(RiskOrchestratorDecisionTrace)
        .filter(RiskOrchestratorDecisionTrace.trace_id == trace_id)
        .first()
    )
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="decision_trace_not_found")

    simulation = (
        db.query(RiskOrchestratorPolicySimulation)
        .filter(RiskOrchestratorPolicySimulation.simulation_id == trace.simulation_id)
        .first()
    )

    similar = (
        db.query(RiskOrchestratorDecisionTrace)
        .filter(
            RiskOrchestratorDecisionTrace.rule_path == trace.rule_path,
            RiskOrchestratorDecisionTrace.classification == trace.classification,
            RiskOrchestratorDecisionTrace.trace_id != trace.trace_id,
        )
        .order_by(RiskOrchestratorDecisionTrace.created_at.desc())
        .limit(5)
        .all()
    )

    why_text = "allowed"
    if trace.decision_state in {"blocked", "rejected", "expired"}:
        why_text = "blocked"
    if trace.decision_state in {"pending", "assigned"}:
        why_text = "pending"

    return {
        "trace": trace,
        "before_after_diff": simulation.diff_summary if simulation else {},
        "risk_breakdown": (simulation.metrics or {}).get("score_components") if simulation else (trace.payload or {}).get("score_components", {}),
        "why_decision": {
            "state": trace.decision_state,
            "rule_path": trace.rule_path,
            "classification": trace.classification,
            "explanation": f"Decision {why_text} by rule {trace.rule_path}",
        },
        "similar_patterns": [
            {
                "trace_id": item.trace_id,
                "decision_state": item.decision_state,
                "risk_score": item.risk_score,
                "created_at": item.created_at,
            }
            for item in similar
        ],
    }


def build_reject_insights(db: Session) -> dict:
    now_ts = _now()
    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "risk_orchestrator_reject",
            AuditLog.created_at >= now_ts - timedelta(minutes=30),
        )
        .all()
    )

    counters: dict[str, int] = {}
    for row in rows:
        reason_codes = (row.details or {}).get("reason_codes") or []
        for reason in reason_codes:
            counters[reason] = counters.get(reason, 0) + 1

    insights: list[dict] = []
    for reason, count in sorted(counters.items(), key=lambda item: item[1], reverse=True):
        if count < 3:
            continue
        suggestion = "policy_too_strict"
        if "symbol" in reason:
            suggestion = "symbol_risk_anomaly"
        elif "cooldown" in reason or "frequency" in reason:
            suggestion = "execution_frequency_tuning"

        insights.append(
            {
                "rule": reason,
                "count": count,
                "window_minutes": 30,
                "suggestion": suggestion,
                "message": f"{reason} son 30 dk içinde {count} kez tetiklendi. Öneri: {suggestion}",
            }
        )

    return {
        "window_minutes": 30,
        "insights": insights,
    }


def build_operational_dashboard(db: Session, *, actor_id: str | None = None) -> dict:
    cache_key = (actor_id or "__none__",)
    cached_payload = _cache_get(_dashboard_cache, cache_key)
    if cached_payload:
        return cached_payload

    process_approval_escalations(db)
    now_ts = _now()

    pending_total = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(RiskOrchestratorApprovalRequest.state.in_(["pending", "assigned"]))
        .count()
    )
    critical_queue = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(
            RiskOrchestratorApprovalRequest.state.in_(["pending", "assigned"]),
            RiskOrchestratorApprovalRequest.classification == "CRITICAL",
        )
        .count()
    )
    unassigned = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(
            RiskOrchestratorApprovalRequest.state.in_(["pending", "assigned"]),
            RiskOrchestratorApprovalRequest.assigned_to.is_(None),
        )
        .count()
    )
    my_approvals = 0
    if actor_id:
        my_approvals = (
            db.query(RiskOrchestratorApprovalRequest)
            .filter(
                RiskOrchestratorApprovalRequest.state.in_(["pending", "assigned"]),
                RiskOrchestratorApprovalRequest.assigned_to == actor_id,
            )
            .count()
        )

    reject_spike = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "risk_orchestrator_reject",
            AuditLog.created_at >= now_ts - timedelta(hours=1),
        )
        .count()
    )

    active_overrides = _active_overrides(db)
    override_usage = {
        "active_count": len(active_overrides),
        "total_notional_pct": sum(float((item.override_value or {}).get("max_notional_pct") or 0) for item in active_overrides),
    }

    traces = (
        db.query(RiskOrchestratorDecisionTrace)
        .filter(RiskOrchestratorDecisionTrace.created_at >= now_ts - timedelta(hours=24))
        .all()
    )
    distribution = {"safe": 0, "warning": 0, "critical": 0}
    for trace in traces:
        cls = (trace.classification or "").lower()
        if cls in distribution:
            distribution[cls] += 1

    throughput_rows = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(
            RiskOrchestratorApprovalRequest.state.in_(["approved", "rejected", "expired"]),
            RiskOrchestratorApprovalRequest.updated_at >= now_ts - timedelta(hours=1),
        )
        .all()
    )
    throughput: dict[str, int] = {}
    for row in throughput_rows:
        approver = row.second_approver_id or "system"
        throughput[approver] = throughput.get(approver, 0) + 1

    governance_rows = (
        db.query(RiskOrchestratorApprovalRequest)
        .filter(
            RiskOrchestratorApprovalRequest.classification == "CRITICAL",
            RiskOrchestratorApprovalRequest.state.in_(["pending", "assigned"]),
        )
        .all()
    )
    quorum_waiting = 0
    weighted_progress: list[dict] = []
    for row in governance_rows:
        progress = _governance_vote_progress(row.context_payload or {})
        total_weight = int(progress.get("total_weight") or 0)
        quorum_weight = int(progress.get("quorum_weight") or GOVERNANCE_QUORUM_WEIGHT)
        distinct = int(progress.get("distinct_voter_count") or 0)
        min_distinct = int(progress.get("min_distinct_approvers") or GOVERNANCE_MIN_DISTINCT_APPROVERS)
        if total_weight < quorum_weight or distinct < min_distinct:
            quorum_waiting += 1
            weighted_progress.append(
                {
                    "approval_id": row.approval_id,
                    "total_weight": total_weight,
                    "quorum_weight": quorum_weight,
                    "distinct_voters": distinct,
                    "required_distinct": min_distinct,
                }
            )

    predictive_signal = _predictive_risk_signal(db)

    payload = {
        "active_pending_approvals": pending_total,
        "critical_queue": critical_queue,
        "unassigned": unassigned,
        "my_approvals": my_approvals,
        "reject_spike_last_hour": reject_spike,
        "override_usage": override_usage,
        "risk_score_distribution": distribution,
        "approval_throughput_last_hour": throughput,
        "predictive_risk_signal": predictive_signal,
        "governance": {
            "critical_quorum_waiting": quorum_waiting,
            "weighted_progress": weighted_progress[:10],
        },
    }
    _cache_set(_dashboard_cache, cache_key, payload, DASHBOARD_CACHE_TTL_SECONDS)
    return payload


def list_decision_traces(db: Session, *, limit: int = 100) -> list[RiskOrchestratorDecisionTrace]:
    return (
        db.query(RiskOrchestratorDecisionTrace)
        .order_by(RiskOrchestratorDecisionTrace.created_at.desc())
        .limit(limit)
        .all()
    )


def export_decision_traces(db: Session, *, limit: int = 500) -> list[dict]:
    traces = list_decision_traces(db, limit=limit)
    payload: list[dict] = []
    for trace in traces:
        payload.append(
            {
                "trace_id": trace.trace_id,
                "flow_type": trace.flow_type,
                "simulation_id": trace.simulation_id,
                "classification": trace.classification,
                "risk_score": trace.risk_score,
                "rule_path": trace.rule_path,
                "decision_state": trace.decision_state,
                "requested_by": trace.requested_by,
                "approver_id": trace.approver_id,
                "request_key": trace.request_key,
                "reason_note": trace.reason_note,
                "approval_note": trace.approval_note,
                "payload": _jsonify(trace.payload),
                "created_at": trace.created_at.isoformat() if trace.created_at else None,
            }
        )
    return payload


def simulate_revert_to_version(
    db: Session,
    *,
    version_id: str,
    actor_id: str,
    actor_role: str,
) -> dict:
    source = (
        db.query(RiskOrchestratorPolicyVersion)
        .filter(RiskOrchestratorPolicyVersion.version_id == version_id)
        .first()
    )
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="policy_version_not_found")

    simulation = simulate_policy_change(
        db,
        actor_id=actor_id,
        actor_role=actor_role,
        candidate_payload=source.policy_payload,
    )
    simulation["approval_flow"] = {
        **simulation.get("approval_flow", {}),
        "flow_type": "revert",
        "source_version_id": version_id,
    }
    return {
        "version_id": version_id,
        "simulation": simulation,
    }


def apply_revert_from_simulation(
    db: Session,
    *,
    version_id: str,
    simulation_id: str,
    actor_id: str,
    actor_role: str,
    reason_note: str,
    double_confirmed: bool,
    apply_with_override: bool,
    request_key: str | None,
    expected_policy_version: int | None,
) -> dict:
    source = (
        db.query(RiskOrchestratorPolicyVersion)
        .filter(RiskOrchestratorPolicyVersion.version_id == version_id)
        .first()
    )
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="policy_version_not_found")

    simulation = (
        db.query(RiskOrchestratorPolicySimulation)
        .filter(RiskOrchestratorPolicySimulation.simulation_id == simulation_id)
        .first()
    )
    if simulation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="simulation_not_found")

    if (simulation.candidate_policy or {}) != (source.policy_payload or {}):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="revert_simulation_payload_mismatch")

    result = apply_policy_from_simulation(
        db,
        simulation_id=simulation_id,
        actor_id=actor_id,
        actor_role=actor_role,
        reason_note=reason_note,
        double_confirmed=double_confirmed,
        apply_with_override=apply_with_override,
        approval_note="revert_apply",
        request_key=request_key,
        expected_policy_version=expected_policy_version,
        flow_type="revert",
    )

    if result.get("policy") is not None and result.get("status") == "applied":
        latest_version = (
            db.query(RiskOrchestratorPolicyVersion)
            .order_by(RiskOrchestratorPolicyVersion.created_at.desc())
            .first()
        )
        if latest_version is not None:
            latest_version.reverted_from_version_id = version_id
            db.commit()

    return result


def list_policy_history(db: Session, *, limit: int = 25) -> dict:
    versions = (
        db.query(RiskOrchestratorPolicyVersion)
        .order_by(RiskOrchestratorPolicyVersion.created_at.desc())
        .limit(limit)
        .all()
    )
    requests = (
        db.query(RiskOrchestratorPolicyChangeRequest)
        .order_by(RiskOrchestratorPolicyChangeRequest.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "versions": versions,
        "change_requests": requests,
    }


def revert_policy_to_version(
    db: Session,
    *,
    version_id: str,
    actor_id: str,
    actor_role: str,
    reason_note: str,
    double_confirmed: bool,
) -> dict:
    if not double_confirmed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="double_confirmation_required")

    source = (
        db.query(RiskOrchestratorPolicyVersion)
        .filter(RiskOrchestratorPolicyVersion.version_id == version_id)
        .first()
    )
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="policy_version_not_found")

    current_policy = get_or_create_policy(db)
    before_payload = _policy_payload(current_policy)
    updated_policy = update_policy(db, payload=source.policy_payload)
    updated_policy.policy_version = int(getattr(updated_policy, "policy_version", 1) or 1) + 1

    new_version = RiskOrchestratorPolicyVersion(
        version_id=f"ro-pv-{uuid4().hex[:18]}",
        version_no=updated_policy.policy_version,
        policy_payload=_policy_payload(updated_policy),
        diff_payload=_policy_diff(before_payload, _policy_payload(updated_policy)),
        changed_by=actor_id,
        changed_role=actor_role,
        reason_note=reason_note,
        simulation_id=None,
        approval_request_id=None,
        reverted_from_version_id=source.version_id,
    )
    db.add(new_version)
    db.commit()
    db.refresh(updated_policy)
    db.refresh(new_version)

    create_audit_log(
        db,
        action="risk_orchestrator_policy_reverted",
        entity_type="risk_orchestrator_policy",
        entity_id=updated_policy.id,
        actor_user_id=actor_id,
        actor_role=actor_role,
        details={
            "reverted_from_version_id": source.version_id,
            "new_version_id": new_version.version_id,
            "reason_note": reason_note,
        },
        severity="high",
    )

    return {
        "policy": updated_policy,
        "new_version": new_version,
        "source_version": source,
    }


def create_manual_override(
    db: Session,
    *,
    actor_id: str,
    actor_role: str,
    override_type: str,
    target_key: str,
    reason_note: str,
    override_value: dict,
    expires_in_minutes: int | None = None,
) -> RiskOrchestratorManualOverride:
    active_overrides = _active_overrides(db)
    if len(active_overrides) >= OVERRIDE_ACTIVE_LIMIT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="override_count_limit_reached")

    requested_notional = float((override_value or {}).get("max_notional_pct") or 0)
    if requested_notional > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="override_notional_too_high")

    projected_total = sum(float((item.override_value or {}).get("max_notional_pct") or 0) for item in active_overrides)
    projected_total += max(requested_notional, 0)
    if projected_total > OVERRIDE_TOTAL_NOTIONAL_LIMIT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="override_total_notional_limit_reached")

    expires_at = None
    if expires_in_minutes and expires_in_minutes > 0:
        expires_at = _now() + timedelta(minutes=expires_in_minutes)

    override = RiskOrchestratorManualOverride(
        override_id=f"ro-ovr-{uuid4().hex[:18]}",
        override_type=override_type,
        target_key=target_key.upper(),
        override_value=override_value,
        reason_note=reason_note,
        actor_id=actor_id,
        actor_role=actor_role,
        status="active",
        expires_at=expires_at,
    )
    db.add(override)
    db.commit()
    db.refresh(override)

    create_audit_log(
        db,
        action="risk_orchestrator_override_created",
        entity_type="risk_orchestrator_override",
        entity_id=override.override_id,
        actor_user_id=actor_id,
        actor_role=actor_role,
        details={
            "override_type": override.override_type,
            "target_key": override.target_key,
            "override_value": override.override_value,
            "reason_note": reason_note,
            "expires_at": _serialize_datetime(override.expires_at),
        },
        severity="medium",
    )
    return override


def list_manual_overrides(db: Session, *, active_only: bool = True) -> list[RiskOrchestratorManualOverride]:
    _maintain_override_health(db)
    query = db.query(RiskOrchestratorManualOverride)
    if active_only:
        now_ts = _now()
        query = query.filter(
            RiskOrchestratorManualOverride.status == "active",
            or_(
                RiskOrchestratorManualOverride.expires_at.is_(None),
                RiskOrchestratorManualOverride.expires_at > now_ts,
            ),
        )
    return query.order_by(RiskOrchestratorManualOverride.created_at.desc()).all()


def deactivate_manual_override(
    db: Session,
    *,
    override_id: str,
    actor_id: str,
    actor_role: str,
    reason_note: str,
) -> RiskOrchestratorManualOverride:
    override = (
        db.query(RiskOrchestratorManualOverride)
        .filter(RiskOrchestratorManualOverride.override_id == override_id)
        .first()
    )
    if override is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="override_not_found")

    override.status = "inactive"
    override.deactivated_at = _now()
    override.updated_at = _now()
    db.commit()
    db.refresh(override)

    create_audit_log(
        db,
        action="risk_orchestrator_override_deactivated",
        entity_type="risk_orchestrator_override",
        entity_id=override.override_id,
        actor_user_id=actor_id,
        actor_role=actor_role,
        details={"reason_note": reason_note, "target_key": override.target_key, "override_type": override.override_type},
        severity="medium",
    )
    return override


def _intent_notional(intent: ExecutionIntent) -> float:
    price_ref = intent.price_reference or {}
    price = price_ref.get("value") or price_ref.get("last_price") or price_ref.get("price") or 0
    price = float(price) if price is not None else 0
    return abs(float(intent.quantity or 0) * float(price or 0))


def _decision_notional(decision_result: dict, context_payload: dict) -> float:
    price_ref = decision_result.get("price_reference") or {}
    price = price_ref.get("value") or price_ref.get("last_price")
    if price is None:
        price = context_payload.get("market_snapshot", {}).get("last_price")
    price = float(price or 0)
    return abs(float(decision_result.get("size") or 0) * float(price or 0))


def _load_intents(
    db: Session,
    *,
    since: datetime | None = None,
    strategy_id: str | None = None,
    symbol: str | None = None,
    account_id: str | None = None,
) -> list[ExecutionIntent]:
    query = db.query(ExecutionIntent)
    if since is not None:
        query = query.filter(ExecutionIntent.created_at >= since)
    if strategy_id:
        query = query.filter(ExecutionIntent.strategy_id == strategy_id)
    if symbol:
        query = query.filter(ExecutionIntent.symbol == symbol)
    if account_id:
        query = query.filter(ExecutionIntent.account_id == account_id)
    return query.all()


def _open_intents(intents: Iterable[ExecutionIntent], db: Session) -> list[ExecutionIntent]:
    intents = list(intents)
    if not intents:
        return []
    intent_ids = [intent.intent_id for intent in intents]
    finalized = (
        db.query(ExecutionIntentEvent)
        .filter(
            ExecutionIntentEvent.intent_id.in_(intent_ids),
            ExecutionIntentEvent.event_type == "execution.order.finalized",
        )
        .all()
    )
    closed_ids = {event.intent_id for event in finalized}
    return [intent for intent in intents if intent.intent_id not in closed_ids]


def _build_exposure_rows(intents: list[ExecutionIntent], *, key_fn) -> list[dict]:
    buckets: dict[str, dict] = {}
    for intent in intents:
        key = key_fn(intent)
        if key not in buckets:
            buckets[key] = {"key": key, "open_count": 0, "notional": 0.0}
        buckets[key]["open_count"] += 1
        buckets[key]["notional"] += _intent_notional(intent)
    rows = list(buckets.values())
    rows.sort(key=lambda item: item["notional"], reverse=True)
    return rows


def build_status_snapshot(db: Session) -> dict:
    _maintain_override_health(db)
    policy = get_or_create_policy(db)
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    safety = execution_safety_snapshot(db)
    since = _now() - timedelta(hours=24)
    open_intents = _open_intents(_load_intents(db, since=since), db)
    kill_switch_active = (not safety.get("trading_enabled", True)) or (bool(control.emergency_mode) if control else False)
    kill_reasons = []
    if not safety.get("trading_enabled", True):
        kill_reasons.append("trading_disabled")
    if control and control.emergency_mode:
        kill_reasons.append("emergency_mode")
    return {
        "policy": policy,
        "kill_switch_active": kill_switch_active,
        "kill_switch_reasons": kill_reasons,
        "trading_enabled": bool(safety.get("trading_enabled", True)),
        "open_intents": len(open_intents),
        "open_intents_by_symbol": _build_exposure_rows(open_intents, key_fn=lambda intent: intent.symbol),
        "open_intents_by_strategy": _build_exposure_rows(open_intents, key_fn=lambda intent: intent.strategy_id),
    }


def _emit_risk_alerts(db: Session, *, reason_codes: list[str], strategy_id: str, symbol: str | None) -> None:
    if not reason_codes:
        return
    if "daily_loss_limit_exceeded" in reason_codes:
        create_system_alert(
            db,
            alert_type="daily_loss_limit_hit",
            severity="CRITICAL",
            message="Daily loss limit breached",
            details={"strategy_id": strategy_id, "symbol": symbol, "reason_codes": reason_codes},
            entity_key=strategy_id,
            root_cause_code="daily_loss_limit_exceeded",
            state_key="daily_loss_limit_exceeded",
        )
    if any(code in {"account_max_notional_exceeded", "symbol_max_exposure_exceeded"} for code in reason_codes):
        create_system_alert(
            db,
            alert_type="exposure_limit_breach",
            severity="CRITICAL",
            message="Exposure limit breach detected",
            details={"strategy_id": strategy_id, "symbol": symbol, "reason_codes": reason_codes},
            entity_key=symbol or strategy_id,
            root_cause_code="exposure_limit_breach",
            state_key="exposure_limit_breach",
        )
    if any(code in {"duplicate_decision_hash", "duplicate_intent_hash"} for code in reason_codes):
        create_system_alert(
            db,
            alert_type="duplicate_execution_attempt",
            severity="CRITICAL",
            message="Duplicate execution attempt detected",
            details={"strategy_id": strategy_id, "symbol": symbol, "reason_codes": reason_codes},
            entity_key=strategy_id,
            root_cause_code="duplicate_execution_attempt",
            state_key="duplicate_execution_attempt",
        )


def evaluate_pre_trade(
    db: Session,
    *,
    strategy_id: str,
    decision_result: dict,
    context_payload: dict,
) -> dict:
    policy = get_or_create_policy(db)
    action = decision_result.get("action")
    if action in {"REJECT", "HOLD"}:
        return {"approved": True, "reason_codes": [], "metrics": {}}

    intent_payload = map_decision_to_intent(
        strategy_id=strategy_id,
        correlation_id=context_payload.get("correlation_id") or "",
        decision_result=decision_result,
        context_payload=context_payload,
    )
    if intent_payload is None:
        return {"approved": True, "reason_codes": [], "metrics": {}}

    account_id = intent_payload.get("account_id") or context_payload.get("account_id")
    reason_codes: list[str] = []

    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    safety = execution_safety_snapshot(db)
    if control and control.emergency_mode:
        reason_codes.append("kill_switch_active")
    if not safety.get("trading_enabled", True):
        reason_codes.append("trading_globally_paused")

    since = _now() - timedelta(hours=24)
    account_intents = _load_intents(db, since=since, account_id=account_id) if account_id else []
    if account_id and not account_intents:
        account_intents = _load_intents(db, since=since, strategy_id=strategy_id)
    if not account_id:
        account_intents = _load_intents(db, since=since, strategy_id=strategy_id)

    symbol_intents = _load_intents(
        db,
        since=since,
        symbol=intent_payload.get("symbol"),
        account_id=account_id,
    )
    if account_id and not symbol_intents:
        symbol_intents = _load_intents(db, since=since, symbol=intent_payload.get("symbol"), strategy_id=strategy_id)
    if not account_id:
        symbol_intents = _load_intents(db, since=since, symbol=intent_payload.get("symbol"), strategy_id=strategy_id)

    strategy_intents = _load_intents(db, since=since, strategy_id=strategy_id)

    open_account_intents = _open_intents(account_intents, db)
    open_symbol_intents = _open_intents(symbol_intents, db)
    open_strategy_intents = _open_intents(strategy_intents, db)

    account_notional = sum(_intent_notional(intent) for intent in open_account_intents)
    symbol_notional = sum(_intent_notional(intent) for intent in open_symbol_intents)

    proposed_notional = _decision_notional(decision_result, context_payload)

    account_state = context_payload.get("account_state_projection", {}) or {}
    equity = float(account_state.get("equity") or policy.reference_equity_usd or 0)

    account_limit = equity * (policy.account_max_notional_pct / 100)
    symbol_limit = equity * (policy.symbol_max_notional_pct / 100)

    applied_override_ids: list[str] = []
    active_overrides = list_manual_overrides(db, active_only=True)
    for override in active_overrides:
        if not _ensure_active_override_scope(override):
            continue
        if not _match_override(
            override,
            symbol=intent_payload.get("symbol"),
            strategy_id=strategy_id,
        ):
            continue

        applied_override_ids.append(override.override_id)
        value = override.override_value or {}
        max_notional_pct = value.get("max_notional_pct")
        max_open_count = value.get("max_open_count")
        block_new_adds = bool(value.get("block_new_adds"))

        if max_notional_pct is not None:
            limit_override = equity * (float(max_notional_pct) / 100)
            if override.override_type in {"symbol", "symbol_exposure"}:
                symbol_limit = min(symbol_limit, limit_override) if symbol_limit > 0 else limit_override
            else:
                account_limit = min(account_limit, limit_override) if account_limit > 0 else limit_override

        if max_open_count is not None:
            if override.override_type in {"symbol", "symbol_exposure"}:
                if len(open_symbol_intents) >= int(max_open_count):
                    reason_codes.append("symbol_override_open_count_limit")
            else:
                if len(open_strategy_intents) >= int(max_open_count):
                    reason_codes.append("strategy_override_open_count_limit")

        if block_new_adds:
            reason_codes.append("manual_block_new_adds")

    if account_limit > 0 and (account_notional + proposed_notional) > account_limit:
        reason_codes.append("account_max_notional_exceeded")
    if symbol_limit > 0 and (symbol_notional + proposed_notional) > symbol_limit:
        reason_codes.append("symbol_max_exposure_exceeded")

    if len(open_strategy_intents) >= policy.strategy_max_concurrent_positions:
        reason_codes.append("strategy_concurrent_limit")

    latest_intent = (
        db.query(ExecutionIntent)
        .filter(ExecutionIntent.strategy_id == strategy_id)
        .order_by(ExecutionIntent.created_at.desc())
        .first()
    )
    if latest_intent is not None:
        cooldown_seconds = policy.strategy_cooldown_seconds
        if cooldown_seconds > 0:
            elapsed = (_now() - latest_intent.created_at).total_seconds()
            if elapsed < cooldown_seconds:
                reason_codes.append("strategy_cooldown_active")

    one_minute = _now() - timedelta(seconds=60)
    recent_count = (
        db.query(ExecutionIntent)
        .filter(ExecutionIntent.strategy_id == strategy_id, ExecutionIntent.created_at >= one_minute)
        .count()
    )
    if recent_count >= policy.max_order_frequency_per_min:
        reason_codes.append("order_frequency_limit")

    ten_seconds = _now() - timedelta(seconds=10)
    burst_count = (
        db.query(ExecutionIntent)
        .filter(ExecutionIntent.strategy_id == strategy_id, ExecutionIntent.created_at >= ten_seconds)
        .count()
    )
    if burst_count >= policy.max_order_burst_per_10s:
        reason_codes.append("order_burst_limit")

    duplicate_window = _now() - timedelta(seconds=policy.duplicate_suppression_window_seconds)
    duplicate_decision = (
        db.query(ExecutionIntent)
        .filter(
            ExecutionIntent.decision_hash == decision_result.get("decision_hash"),
            ExecutionIntent.created_at >= duplicate_window,
        )
        .first()
    )
    if duplicate_decision is not None:
        reason_codes.append("duplicate_decision_hash")

    duplicate_intent = (
        db.query(ExecutionIntent)
        .filter(ExecutionIntent.intent_hash == intent_payload.get("intent_hash"))
        .first()
    )
    if duplicate_intent is not None:
        reason_codes.append("duplicate_intent_hash")

    daily_loss_pct = float(account_state.get("daily_loss_pct") or 0)
    daily_loss_usd = float(account_state.get("daily_loss_usd") or 0)
    if daily_loss_pct >= policy.daily_loss_limit_pct:
        reason_codes.append("daily_loss_limit_exceeded")
    if equity > 0 and daily_loss_usd >= (equity * (policy.daily_loss_limit_pct / 100)):
        reason_codes.append("daily_loss_limit_exceeded")

    if reason_codes:
        _emit_risk_alerts(
            db,
            reason_codes=reason_codes,
            strategy_id=strategy_id,
            symbol=intent_payload.get("symbol"),
        )

    return {
        "approved": len(reason_codes) == 0,
        "reason_codes": reason_codes,
        "metrics": {
            "account_notional": account_notional,
            "symbol_notional": symbol_notional,
            "proposed_notional": proposed_notional,
            "open_strategy_intents": len(open_strategy_intents),
            "open_account_intents": len(open_account_intents),
            "open_symbol_intents": len(open_symbol_intents),
            "recent_count": recent_count,
            "burst_count": burst_count,
            "equity": equity,
            "applied_override_ids": applied_override_ids,
        },
    }


def run_in_trade_supervisor(
    db: Session,
    *,
    persist: bool = False,
    actor_id: str | None = None,
    actor_role: str = "system",
) -> dict:
    snapshot = build_status_snapshot(db)
    policy: RiskOrchestratorPolicy = snapshot["policy"]
    breaches: list[dict] = []
    reference_equity = float(policy.reference_equity_usd or 0)

    for row in snapshot["open_intents_by_strategy"]:
        if row["open_count"] > policy.strategy_max_concurrent_positions:
            breaches.append(
                {
                    "breach_type": "strategy_concurrent_limit",
                    "key": row["key"],
                    "open_count": row["open_count"],
                    "notional": row["notional"],
                    "limit_pct": None,
                }
            )
        if reference_equity > 0:
            limit = reference_equity * (policy.account_max_notional_pct / 100)
            if row["notional"] > limit:
                breaches.append(
                    {
                        "breach_type": "account_max_notional_exceeded",
                        "key": row["key"],
                        "open_count": row["open_count"],
                        "notional": row["notional"],
                        "limit_pct": policy.account_max_notional_pct,
                    }
                )

    for row in snapshot["open_intents_by_symbol"]:
        if reference_equity > 0:
            limit = reference_equity * (policy.symbol_max_notional_pct / 100)
            if row["notional"] > limit:
                breaches.append(
                    {
                        "breach_type": "symbol_max_exposure_exceeded",
                        "key": row["key"],
                        "open_count": row["open_count"],
                        "notional": row["notional"],
                        "limit_pct": policy.symbol_max_notional_pct,
                    }
                )

    if persist and breaches:
        for breach in breaches:
            severity = "CRITICAL"
            suggested_action = "reduce_position"
            if breach["breach_type"] in {"strategy_concurrent_limit", "symbol_max_exposure_exceeded"}:
                severity = "WARNING"
            if breach["breach_type"] == "account_max_notional_exceeded":
                suggested_action = "global_trading_pause"

            trigger = RiskOrchestratorAutoTriggerLog(
                trigger_id=f"ro-trigger-{uuid4().hex[:18]}",
                breach_type=breach["breach_type"],
                target_key=str(breach["key"]),
                severity=severity.lower(),
                suggested_action=suggested_action,
                payload=breach,
            )
            db.add(trigger)

            create_system_alert(
                db,
                alert_type="risk_orchestrator_breach",
                severity=severity,
                message=f"Risk breach detected: {breach['breach_type']}",
                details=breach,
                entity_key=str(breach["key"]),
                root_cause_code=breach["breach_type"],
                state_key=f"risk_orchestrator_breach_{breach['breach_type']}",
            )

        db.commit()

        if actor_id:
            create_audit_log(
                db,
                action="risk_orchestrator_supervisor_run",
                entity_type="risk_orchestrator_supervisor",
                entity_id="global",
                actor_user_id=actor_id,
                actor_role=actor_role,
                details={"breach_count": len(breaches), "breaches": breaches},
                severity="medium",
            )

    return {
        "evaluated_at": _now(),
        "breaches": breaches,
    }


def execute_control_action(
    db: Session,
    *,
    action_type: str,
    reason_note: str,
    actor_id: str,
    actor_role: str,
    context: dict | None = None,
) -> dict:
    payload = context or {}
    effective_state: dict = {}

    if action_type in {"kill_switch", "global_trading_pause"}:
        effective_state = _jsonify(
            update_execution_safety_state(
                db,
                trading_enabled=False,
                max_total_exposure=float(payload.get("max_total_exposure") or 0),
                max_active_positions=int(payload.get("max_active_positions") or 0),
                reason=f"risk_orchestrator:{action_type}:{reason_note}",
                requested_by=actor_id,
                effective_at=None,
                actor_user_id=actor_id,
                actor_role=actor_role,
            )
        )
    elif action_type == "force_risk_check":
        effective_state = _jsonify(
            run_in_trade_supervisor(
                db,
                persist=True,
                actor_id=actor_id,
                actor_role=actor_role,
            )
        )
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_action_type")

    intervention = RiskOrchestratorInterventionLog(
        intervention_id=f"ro-int-{uuid4().hex[:18]}",
        intent_id=None,
        action_type=f"control_{action_type}",
        reason_note=reason_note,
        actor_id=actor_id,
        actor_role=actor_role,
        status="success",
        payload=payload,
        result_summary=effective_state,
    )
    db.add(intervention)
    db.commit()
    db.refresh(intervention)

    create_audit_log(
        db,
        action="risk_orchestrator_control_action",
        entity_type="risk_orchestrator_control",
        entity_id=intervention.intervention_id,
        actor_user_id=actor_id,
        actor_role=actor_role,
        details={"action_type": action_type, "reason_note": reason_note, "effective_state": effective_state},
        severity="high",
    )
    return {
        "intervention": intervention,
        "effective_state": effective_state,
    }


def list_open_positions(db: Session, *, limit: int = 100) -> list[Position]:
    return (
        db.query(Position)
        .filter(Position.status.in_(["OPEN", "open"]))
        .order_by(Position.updated_at.desc())
        .limit(limit)
        .all()
    )


def execute_position_intervention(
    db: Session,
    *,
    position_id: str,
    action_type: str,
    reason_note: str,
    actor_id: str,
    actor_role: str,
    payload: dict | None = None,
) -> dict:
    position = db.query(Position).filter(Position.position_id == position_id).first()
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="position_not_found")

    context = payload or {}
    result_summary: dict = {}

    if action_type == "reduce_position":
        reduce_ratio = float(context.get("reduce_ratio") or 0.5)
        reduce_ratio = max(0.05, min(0.95, reduce_ratio))
        before_qty = float(position.size or 0)
        new_qty = max(before_qty * (1 - reduce_ratio), 0.0)
        position.size = new_qty
        if new_qty <= 0.0000001:
            position.status = "closed"
        position.updated_at = _now()
        result_summary = {"before_quantity": before_qty, "after_quantity": new_qty, "reduce_ratio": reduce_ratio}
    elif action_type == "close_position":
        before_qty = float(position.size or 0)
        position.size = 0.0
        position.status = "closed"
        position.updated_at = _now()
        result_summary = {"before_quantity": before_qty, "after_quantity": 0.0, "closed": True}
    elif action_type == "block_further_adds":
        target_key = f"SYMBOL:{(position.symbol or '').upper()}"
        override = create_manual_override(
            db,
            actor_id=actor_id,
            actor_role=actor_role,
            override_type="block_adds",
            target_key=target_key,
            reason_note=reason_note,
            override_value={"block_new_adds": True},
            expires_in_minutes=int(context.get("expires_in_minutes") or 60),
        )
        result_summary = {"created_override_id": override.override_id, "target_key": target_key}
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_intervention_type")

    intervention = RiskOrchestratorInterventionLog(
        intervention_id=f"ro-int-{uuid4().hex[:18]}",
        intent_id=position.position_id,
        action_type=action_type,
        reason_note=reason_note,
        actor_id=actor_id,
        actor_role=actor_role,
        status="success",
        payload=context,
        result_summary=result_summary,
    )
    db.add(intervention)
    db.commit()
    db.refresh(intervention)
    db.refresh(position)

    create_audit_log(
        db,
        action="risk_orchestrator_position_intervention",
        entity_type="position",
        entity_id=position.position_id,
        actor_user_id=actor_id,
        actor_role=actor_role,
        details={"action_type": action_type, "reason_note": reason_note, "result_summary": result_summary},
        severity="high",
    )

    return {
        "position": position,
        "intervention": intervention,
    }


def list_auto_trigger_logs(db: Session, *, limit: int = 50) -> list[RiskOrchestratorAutoTriggerLog]:
    return (
        db.query(RiskOrchestratorAutoTriggerLog)
        .order_by(RiskOrchestratorAutoTriggerLog.created_at.desc())
        .limit(limit)
        .all()
    )


def list_risk_alerts(db: Session, *, severity: str | None = None, limit: int = 50) -> list[SystemAlert]:
    _maintain_override_health(db)
    query = db.query(SystemAlert).filter(
        SystemAlert.alert_type.in_(
            [
                "risk_orchestrator_breach",
                "daily_loss_limit_hit",
                "exposure_limit_breach",
                "risk_override_expiry_soon",
            ]
        )
    )
    if severity:
        query = query.filter(SystemAlert.severity == severity.upper())
    return query.order_by(SystemAlert.created_at.desc()).limit(limit).all()


def list_risk_rejects(
    db: Session,
    *,
    reason_code: str | None = None,
    symbol: str | None = None,
    strategy_id: str | None = None,
    limit: int = 100,
) -> list[AuditLog]:
    query = (
        db.query(AuditLog)
        .filter(AuditLog.action == "risk_orchestrator_reject")
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    rows = query.all()
    filtered: list[AuditLog] = []
    for row in rows:
        details = row.details or {}
        if reason_code and reason_code not in (details.get("reason_codes") or []):
            continue
        if symbol and (details.get("symbol") or "").upper() != symbol.upper():
            continue
        if strategy_id and details.get("strategy_id") != strategy_id:
            continue
        filtered.append(row)
    return filtered


def get_reject_detail(db: Session, *, audit_log_id: str) -> AuditLog:
    row = db.query(AuditLog).filter(AuditLog.id == audit_log_id, AuditLog.action == "risk_orchestrator_reject").first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="risk_reject_not_found")
    return row


def build_audit_timeline(db: Session, *, limit: int = 100) -> list[dict]:
    items: list[dict] = []

    versions = (
        db.query(RiskOrchestratorPolicyVersion)
        .order_by(RiskOrchestratorPolicyVersion.created_at.desc())
        .limit(limit)
        .all()
    )
    for version in versions:
        items.append(
            {
                "event_id": version.version_id,
                "event_type": "policy_version",
                "actor_id": version.changed_by,
                "actor_role": version.changed_role,
                "status": "applied",
                "reason_note": version.reason_note,
                "payload": {
                    "version_no": version.version_no,
                    "simulation_id": version.simulation_id,
                    "approval_request_id": version.approval_request_id,
                },
                "created_at": version.created_at,
            }
        )

    overrides = (
        db.query(RiskOrchestratorManualOverride)
        .order_by(RiskOrchestratorManualOverride.created_at.desc())
        .limit(limit)
        .all()
    )
    for override in overrides:
        items.append(
            {
                "event_id": override.override_id,
                "event_type": "manual_override",
                "actor_id": override.actor_id,
                "actor_role": override.actor_role,
                "status": override.status,
                "reason_note": override.reason_note,
                "payload": {
                    "override_type": override.override_type,
                    "target_key": override.target_key,
                    "override_value": override.override_value,
                },
                "created_at": override.created_at,
            }
        )

    interventions = (
        db.query(RiskOrchestratorInterventionLog)
        .order_by(RiskOrchestratorInterventionLog.created_at.desc())
        .limit(limit)
        .all()
    )
    for intervention in interventions:
        items.append(
            {
                "event_id": intervention.intervention_id,
                "event_type": "intervention",
                "actor_id": intervention.actor_id,
                "actor_role": intervention.actor_role,
                "status": intervention.status,
                "reason_note": intervention.reason_note,
                "payload": {
                    "action_type": intervention.action_type,
                    "intent_id": intervention.intent_id,
                    "result_summary": intervention.result_summary,
                },
                "created_at": intervention.created_at,
            }
        )

    triggers = (
        db.query(RiskOrchestratorAutoTriggerLog)
        .order_by(RiskOrchestratorAutoTriggerLog.created_at.desc())
        .limit(limit)
        .all()
    )
    for trigger in triggers:
        items.append(
            {
                "event_id": trigger.trigger_id,
                "event_type": "auto_trigger",
                "actor_id": trigger.acknowledged_by,
                "actor_role": "system",
                "status": trigger.severity,
                "reason_note": trigger.breach_type,
                "payload": {
                    "target_key": trigger.target_key,
                    "suggested_action": trigger.suggested_action,
                    "payload": trigger.payload,
                },
                "created_at": trigger.created_at,
            }
        )

    approvals = (
        db.query(RiskOrchestratorApprovalRequest)
        .order_by(RiskOrchestratorApprovalRequest.created_at.desc())
        .limit(limit)
        .all()
    )
    for request in approvals:
        items.append(
            {
                "event_id": request.approval_id,
                "event_type": "approval_request",
                "actor_id": request.requested_by,
                "actor_role": request.requested_role,
                "status": request.state,
                "reason_note": request.reason_note,
                "payload": {
                    "classification": request.classification,
                    "risk_score": request.risk_score,
                    "simulation_id": request.simulation_id,
                    "second_approver_id": request.second_approver_id,
                },
                "created_at": request.created_at,
            }
        )

    decision_traces = (
        db.query(RiskOrchestratorDecisionTrace)
        .order_by(RiskOrchestratorDecisionTrace.created_at.desc())
        .limit(limit)
        .all()
    )
    for trace in decision_traces:
        items.append(
            {
                "event_id": trace.trace_id,
                "event_type": "decision_trace",
                "actor_id": trace.requested_by,
                "actor_role": None,
                "status": trace.decision_state,
                "reason_note": trace.reason_note,
                "payload": {
                    "classification": trace.classification,
                    "risk_score": trace.risk_score,
                    "rule_path": trace.rule_path,
                    "approver_id": trace.approver_id,
                    "request_key": trace.request_key,
                },
                "created_at": trace.created_at,
            }
        )

    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items[:limit]
