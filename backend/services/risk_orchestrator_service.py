from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import (
    AdminControl,
    AuditLog,
    ExecutionIntent,
    ExecutionIntentEvent,
    Position,
    RiskOrchestratorAutoTriggerLog,
    RiskOrchestratorInterventionLog,
    RiskOrchestratorManualOverride,
    RiskOrchestratorPolicy,
    RiskOrchestratorPolicyChangeRequest,
    RiskOrchestratorPolicySimulation,
    RiskOrchestratorPolicyVersion,
    SystemAlert,
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
    snapshot = build_status_snapshot(db)

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
        metrics=diff["metrics"],
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
    approval_note: str | None,
) -> dict:
    if not double_confirmed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="double_confirmation_required")

    simulation = (
        db.query(RiskOrchestratorPolicySimulation)
        .filter(RiskOrchestratorPolicySimulation.simulation_id == simulation_id)
        .first()
    )
    if simulation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="simulation_not_found")

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
        payload=simulation.candidate_policy,
        simulation_id=simulation.simulation_id,
        critical_fields=simulation.diff_summary.get("critical_fields") or [],
        double_confirmed=True,
        decided_at=_now(),
    )
    db.add(change_request)

    updated_policy = update_policy(db, payload=simulation.candidate_policy)
    updated_policy.policy_version = int(getattr(updated_policy, "policy_version", 1) or 1) + 1

    diff_payload = _policy_diff(previous_payload, _policy_payload(updated_policy))
    version = RiskOrchestratorPolicyVersion(
        version_id=f"ro-pv-{uuid4().hex[:18]}",
        version_no=updated_policy.policy_version,
        policy_payload=_policy_payload(updated_policy),
        diff_payload=diff_payload,
        changed_by=actor_id,
        changed_role=actor_role,
        reason_note=reason_note,
        simulation_id=simulation.simulation_id,
        approval_request_id=change_request.request_id,
    )
    db.add(version)
    db.commit()
    db.refresh(updated_policy)
    db.refresh(version)

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
        },
        severity="high",
    )

    return {
        "policy": updated_policy,
        "version": version,
        "change_request": change_request,
        "simulation": simulation,
    }


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
    query = db.query(SystemAlert).filter(
        SystemAlert.alert_type.in_(["risk_orchestrator_breach", "daily_loss_limit_hit", "exposure_limit_breach"])
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

    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items[:limit]
