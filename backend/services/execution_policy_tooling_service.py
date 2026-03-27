from __future__ import annotations

import copy
from dataclasses import dataclass

from sqlalchemy.orm import Session

from models import ExecutionPolicyVersion


ACTION_PRIORITY = {
    "NONE": 0,
    "WARN": 1,
    "THROTTLE": 2,
    "REDUCE_ONLY": 3,
    "DISABLE_STRATEGY": 4,
    "BLOCK": 5,
}
SEVERITY_PRIORITY = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}
ALLOWED_OPERATORS = {">", "<", "=", "!=", ">=", "<="}
ALLOWED_ACTIONS = {"BLOCK", "WARN", "THROTTLE", "REDUCE_ONLY", "DISABLE_STRATEGY"}


@dataclass
class ValidationResult:
    errors: list[str]
    warnings: list[str]
    risk_level: str


def _to_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def build_internal_policy_schema(builder_payload: dict) -> dict:
    payload = dict(builder_payload or {})
    scope = dict(payload.get("scope") or {})
    rules = [dict(item) for item in list(payload.get("rules") or [])]
    schema = {
        "policy_code": str(payload.get("policy_code") or "").strip(),
        "version_label": str(payload.get("version_label") or "builder"),
        "scope": {
            "environment": str(scope.get("environment") or "DEV").upper(),
            "strategy": str(scope.get("strategy") or "").strip(),
            "user": str(scope.get("user") or "").strip(),
            "portfolio": str(scope.get("portfolio") or "").strip(),
            "symbol": str(scope.get("symbol") or "").upper().strip(),
        },
        "rules": rules,
        "metadata": {
            "source": "policy_builder",
            "description": str(payload.get("description") or ""),
        },
    }

    conditions_payload = {}
    env = schema["scope"].get("environment")
    if env:
        conditions_payload["environment_in"] = [env.lower()]

    rules_payload = {
        "builder_rules": copy.deepcopy(rules),
        "builder_metadata": copy.deepcopy(schema["metadata"]),
        "builder_scope": copy.deepcopy(schema["scope"]),
    }
    return {
        "schema": schema,
        "conditions_payload": conditions_payload,
        "rules_payload": rules_payload,
    }


def validate_policy_schema(policy_schema: dict) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    schema = dict(policy_schema or {})
    policy_code = str(schema.get("policy_code") or "").strip()
    rules = list(schema.get("rules") or [])
    if not policy_code:
        errors.append("policy_code zorunludur")
    if not rules:
        errors.append("En az bir rule tanımlanmalı")

    seen_signatures: dict[str, str] = {}
    has_block_action = False
    for idx, rule in enumerate(rules):
        rule_id = str(rule.get("rule_id") or f"rule_{idx+1}")
        action = str(rule.get("action") or "").upper()
        severity = str(rule.get("severity") or "").upper()
        conditions = list(rule.get("conditions") or [])

        if action not in ALLOWED_ACTIONS:
            errors.append(f"{rule_id}: action geçersiz")
        if severity not in SEVERITY_PRIORITY:
            errors.append(f"{rule_id}: severity geçersiz")
        if action == "BLOCK":
            has_block_action = True
        if not conditions:
            errors.append(f"{rule_id}: en az bir condition gerekli")

        signature_parts = []
        for c_idx, cond in enumerate(conditions):
            field = str(cond.get("field") or "").strip()
            operator = str(cond.get("operator") or "")
            value = cond.get("value")
            if not field:
                errors.append(f"{rule_id}.conditions[{c_idx}]: field zorunlu")
            if operator not in ALLOWED_OPERATORS:
                errors.append(f"{rule_id}.conditions[{c_idx}]: operator geçersiz")
            if value is None or str(value) == "":
                errors.append(f"{rule_id}.conditions[{c_idx}]: value zorunlu")
            signature_parts.append(f"{field}:{operator}:{value}")

        signature = "|".join(sorted(signature_parts))
        if signature in seen_signatures and seen_signatures[signature] != action:
            errors.append(f"{rule_id}: çakışan action (semantic conflict)")
        seen_signatures[signature] = action

        # Basit unreachable condition kontrolü
        bounds: dict[str, dict[str, float]] = {}
        for cond in conditions:
            field = str(cond.get("field") or "")
            op = str(cond.get("operator") or "")
            val = _to_float(cond.get("value"), fallback=float("nan"))
            if val != val:  # NaN
                continue
            data = bounds.setdefault(field, {"min": float("-inf"), "max": float("inf")})
            if op in {">", ">="}:
                data["min"] = max(data["min"], val)
            if op in {"<", "<="}:
                data["max"] = min(data["max"], val)
        for field, boundary in bounds.items():
            if boundary["min"] > boundary["max"]:
                errors.append(f"{rule_id}: unreachable condition ({field})")

    if not has_block_action:
        warnings.append("Risk validation: hiç BLOCK action yok (yüksek risk)")

    risk_level = "LOW"
    if errors:
        risk_level = "HIGH"
    elif any("yüksek risk" in warn.lower() for warn in warnings):
        risk_level = "HIGH"
    elif warnings:
        risk_level = "MEDIUM"

    return ValidationResult(errors=errors, warnings=warnings, risk_level=risk_level)


def _condition_passes(condition: dict, values: dict) -> bool:
    field = str(condition.get("field") or "")
    operator = str(condition.get("operator") or "")
    expected = condition.get("value")
    actual = values.get(field)
    if actual is None:
        return False

    if operator == "=":
        return str(actual) == str(expected)
    if operator == "!=":
        return str(actual) != str(expected)

    actual_f = _to_float(actual, fallback=float("nan"))
    expected_f = _to_float(expected, fallback=float("nan"))
    if actual_f != actual_f or expected_f != expected_f:
        return False
    if operator == ">":
        return actual_f > expected_f
    if operator == "<":
        return actual_f < expected_f
    if operator == ">=":
        return actual_f >= expected_f
    if operator == "<=":
        return actual_f <= expected_f
    return False


def _rule_passes(rule: dict, values: dict) -> tuple[bool, list[dict]]:
    conditions = list(rule.get("conditions") or [])
    logical = str(rule.get("logical_operator") or "AND").upper()
    checks = []
    passed_flags = []
    for cond in conditions:
        passed = _condition_passes(cond, values)
        checks.append({"condition": cond, "passed": passed})
        passed_flags.append(passed)
    if not passed_flags:
        return False, checks
    if logical == "OR":
        return any(passed_flags), checks
    return all(passed_flags), checks


def simulate_policy_schema(policy_schema: dict, simulation_input: dict) -> dict:
    schema = dict(policy_schema or {})
    values = {
        **dict(simulation_input.get("order") or {}),
        **dict(simulation_input.get("market_state") or {}),
        "environment": simulation_input.get("environment"),
        "strategy_risk_class": simulation_input.get("strategy_risk_class"),
        "strategy": simulation_input.get("strategy"),
    }
    rules = list(schema.get("rules") or [])
    matched_rules = []
    trace = []
    final_action = "WARN"
    final_severity = "LOW"
    current_action_score = -1
    current_severity_score = -1

    for idx, rule in enumerate(rules):
        passed, checks = _rule_passes(rule, values)
        trace.append(
            {
                "step_index": idx,
                "rule_id": rule.get("rule_id") or f"rule_{idx+1}",
                "passed": passed,
                "checks": checks,
            }
        )
        if not passed:
            continue
        action = str(rule.get("action") or "WARN").upper()
        severity = str(rule.get("severity") or "LOW").upper()
        matched_rules.append(
            {
                "rule_id": rule.get("rule_id") or f"rule_{idx+1}",
                "action": action,
                "severity": severity,
            }
        )
        action_score = ACTION_PRIORITY.get(action, 0)
        severity_score = SEVERITY_PRIORITY.get(severity, 1)
        if action_score > current_action_score or (
            action_score == current_action_score and severity_score > current_severity_score
        ):
            final_action = action
            final_severity = severity
            current_action_score = action_score
            current_severity_score = severity_score

    decision = "ALLOW"
    if final_action in {"BLOCK", "DISABLE_STRATEGY"}:
        decision = "BLOCK"
    elif matched_rules:
        decision = "FLAG"

    return {
        "decision": decision,
        "action": final_action,
        "severity": final_severity,
        "triggered_rules": matched_rules,
        "trace": trace,
        "simulation_mode": True,
    }


def generate_human_readable_policy(policy_schema: dict) -> dict:
    schema = dict(policy_schema or {})
    rules = list(schema.get("rules") or [])
    scope = dict(schema.get("scope") or {})
    if not rules:
        summary = "Bu policy için tanımlı rule bulunmuyor."
        return {
            "summary": summary,
            "description": summary,
            "trigger_conditions": [],
            "affected_scopes": scope,
        }

    first_rule = rules[0]
    conditions = [
        f"{c.get('field')} {c.get('operator')} {c.get('value')}"
        for c in list(first_rule.get("conditions") or [])
    ]
    action = str(first_rule.get("action") or "WARN").upper()
    summary = f"Koşullar sağlanırsa aksiyon: {action}."
    description = (
        f"Policy, {len(rules)} rule içerir. İlk rule tetikleyicileri: "
        + (", ".join(conditions) if conditions else "koşul yok")
        + f". Etkilenen ana scope: env={scope.get('environment')}, strategy={scope.get('strategy')}."
    )
    return {
        "summary": summary,
        "description": description,
        "trigger_conditions": conditions,
        "affected_scopes": scope,
    }


def get_policy_version_diff(db: Session, *, policy_code: str, version_a: str, version_b: str) -> dict:
    row_a = db.query(ExecutionPolicyVersion).filter(ExecutionPolicyVersion.version_id == version_a).first()
    row_b = db.query(ExecutionPolicyVersion).filter(ExecutionPolicyVersion.version_id == version_b).first()
    if row_a is None or row_b is None:
        raise ValueError("diff_versions_not_found")
    if row_a.policy_code != policy_code or row_b.policy_code != policy_code:
        raise ValueError("diff_policy_code_mismatch")

    schema_a = {
        "policy_code": row_a.policy_code,
        "scope": dict((row_a.rules_payload or {}).get("builder_scope") or {}),
        "rules": list((row_a.rules_payload or {}).get("builder_rules") or []),
    }
    schema_b = {
        "policy_code": row_b.policy_code,
        "scope": dict((row_b.rules_payload or {}).get("builder_scope") or {}),
        "rules": list((row_b.rules_payload or {}).get("builder_rules") or []),
    }

    def _risk_mark(before, after):
        before_action = str(before or "WARN").upper()
        after_action = str(after or "WARN").upper()
        delta = ACTION_PRIORITY.get(after_action, 0) - ACTION_PRIORITY.get(before_action, 0)
        if delta > 0:
            return "🔴"
        if delta < 0:
            return "🟢"
        return "🟡"

    rule_map_a = {str(r.get("rule_id") or f"a_{idx}"): r for idx, r in enumerate(schema_a.get("rules") or [])}
    rule_map_b = {str(r.get("rule_id") or f"b_{idx}"): r for idx, r in enumerate(schema_b.get("rules") or [])}

    changed = []
    for key in sorted(set(rule_map_a.keys()) | set(rule_map_b.keys())):
        before = rule_map_a.get(key)
        after = rule_map_b.get(key)
        if before == after:
            continue
        changed.append(
            {
                "rule_id": key,
                "before": before,
                "after": after,
                "risk_impact": _risk_mark(
                    (before or {}).get("action") if before else None,
                    (after or {}).get("action") if after else None,
                ),
            }
        )

    return {
        "policy_code": policy_code,
        "version_a": {
            "version_id": row_a.version_id,
            "version_number": row_a.version_number,
            "state": row_a.state,
            "schema": schema_a,
        },
        "version_b": {
            "version_id": row_b.version_id,
            "version_number": row_b.version_number,
            "state": row_b.state,
            "schema": schema_b,
        },
        "changes": changed,
    }
