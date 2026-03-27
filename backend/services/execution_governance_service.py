from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import (
    BrandSetting,
    ExecutionGovernanceEvent,
    ExecutionPolicy,
    ExecutionPolicyDecisionLog,
    ExecutionPolicyVersion,
    ExecutionRemediationRecommendation,
    ExecutionStrategyBinding,
)

GOVERNANCE_METADATA_KEY = "execution_governance"
DEFAULT_GOVERNANCE_CONFIG = {
    "auto_remediation_mode": "manual_recommend",
    "severity_overrides": {},
    "debug": {
        "enabled": False,
        "environments": [],
        "strategies": [],
        "request_ids": [],
    },
    "ab_testing_enabled": True,
}
SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_mode(context: dict) -> str:
    mode = str((context or {}).get("execution_mode") or "").strip().upper()
    if mode in {"REAL", "SIMULATION"}:
        return mode
    env = str((context or {}).get("environment") or "").strip().lower()
    return "REAL" if env in {"live", "prod", "production"} else "SIMULATION"


def _is_simulation_mode(context: dict) -> bool:
    return _normalize_mode(context) == "SIMULATION"


def get_governance_config(db: Session) -> dict:
    row = db.query(BrandSetting).filter(BrandSetting.id == "default").first()
    if row is None:
        row = BrandSetting(id="default", metadata_json={})
        db.add(row)
        db.flush()
    metadata = dict(row.metadata_json or {})
    config = dict(metadata.get(GOVERNANCE_METADATA_KEY) or {})
    merged = {
        **DEFAULT_GOVERNANCE_CONFIG,
        **config,
    }
    merged["debug"] = {
        **DEFAULT_GOVERNANCE_CONFIG["debug"],
        **dict(config.get("debug") or {}),
    }
    return merged


def is_debug_mode_enabled(db: Session, *, context: dict) -> bool:
    config = get_governance_config(db)
    debug = dict(config.get("debug") or {})
    if not bool(debug.get("enabled", False)):
        return False
    env = str(context.get("environment") or "").lower()
    strategy = str(context.get("strategy_binding") or "")
    request_id = str(context.get("request_id") or context.get("intent_token") or "")

    envs = {str(item).lower() for item in list(debug.get("environments") or []) if str(item).strip()}
    strategies = {str(item) for item in list(debug.get("strategies") or []) if str(item).strip()}
    request_ids = {str(item) for item in list(debug.get("request_ids") or []) if str(item).strip()}

    if envs and env not in envs:
        return False
    if strategies and strategy not in strategies:
        return False
    if request_ids and request_id not in request_ids:
        return False
    return True


def seed_default_strategy_bindings(db: Session, *, strategy_ids: list[str]) -> int:
    created = 0
    for strategy_id in strategy_ids:
        exists = db.query(ExecutionStrategyBinding).filter(ExecutionStrategyBinding.strategy_id == strategy_id).first()
        if exists is not None:
            continue
        db.add(
            ExecutionStrategyBinding(
                strategy_id=strategy_id,
                bound_policy_set=f"policy_set:{strategy_id}",
                risk_class="MEDIUM",
                execution_mode="SIMULATION",
                enabled=True,
                auto_disable_enabled=True,
                max_violation_count=5,
                limits={
                    "max_order_notional": 50000,
                    "max_exposure": 200000,
                    "max_daily_loss": 5000,
                    "max_open_positions": 20,
                },
                allowed_symbols=[],
                allowed_margin_modes=[],
                allowed_environments=["testnet", "staging", "dev", "live"],
                state="enabled",
            )
        )
        created += 1
    if created > 0:
        db.flush()
    return created


def get_strategy_binding(db: Session, strategy_id: str) -> ExecutionStrategyBinding | None:
    return db.query(ExecutionStrategyBinding).filter(ExecutionStrategyBinding.strategy_id == strategy_id).first()


def evaluate_strategy_binding_constraints(db: Session, *, context: dict) -> dict:
    strategy_id = str(context.get("strategy_binding") or "")
    env = str(context.get("environment") or "testnet").lower()
    symbol = str(context.get("symbol") or "").upper()
    margin_mode = str(context.get("margin_mode") or "").lower()

    binding = get_strategy_binding(db, strategy_id) if strategy_id else None
    if binding is None:
        return {
            "binding": None,
            "risk_class": "MEDIUM",
            "limits": {},
            "violations": [
                {
                    "reason_code": "STRATEGY_BINDING_MISSING",
                    "reason_message": "Strategy is not bound to governance policy set",
                    "severity": "HIGH",
                    "rule_id": "strategy.binding.required",
                }
            ],
        }

    violations = []
    if not bool(binding.enabled) or str(binding.state or "enabled").lower() == "disabled":
        violations.append(
            {
                "reason_code": "STRATEGY_DISABLED",
                "reason_message": "Strategy is disabled by governance state",
                "severity": "CRITICAL",
                "rule_id": "strategy.state",
            }
        )

    allowed_envs = [str(item).lower() for item in list(binding.allowed_environments or []) if str(item).strip()]
    if allowed_envs and env not in allowed_envs:
        violations.append(
            {
                "reason_code": "STRATEGY_ENVIRONMENT_NOT_ALLOWED",
                "reason_message": "Environment is not allowed for strategy",
                "severity": "HIGH",
                "rule_id": "strategy.allowed_environments",
            }
        )

    allowed_symbols = [str(item).upper() for item in list(binding.allowed_symbols or []) if str(item).strip()]
    if allowed_symbols and symbol and symbol not in allowed_symbols:
        violations.append(
            {
                "reason_code": "STRATEGY_SYMBOL_NOT_ALLOWED",
                "reason_message": "Symbol is not allowed for strategy",
                "severity": "HIGH",
                "rule_id": "strategy.allowed_symbols",
            }
        )

    allowed_margin_modes = [str(item).lower() for item in list(binding.allowed_margin_modes or []) if str(item).strip()]
    if allowed_margin_modes and margin_mode and margin_mode not in allowed_margin_modes:
        violations.append(
            {
                "reason_code": "STRATEGY_MARGIN_MODE_NOT_ALLOWED",
                "reason_message": "Margin mode is not allowed for strategy",
                "severity": "HIGH",
                "rule_id": "strategy.allowed_margin_modes",
            }
        )

    return {
        "binding": binding,
        "risk_class": str(binding.risk_class or "MEDIUM").upper(),
        "limits": dict(binding.limits or {}),
        "violations": violations,
    }


def _severity_index(severity: str) -> int:
    level = str(severity or "LOW").upper()
    if level not in SEVERITY_ORDER:
        return 0
    return SEVERITY_ORDER.index(level)


def classify_violation_severity(
    db: Session,
    *,
    reason_code: str,
    default_severity: str,
    strategy_risk_class: str,
) -> str:
    config = get_governance_config(db)
    overrides = dict(config.get("severity_overrides") or {})
    base = str(overrides.get(reason_code) or default_severity or "LOW").upper()
    base_idx = _severity_index(base)

    risk_class = str(strategy_risk_class or "MEDIUM").upper()
    if risk_class == "HIGH":
        base_idx = min(base_idx + 1, len(SEVERITY_ORDER) - 1)
    if str(reason_code or "").startswith("FAILSAFE_"):
        base_idx = len(SEVERITY_ORDER) - 1
    return SEVERITY_ORDER[base_idx]


def select_auto_action(
    db: Session,
    *,
    severity: str,
    reason_code: str,
    environment: str,
    strategy_risk_class: str,
    strategy_id: str,
    rolling_minutes: int = 60,
) -> str:
    _ = db
    severity_normalized = str(severity or "LOW").upper()
    env = str(environment or "testnet").lower()
    reason = str(reason_code or "")
    risk_class = str(strategy_risk_class or "MEDIUM").upper()

    if reason.startswith("FAILSAFE_"):
        return "ESCALATE_RELEASE_GATE"
    if severity_normalized == "CRITICAL":
        if risk_class == "HIGH":
            return "DISABLE_STRATEGY"
        return "BLOCK" if env in {"live", "prod", "production"} else "THROTTLE"
    if severity_normalized == "HIGH":
        return "THROTTLE"
    if severity_normalized == "MEDIUM":
        return "WARN"
    return "NONE"


def create_remediation_recommendation(
    db: Session,
    *,
    trace_id: str | None,
    source_violation_id: str | None,
    recommendation_type: str,
    severity: str,
    reason_code: str | None,
    summary: str,
    payload: dict,
    created_by: str | None = None,
) -> ExecutionRemediationRecommendation:
    row = ExecutionRemediationRecommendation(
        recommendation_id=str(uuid.uuid4()),
        trace_id=trace_id,
        source_violation_id=source_violation_id,
        recommendation_type=str(recommendation_type or "WARN"),
        severity=str(severity or "LOW").upper(),
        reason_code=reason_code,
        summary=summary,
        payload=dict(payload or {}),
        requires_manual_approval=True,
        status="PENDING",
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def list_remediation_recommendations(db: Session, *, status_filter: str | None = None, limit: int = 100) -> list[dict]:
    query = db.query(ExecutionRemediationRecommendation).order_by(ExecutionRemediationRecommendation.created_at.desc())
    if status_filter:
        query = query.filter(ExecutionRemediationRecommendation.status == str(status_filter).upper())
    rows = query.limit(max(min(limit, 500), 1)).all()
    return [
        {
            "recommendation_id": row.recommendation_id,
            "trace_id": row.trace_id,
            "source_violation_id": row.source_violation_id,
            "recommendation_type": row.recommendation_type,
            "severity": row.severity,
            "reason_code": row.reason_code,
            "summary": row.summary,
            "payload": row.payload or {},
            "status": row.status,
            "requires_manual_approval": bool(row.requires_manual_approval),
            "created_at": row.created_at,
            "approved_at": row.approved_at,
            "rejected_at": row.rejected_at,
        }
        for row in rows
    ]


def update_remediation_recommendation_status(
    db: Session,
    *,
    recommendation_id: str,
    action: str,
    actor_user_id: str,
) -> ExecutionRemediationRecommendation:
    row = (
        db.query(ExecutionRemediationRecommendation)
        .filter(ExecutionRemediationRecommendation.recommendation_id == recommendation_id)
        .first()
    )
    if row is None:
        raise ValueError("remediation_recommendation_not_found")

    normalized_action = str(action or "").strip().lower()
    if normalized_action == "approve":
        row.status = "APPROVED"
        row.approved_by = actor_user_id
        row.approved_at = _utcnow()
        emit_governance_event(
            db,
            event_type="remediation.approved",
            payload={
                "recommendation_id": row.recommendation_id,
                "action": row.recommendation_type,
                "actor_user_id": actor_user_id,
            },
            idempotency_key=f"remediation.approved:{row.recommendation_id}",
        )
    elif normalized_action == "reject":
        row.status = "REJECTED"
        row.rejected_by = actor_user_id
        row.rejected_at = _utcnow()
        emit_governance_event(
            db,
            event_type="remediation.rejected",
            payload={
                "recommendation_id": row.recommendation_id,
                "action": row.recommendation_type,
                "actor_user_id": actor_user_id,
            },
            idempotency_key=f"remediation.rejected:{row.recommendation_id}",
        )
    else:
        raise ValueError("invalid_remediation_action")
    row.updated_at = _utcnow()
    db.flush()
    return row


def emit_governance_event(db: Session, *, event_type: str, payload: dict, idempotency_key: str | None = None) -> ExecutionGovernanceEvent:
    idem = str(idempotency_key or f"{event_type}:{hashlib.sha1(str(payload).encode('utf-8')).hexdigest()[:24]}")
    existing = db.query(ExecutionGovernanceEvent).filter(ExecutionGovernanceEvent.idempotency_key == idem).first()
    if existing is not None:
        return existing
    row = ExecutionGovernanceEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        idempotency_key=idem,
        payload=dict(payload or {}),
        status="PENDING",
        retry_count=0,
    )
    db.add(row)
    db.flush()
    return row


def _rollout_matches(rollout_strategy: dict, context: dict) -> bool:
    strategy = dict(rollout_strategy or {})
    env = str(context.get("environment") or "").lower()
    strategy_id = str(context.get("strategy_binding") or "")
    symbol = str(context.get("symbol") or "").upper()
    user_id = str(context.get("user_id") or "")

    envs = [str(item).lower() for item in list(strategy.get("environments") or []) if str(item).strip()]
    strategies = [str(item) for item in list(strategy.get("strategy_ids") or []) if str(item).strip()]
    symbols = [str(item).upper() for item in list(strategy.get("symbols") or []) if str(item).strip()]
    if envs and env not in envs:
        return False
    if strategies and strategy_id not in strategies:
        return False
    if symbols and symbol not in symbols:
        return False

    pct = int(float(strategy.get("traffic_percentage") or 100))
    pct = max(min(pct, 100), 0)
    if pct >= 100:
        return True
    if pct <= 0:
        return False
    bucket_seed = user_id or str(context.get("trace_id") or context.get("intent_token") or "fallback")
    bucket = int(hashlib.sha1(bucket_seed.encode("utf-8")).hexdigest()[:8], 16) % 100
    return bucket < pct


def list_policy_versions(db: Session, *, policy_code: str | None = None, limit: int = 200) -> list[dict]:
    query = db.query(ExecutionPolicyVersion).order_by(ExecutionPolicyVersion.created_at.desc())
    if policy_code:
        query = query.filter(ExecutionPolicyVersion.policy_code == policy_code)
    rows = query.limit(max(min(limit, 500), 1)).all()
    return [
        {
            "version_id": row.version_id,
            "policy_code": row.policy_code,
            "version_number": row.version_number,
            "state": row.state,
            "approval_status": row.approval_status,
            "created_by": row.created_by,
            "approved_by": row.approved_by,
            "change_summary": row.change_summary,
            "effective_from": row.effective_from,
            "effective_to": row.effective_to,
            "rollback_target_version": row.rollback_target_version,
            "rollout_strategy": row.rollout_strategy or {},
            "created_at": row.created_at,
        }
        for row in rows
    ]


def create_policy_version(
    db: Session,
    *,
    policy_code: str,
    conditions_payload: dict,
    rules_payload: dict,
    change_summary: str,
    created_by: str,
    state: str = "DRAFT",
) -> ExecutionPolicyVersion:
    latest = (
        db.query(ExecutionPolicyVersion)
        .filter(ExecutionPolicyVersion.policy_code == policy_code)
        .order_by(ExecutionPolicyVersion.version_number.desc())
        .first()
    )
    version_no = int(latest.version_number if latest else 0) + 1
    row = ExecutionPolicyVersion(
        version_id=str(uuid.uuid4()),
        policy_code=policy_code,
        version_number=version_no,
        state=str(state or "DRAFT").upper(),
        approval_status="pending",
        created_by=created_by,
        change_summary=change_summary,
        rollout_strategy={},
        conditions_payload=dict(conditions_payload or {}),
        rules_payload=dict(rules_payload or {}),
    )
    db.add(row)
    db.flush()
    return row


def activate_policy_version(
    db: Session,
    *,
    version_id: str,
    actor_user_id: str,
    environment: str,
) -> ExecutionPolicyVersion:
    row = db.query(ExecutionPolicyVersion).filter(ExecutionPolicyVersion.version_id == version_id).first()
    if row is None:
        raise ValueError("policy_version_not_found")
    env = str(environment or "testnet").lower()
    if env in {"live", "prod", "production"} and str(row.approval_status or "pending").lower() != "approved":
        raise ValueError("approval_required_for_prod_activation")

    db.query(ExecutionPolicyVersion).filter(
        ExecutionPolicyVersion.policy_code == row.policy_code,
        ExecutionPolicyVersion.state.in_(["ACTIVE", "CANARY"]),
        ExecutionPolicyVersion.version_id != row.version_id,
    ).update({"state": "DEPRECATED", "updated_at": _utcnow()}, synchronize_session=False)

    row.state = "ACTIVE"
    row.effective_from = _utcnow()
    row.approved_by = actor_user_id if str(row.approval_status or "").lower() == "approved" else row.approved_by
    row.updated_at = _utcnow()

    policy = db.query(ExecutionPolicy).filter(ExecutionPolicy.policy_code == row.policy_code).first()
    if policy is not None:
        policy.rules_payload = dict(row.rules_payload or {})
        policy.conditions_payload = dict(row.conditions_payload or {})
        policy.updated_at = _utcnow()
    db.flush()
    return row


def approve_policy_version(
    db: Session,
    *,
    version_id: str,
    actor_user_id: str,
) -> ExecutionPolicyVersion:
    row = db.query(ExecutionPolicyVersion).filter(ExecutionPolicyVersion.version_id == version_id).first()
    if row is None:
        raise ValueError("policy_version_not_found")
    row.approval_status = "approved"
    row.approved_by = actor_user_id
    row.updated_at = _utcnow()
    db.flush()
    return row


def rollback_policy_version(
    db: Session,
    *,
    policy_code: str,
    target_version_id: str,
    actor_user_id: str,
    reason: str,
) -> ExecutionPolicyVersion:
    target = db.query(ExecutionPolicyVersion).filter(ExecutionPolicyVersion.version_id == target_version_id).first()
    if target is None or target.policy_code != policy_code:
        raise ValueError("rollback_target_not_found")

    db.query(ExecutionPolicyVersion).filter(
        ExecutionPolicyVersion.policy_code == policy_code,
        ExecutionPolicyVersion.state == "ACTIVE",
    ).update({
        "state": "ROLLED_BACK",
        "rollback_target_version": target_version_id,
        "updated_at": _utcnow(),
    }, synchronize_session=False)

    target.state = "ACTIVE"
    target.approved_by = actor_user_id
    target.approval_status = "approved"
    target.change_summary = f"{target.change_summary or ''}\nROLLBACK_REASON:{reason}".strip()
    target.updated_at = _utcnow()

    policy = db.query(ExecutionPolicy).filter(ExecutionPolicy.policy_code == policy_code).first()
    if policy is not None:
        policy.rules_payload = dict(target.rules_payload or {})
        policy.conditions_payload = dict(target.conditions_payload or {})
        policy.updated_at = _utcnow()
    db.flush()
    return target


def resolve_policy_version_override(db: Session, *, policy_code: str, context: dict) -> dict | None:
    active = (
        db.query(ExecutionPolicyVersion)
        .filter(ExecutionPolicyVersion.policy_code == policy_code, ExecutionPolicyVersion.state == "ACTIVE")
        .order_by(ExecutionPolicyVersion.version_number.desc())
        .first()
    )
    canary = (
        db.query(ExecutionPolicyVersion)
        .filter(ExecutionPolicyVersion.policy_code == policy_code, ExecutionPolicyVersion.state == "CANARY")
        .order_by(ExecutionPolicyVersion.version_number.desc())
        .first()
    )

    chosen = active
    mode = "ACTIVE"
    if canary is not None and _rollout_matches(canary.rollout_strategy or {}, context):
        chosen = canary
        mode = "CANARY"

    if chosen is None:
        return None
    return {
        "version_id": chosen.version_id,
        "version_number": chosen.version_number,
        "state": chosen.state,
        "mode": mode,
        "rules_payload": dict(chosen.rules_payload or {}),
        "conditions_payload": dict(chosen.conditions_payload or {}),
    }


def compare_policy_versions_ab(
    db: Session,
    *,
    policy_code: str,
    primary_version_id: str,
    shadow_version_id: str,
) -> dict:
    primary = db.query(ExecutionPolicyVersion).filter(ExecutionPolicyVersion.version_id == primary_version_id).first()
    shadow = db.query(ExecutionPolicyVersion).filter(ExecutionPolicyVersion.version_id == shadow_version_id).first()
    if primary is None or shadow is None:
        raise ValueError("ab_policy_versions_not_found")
    if primary.policy_code != policy_code or shadow.policy_code != policy_code:
        raise ValueError("ab_policy_code_mismatch")

    primary_rules = dict(primary.rules_payload or {})
    shadow_rules = dict(shadow.rules_payload or {})
    primary_conditions = dict(primary.conditions_payload or {})
    shadow_conditions = dict(shadow.conditions_payload or {})

    rules_delta_keys = sorted(set(primary_rules.keys()) ^ set(shadow_rules.keys()))
    changed_rule_keys = sorted(
        [key for key in set(primary_rules.keys()) & set(shadow_rules.keys()) if primary_rules.get(key) != shadow_rules.get(key)]
    )
    changed_condition_keys = sorted(
        [
            key
            for key in set(primary_conditions.keys()) | set(shadow_conditions.keys())
            if primary_conditions.get(key) != shadow_conditions.get(key)
        ]
    )

    return {
        "policy_code": policy_code,
        "primary_version": {
            "version_id": primary.version_id,
            "state": primary.state,
            "version_number": primary.version_number,
        },
        "shadow_version": {
            "version_id": shadow.version_id,
            "state": shadow.state,
            "version_number": shadow.version_number,
        },
        "decision_delta": {
            "rules_delta_keys": rules_delta_keys,
            "changed_rule_keys": changed_rule_keys,
            "changed_condition_keys": changed_condition_keys,
            "delta_score": len(rules_delta_keys) + len(changed_rule_keys) + len(changed_condition_keys),
        },
        "severity_delta": "estimated",
        "rejection_delta": "estimated",
        "trace_delta": {
            "primary_trace_hint": f"v{primary.version_number}",
            "shadow_trace_hint": f"v{shadow.version_number}",
        },
    }


def build_violation_aggregation(db: Session, *, window: str = "24h") -> dict:
    now = _utcnow()
    window_map = {
        "5m": timedelta(minutes=5),
        "1h": timedelta(hours=1),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
    }
    delta = window_map.get(window, timedelta(hours=24))
    since = now - delta
    rows = (
        db.query(ExecutionPolicyDecisionLog)
        .filter(ExecutionPolicyDecisionLog.created_at >= since, ExecutionPolicyDecisionLog.is_violation.is_(True))
        .order_by(ExecutionPolicyDecisionLog.created_at.desc())
        .all()
    )

    reason_dist: dict[str, int] = {}
    severity_dist: dict[str, int] = {}
    strategy_dist: dict[str, int] = {}
    user_dist: dict[str, int] = {}
    symbol_dist: dict[str, int] = {}
    simulation_count = 0
    real_count = 0
    for row in rows:
        code = str(row.reason_code or "UNKNOWN")
        severity = str(row.severity or "UNKNOWN").upper()
        strategy = str(row.strategy_binding or "UNKNOWN")
        user = str(row.user_id or "UNKNOWN")
        symbol = str(row.symbol or "UNKNOWN")
        reason_dist[code] = reason_dist.get(code, 0) + 1
        severity_dist[severity] = severity_dist.get(severity, 0) + 1
        strategy_dist[strategy] = strategy_dist.get(strategy, 0) + 1
        user_dist[user] = user_dist.get(user, 0) + 1
        symbol_dist[symbol] = symbol_dist.get(symbol, 0) + 1
        if bool(row.simulation_mode):
            simulation_count += 1
        else:
            real_count += 1

    return {
        "window": window,
        "violation_count": len(rows),
        "reason_code_distribution": reason_dist,
        "severity_distribution": severity_dist,
        "strategy_violation_density": strategy_dist,
        "user_repeat_violations": user_dist,
        "symbol_breach_rate": symbol_dist,
        "simulation_violation_count": simulation_count,
        "real_violation_count": real_count,
    }


def build_strategy_health_state(db: Session, *, window_hours: int = 24) -> list[dict]:
    since = _utcnow() - timedelta(hours=max(window_hours, 1))
    bindings = db.query(ExecutionStrategyBinding).all()
    payload = []
    for binding in bindings:
        violations = (
            db.query(ExecutionPolicyDecisionLog)
            .filter(
                ExecutionPolicyDecisionLog.strategy_binding == binding.strategy_id,
                ExecutionPolicyDecisionLog.is_violation.is_(True),
                ExecutionPolicyDecisionLog.created_at >= since,
            )
            .count()
        )
        critical = (
            db.query(ExecutionPolicyDecisionLog)
            .filter(
                ExecutionPolicyDecisionLog.strategy_binding == binding.strategy_id,
                ExecutionPolicyDecisionLog.is_violation.is_(True),
                ExecutionPolicyDecisionLog.severity == "CRITICAL",
                ExecutionPolicyDecisionLog.created_at >= since,
            )
            .count()
        )
        payload.append(
            {
                "strategy_id": binding.strategy_id,
                "bound_policy_set": binding.bound_policy_set,
                "risk_class": binding.risk_class,
                "state": binding.state,
                "enabled": bool(binding.enabled),
                "violation_count": violations,
                "last_critical_breach_count": critical,
            }
        )
    return payload


def build_release_gate_status(db: Session, *, window_hours: int = 24) -> dict:
    since = _utcnow() - timedelta(hours=max(window_hours, 1))
    violation_rows = (
        db.query(ExecutionPolicyDecisionLog)
        .filter(ExecutionPolicyDecisionLog.created_at >= since, ExecutionPolicyDecisionLog.is_violation.is_(True))
        .all()
    )
    total = len(violation_rows)
    critical = len([row for row in violation_rows if str(row.severity or "").upper() == "CRITICAL"])
    failsafe_hard = len(
        [
            row
            for row in violation_rows
            if str(row.reason_code or "").startswith("FAILSAFE_") and str(row.action_taken or "").upper() == "HARD_BLOCK"
        ]
    )
    disabled_strategy_count = (
        db.query(ExecutionStrategyBinding)
        .filter(ExecutionStrategyBinding.state == "disabled")
        .count()
    )

    if failsafe_hard > 0 or critical >= 3:
        status = "FAIL"
    elif critical > 0 or total >= 10:
        status = "WARN"
    elif disabled_strategy_count > 0:
        status = "PARTIAL_UNLOCK"
    else:
        status = "PASS"

    blocking_reasons = []
    if failsafe_hard > 0:
        blocking_reasons.append("failsafe_hard_block_detected")
    if critical >= 3:
        blocking_reasons.append("critical_violation_threshold_exceeded")
    if disabled_strategy_count > 0:
        blocking_reasons.append("strategy_disabled_present")

    recommendations = []
    if status in {"WARN", "FAIL", "PARTIAL_UNLOCK"}:
        recommendations.extend(
            [
                "Rollout fazını shadow/soft seviyesine çekin",
                "Yüksek violation reason_code’larını düzeltmeden canlı genişletmeyin",
                "Gerekirse policy rollback veya canary scope daraltması uygulayın",
            ]
        )

    affected_scopes = sorted(
        {
            str(row.strategy_binding)
            for row in violation_rows
            if str(row.strategy_binding or "").strip()
        }
    )

    return {
        "status": status,
        "summary": {
            "window_hours": window_hours,
            "violation_count": total,
            "critical_violation_count": critical,
            "failsafe_hard_block_count": failsafe_hard,
            "disabled_strategy_count": disabled_strategy_count,
        },
        "blocking_reasons": blocking_reasons,
        "recommended_actions": recommendations,
        "affected_scopes": {
            "strategies": affected_scopes,
            "environments": sorted({str(row.environment or "").lower() for row in violation_rows if row.environment}),
            "symbols": sorted({str(row.symbol or "").upper() for row in violation_rows if row.symbol}),
        },
        "safe_rollout_suggestion": "limited_canary" if status in {"WARN", "PARTIAL_UNLOCK"} else ("hold_release" if status == "FAIL" else "progressive_rollout"),
    }
