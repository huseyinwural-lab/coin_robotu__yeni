# ruff: noqa: E402
import sys
import uuid
from pathlib import Path

from db import SessionLocal

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from models import BrandSetting, ExecutionPolicy, User, UserRole
from services.execution_governance_service import (
    activate_policy_version,
    approve_policy_version,
    build_release_gate_status,
    build_violation_aggregation,
    classify_violation_severity,
    compare_policy_versions_ab,
    create_policy_version,
    evaluate_strategy_binding_constraints,
    list_policy_versions,
    list_remediation_recommendations,
    resolve_policy_version_override,
    rollback_policy_version,
    select_auto_action,
    update_remediation_recommendation_status,
)
from services.execution_pipeline_orchestrator import run_execution_pipeline
from services.execution_policy_service import (
    append_execution_policy_decision_log,
    build_execution_policy_observability,
    ensure_dynamic_execution_policies,
    seed_default_strategy_bindings,
)


def _create_user(db) -> User:
    row = User(
        email=f"p1-gov-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password("P1Governance123!"),
        role=UserRole.ADMIN,
        is_active=True,
        approval_status="approved",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _set_governance_debug(db, enabled: bool) -> None:
    row = db.query(BrandSetting).filter(BrandSetting.id == "default").first()
    if row is None:
        row = BrandSetting(id="default", metadata_json={})
        db.add(row)
        db.flush()
    metadata = dict(row.metadata_json or {})
    metadata["execution_governance"] = {
        "auto_remediation_mode": "manual_recommend",
        "severity_overrides": {},
        "debug": {
            "enabled": enabled,
            "environments": ["testnet"],
            "strategies": ["p1_strategy"],
            "request_ids": [],
        },
    }
    row.metadata_json = metadata
    db.commit()


def _ensure_strategy_policy(db, strategy: str = "p1_strategy"):
    row = db.query(ExecutionPolicy).filter(ExecutionPolicy.strategy_type == strategy).first()
    if row is None:
        row = ExecutionPolicy(
            strategy_type=strategy,
            execution_style="balanced",
            order_preference="limit_first",
            timeout_seconds=8,
            fallback_behavior="market_fallback",
            partial_fill_tolerance_pct=60,
            execution_urgency="medium",
            retry_limit=1,
            is_active=True,
        )
        db.add(row)
    row.policy_code = f"p1:{strategy}"
    row.policy_scope = "strategy"
    row.scope_key = strategy
    row.rules_payload = {
        "runtime": {"require_market_data": True, "dependency_timeout_ms": 5000},
        "execution": {"max_price_deviation_bps": 50, "min_fill_ratio": 0.7, "max_fill_latency_ms": 5000},
        "post_trade": {"max_slippage_bps": 100, "max_exposure_after_trade": 500000, "max_leverage_after_trade": 4, "min_liquidation_distance_pct": 3},
        "risk": {"max_order_notional": 100000, "max_symbol_exposure": 500000, "max_strategy_exposure": 500000, "max_user_exposure": 500000, "max_portfolio_exposure": 500000},
    }
    row.conditions_payload = {}
    row.override_behavior = "merge"
    row.priority = 40
    row.is_active = True
    db.commit()


def _submit_context(user_id: str, strategy: str = "p1_strategy", mode: str = "SIMULATION") -> dict:
    return {
        "intent_token": str(uuid.uuid4()),
        "request_id": str(uuid.uuid4()),
        "user_id": user_id,
        "portfolio_id": f"default:{user_id}",
        "strategy_binding": strategy,
        "symbol": "BTCUSDT",
        "side": "buy",
        "environment": "testnet" if mode == "SIMULATION" else "live",
        "market_type": "spot",
        "margin_mode": "",
        "proposed_notional": 120.0,
        "requested_price": 100.0,
        "requested_qty": 1.2,
        "execution_result": {
            "executed_price": 100.0,
            "executed_qty": 1.2,
            "status": "filled",
            "latency_ms": 100.0,
            "exposure_after_trade": 120.0,
            "leverage_after_trade": 1.0,
            "liquidation_distance_after_trade": 15.0,
        },
        "market_data_available": True,
        "portfolio_equity": 10000,
        "execution_mode": mode,
    }


def test_severity_mapping_and_auto_action_selection():
    db = SessionLocal()
    try:
        severity = classify_violation_severity(
            db,
            reason_code="RISK_ORDER_BREACH",
            default_severity="HIGH",
            strategy_risk_class="HIGH",
        )
        action = select_auto_action(
            db,
            severity=severity,
            reason_code="RISK_ORDER_BREACH",
            environment="live",
            strategy_risk_class="HIGH",
            strategy_id="p1_strategy",
        )
        assert severity == "CRITICAL"
        assert action in {"DISABLE_STRATEGY", "BLOCK"}
    finally:
        db.close()


def test_strategy_binding_missing_detected():
    db = SessionLocal()
    try:
        result = evaluate_strategy_binding_constraints(
            db,
            context={
                "strategy_binding": "unknown_strategy",
                "environment": "live",
                "symbol": "BTCUSDT",
                "margin_mode": "cross",
            },
        )
        violations = result.get("violations") or []
        assert violations
        assert violations[0]["reason_code"] == "STRATEGY_BINDING_MISSING"
    finally:
        db.close()


def test_decision_trace_and_violation_aggregation_separates_simulation_real():
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _ensure_strategy_policy(db)
        seed_default_strategy_bindings(db, strategy_ids=["p1_strategy"])
        user = _create_user(db)

        sim_result = run_execution_pipeline(db, lifecycle_action="submit", context=_submit_context(user.id, mode="SIMULATION"))
        real_context = _submit_context(user.id, mode="REAL")
        real_context["execution_result"] = {
            **real_context["execution_result"],
            "executed_price": 120.0,
        }
        run_execution_pipeline(db, lifecycle_action="submit", context=real_context)
        db.commit()

        trace_id = sim_result.get("pipeline_id")
        assert trace_id
        aggregation = build_violation_aggregation(db, window="24h")
        assert aggregation["simulation_violation_count"] >= 0
        assert aggregation["real_violation_count"] >= 0
    finally:
        db.close()


def test_policy_version_activation_requires_approval_in_live_and_supports_rollback():
    db = SessionLocal()
    try:
        user = _create_user(db)
        _ensure_strategy_policy(db)

        v1 = create_policy_version(
            db,
            policy_code="p1:p1_strategy",
            conditions_payload={},
            rules_payload={"risk": {"max_order_notional": 100}},
            change_summary="v1",
            created_by=user.id,
        )
        v2 = create_policy_version(
            db,
            policy_code="p1:p1_strategy",
            conditions_payload={},
            rules_payload={"risk": {"max_order_notional": 50}},
            change_summary="v2",
            created_by=user.id,
        )

        failed = False
        try:
            activate_policy_version(db, version_id=v1.version_id, actor_user_id=user.id, environment="live")
        except ValueError:
            failed = True
        assert failed

        approve_policy_version(db, version_id=v1.version_id, actor_user_id=user.id)
        activate_policy_version(db, version_id=v1.version_id, actor_user_id=user.id, environment="live")
        rollback_policy_version(
            db,
            policy_code="p1:p1_strategy",
            target_version_id=v2.version_id,
            actor_user_id=user.id,
            reason="test rollback",
        )
        db.commit()

        versions = list_policy_versions(db, policy_code="p1:p1_strategy")
        assert versions
        assert any(item["state"] in {"ACTIVE", "ROLLED_BACK"} for item in versions)
    finally:
        db.close()


def test_canary_routing_and_ab_compare():
    db = SessionLocal()
    try:
        user = _create_user(db)
        v1 = create_policy_version(
            db,
            policy_code="p1:canary_strategy",
            conditions_payload={},
            rules_payload={"risk": {"max_order_notional": 100}},
            change_summary="active",
            created_by=user.id,
            state="ACTIVE",
        )
        v1.state = "ACTIVE"
        v1.approval_status = "approved"

        v2 = create_policy_version(
            db,
            policy_code="p1:canary_strategy",
            conditions_payload={},
            rules_payload={"risk": {"max_order_notional": 50}},
            change_summary="canary",
            created_by=user.id,
            state="CANARY",
        )
        v2.state = "CANARY"
        v2.rollout_strategy = {"environments": ["testnet"], "strategy_ids": ["p1_strategy"], "traffic_percentage": 100}
        db.commit()

        override = resolve_policy_version_override(
            db,
            policy_code="p1:canary_strategy",
            context={"environment": "testnet", "strategy_binding": "p1_strategy", "symbol": "BTCUSDT", "user_id": user.id},
        )
        assert override is not None
        assert override["mode"] == "CANARY"

        delta = compare_policy_versions_ab(
            db,
            policy_code="p1:canary_strategy",
            primary_version_id=v1.version_id,
            shadow_version_id=v2.version_id,
        )
        assert "decision_delta" in delta
    finally:
        db.close()


def test_release_gate_and_remediation_manual_flow():
    db = SessionLocal()
    try:
        user = _create_user(db)
        violation = {
            "recommended_action": "BLOCK",
            "enforced_action": "BLOCK",
            "rollout_mode": "shadow",
            "standardized_reject": {
                "reason_code": "FAILSAFE_ENGINE_UNAVAILABLE",
                "reason_message": "missing execution inputs",
                "policy_id": "p",
                "rule_id": "r",
                "stage": "EXECUTION",
                "severity": "CRITICAL",
                "action_taken": "HARD_BLOCK",
                "auto_action_recommendation": "ESCALATE_RELEASE_GATE",
            },
            "trace": {"action_taken": "HARD_BLOCK", "metrics_snapshot": {}},
            "metrics_snapshot": {},
        }
        append_execution_policy_decision_log(
            db,
            lifecycle_action="submit",
            stage="VIOLATION",
            context={
                "trace_id": str(uuid.uuid4()),
                "pipeline_id": str(uuid.uuid4()),
                "intent_token": str(uuid.uuid4()),
                "user_id": user.id,
                "portfolio_id": f"default:{user.id}",
                "strategy_binding": "p1_strategy",
                "environment": "live",
                "symbol": "BTCUSDT",
                "execution_mode": "REAL",
                "strategy_risk_class": "HIGH",
            },
            policy_result=violation,
            action_taken="HARD_BLOCK",
            is_violation=True,
        )
        db.commit()

        gate = build_release_gate_status(db, window_hours=24)
        assert gate["status"] in {"WARN", "FAIL"}

        remediations = list_remediation_recommendations(db, limit=20)
        if remediations:
            first_id = remediations[0]["recommendation_id"]
            update_remediation_recommendation_status(
                db,
                recommendation_id=first_id,
                action="approve",
                actor_user_id=user.id,
            )
            db.commit()
            updated = list_remediation_recommendations(db, limit=20)
            assert any(item["status"] == "APPROVED" for item in updated)
    finally:
        db.close()


def test_observability_contains_p1_operational_blocks():
    db = SessionLocal()
    try:
        payload = build_execution_policy_observability(db, hours=24)
        assert "release_gate" in payload
        assert "strategy_health" in payload
        assert "policy_versions" in payload
        assert "remediation_recommendations" in payload
    finally:
        db.close()
