from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import AuditLog, ExecutionEnvironmentOverride, ExecutionPolicyDecisionLog, ExecutionSafeModeState
from services.execution_governance_service import build_release_gate_status


ENVIRONMENT_MAP = {
    "dev": "DEV",
    "development": "DEV",
    "staging": "STAGING",
    "stage": "STAGING",
    "prod": "PROD",
    "production": "PROD",
    "live": "PROD",
}


def normalize_environment(value: str | None) -> str:
    key = str(value or "").strip().lower()
    if not key:
        return "DEV"
    return ENVIRONMENT_MAP.get(key, key.upper())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _deep_merge(base: dict, patch: dict) -> dict:
    result = dict(base or {})
    for key, value in dict(patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _set_nested(payload: dict, path: str, value) -> dict:
    target = dict(payload or {})
    chunks = [item for item in str(path).split(".") if item]
    if not chunks:
        return target
    cursor = target
    for key in chunks[:-1]:
        nested = cursor.get(key)
        if not isinstance(nested, dict):
            nested = {}
            cursor[key] = nested
        cursor = nested
    cursor[chunks[-1]] = value
    return target


def _delete_nested(payload: dict, path: str) -> dict:
    target = dict(payload or {})
    chunks = [item for item in str(path).split(".") if item]
    if not chunks:
        return target
    cursor = target
    for key in chunks[:-1]:
        nested = cursor.get(key)
        if not isinstance(nested, dict):
            return target
        cursor = nested
    cursor.pop(chunks[-1], None)
    return target


def _scope_matches(row: ExecutionEnvironmentOverride, context: dict) -> bool:
    scope_type = str(row.scope_type or "GLOBAL").upper()
    scope_value = str(row.scope_value or "*")
    if scope_type == "GLOBAL":
        return True
    if scope_type == "ENVIRONMENT":
        return normalize_environment(context.get("environment")) == normalize_environment(scope_value)
    if scope_type == "STRATEGY":
        return str(context.get("strategy_binding") or "") == scope_value
    if scope_type == "SYMBOL":
        return str(context.get("symbol") or "").upper() == scope_value.upper()
    if scope_type == "USER":
        return str(context.get("user_id") or "") == scope_value
    if scope_type == "PORTFOLIO":
        return str(context.get("portfolio_id") or "") == scope_value
    return False


def list_environment_overrides(db: Session, *, environment: str | None = None) -> list[dict]:
    query = db.query(ExecutionEnvironmentOverride).order_by(ExecutionEnvironmentOverride.priority.asc(), ExecutionEnvironmentOverride.created_at.asc())
    if environment:
        env_norm = normalize_environment(environment)
        query = query.filter(ExecutionEnvironmentOverride.environment == env_norm)
    rows = query.all()
    return [
        {
            "override_id": row.override_id,
            "environment": row.environment,
            "scope_type": row.scope_type,
            "scope_value": row.scope_value,
            "priority": row.priority,
            "is_active": bool(row.is_active),
            "override_payload": row.override_payload or {},
            "change_summary": row.change_summary,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


def upsert_environment_override(
    db: Session,
    *,
    environment: str,
    scope_type: str,
    scope_value: str,
    priority: int,
    override_payload: dict,
    actor_user_id: str,
    change_summary: str,
) -> ExecutionEnvironmentOverride:
    env_norm = normalize_environment(environment)
    row = (
        db.query(ExecutionEnvironmentOverride)
        .filter(
            ExecutionEnvironmentOverride.environment == env_norm,
            ExecutionEnvironmentOverride.scope_type == str(scope_type or "GLOBAL").upper(),
            ExecutionEnvironmentOverride.scope_value == str(scope_value or "*"),
        )
        .first()
    )
    if row is None:
        row = ExecutionEnvironmentOverride(
            override_id=str(uuid.uuid4()),
            environment=env_norm,
            scope_type=str(scope_type or "GLOBAL").upper(),
            scope_value=str(scope_value or "*"),
            created_by=actor_user_id,
        )
        db.add(row)

    row.priority = int(priority)
    row.is_active = True
    row.override_payload = dict(override_payload or {})
    row.change_summary = change_summary
    row.updated_at = _utcnow()
    db.flush()
    return row


def apply_environment_overrides(db: Session, *, effective_rules: dict, context: dict) -> tuple[dict, list[dict]]:
    env_norm = normalize_environment(context.get("environment"))
    rows = (
        db.query(ExecutionEnvironmentOverride)
        .filter(
            ExecutionEnvironmentOverride.environment == env_norm,
            ExecutionEnvironmentOverride.is_active.is_(True),
        )
        .order_by(ExecutionEnvironmentOverride.priority.asc(), ExecutionEnvironmentOverride.created_at.asc())
        .all()
    )
    updated = dict(effective_rules or {})
    trace = []
    for row in rows:
        if not _scope_matches(row, context):
            continue
        payload = dict(row.override_payload or {})
        rule_sets = dict(payload.get("set_rules") or {})
        disabled_rules = list(payload.get("disable_rules") or [])

        for path, value in rule_sets.items():
            updated = _set_nested(updated, path, value)
        for path in disabled_rules:
            updated = _delete_nested(updated, path)

        if payload.get("rule_merge"):
            updated = _deep_merge(updated, dict(payload.get("rule_merge") or {}))

        trace.append(
            {
                "override_id": row.override_id,
                "environment": row.environment,
                "scope_type": row.scope_type,
                "scope_value": row.scope_value,
                "priority": row.priority,
                "set_rules": rule_sets,
                "disable_rules": disabled_rules,
            }
        )

    return updated, trace


def _safe_mode_default_payload() -> dict:
    return {
        "risk_multiplier": 0.5,
        "max_order_notional_cap": 10000,
        "leverage_cap": 1.5,
        "restrict_new_strategy_execution": True,
        "reduce_only_only": True,
    }


def _activate_safe_mode(
    db: Session,
    *,
    environment: str,
    scope_type: str,
    scope_value: str,
    trigger_reason: str,
    trigger_source: str,
    override_payload: dict,
    actor_user_id: str | None,
) -> ExecutionSafeModeState:
    row = (
        db.query(ExecutionSafeModeState)
        .filter(
            ExecutionSafeModeState.environment == environment,
            ExecutionSafeModeState.scope_type == scope_type,
            ExecutionSafeModeState.scope_value == scope_value,
            ExecutionSafeModeState.is_active.is_(True),
        )
        .first()
    )
    if row is None:
        row = ExecutionSafeModeState(
            safe_mode_id=str(uuid.uuid4()),
            environment=environment,
            scope_type=scope_type,
            scope_value=scope_value,
            is_active=True,
            trigger_reason=trigger_reason,
            trigger_source=trigger_source,
            activated_by=actor_user_id,
            activated_at=_utcnow(),
            override_payload=dict(override_payload or _safe_mode_default_payload()),
        )
        db.add(row)
    else:
        row.trigger_reason = trigger_reason
        row.trigger_source = trigger_source
        row.override_payload = dict(override_payload or row.override_payload or _safe_mode_default_payload())
        row.last_evaluated_at = _utcnow()
        row.updated_at = _utcnow()

    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_role="system" if actor_user_id is None else "admin",
            action="SAFE_MODE_ACTIVATED",
            entity_type="execution_safe_mode",
            entity_id=row.safe_mode_id,
            details={
                "environment": environment,
                "scope_type": scope_type,
                "scope_value": scope_value,
                "trigger_reason": trigger_reason,
                "trigger_source": trigger_source,
            },
        )
    )
    db.flush()
    return row


def evaluate_auto_safe_mode(db: Session, *, context: dict) -> list[ExecutionSafeModeState]:
    env_norm = normalize_environment(context.get("environment"))
    now = _utcnow()
    since = now - timedelta(minutes=15)
    rows = (
        db.query(ExecutionPolicyDecisionLog)
        .filter(
            ExecutionPolicyDecisionLog.environment == env_norm,
            ExecutionPolicyDecisionLog.is_violation.is_(True),
            ExecutionPolicyDecisionLog.created_at >= since,
        )
        .all()
    )
    critical_count = len([row for row in rows if str(row.severity or "").upper() == "CRITICAL"])
    failsafe_count = len([row for row in rows if str(row.reason_code or "").startswith("FAILSAFE_")])

    release_gate = build_release_gate_status(db, window_hours=1)
    trigger_reason = None
    if critical_count >= 5:
        trigger_reason = "critical_violation_rate_high"
    elif failsafe_count >= 3:
        trigger_reason = "failsafe_spike_detected"
    elif str(release_gate.get("status") or "PASS").upper() == "FAIL":
        trigger_reason = "release_gate_fail"

    if trigger_reason is None:
        return get_active_safe_modes(db, context=context)

    _activate_safe_mode(
        db,
        environment=env_norm,
        scope_type="ENVIRONMENT",
        scope_value=env_norm,
        trigger_reason=trigger_reason,
        trigger_source="AUTO",
        override_payload=_safe_mode_default_payload(),
        actor_user_id=None,
    )
    return get_active_safe_modes(db, context=context)


def get_active_safe_modes(db: Session, *, context: dict) -> list[ExecutionSafeModeState]:
    env_norm = normalize_environment(context.get("environment"))
    strategy = str(context.get("strategy_binding") or "")
    symbol = str(context.get("symbol") or "").upper()
    rows = (
        db.query(ExecutionSafeModeState)
        .filter(
            ExecutionSafeModeState.is_active.is_(True),
            ExecutionSafeModeState.environment.in_([env_norm, "GLOBAL"]),
        )
        .order_by(ExecutionSafeModeState.activated_at.desc())
        .all()
    )
    matched = []
    for row in rows:
        scope_type = str(row.scope_type or "GLOBAL").upper()
        scope_value = str(row.scope_value or "*")
        if scope_type == "GLOBAL":
            matched.append(row)
        elif scope_type == "ENVIRONMENT" and scope_value == env_norm:
            matched.append(row)
        elif scope_type == "STRATEGY" and scope_value == strategy:
            matched.append(row)
        elif scope_type == "SYMBOL" and scope_value.upper() == symbol:
            matched.append(row)
    return matched


def apply_safe_mode_overrides(db: Session, *, effective_rules: dict, context: dict) -> tuple[dict, list[dict], list[dict]]:
    active_states = evaluate_auto_safe_mode(db, context=context)
    if not active_states:
        return dict(effective_rules or {}), [], []

    merged = dict(effective_rules or {})
    traces: list[dict] = []
    findings: list[dict] = []

    risk_rules = dict(merged.get("risk") or {})
    execution_rules = dict(merged.get("execution") or {})
    post_trade_rules = dict(merged.get("post_trade") or {})

    risk_multiplier = 1.0
    max_order_cap = None
    leverage_cap = None
    restrict_new_strategy_execution = False
    reduce_only_only = False

    for state in active_states:
        payload = dict(state.override_payload or {})
        risk_multiplier = min(risk_multiplier, float(payload.get("risk_multiplier") or 1.0))
        if payload.get("max_order_notional_cap") is not None:
            value = float(payload.get("max_order_notional_cap"))
            max_order_cap = value if max_order_cap is None else min(max_order_cap, value)
        if payload.get("leverage_cap") is not None:
            value = float(payload.get("leverage_cap"))
            leverage_cap = value if leverage_cap is None else min(leverage_cap, value)
        restrict_new_strategy_execution = restrict_new_strategy_execution or bool(payload.get("restrict_new_strategy_execution"))
        reduce_only_only = reduce_only_only or bool(payload.get("reduce_only_only"))
        traces.append(
            {
                "safe_mode_id": state.safe_mode_id,
                "scope_type": state.scope_type,
                "scope_value": state.scope_value,
                "trigger_reason": state.trigger_reason,
                "activated_at": state.activated_at,
                "override_payload": payload,
            }
        )

    for key in [
        "max_order_notional",
        "max_symbol_exposure",
        "max_strategy_exposure",
        "max_user_exposure",
        "max_portfolio_exposure",
    ]:
        if key in risk_rules and risk_rules.get(key) is not None:
            risk_rules[key] = float(risk_rules[key]) * risk_multiplier

    if max_order_cap is not None:
        current = float(risk_rules.get("max_order_notional") or max_order_cap)
        risk_rules["max_order_notional"] = min(current, max_order_cap)

    if leverage_cap is not None:
        post_trade_rules["max_leverage_after_trade"] = min(
            float(post_trade_rules.get("max_leverage_after_trade") or leverage_cap),
            leverage_cap,
        )

    merged["risk"] = risk_rules
    merged["execution"] = execution_rules
    merged["post_trade"] = post_trade_rules

    intent_type = str(context.get("intent_type") or "OPEN_POSITION").upper()
    reduce_only = bool(context.get("reduce_only"))
    if restrict_new_strategy_execution and intent_type == "OPEN_POSITION":
        findings.append(
            {
                "reason_code": "SAFE_MODE_STRATEGY_RESTRICTED",
                "reason_message": "Safe mode restricts new strategy executions",
                "severity": "CRITICAL",
                "rule_id": "safe_mode.restrict_new_strategy_execution",
            }
        )
    if reduce_only_only and intent_type == "OPEN_POSITION" and not reduce_only:
        findings.append(
            {
                "reason_code": "SAFE_MODE_REDUCE_ONLY_REQUIRED",
                "reason_message": "Safe mode allows reduce-only operations",
                "severity": "CRITICAL",
                "rule_id": "safe_mode.reduce_only_only",
            }
        )

    return merged, traces, findings


def list_safe_mode_states(db: Session, *, environment: str | None = None, active_only: bool = False) -> list[dict]:
    query = db.query(ExecutionSafeModeState).order_by(ExecutionSafeModeState.activated_at.desc())
    if environment:
        query = query.filter(ExecutionSafeModeState.environment == normalize_environment(environment))
    if active_only:
        query = query.filter(ExecutionSafeModeState.is_active.is_(True))
    rows = query.limit(300).all()
    return [
        {
            "safe_mode_id": row.safe_mode_id,
            "environment": row.environment,
            "scope_type": row.scope_type,
            "scope_value": row.scope_value,
            "is_active": bool(row.is_active),
            "trigger_reason": row.trigger_reason,
            "trigger_source": row.trigger_source,
            "activated_at": row.activated_at,
            "deactivated_at": row.deactivated_at,
            "override_payload": row.override_payload or {},
        }
        for row in rows
    ]


def deactivate_safe_mode(
    db: Session,
    *,
    safe_mode_id: str,
    actor_user_id: str,
    reason: str,
) -> ExecutionSafeModeState:
    row = db.query(ExecutionSafeModeState).filter(ExecutionSafeModeState.safe_mode_id == safe_mode_id).first()
    if row is None:
        raise ValueError("safe_mode_not_found")
    row.is_active = False
    row.deactivated_by = actor_user_id
    row.deactivated_at = _utcnow()
    row.updated_at = _utcnow()

    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_role="admin",
            action="SAFE_MODE_DEACTIVATED",
            entity_type="execution_safe_mode",
            entity_id=safe_mode_id,
            details={
                "reason": reason,
                "environment": row.environment,
                "scope_type": row.scope_type,
                "scope_value": row.scope_value,
            },
        )
    )
    db.flush()
    return row
