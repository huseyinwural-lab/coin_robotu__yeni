from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from services.execution_governance_service import (
    build_release_gate_status,
    build_strategy_health_state,
    build_violation_aggregation,
    classify_violation_severity,
    create_remediation_recommendation,
    emit_governance_event,
    evaluate_strategy_binding_constraints,
    get_governance_config,
    is_debug_mode_enabled,
    list_policy_versions,
    list_remediation_recommendations,
    resolve_policy_version_override,
    seed_default_strategy_bindings,
    select_auto_action,
)

from models import (
    BrandSetting,
    ExecutionPolicy,
    ExecutionPolicyDecisionLog,
    ExecutionPortfolio,
    LiveActivationConfig,
    Position,
    User,
    UserExecutionIntent,
)

DEFAULT_POLICY_MAP = {
    "breakout": {
        "execution_style": "aggressive",
        "order_preference": "market_first",
        "timeout_seconds": 4,
        "fallback_behavior": "market_fallback",
        "partial_fill_tolerance_pct": 85,
        "execution_urgency": "high",
        "retry_limit": 1,
    },
    "mean_reversion": {
        "execution_style": "passive",
        "order_preference": "limit_first",
        "timeout_seconds": 12,
        "fallback_behavior": "cancel_no_fill",
        "partial_fill_tolerance_pct": 35,
        "execution_urgency": "low",
        "retry_limit": 3,
    },
    "trend_following": {
        "execution_style": "balanced",
        "order_preference": "limit_first",
        "timeout_seconds": 8,
        "fallback_behavior": "market_fallback",
        "partial_fill_tolerance_pct": 60,
        "execution_urgency": "medium",
        "retry_limit": 2,
    },
    "volatility_expansion": {
        "execution_style": "balanced",
        "order_preference": "market_first",
        "timeout_seconds": 6,
        "fallback_behavior": "limit_retry_then_market",
        "partial_fill_tolerance_pct": 70,
        "execution_urgency": "medium",
        "retry_limit": 2,
    },
    "spot_pullback_v1": {
        "execution_style": "balanced",
        "order_preference": "limit_first",
        "timeout_seconds": 8,
        "fallback_behavior": "market_fallback",
        "partial_fill_tolerance_pct": 60,
        "execution_urgency": "medium",
        "retry_limit": 1,
    },
    "spot_range_reversion_v1": {
        "execution_style": "balanced",
        "order_preference": "limit_first",
        "timeout_seconds": 10,
        "fallback_behavior": "market_fallback",
        "partial_fill_tolerance_pct": 55,
        "execution_urgency": "low",
        "retry_limit": 1,
    },
    "spot_volatility_breakout_v1": {
        "execution_style": "aggressive",
        "order_preference": "market_first",
        "timeout_seconds": 6,
        "fallback_behavior": "market_fallback",
        "partial_fill_tolerance_pct": 70,
        "execution_urgency": "high",
        "retry_limit": 2,
    },
}

ENGINE_METADATA_KEY = "execution_policy_engine"
DEFAULT_ENGINE_CONFIG = {
    "enabled": True,
    "rollout_mode": "shadow",
    "progression": ["shadow", "soft", "partial", "full"],
    "fail_safe_mode": "block",
    "partial_live_only": True,
}
PENDING_INTENT_STATES = {"PREVIEWED", "SUBMITTED", "QUEUED", "APPROVED"}
LIVE_ENVIRONMENTS = {"live", "prod", "production"}
SCOPE_ORDER = {
    "global": 0,
    "environment": 1,
    "portfolio": 2,
    "user": 3,
    "strategy": 4,
    "symbol": 5,
}
FAILSAFE_REASON_CODES = {
    "FAILSAFE_POLICY_LOAD_ERROR",
    "FAILSAFE_RISK_COMPUTE_ERROR",
    "FAILSAFE_MARKET_DATA_MISSING",
    "FAILSAFE_DEPENDENCY_TIMEOUT",
    "FAILSAFE_ENGINE_UNAVAILABLE",
}
DEFAULT_PORTFOLIO_LIMITS = {
    "max_portfolio_exposure": 300000.0,
    "max_drawdown_pct": 25.0,
    "max_leverage": 4.0,
}


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _is_live_environment(environment: str | None) -> bool:
    return str(environment or "").strip().lower() in LIVE_ENVIRONMENTS


def _normalize_scope_value(value: str | None) -> str:
    return str(value or "").strip().lower()


def _is_failsafe_reason_code(reason_code: str | None) -> bool:
    return str(reason_code or "").strip().upper() in FAILSAFE_REASON_CODES


def _scope_strategy_type(scope: str, scope_key: str) -> str:
    seed = f"{scope}:{scope_key}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:18]
    return f"scope_{scope}_{digest}"[:50]


def _deep_merge(base: dict, patch: dict) -> dict:
    result = dict(base or {})
    for key, value in dict(patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _default_portfolio_id(user_id: str) -> str:
    return f"default:{user_id}"


def ensure_user_default_portfolio(db: Session, *, user_id: str, portfolio_id: str | None = None) -> ExecutionPortfolio:
    normalized_user = str(user_id or "").strip()
    if not normalized_user:
        raise ValueError("user_id_required_for_portfolio")

    target_portfolio_id = str(portfolio_id or _default_portfolio_id(normalized_user)).strip()
    row = db.query(ExecutionPortfolio).filter(ExecutionPortfolio.portfolio_id == target_portfolio_id).first()
    if row is not None:
        return row

    default_row = (
        db.query(ExecutionPortfolio)
        .filter(ExecutionPortfolio.user_id == normalized_user, ExecutionPortfolio.is_default.is_(True))
        .first()
    )
    if default_row is not None and (portfolio_id is None or target_portfolio_id == default_row.portfolio_id):
        return default_row

    row = ExecutionPortfolio(
        portfolio_id=target_portfolio_id,
        user_id=normalized_user,
        name="default" if portfolio_id is None else str(portfolio_id),
        is_default=portfolio_id is None,
        exposure=0.0,
        gross_exposure=0.0,
        net_exposure=0.0,
        concentration=0.0,
        drawdown=0.0,
        limits=dict(DEFAULT_PORTFOLIO_LIMITS),
        risk_profile={"version": "portfolio_v1", "created_by": "execution_policy_engine"},
    )
    db.add(row)
    db.flush()
    return row


def backfill_default_portfolios(db: Session) -> int:
    created = 0
    users = db.query(User.id).all()
    for (user_id,) in users:
        existing = (
            db.query(ExecutionPortfolio)
            .filter(ExecutionPortfolio.user_id == user_id, ExecutionPortfolio.is_default.is_(True))
            .first()
        )
        if existing is None:
            ensure_user_default_portfolio(db, user_id=user_id, portfolio_id=None)
            created += 1
    return created


def _legacy_policy_to_rules(policy: ExecutionPolicy) -> dict:
    return {
        "execution": {
            "execution_style": policy.execution_style,
            "order_preference": policy.order_preference,
            "timeout_seconds": int(policy.timeout_seconds or 8),
            "fallback_behavior": policy.fallback_behavior,
            "partial_fill_tolerance_pct": _safe_float(policy.partial_fill_tolerance_pct, 50.0),
            "execution_urgency": policy.execution_urgency,
            "retry_limit": int(policy.retry_limit or 2),
        }
    }


def _policy_conditions_match(conditions: dict, context: dict) -> tuple[bool, list[dict]]:
    checks: list[dict] = []
    env = _normalize_scope_value(context.get("environment"))
    market_type = _normalize_scope_value(context.get("market_type"))
    symbol = str(context.get("symbol") or "").strip().upper()
    margin_mode = _normalize_scope_value(context.get("margin_mode"))
    notional = _safe_float(context.get("proposed_notional"), 0.0)
    volatility = _safe_float(context.get("volatility_pct"), 0.0)

    def _record(name: str, actual, expected, passed: bool) -> bool:
        checks.append({"name": name, "actual": actual, "expected": expected, "passed": bool(passed)})
        return passed

    ok = True
    if conditions.get("environment_in"):
        expected = [str(item).lower() for item in conditions.get("environment_in") or []]
        ok = _record("environment_in", env, expected, env in expected) and ok
    if conditions.get("market_type_in"):
        expected = [str(item).lower() for item in conditions.get("market_type_in") or []]
        ok = _record("market_type_in", market_type, expected, market_type in expected) and ok
    if conditions.get("symbol_in"):
        expected = [str(item).upper() for item in conditions.get("symbol_in") or []]
        ok = _record("symbol_in", symbol, expected, symbol in expected) and ok
    if conditions.get("margin_mode_in"):
        expected = [str(item).lower() for item in conditions.get("margin_mode_in") or []]
        ok = _record("margin_mode_in", margin_mode, expected, margin_mode in expected) and ok
    if "min_notional" in conditions:
        expected = _safe_float(conditions.get("min_notional"), 0.0)
        ok = _record("min_notional", notional, expected, notional >= expected) and ok
    if "max_notional" in conditions:
        expected = _safe_float(conditions.get("max_notional"), 0.0)
        ok = _record("max_notional", notional, expected, notional <= expected) and ok
    if "volatility_gte" in conditions:
        expected = _safe_float(conditions.get("volatility_gte"), 0.0)
        ok = _record("volatility_gte", volatility, expected, volatility >= expected) and ok
    if "volatility_lte" in conditions:
        expected = _safe_float(conditions.get("volatility_lte"), 0.0)
        ok = _record("volatility_lte", volatility, expected, volatility <= expected) and ok

    return ok, checks


def _policy_matches_scope(policy: ExecutionPolicy, context: dict) -> tuple[bool, dict]:
    scope = _normalize_scope_value(getattr(policy, "policy_scope", None) or "strategy")
    key = _normalize_scope_value(getattr(policy, "scope_key", None) or "")

    strategy_binding = _normalize_scope_value(context.get("strategy_binding"))
    user_id = _normalize_scope_value(context.get("user_id"))
    symbol = _normalize_scope_value(context.get("symbol"))
    environment = _normalize_scope_value(context.get("environment"))
    portfolio_id = _normalize_scope_value(context.get("portfolio_id") or context.get("user_id"))

    effective_key = key
    if scope == "strategy" and (not effective_key or effective_key == "default"):
        effective_key = _normalize_scope_value(policy.strategy_type)

    target_map = {
        "global": "global",
        "environment": environment,
        "portfolio": portfolio_id,
        "user": user_id,
        "strategy": strategy_binding,
        "symbol": symbol,
    }
    target = _normalize_scope_value(target_map.get(scope) or "")
    scope_match = scope == "global" or effective_key in {target, "*", "all"}

    condition_match, checks = _policy_conditions_match(getattr(policy, "conditions_payload", None) or {}, context)
    return scope_match and condition_match, {
        "scope": scope,
        "scope_key": effective_key,
        "target": target,
        "scope_match": scope_match,
        "condition_checks": checks,
        "condition_match": condition_match,
    }


def _reject_contract(
    *,
    reason_code: str,
    reason_message: str,
    stage: str,
    severity: str,
    action_taken: str,
    policy_id: str | None,
    rule_id: str | None,
) -> dict:
    return {
        "reason_code": reason_code,
        "reason_message": reason_message,
        "policy_id": policy_id,
        "rule_id": rule_id,
        "stage": stage,
        "severity": severity,
        "action_taken": action_taken,
    }


def _resolve_rollout_action(*, rollout_mode: str, recommended_action: str, context: dict, soft_non_live: bool = False) -> tuple[str, str]:
    normalized_mode = str(rollout_mode or "shadow").strip().lower()
    is_live = _is_live_environment(context.get("environment"))

    if recommended_action != "BLOCK":
        return "ALLOW", "ALLOW"

    if soft_non_live and not is_live:
        return "ALLOW", "SOFT_ALLOW_NON_LIVE"

    if normalized_mode == "shadow":
        return "ALLOW", "SHADOW_ALLOW"
    if normalized_mode == "soft":
        return "ALLOW", "SOFT_ALLOW"
    if normalized_mode == "partial":
        if is_live:
            return "BLOCK", "PARTIAL_BLOCK_LIVE"
        return "ALLOW", "PARTIAL_SOFT_NON_LIVE"
    return "BLOCK", "FULL_BLOCK"


def _get_or_create_brand_setting(db: Session) -> BrandSetting:
    row = db.query(BrandSetting).filter(BrandSetting.id == "default").first()
    if row is not None:
        return row
    row = BrandSetting(id="default", metadata_json={})
    db.add(row)
    db.flush()
    return row


def get_execution_policy_engine_config(db: Session) -> dict:
    row = _get_or_create_brand_setting(db)
    metadata = dict(row.metadata_json or {})
    config = dict(metadata.get(ENGINE_METADATA_KEY) or {})
    normalized = {
        **DEFAULT_ENGINE_CONFIG,
        **config,
    }
    normalized["rollout_mode"] = str(normalized.get("rollout_mode") or "shadow").strip().lower()
    if normalized["rollout_mode"] not in {"shadow", "soft", "partial", "full"}:
        normalized["rollout_mode"] = "shadow"
    return normalized


def _ensure_policy(
    db: Session,
    *,
    policy_code: str,
    scope: str,
    scope_key: str,
    priority: int,
    override_behavior: str,
    conditions_payload: dict,
    rules_payload: dict,
    severity: str = "HIGH",
    enforcement_action: str = "BLOCK",
    strategy_type: str | None = None,
    execution_defaults: dict | None = None,
) -> None:
    row = db.query(ExecutionPolicy).filter(ExecutionPolicy.policy_code == policy_code).first()
    if row is None and strategy_type:
        row = db.query(ExecutionPolicy).filter(ExecutionPolicy.strategy_type == strategy_type).first()
    payload_defaults = execution_defaults or DEFAULT_POLICY_MAP["trend_following"]
    if row is None:
        row = ExecutionPolicy(
            strategy_type=strategy_type or _scope_strategy_type(scope, scope_key),
            execution_style=payload_defaults.get("execution_style") or "balanced",
            order_preference=payload_defaults.get("order_preference") or "limit_first",
            timeout_seconds=int(payload_defaults.get("timeout_seconds") or 8),
            fallback_behavior=payload_defaults.get("fallback_behavior") or "market_fallback",
            partial_fill_tolerance_pct=_safe_float(payload_defaults.get("partial_fill_tolerance_pct"), 50.0),
            execution_urgency=payload_defaults.get("execution_urgency") or "medium",
            retry_limit=int(payload_defaults.get("retry_limit") or 2),
            is_active=True,
        )
        db.add(row)

    row.policy_code = policy_code
    row.policy_scope = scope
    row.scope_key = scope_key
    row.priority = int(priority)
    row.override_behavior = str(override_behavior or "merge").lower()
    row.conditions_payload = dict(conditions_payload or {})
    row.rules_payload = dict(rules_payload or {})
    row.severity = str(severity or "HIGH").upper()
    row.enforcement_action = str(enforcement_action or "BLOCK").upper()
    row.is_active = True
    row.updated_at = datetime.now(timezone.utc)


def ensure_dynamic_execution_policies(db: Session) -> None:
    seeded = (
        db.query(ExecutionPolicy.id)
        .filter(ExecutionPolicy.policy_code.like("sprint1:%"))
        .limit(1)
        .first()
    )
    if seeded is not None:
        return

    default_risk = {
        "max_order_notional": 50000,
        "max_symbol_exposure": 120000,
        "max_strategy_exposure": 180000,
        "max_user_exposure": 250000,
        "max_portfolio_exposure": 300000,
    }
    global_rules = {
        "runtime": {
            "require_market_data": True,
            "dependency_timeout_ms": 5000,
        },
        "risk": default_risk,
        "safety": {
            "max_loss_usdt": 5000,
            "max_drawdown_pct": 25,
            "circuit_breaker_window_minutes": 15,
            "circuit_breaker_violation_threshold": 8,
            "strategy_kill_switches": [],
            "symbol_kill_switches": [],
            "environment_kill_switches": [],
        },
        "enforcement": {
            "require_strategy_policy": True,
        },
    }
    _ensure_policy(
        db,
        policy_code="sprint1:global:baseline",
        scope="global",
        scope_key="global",
        priority=10,
        override_behavior="merge",
        conditions_payload={},
        rules_payload=global_rules,
    )
    _ensure_policy(
        db,
        policy_code="sprint1:env:live",
        scope="environment",
        scope_key="live",
        priority=20,
        override_behavior="merge",
        conditions_payload={"environment_in": ["live", "prod", "production"]},
        rules_payload={"enforcement": {"require_strategy_policy": True}},
    )
    _ensure_policy(
        db,
        policy_code="sprint1:env:testnet",
        scope="environment",
        scope_key="testnet",
        priority=20,
        override_behavior="merge",
        conditions_payload={"environment_in": ["testnet", "staging", "dev"]},
        rules_payload={"enforcement": {"require_strategy_policy": True}},
    )

    for strategy_name, defaults in DEFAULT_POLICY_MAP.items():
        _ensure_policy(
            db,
            policy_code=f"sprint1:strategy:{strategy_name}",
            scope="strategy",
            scope_key=strategy_name,
            priority=40,
            override_behavior="merge",
            conditions_payload={},
            rules_payload={
                "execution": {
                    "execution_style": defaults.get("execution_style"),
                    "order_preference": defaults.get("order_preference"),
                    "timeout_seconds": defaults.get("timeout_seconds"),
                    "fallback_behavior": defaults.get("fallback_behavior"),
                    "partial_fill_tolerance_pct": defaults.get("partial_fill_tolerance_pct"),
                    "execution_urgency": defaults.get("execution_urgency"),
                    "retry_limit": defaults.get("retry_limit"),
                },
                "risk": {
                    "max_order_notional": 50000,
                    "max_symbol_exposure": 120000,
                    "max_strategy_exposure": 150000,
                    "max_user_exposure": 250000,
                    "max_portfolio_exposure": 300000,
                },
            },
            strategy_type=strategy_name,
            execution_defaults=defaults,
        )

    seed_default_strategy_bindings(db, strategy_ids=list(DEFAULT_POLICY_MAP.keys()))


def _load_active_policies(db: Session) -> list[ExecutionPolicy]:
    return db.query(ExecutionPolicy).filter(ExecutionPolicy.is_active.is_(True)).all()


def _resolve_effective_rules(db: Session, context: dict) -> tuple[list[ExecutionPolicy], dict, list[dict]]:
    ensure_dynamic_execution_policies(db)
    matched: list[tuple[ExecutionPolicy, dict]] = []
    traces: list[dict] = []
    for row in _load_active_policies(db):
        ok, trace_payload = _policy_matches_scope(row, context)
        traces.append({
            "policy_id": row.id,
            "policy_code": getattr(row, "policy_code", None),
            "matched": ok,
            **trace_payload,
        })
        if ok:
            matched.append((row, trace_payload))

    matched.sort(
        key=lambda item: (
            SCOPE_ORDER.get(_normalize_scope_value(getattr(item[0], "policy_scope", None) or "strategy"), 99),
            int(getattr(item[0], "priority", 100) or 100),
        )
    )

    effective_rules: dict = {}
    matched_rows: list[ExecutionPolicy] = []
    for row, _ in matched:
        matched_rows.append(row)
        version_override = None
        if getattr(row, "policy_code", None):
            version_override = resolve_policy_version_override(
                db,
                policy_code=str(row.policy_code),
                context=context,
            )
        incoming = dict((version_override or {}).get("rules_payload") or getattr(row, "rules_payload", None) or {})
        if not incoming:
            incoming = _legacy_policy_to_rules(row)
        if str(getattr(row, "override_behavior", "merge") or "merge").lower() == "replace":
            effective_rules = dict(incoming)
        else:
            effective_rules = _deep_merge(effective_rules, incoming)

        traces.append(
            {
                "policy_id": row.id,
                "policy_code": getattr(row, "policy_code", None),
                "version_override": version_override,
            }
        )

    return matched_rows, effective_rules, traces


def _compute_multi_layer_risk(db: Session, context: dict, rules: dict) -> dict:
    user_id = str(context.get("user_id") or "")
    symbol = str(context.get("symbol") or "").upper()
    strategy_binding = str(context.get("strategy_binding") or "")
    proposed_notional = max(_safe_float(context.get("proposed_notional"), 0.0), 0.0)
    portfolio_id = str(context.get("portfolio_id") or _default_portfolio_id(user_id))
    side = str(context.get("side") or "buy").lower()

    portfolio = ensure_user_default_portfolio(db, user_id=user_id, portfolio_id=portfolio_id)
    portfolio_limits = dict(DEFAULT_PORTFOLIO_LIMITS)
    portfolio_limits.update(dict(portfolio.limits or {}))
    portfolio_profile = dict(portfolio.risk_profile or {})
    profile_symbol_exposure = {
        str(key).upper(): _safe_float(value)
        for key, value in dict(portfolio_profile.get("symbol_exposure") or {}).items()
    }
    profile_strategy_exposure = {
        str(key): _safe_float(value)
        for key, value in dict(portfolio_profile.get("strategy_exposure") or {}).items()
    }

    open_rows = (
        db.query(Position.symbol, Position.strategy_id, Position.size, Position.entry_price)
        .filter(Position.user_id == user_id, Position.status == "open")
        .all()
    )
    pending_rows = (
        db.query(UserExecutionIntent.symbol, UserExecutionIntent.notional, UserExecutionIntent.normalized_order_payload)
        .filter(UserExecutionIntent.user_id == user_id, UserExecutionIntent.status.in_(list(PENDING_INTENT_STATES)))
        .all()
    )

    symbol_exposure = 0.0
    strategy_exposure = 0.0
    user_exposure = 0.0
    portfolio_symbol_exposure = profile_symbol_exposure.get(symbol, 0.0)
    portfolio_strategy_exposure = profile_strategy_exposure.get(strategy_binding, 0.0)
    portfolio_exposure = max(_safe_float(portfolio.exposure), 0.0)
    portfolio_gross_exposure = max(_safe_float(portfolio.gross_exposure), portfolio_exposure)
    portfolio_net_exposure = _safe_float(portfolio.net_exposure)
    portfolio_drawdown = _safe_float(portfolio.drawdown)

    for row_symbol, row_strategy, size, entry_price in open_rows:
        notional = abs(_safe_float(size) * _safe_float(entry_price))
        user_exposure += notional
        if str(row_symbol or "").upper() == symbol:
            symbol_exposure += notional
        if strategy_binding and str(row_strategy or "") == strategy_binding:
            strategy_exposure += notional

    for row_symbol, row_notional, payload in pending_rows:
        pending_notional = abs(_safe_float(row_notional))
        user_exposure += pending_notional
        payload_strategy = str((payload or {}).get("strategy_binding") or "")
        payload_portfolio = str((payload or {}).get("portfolio_id") or _default_portfolio_id(user_id))
        if str(row_symbol or "").upper() == symbol:
            symbol_exposure += pending_notional
        if strategy_binding and payload_strategy == strategy_binding:
            strategy_exposure += pending_notional
        if payload_portfolio == portfolio.portfolio_id:
            portfolio_exposure += pending_notional
            portfolio_gross_exposure += pending_notional
            portfolio_symbol_exposure += pending_notional if str(row_symbol or "").upper() == symbol else 0.0
            portfolio_strategy_exposure += pending_notional if payload_strategy == strategy_binding else 0.0

    side_sign = -1.0 if side == "sell" else 1.0
    projected_portfolio_exposure = portfolio_exposure + proposed_notional
    projected_portfolio_gross = portfolio_gross_exposure + proposed_notional
    projected_portfolio_net = portfolio_net_exposure + (proposed_notional * side_sign)
    concentration_pct = (
        (portfolio_symbol_exposure + proposed_notional) / max(projected_portfolio_gross, 1.0)
    ) * 100.0

    projected = {
        "symbol": symbol_exposure + proposed_notional,
        "strategy": strategy_exposure + proposed_notional,
        "user": user_exposure + proposed_notional,
        "portfolio": projected_portfolio_exposure,
        "order": proposed_notional,
    }

    risk_rules = dict(rules.get("risk") or {})
    policy_portfolio_limit = _safe_float(risk_rules.get("max_portfolio_exposure"), 0.0)
    portfolio_domain_limit = _safe_float(portfolio_limits.get("max_portfolio_exposure"), 300000)
    effective_portfolio_limit = portfolio_domain_limit
    if policy_portfolio_limit > 0 and portfolio_domain_limit > 0:
        effective_portfolio_limit = min(policy_portfolio_limit, portfolio_domain_limit)
    elif policy_portfolio_limit > 0:
        effective_portfolio_limit = policy_portfolio_limit

    thresholds = {
        "order": _safe_float(risk_rules.get("max_order_notional"), 50000),
        "symbol": _safe_float(risk_rules.get("max_symbol_exposure"), 120000),
        "strategy": _safe_float(risk_rules.get("max_strategy_exposure"), 180000),
        "user": _safe_float(risk_rules.get("max_user_exposure"), 250000),
        "portfolio": effective_portfolio_limit,
    }
    breaches: list[dict] = []
    for key, projected_value in projected.items():
        limit = thresholds.get(key, 0.0)
        if limit > 0 and projected_value > limit:
            breaches.append(
                {
                    "reason_code": f"RISK_{key.upper()}_BREACH",
                    "reason_message": f"{key} exposure limit exceeded",
                    "rule_id": f"risk.{key}",
                    "projected": round(projected_value, 6),
                    "limit": round(limit, 6),
                }
            )

    has_concentration_rule = "max_concentration_pct" in risk_rules
    max_concentration_pct = _safe_float(risk_rules.get("max_concentration_pct"), 100.0)
    if has_concentration_rule and max_concentration_pct > 0 and concentration_pct > max_concentration_pct:
        breaches.append(
            {
                "reason_code": "RISK_PORTFOLIO_CONCENTRATION_BREACH",
                "reason_message": "portfolio concentration limit exceeded",
                "rule_id": "risk.max_concentration_pct",
                "projected": round(concentration_pct, 6),
                "limit": round(max_concentration_pct, 6),
            }
        )

    max_drawdown_pct = _safe_float(portfolio_limits.get("max_drawdown_pct"), 0.0)
    if max_drawdown_pct > 0 and portfolio_drawdown >= max_drawdown_pct:
        breaches.append(
            {
                "reason_code": "RISK_PORTFOLIO_DRAWDOWN_BREACH",
                "reason_message": "portfolio drawdown limit exceeded",
                "rule_id": "risk.max_drawdown_pct",
                "projected": round(portfolio_drawdown, 6),
                "limit": round(max_drawdown_pct, 6),
            }
        )

    return {
        "portfolio_id": portfolio.portfolio_id,
        "thresholds": thresholds,
        "current": {
            "symbol": round(symbol_exposure, 6),
            "strategy": round(strategy_exposure, 6),
            "user": round(user_exposure, 6),
            "portfolio": round(portfolio_exposure, 6),
        },
        "projected": {k: round(v, 6) for k, v in projected.items()},
        "portfolio_domain": {
            "portfolio_id": portfolio.portfolio_id,
            "gross_exposure": round(projected_portfolio_gross, 6),
            "net_exposure": round(projected_portfolio_net, 6),
            "concentration_pct": round(concentration_pct, 6),
            "drawdown_pct": round(portfolio_drawdown, 6),
            "limits": {
                "max_portfolio_exposure": round(thresholds["portfolio"], 6),
                "max_concentration_pct": round(max_concentration_pct, 6),
                "max_drawdown_pct": round(max_drawdown_pct, 6),
            },
        },
        "breaches": breaches,
    }


def apply_portfolio_post_trade_update(db: Session, *, context: dict, post_trade_metrics: dict) -> ExecutionPortfolio | None:
    user_id = str(context.get("user_id") or "")
    if not user_id:
        return None
    portfolio_id = str(context.get("portfolio_id") or _default_portfolio_id(user_id))
    row = ensure_user_default_portfolio(db, user_id=user_id, portfolio_id=portfolio_id)

    gross_exposure = max(_safe_float(post_trade_metrics.get("exposure_after_trade"), _safe_float(row.gross_exposure)), 0.0)
    net_exposure = _safe_float(post_trade_metrics.get("net_exposure_after_trade"), _safe_float(row.net_exposure))
    concentration = max(_safe_float(post_trade_metrics.get("concentration_pct"), _safe_float(row.concentration)), 0.0)
    drawdown = max(_safe_float(post_trade_metrics.get("drawdown_pct"), _safe_float(row.drawdown)), 0.0)

    row.exposure = gross_exposure
    row.gross_exposure = gross_exposure
    row.net_exposure = net_exposure
    row.concentration = concentration
    row.drawdown = drawdown
    row.risk_profile = {
        **dict(row.risk_profile or {}),
        "last_post_trade_update": datetime.now(timezone.utc).isoformat(),
        "last_metrics": {
            "gross_exposure": round(gross_exposure, 6),
            "net_exposure": round(net_exposure, 6),
            "concentration_pct": round(concentration, 6),
            "drawdown_pct": round(drawdown, 6),
        },
    }
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row


def _compute_safety_layer(db: Session, context: dict, rules: dict) -> dict:
    user_id = str(context.get("user_id") or "")
    symbol = str(context.get("symbol") or "").upper()
    strategy_binding = str(context.get("strategy_binding") or "")
    environment = str(context.get("environment") or "").lower()

    safety_rules = dict(rules.get("safety") or {})
    config = db.query(LiveActivationConfig).filter(LiveActivationConfig.id == "global").first()

    breaches: list[dict] = []
    enforce_live_only = _is_live_environment(environment)
    if config is not None and enforce_live_only and bool(getattr(config, "kill_switch_enabled", False)):
        breaches.append(
            {
                "reason_code": "SAFETY_GLOBAL_KILL_SWITCH",
                "reason_message": "Global kill switch is active",
                "rule_id": "safety.global_kill_switch",
            }
        )

    if config is not None and enforce_live_only and not bool(getattr(config, "trading_enabled", True)):
        breaches.append(
            {
                "reason_code": "SAFETY_TRADING_DISABLED",
                "reason_message": "Trading disabled by safety layer",
                "rule_id": "safety.trading_enabled",
            }
        )

    env_switches = [str(item).lower() for item in (safety_rules.get("environment_kill_switches") or [])]
    if environment and environment in env_switches:
        breaches.append(
            {
                "reason_code": "SAFETY_ENVIRONMENT_KILL_SWITCH",
                "reason_message": f"Environment kill switch active for {environment}",
                "rule_id": "safety.environment_kill_switches",
            }
        )

    strategy_switches = [str(item) for item in (safety_rules.get("strategy_kill_switches") or [])]
    if strategy_binding and strategy_binding in strategy_switches:
        breaches.append(
            {
                "reason_code": "SAFETY_STRATEGY_KILL_SWITCH",
                "reason_message": "Strategy kill switch is active",
                "rule_id": "safety.strategy_kill_switches",
            }
        )

    symbol_switches = [str(item).upper() for item in (safety_rules.get("symbol_kill_switches") or [])]
    if symbol and symbol in symbol_switches:
        breaches.append(
            {
                "reason_code": "SAFETY_SYMBOL_KILL_SWITCH",
                "reason_message": "Symbol kill switch is active",
                "rule_id": "safety.symbol_kill_switches",
            }
        )

    pnl_rows = db.query(Position.unrealized_pnl).filter(Position.user_id == user_id).all()
    current_pnl = sum(_safe_float(item[0]) for item in pnl_rows)
    max_loss = abs(_safe_float(safety_rules.get("max_loss_usdt"), 0.0))
    if max_loss > 0 and current_pnl <= -max_loss:
        breaches.append(
            {
                "reason_code": "SAFETY_MAX_LOSS_BREACH",
                "reason_message": "Max loss guard breached",
                "rule_id": "safety.max_loss_usdt",
                "current_pnl": round(current_pnl, 6),
                "max_loss": round(max_loss, 6),
            }
        )

    drawdown_limit = _safe_float(safety_rules.get("max_drawdown_pct"), 0.0)
    drawdown_pct = context.get("portfolio_drawdown_pct")
    drawdown_pct = _safe_float(drawdown_pct, abs(current_pnl) / max(_safe_float(context.get("proposed_notional"), 1.0), 1.0) * 100.0)
    if drawdown_limit > 0 and drawdown_pct >= drawdown_limit:
        breaches.append(
            {
                "reason_code": "SAFETY_DRAWDOWN_STOP",
                "reason_message": "Drawdown stop triggered",
                "rule_id": "safety.max_drawdown_pct",
                "drawdown_pct": round(drawdown_pct, 6),
                "limit": round(drawdown_limit, 6),
            }
        )

    breaker_window = int(_safe_float(safety_rules.get("circuit_breaker_window_minutes"), 0.0))
    breaker_threshold = int(_safe_float(safety_rules.get("circuit_breaker_violation_threshold"), 0.0))
    breaker_count = 0
    if breaker_window > 0 and breaker_threshold > 0:
        since = datetime.now(timezone.utc) - timedelta(minutes=max(breaker_window, 1))
        breaker_count = (
            db.query(ExecutionPolicyDecisionLog)
            .filter(
                ExecutionPolicyDecisionLog.user_id == user_id,
                ExecutionPolicyDecisionLog.is_violation.is_(True),
                ExecutionPolicyDecisionLog.created_at >= since,
            )
            .count()
        )
        if breaker_count >= breaker_threshold:
            breaches.append(
                {
                    "reason_code": "SAFETY_CIRCUIT_BREAKER_TRIGGERED",
                    "reason_message": "Circuit breaker threshold exceeded",
                    "rule_id": "safety.circuit_breaker",
                    "count": breaker_count,
                    "threshold": breaker_threshold,
                    "window_minutes": breaker_window,
                }
            )

    return {
        "breaches": breaches,
        "metrics": {
            "current_user_pnl": round(current_pnl, 6),
            "drawdown_pct": round(drawdown_pct, 6),
            "circuit_breaker_count": breaker_count,
        },
    }


def evaluate_execution_policy_engine(db: Session, context: dict, *, stage: str = "PRE_TRADE") -> dict:
    decision_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    config = get_execution_policy_engine_config(db)
    rollout_mode = str(config.get("rollout_mode") or "shadow").lower()
    user_id = str(context.get("user_id") or "").strip()
    if user_id:
        ensure_user_default_portfolio(
            db,
            user_id=user_id,
            portfolio_id=str(context.get("portfolio_id") or _default_portfolio_id(user_id)),
        )

    try:
        matched_rows, effective_rules, scope_trace = _resolve_effective_rules(db, context)
    except Exception as exc:  # pragma: no cover - fail-safe path
        reject = _reject_contract(
            reason_code="FAILSAFE_POLICY_LOAD_ERROR",
            reason_message=f"Policy loading failed: {exc}",
            stage=stage,
            severity="CRITICAL",
            action_taken="HARD_BLOCK",
            policy_id=None,
            rule_id="failsafe.policy_load",
        )
        return {
            "decision_id": decision_id,
            "recommended_action": "BLOCK",
            "enforced_action": "BLOCK",
            "rollout_mode": rollout_mode,
            "standardized_reject": reject,
            "trace": {
                "stage": stage,
                "decision_id": decision_id,
                "trace_id": str(context.get("trace_id") or context.get("pipeline_id") or context.get("intent_token") or decision_id),
                "scope_trace": [],
                "effective_rules": {},
                "error": str(exc),
                "action_taken": "HARD_BLOCK",
            },
        }

    strategy_binding = str(context.get("strategy_binding") or "").strip()
    strategy_binding_eval = evaluate_strategy_binding_constraints(db, context=context)
    strategy_risk_class = str(strategy_binding_eval.get("risk_class") or "MEDIUM").upper()
    strategy_limits = dict(strategy_binding_eval.get("limits") or {})
    if strategy_limits:
        effective_rules = _deep_merge(effective_rules, {"risk": strategy_limits})

    has_strategy_policy = any(
        _normalize_scope_value(getattr(row, "policy_scope", None) or "strategy") == "strategy"
        and _normalize_scope_value(getattr(row, "scope_key", None) or row.strategy_type) == _normalize_scope_value(strategy_binding)
        for row in matched_rows
    )

    findings: list[dict] = []
    soft_non_live = False
    for strategy_violation in list(strategy_binding_eval.get("violations") or []):
        is_live_binding = _is_live_environment(context.get("environment"))
        finding_action = "BLOCK" if is_live_binding else "SOFT_ALLOW_NON_LIVE"
        findings.append(
            _reject_contract(
                reason_code=str(strategy_violation.get("reason_code") or "STRATEGY_GOVERNANCE_VIOLATION"),
                reason_message=str(strategy_violation.get("reason_message") or "Strategy governance violation"),
                stage=stage,
                severity=str(strategy_violation.get("severity") or "HIGH"),
                action_taken=finding_action,
                policy_id=matched_rows[-1].id if matched_rows else None,
                rule_id=str(strategy_violation.get("rule_id") or "strategy.governance"),
            )
        )
        if not is_live_binding:
            soft_non_live = True

    if not strategy_binding or not has_strategy_policy:
        is_live = _is_live_environment(context.get("environment"))
        soft_non_live = not is_live
        findings.append(
            _reject_contract(
                reason_code="STRATEGY_POLICY_MISSING",
                reason_message="Strategy policy binding required",
                stage=stage,
                severity="HIGH",
                action_taken="SOFT_ALLOW_NON_LIVE" if soft_non_live else "BLOCK",
                policy_id=None,
                rule_id="strategy_binding.required",
            )
        )

    runtime_rules = dict((effective_rules or {}).get("runtime") or {})
    market_data_available = bool(context.get("market_data_available"))
    if bool(runtime_rules.get("require_market_data", True)) and not market_data_available:
        findings.append(
            _reject_contract(
                reason_code="FAILSAFE_MARKET_DATA_MISSING",
                reason_message="Market data snapshot unavailable",
                stage=stage,
                severity="CRITICAL",
                action_taken="FAILSAFE_BLOCK",
                policy_id=matched_rows[-1].id if matched_rows else None,
                rule_id="runtime.require_market_data",
            )
        )

    dependency_timeout_ms = int(_safe_float(runtime_rules.get("dependency_timeout_ms"), 5000))
    elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    timeout_signal = bool(context.get("dependency_timeout"))
    enforce_wall_clock_timeout = bool(context.get("enforce_dependency_timeout"))
    if timeout_signal or (
        enforce_wall_clock_timeout
        and dependency_timeout_ms > 0
        and elapsed_ms > dependency_timeout_ms
    ):
        findings.append(
            _reject_contract(
                reason_code="FAILSAFE_DEPENDENCY_TIMEOUT",
                reason_message="Policy evaluation timeout",
                stage=stage,
                severity="CRITICAL",
                action_taken="FAILSAFE_BLOCK",
                policy_id=matched_rows[-1].id if matched_rows else None,
                rule_id="runtime.dependency_timeout_ms",
            )
        )

    try:
        risk_result = _compute_multi_layer_risk(db, context, effective_rules)
    except Exception as exc:  # pragma: no cover - fail-safe path
        risk_result = {"breaches": []}
        findings.append(
            _reject_contract(
                reason_code="FAILSAFE_RISK_COMPUTE_ERROR",
                reason_message=f"Risk compute failed: {exc}",
                stage=stage,
                severity="CRITICAL",
                action_taken="FAILSAFE_BLOCK",
                policy_id=matched_rows[-1].id if matched_rows else None,
                rule_id="failsafe.risk_compute",
            )
        )
    for risk_breach in list(risk_result.get("breaches") or []):
        findings.append(
            _reject_contract(
                reason_code=risk_breach.get("reason_code") or "RISK_BREACH",
                reason_message=risk_breach.get("reason_message") or "Risk limit breached",
                stage=stage,
                severity="HIGH",
                action_taken="BLOCK",
                policy_id=matched_rows[-1].id if matched_rows else None,
                rule_id=risk_breach.get("rule_id"),
            )
        )

    safety_result = _compute_safety_layer(db, context, effective_rules)
    for safety_breach in list(safety_result.get("breaches") or []):
        findings.append(
            _reject_contract(
                reason_code=safety_breach.get("reason_code") or "SAFETY_BREACH",
                reason_message=safety_breach.get("reason_message") or "Safety guard breached",
                stage=stage,
                severity="CRITICAL",
                action_taken="BLOCK",
                policy_id=matched_rows[-1].id if matched_rows else None,
                rule_id=safety_breach.get("rule_id"),
            )
        )

    governance_config = get_governance_config(db)
    debug_enabled = is_debug_mode_enabled(db, context=context)
    enriched_findings = []
    for item in findings:
        severity = classify_violation_severity(
            db,
            reason_code=str(item.get("reason_code") or ""),
            default_severity=str(item.get("severity") or "LOW"),
            strategy_risk_class=strategy_risk_class,
        )
        auto_action = select_auto_action(
            db,
            severity=severity,
            reason_code=str(item.get("reason_code") or ""),
            environment=str(context.get("environment") or "testnet"),
            strategy_risk_class=strategy_risk_class,
            strategy_id=str(strategy_binding or ""),
        )
        enriched_findings.append(
            {
                **item,
                "severity": severity,
                "auto_action_recommendation": auto_action,
                "manual_approval_required": bool(
                    str(governance_config.get("auto_remediation_mode") or "manual_recommend").lower() == "manual_recommend"
                ),
            }
        )
    findings = enriched_findings

    recommended_action = "BLOCK" if findings else "ALLOW"
    has_hard_failsafe = any(_is_failsafe_reason_code(item.get("reason_code")) for item in findings)
    if has_hard_failsafe:
        findings = [
            {
                **item,
                "severity": "CRITICAL" if _is_failsafe_reason_code(item.get("reason_code")) else item.get("severity"),
                "action_taken": "HARD_BLOCK" if _is_failsafe_reason_code(item.get("reason_code")) else item.get("action_taken"),
            }
            for item in findings
        ]
    if has_hard_failsafe:
        enforced_action, action_taken = "BLOCK", "HARD_BLOCK"
    else:
        enforced_action, action_taken = _resolve_rollout_action(
            rollout_mode=rollout_mode,
            recommended_action=recommended_action,
            context=context,
            soft_non_live=soft_non_live,
        )

    primary_reject = findings[0] if findings else None
    if primary_reject is not None:
        if has_hard_failsafe and _is_failsafe_reason_code(primary_reject.get("reason_code")):
            primary_reject = {**primary_reject, "severity": "CRITICAL", "action_taken": "HARD_BLOCK"}
        else:
            primary_reject = {**primary_reject, "action_taken": action_taken}

    decision_steps: list[dict] = []
    for idx, item in enumerate(scope_trace):
        decision_steps.append(
            {
                "step_index": idx,
                "step_type": "POLICY_MATCH" if item.get("matched") else "POLICY_SKIP",
                "policy_id": item.get("policy_id"),
                "rule_id": None,
                "condition_result": bool(item.get("condition_match")),
                "previous_state": "EVALUATING",
                "new_state": "MATCHED" if item.get("matched") else "SKIPPED",
                "comment": f"scope={item.get('scope')} key={item.get('scope_key')}",
            }
        )
    start_index = len(decision_steps)
    for offset, finding in enumerate(findings):
        decision_steps.append(
            {
                "step_index": start_index + offset,
                "step_type": "SEVERITY_ESCALATED",
                "policy_id": finding.get("policy_id"),
                "rule_id": finding.get("rule_id"),
                "condition_result": True,
                "previous_state": "ALLOW",
                "new_state": finding.get("severity"),
                "comment": f"{finding.get('reason_code')} -> {finding.get('auto_action_recommendation')}",
            }
        )
    decision_steps.append(
        {
            "step_index": len(decision_steps),
            "step_type": "ACTION_FINALIZED",
            "policy_id": primary_reject.get("policy_id") if primary_reject else None,
            "rule_id": primary_reject.get("rule_id") if primary_reject else None,
            "condition_result": True,
            "previous_state": recommended_action,
            "new_state": enforced_action,
            "comment": f"action={action_taken}",
        }
    )

    return {
        "decision_id": decision_id,
        "recommended_action": recommended_action,
        "enforced_action": enforced_action,
        "rollout_mode": rollout_mode,
        "standardized_reject": primary_reject,
        "decision_reason_summary": (
            primary_reject.get("reason_message")
            if primary_reject
            else "Order allowed after policy/risk/safety evaluation"
        ),
        "all_findings": findings,
        "effective_rules": effective_rules,
        "matched_policies": [
            {
                "policy_id": row.id,
                "policy_code": getattr(row, "policy_code", None),
                "policy_scope": getattr(row, "policy_scope", None),
                "scope_key": getattr(row, "scope_key", None),
                "priority": int(getattr(row, "priority", 100) or 100),
                "override_behavior": getattr(row, "override_behavior", None),
            }
            for row in matched_rows
        ],
        "trace": {
            "stage": stage,
            "decision_id": decision_id,
            "trace_id": str(context.get("trace_id") or context.get("pipeline_id") or context.get("intent_token") or decision_id),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "scope_trace": scope_trace,
            "matched_policies": [
                {
                    "policy_id": row.id,
                    "policy_code": getattr(row, "policy_code", None),
                    "policy_scope": getattr(row, "policy_scope", None),
                    "scope_key": getattr(row, "scope_key", None),
                }
                for row in matched_rows
            ],
            "applied_overrides": [
                {
                    "policy_id": row.id,
                    "policy_code": getattr(row, "policy_code", None),
                    "override_behavior": getattr(row, "override_behavior", None),
                    "priority": int(getattr(row, "priority", 100) or 100),
                }
                for row in matched_rows
            ],
            "risk": risk_result,
            "safety": safety_result,
            "findings": findings,
            "effective_rules": effective_rules,
            "action_taken": action_taken,
            "hard_failsafe_applied": has_hard_failsafe,
            "final_decision_path": {
                "recommended_action": recommended_action,
                "enforced_action": enforced_action,
                "rollout_mode": rollout_mode,
            },
            "strategy_governance": {
                "risk_class": strategy_risk_class,
                "binding": {
                    "strategy_id": getattr(strategy_binding_eval.get("binding"), "strategy_id", None),
                    "bound_policy_set": getattr(strategy_binding_eval.get("binding"), "bound_policy_set", None),
                    "state": getattr(strategy_binding_eval.get("binding"), "state", None),
                    "enabled": bool(getattr(strategy_binding_eval.get("binding"), "enabled", False)) if strategy_binding_eval.get("binding") else False,
                },
                "violations": list(strategy_binding_eval.get("violations") or []),
                "limits": strategy_limits,
            },
            "execution_mode": "REAL" if _is_live_environment(context.get("environment")) else "SIMULATION",
            "decision_steps": decision_steps,
            "debug": {
                "enabled": debug_enabled,
                "input_snapshot": dict(context) if debug_enabled else {},
                "timing": {"elapsed_ms": elapsed_ms} if debug_enabled else {},
            },
        },
    }


def evaluate_execution_stage_enforcement(*, context: dict, effective_rules: dict, rollout_mode: str) -> dict:
    execution_rules = dict((effective_rules or {}).get("execution") or {})
    requested_price = _safe_float(context.get("requested_price"), 0.0)
    requested_qty = _safe_float(context.get("requested_qty"), 0.0)
    execution_result = dict(context.get("execution_result") or {})

    if requested_price <= 0 or requested_qty <= 0 or not execution_result:
        reject = _reject_contract(
            reason_code="FAILSAFE_ENGINE_UNAVAILABLE",
            reason_message="Execution stage required inputs are missing",
            stage="EXECUTION",
            severity="CRITICAL",
            action_taken="HARD_BLOCK",
            policy_id=None,
            rule_id="execution.required_inputs",
        )
        return {
            "recommended_action": "BLOCK",
            "enforced_action": "BLOCK",
            "rollout_mode": str(rollout_mode or "shadow").lower(),
            "standardized_reject": reject,
            "stage_decision": "VIOLATION",
            "trace": {
                "stage": "EXECUTION",
                "required_inputs": {
                    "requested_price": requested_price,
                    "requested_qty": requested_qty,
                    "execution_result_present": bool(execution_result),
                },
                "metrics_snapshot": {},
                "action_taken": "HARD_BLOCK",
            },
            "metrics_snapshot": {},
        }

    executed_price = _safe_float(execution_result.get("executed_price") or execution_result.get("price"), requested_price)
    executed_qty = _safe_float(execution_result.get("executed_qty") or execution_result.get("filled_qty"), requested_qty)
    status = str(execution_result.get("status") or "").lower()
    latency_ms = _safe_float(execution_result.get("latency_ms"), -1)

    max_deviation_bps = _safe_float(execution_rules.get("max_price_deviation_bps"), 50.0)
    min_fill_ratio = _safe_float(execution_rules.get("min_fill_ratio"), 0.7)
    max_latency_ms = _safe_float(execution_rules.get("max_fill_latency_ms"), 5000.0)

    deviation_bps = abs(executed_price - requested_price) / max(requested_price, 1e-9) * 10000.0
    fill_ratio = executed_qty / max(requested_qty, 1e-9)

    violations: list[dict] = []
    if deviation_bps > max_deviation_bps:
        violations.append(
            {
                "reason_code": "EXECUTION_PRICE_DEVIATION",
                "reason_message": "Execution price deviation exceeded threshold",
                "severity": "HIGH",
                "rule_id": "execution.max_price_deviation_bps",
            }
        )
    if fill_ratio < min_fill_ratio:
        violations.append(
            {
                "reason_code": "EXECUTION_PARTIAL_FILL_LOW_RATIO",
                "reason_message": "Execution fill ratio below threshold",
                "severity": "HIGH",
                "rule_id": "execution.min_fill_ratio",
            }
        )
    if latency_ms < 0 or latency_ms > max_latency_ms:
        violations.append(
            {
                "reason_code": "EXECUTION_TIMEOUT",
                "reason_message": "Execution latency threshold breached",
                "severity": "CRITICAL",
                "rule_id": "execution.max_fill_latency_ms",
            }
        )
    if status not in {"filled", "partial_fill", "accepted"}:
        violations.append(
            {
                "reason_code": "EXECUTION_STATUS_INVALID",
                "reason_message": "Execution status is invalid for enforcement",
                "severity": "CRITICAL",
                "rule_id": "execution.status",
            }
        )

    metrics_snapshot = {
        "requested_price": round(requested_price, 8),
        "requested_qty": round(requested_qty, 8),
        "executed_price": round(executed_price, 8),
        "executed_qty": round(executed_qty, 8),
        "deviation_bps": round(deviation_bps, 6),
        "fill_ratio": round(fill_ratio, 6),
        "latency_ms": round(latency_ms, 6),
        "status": status,
    }

    if not violations:
        return {
            "recommended_action": "ALLOW",
            "enforced_action": "ALLOW",
            "rollout_mode": str(rollout_mode or "shadow").lower(),
            "standardized_reject": None,
            "stage_decision": "ACCEPT",
            "trace": {
                "stage": "EXECUTION",
                "metrics_snapshot": metrics_snapshot,
                "action_taken": "ACCEPT",
            },
            "metrics_snapshot": metrics_snapshot,
        }

    has_critical = any(str(item.get("severity") or "").upper() == "CRITICAL" for item in violations)
    first = violations[0]
    action_taken = "HARD_BLOCK" if has_critical else "THROTTLE_FUTURE"
    reject = _reject_contract(
        reason_code=str(first.get("reason_code") or "EXECUTION_VIOLATION"),
        reason_message=str(first.get("reason_message") or "Execution stage violation"),
        stage="EXECUTION",
        severity="CRITICAL" if has_critical else "HIGH",
        action_taken=action_taken,
        policy_id=None,
        rule_id=str(first.get("rule_id") or "execution.validation"),
    )
    return {
        "recommended_action": "BLOCK" if has_critical else "ALLOW",
        "enforced_action": "BLOCK" if has_critical else "ALLOW",
        "rollout_mode": str(rollout_mode or "shadow").lower(),
        "standardized_reject": reject,
        "stage_decision": "VIOLATION" if has_critical else "FLAG",
        "trace": {
            "stage": "EXECUTION",
            "metrics_snapshot": metrics_snapshot,
            "violations": violations,
            "action_taken": action_taken,
        },
        "metrics_snapshot": metrics_snapshot,
    }


def evaluate_post_trade_enforcement(*, context: dict, effective_rules: dict, risk_reference: dict, rollout_mode: str) -> dict:
    post_rules = dict((effective_rules or {}).get("post_trade") or {})
    execution_result = dict(context.get("execution_result") or {})
    requested_price = _safe_float(context.get("requested_price"), 0.0)
    executed_price = _safe_float(execution_result.get("executed_price") or execution_result.get("price"), 0.0)
    executed_qty = _safe_float(execution_result.get("executed_qty") or execution_result.get("filled_qty"), 0.0)
    slippage_bps = abs(executed_price - requested_price) / max(requested_price, 1e-9) * 10000.0

    projected = dict((risk_reference or {}).get("projected") or {})
    portfolio_domain = dict((risk_reference or {}).get("portfolio_domain") or {})
    exposure_after_trade = _safe_float(context.get("exposure_after_trade"), _safe_float(projected.get("portfolio"), 0.0))
    leverage_after_trade = _safe_float(context.get("leverage_after_trade"), exposure_after_trade / max(_safe_float(context.get("portfolio_equity"), 1.0), 1.0))
    liquidation_distance = _safe_float(
        context.get("liquidation_distance_after_trade")
        or execution_result.get("liquidation_distance_pct"),
        -1,
    )

    max_slippage_bps = _safe_float(post_rules.get("max_slippage_bps"), 80.0)
    max_exposure_after = _safe_float(post_rules.get("max_exposure_after_trade"), _safe_float(projected.get("portfolio"), 300000.0))
    min_liq_distance = _safe_float(post_rules.get("min_liquidation_distance_pct"), 3.0)
    max_leverage_after = _safe_float(post_rules.get("max_leverage_after_trade"), _safe_float(portfolio_domain.get("limits", {}).get("max_leverage"), 4.0))

    violations: list[dict] = []
    if slippage_bps > max_slippage_bps:
        violations.append(
            {
                "reason_code": "POST_TRADE_SLIPPAGE_BREACH",
                "reason_message": "Post-trade slippage limit exceeded",
                "severity": "HIGH",
                "rule_id": "post_trade.max_slippage_bps",
            }
        )
    if exposure_after_trade > max_exposure_after:
        violations.append(
            {
                "reason_code": "POST_TRADE_EXPOSURE_BREACH",
                "reason_message": "Post-trade portfolio exposure limit exceeded",
                "severity": "CRITICAL",
                "rule_id": "post_trade.max_exposure_after_trade",
            }
        )
    if leverage_after_trade > max_leverage_after:
        violations.append(
            {
                "reason_code": "POST_TRADE_LEVERAGE_BREACH",
                "reason_message": "Post-trade leverage limit exceeded",
                "severity": "CRITICAL",
                "rule_id": "post_trade.max_leverage_after_trade",
            }
        )
    if liquidation_distance < min_liq_distance:
        violations.append(
            {
                "reason_code": "POST_TRADE_LIQUIDATION_RISK_BREACH",
                "reason_message": "Liquidation distance below safety threshold",
                "severity": "CRITICAL",
                "rule_id": "post_trade.min_liquidation_distance_pct",
            }
        )

    metrics_snapshot = {
        "requested_price": round(requested_price, 8),
        "executed_price": round(executed_price, 8),
        "executed_qty": round(executed_qty, 8),
        "actual_slippage_bps": round(slippage_bps, 6),
        "exposure_after_trade": round(exposure_after_trade, 6),
        "leverage_after_trade": round(leverage_after_trade, 6),
        "liquidation_distance_after_trade": round(liquidation_distance, 6),
    }

    if not violations:
        return {
            "recommended_action": "ALLOW",
            "enforced_action": "ALLOW",
            "rollout_mode": str(rollout_mode or "shadow").lower(),
            "standardized_reject": None,
            "stage_decision": "ACCEPT",
            "trace": {
                "stage": "POST_TRADE",
                "metrics_snapshot": metrics_snapshot,
                "action_taken": "WARN",
            },
            "metrics_snapshot": metrics_snapshot,
            "action_recommendation": "WARN",
        }

    first = violations[0]
    has_critical = any(str(item.get("severity") or "").upper() == "CRITICAL" for item in violations)
    action_taken = "BLOCK_FUTURE" if has_critical else "THROTTLE_FUTURE"
    reject = _reject_contract(
        reason_code=str(first.get("reason_code") or "POST_TRADE_VIOLATION"),
        reason_message=str(first.get("reason_message") or "Post-trade violation"),
        stage="POST_TRADE",
        severity="CRITICAL" if has_critical else "HIGH",
        action_taken=action_taken,
        policy_id=None,
        rule_id=str(first.get("rule_id") or "post_trade.validation"),
    )
    return {
        "recommended_action": "BLOCK" if has_critical else "ALLOW",
        "enforced_action": "ALLOW",
        "rollout_mode": str(rollout_mode or "shadow").lower(),
        "standardized_reject": reject,
        "stage_decision": "VIOLATION",
        "trace": {
            "stage": "POST_TRADE",
            "metrics_snapshot": metrics_snapshot,
            "violations": violations,
            "action_taken": action_taken,
        },
        "metrics_snapshot": metrics_snapshot,
        "action_recommendation": action_taken,
    }


def append_execution_policy_decision_log(
    db: Session,
    *,
    lifecycle_action: str,
    stage: str,
    context: dict,
    policy_result: dict,
    action_taken: str,
    is_violation: bool,
) -> ExecutionPolicyDecisionLog:
    reject = dict(policy_result.get("standardized_reject") or {})
    trace_payload = dict(policy_result.get("trace") or {})
    metrics_snapshot = dict(policy_result.get("metrics_snapshot") or trace_payload.get("metrics_snapshot") or {})
    trace_id = str(context.get("trace_id") or context.get("pipeline_id") or context.get("intent_token") or "") or None
    execution_mode = str(context.get("execution_mode") or ("REAL" if _is_live_environment(context.get("environment")) else "SIMULATION")).upper()
    simulation_mode = execution_mode == "SIMULATION"
    violation_id = str(context.get("violation_id") or "") or None
    if is_violation and violation_id is None:
        violation_id = str(uuid.uuid4())
    row = ExecutionPolicyDecisionLog(
        id=str(uuid.uuid4()),
        pipeline_id=str(context.get("pipeline_id") or ""),
        lifecycle_action=str(lifecycle_action or "").lower(),
        stage=str(stage or "").upper(),
        intent_id=str(context.get("intent_id") or "") or None,
        intent_token=str(context.get("intent_token") or "") or None,
        user_id=str(context.get("user_id") or "") or None,
        portfolio_id=str(context.get("portfolio_id") or "") or None,
        trace_id=trace_id,
        execution_mode=execution_mode,
        simulation_mode=simulation_mode,
        symbol=str(context.get("symbol") or "").upper() or None,
        strategy_binding=str(context.get("strategy_binding") or "") or None,
        environment=str(context.get("environment") or "testnet").lower(),
        rollout_mode=str(policy_result.get("rollout_mode") or "shadow").lower(),
        recommended_action=str(policy_result.get("recommended_action") or "ALLOW"),
        enforced_action=str(policy_result.get("enforced_action") or "ALLOW"),
        reason_code=reject.get("reason_code"),
        reason_message=reject.get("reason_message"),
        policy_id=reject.get("policy_id"),
        rule_id=reject.get("rule_id"),
        violation_id=violation_id,
        triggered_policy=reject.get("policy_id"),
        triggered_rule=reject.get("rule_id"),
        metrics_snapshot=metrics_snapshot,
        severity=str(reject.get("severity") or "INFO").upper(),
        action_taken=action_taken,
        is_violation=bool(is_violation),
        trace_payload=trace_payload,
        created_at=datetime.now(timezone.utc),
    )

    auto_action = str(
        reject.get("auto_action_recommendation")
        or trace_payload.get("auto_action_recommendation")
        or select_auto_action(
            db,
            severity=str(reject.get("severity") or row.severity),
            reason_code=str(reject.get("reason_code") or ""),
            environment=str(context.get("environment") or "testnet"),
            strategy_risk_class=str(context.get("strategy_risk_class") or "MEDIUM"),
            strategy_id=str(context.get("strategy_binding") or ""),
        )
    ).upper()
    row.trace_payload = {
        **trace_payload,
        "decision_id": policy_result.get("decision_id") or trace_payload.get("decision_id"),
        "decision_reason_summary": policy_result.get("decision_reason_summary"),
        "auto_action_recommendation": auto_action,
        "execution_mode": execution_mode,
        "simulation_mode": simulation_mode,
    }

    if is_violation:
        emit_governance_event(
            db,
            event_type="violation.created",
            payload={
                "violation_id": violation_id or row.id,
                "trace_id": trace_id,
                "reason_code": row.reason_code,
                "severity": row.severity,
                "stage": row.stage,
                "execution_mode": execution_mode,
            },
            idempotency_key=f"violation.created:{violation_id or row.id}",
        )
        if str(row.severity or "").upper() == "CRITICAL":
            emit_governance_event(
                db,
                event_type="violation.severity_escalated",
                payload={
                    "violation_id": violation_id or row.id,
                    "severity": row.severity,
                    "reason_code": row.reason_code,
                },
                idempotency_key=f"violation.severity_escalated:{violation_id or row.id}",
            )

        if auto_action not in {"NONE", "WARN"}:
            rec = create_remediation_recommendation(
                db,
                trace_id=trace_id,
                source_violation_id=violation_id or row.id,
                recommendation_type=auto_action,
                severity=row.severity,
                reason_code=row.reason_code,
                summary=f"{auto_action} önerisi: {row.reason_code}",
                payload={
                    "stage": row.stage,
                    "reason_message": row.reason_message,
                    "strategy_id": row.strategy_binding,
                    "environment": row.environment,
                    "metrics_snapshot": row.metrics_snapshot,
                    "manual_required": True,
                },
                created_by=context.get("user_id"),
            )
            row.trace_payload = {
                **dict(row.trace_payload or {}),
                "remediation_recommendation_id": rec.recommendation_id,
            }
            event_map = {
                "DISABLE_STRATEGY": "strategy.disabled",
                "THROTTLE": "throttle.applied",
                "ESCALATE_RELEASE_GATE": "release_gate.escalated",
            }
            mapped_event = event_map.get(auto_action)
            if mapped_event:
                emit_governance_event(
                    db,
                    event_type=mapped_event,
                    payload={
                        "trace_id": trace_id,
                        "violation_id": violation_id or row.id,
                        "recommendation_id": rec.recommendation_id,
                        "action": auto_action,
                    },
                    idempotency_key=f"{mapped_event}:{violation_id or row.id}",
                )

    db.add(row)
    return row


def list_recent_execution_policy_decisions(db: Session, *, limit: int = 50) -> list[dict]:
    rows = (
        db.query(ExecutionPolicyDecisionLog)
        .order_by(ExecutionPolicyDecisionLog.created_at.desc())
        .limit(max(min(limit, 200), 1))
        .all()
    )
    return [
        {
            "id": row.id,
            "pipeline_id": row.pipeline_id,
            "lifecycle_action": row.lifecycle_action,
            "stage": row.stage,
            "intent_id": row.intent_id,
            "user_id": row.user_id,
            "portfolio_id": row.portfolio_id,
            "trace_id": row.trace_id,
            "execution_mode": row.execution_mode,
            "simulation_mode": bool(row.simulation_mode),
            "symbol": row.symbol,
            "strategy_binding": row.strategy_binding,
            "environment": row.environment,
            "rollout_mode": row.rollout_mode,
            "recommended_action": row.recommended_action,
            "enforced_action": row.enforced_action,
            "reason_code": row.reason_code,
            "reason_message": row.reason_message,
            "violation_id": row.violation_id,
            "triggered_policy": row.triggered_policy,
            "triggered_rule": row.triggered_rule,
            "metrics_snapshot": row.metrics_snapshot or {},
            "decision_reason_summary": (
                f"{row.stage} stage decision: {row.reason_message}"
                if row.reason_message
                else f"{row.stage} stage decision: {row.enforced_action}"
            ),
            "severity": row.severity,
            "action_taken": row.action_taken,
            "is_violation": bool(row.is_violation),
            "created_at": row.created_at,
        }
        for row in rows
    ]


def get_decision_trace_detail(db: Session, *, trace_id: str) -> dict:
    rows = (
        db.query(ExecutionPolicyDecisionLog)
        .filter(ExecutionPolicyDecisionLog.trace_id == trace_id)
        .order_by(ExecutionPolicyDecisionLog.created_at.asc())
        .all()
    )
    if not rows:
        rows = (
            db.query(ExecutionPolicyDecisionLog)
            .filter(ExecutionPolicyDecisionLog.pipeline_id == trace_id)
            .order_by(ExecutionPolicyDecisionLog.created_at.asc())
            .all()
        )
    if not rows:
        raise ValueError("decision_trace_not_found")

    first = rows[0]
    step_rows = []
    for idx, row in enumerate(rows):
        trace_payload = dict(row.trace_payload or {})
        step_rows.append(
            {
                "step_index": idx,
                "step_type": row.stage,
                "policy_id": row.policy_id,
                "rule_id": row.rule_id,
                "condition_result": True,
                "previous_state": row.recommended_action,
                "new_state": row.enforced_action,
                "comment": row.reason_message or row.action_taken,
                "metrics_snapshot": row.metrics_snapshot or {},
                "trace_payload": trace_payload,
            }
        )

    return {
        "decision_id": (first.trace_payload or {}).get("decision_id") or first.id,
        "trace_id": trace_id,
        "final_decision": rows[-1].enforced_action,
        "decision_reason_summary": rows[-1].reason_message or rows[-1].action_taken,
        "matched_policies": (first.trace_payload or {}).get("matched_policies") or [],
        "matched_rules": [row.rule_id for row in rows if row.rule_id],
        "applied_overrides": (first.trace_payload or {}).get("applied_overrides") or [],
        "evaluation_order": [row.stage for row in rows],
        "input_snapshot": (first.trace_payload or {}).get("debug", {}).get("input_snapshot") or {},
        "output_snapshot": {
            "recommended_action": rows[-1].recommended_action,
            "enforced_action": rows[-1].enforced_action,
            "severity": rows[-1].severity,
            "reason_code": rows[-1].reason_code,
        },
        "steps": step_rows,
    }


def build_execution_policy_observability(db: Session, *, hours: int = 24) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=max(hours, 1))
    rows = (
        db.query(ExecutionPolicyDecisionLog)
        .filter(ExecutionPolicyDecisionLog.created_at >= since)
        .order_by(ExecutionPolicyDecisionLog.created_at.desc())
        .all()
    )

    reason_distribution: dict[str, int] = {}
    stage_stats: dict[str, dict[str, int]] = {}
    stage_violation_distribution: dict[str, int] = {}
    violation_count = 0
    risk_breach_count = 0
    execution_stage_violation_count = 0
    post_trade_violation_count = 0
    failsafe_hard_block_count = 0
    simulation_violation_count = 0
    real_violation_count = 0
    critical_violations: list[dict] = []
    for row in rows:
        stage = str(row.stage or "UNKNOWN").upper()
        stage_bucket = stage_stats.setdefault(stage, {"allow": 0, "block": 0, "total": 0})
        stage_bucket["total"] += 1
        if str(row.enforced_action or "ALLOW").upper() == "BLOCK":
            stage_bucket["block"] += 1
        else:
            stage_bucket["allow"] += 1

        if row.reason_code:
            reason_distribution[row.reason_code] = reason_distribution.get(row.reason_code, 0) + 1
            if str(row.reason_code).startswith("RISK_"):
                risk_breach_count += 1
        if bool(row.is_violation):
            violation_count += 1
            stage_violation_distribution[stage] = stage_violation_distribution.get(stage, 0) + 1
            if bool(row.simulation_mode):
                simulation_violation_count += 1
            else:
                real_violation_count += 1
            if stage == "EXECUTION":
                execution_stage_violation_count += 1
            if stage == "POST_TRADE":
                post_trade_violation_count += 1
        if str(row.action_taken or "").upper() == "HARD_BLOCK" and _is_failsafe_reason_code(row.reason_code):
            failsafe_hard_block_count += 1
        if bool(row.is_violation) and str(row.severity or "").upper() == "CRITICAL" and len(critical_violations) < 20:
            critical_violations.append(
                {
                    "violation_id": row.violation_id or row.id,
                    "reason_code": row.reason_code,
                    "stage": row.stage,
                    "severity": row.severity,
                    "triggered_policy": row.triggered_policy,
                    "triggered_rule": row.triggered_rule,
                    "metrics_snapshot": row.metrics_snapshot or {},
                    "created_at": row.created_at,
                }
            )

    stage_decision_rates = {
        stage.lower(): {
            "allow": stats["allow"],
            "block": stats["block"],
            "allow_rate": round(stats["allow"] / max(stats["total"], 1), 6),
            "block_rate": round(stats["block"] / max(stats["total"], 1), 6),
            "total": stats["total"],
        }
        for stage, stats in stage_stats.items()
    }

    return {
        "window_hours": max(hours, 1),
        "decision_log_count": len(rows),
        "violation_count": violation_count,
        "execution_stage_violation_count": execution_stage_violation_count,
        "post_trade_violation_count": post_trade_violation_count,
        "failsafe_hard_block_count": failsafe_hard_block_count,
        "simulation_violation_count": simulation_violation_count,
        "real_violation_count": real_violation_count,
        "risk_breach_metrics": {
            "breach_count": risk_breach_count,
            "breach_rate": round(risk_breach_count / max(len(rows), 1), 6),
        },
        "reject_reason_distribution": [
            {"reason_code": code, "count": count}
            for code, count in sorted(reason_distribution.items(), key=lambda item: item[1], reverse=True)
        ],
        "top_reason_codes": [
            {"reason_code": code, "count": count}
            for code, count in sorted(reason_distribution.items(), key=lambda item: item[1], reverse=True)[:10]
        ],
        "stage_violation_distribution": {
            stage.lower(): count for stage, count in sorted(stage_violation_distribution.items(), key=lambda item: item[0])
        },
        "recent_critical_violations": critical_violations,
        "violation_aggregations": {
            "5m": build_violation_aggregation(db, window="5m"),
            "1h": build_violation_aggregation(db, window="1h"),
            "24h": build_violation_aggregation(db, window="24h"),
            "7d": build_violation_aggregation(db, window="7d"),
        },
        "strategy_health": build_strategy_health_state(db, window_hours=24),
        "policy_versions": list_policy_versions(db, limit=100),
        "remediation_recommendations": list_remediation_recommendations(db, limit=100),
        "release_gate": build_release_gate_status(db, window_hours=24),
        "stage_decision_rates": stage_decision_rates,
        "pre_post_ratio": {
            "pre_trade_total": stage_stats.get("PRE_TRADE", {}).get("total", 0),
            "post_trade_total": stage_stats.get("POST_TRADE", {}).get("total", 0),
        },
    }


def get_policy_for_strategy(db: Session, strategy_type: str) -> ExecutionPolicy:
    policy = (
        db.query(ExecutionPolicy)
        .filter(ExecutionPolicy.strategy_type == strategy_type, ExecutionPolicy.is_active.is_(True))
        .first()
    )
    if policy:
        return policy

    defaults = DEFAULT_POLICY_MAP.get(strategy_type, DEFAULT_POLICY_MAP["trend_following"])
    policy = ExecutionPolicy(
        strategy_type=strategy_type,
        policy_scope="strategy",
        scope_key=strategy_type,
        policy_code=f"legacy:{strategy_type}",
        priority=40,
        override_behavior="merge",
        conditions_payload={},
        rules_payload={"execution": dict(defaults)},
        **defaults,
        is_active=True,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy
