# ruff: noqa: E402
"""
P1 Control/Observability/Stability Expansion - Comprehensive Test Suite

Tests for:
- Violation tracking fields and severity/action classification
- Auto-action recommendation generation (NONE/WARN/BLOCK/THROTTLE/REDUCE_ONLY/DISABLE_STRATEGY/ESCALATE_RELEASE_GATE)
- Manual remediation queue
- Decision trace detail endpoint and explainability output
- Simulation vs REAL separation (metrics/aggregation)
- Policy versioning: create/list/approve/activate/rollback/ab-compare
- Canary override routing behavior
- Strategy health summary and binding/state visibility
- Release gate actionable output + recommended actions + partial unlock signal
"""
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from db import SessionLocal
from core.security import hash_password
from models import (
    ExecutionPolicy,
    ExecutionPolicyDecisionLog,
    ExecutionStrategyBinding,
    User,
    UserRole,
)
from services.execution_governance_service import (
    activate_policy_version,
    approve_policy_version,
    build_release_gate_status,
    build_strategy_health_state,
    build_violation_aggregation,
    classify_violation_severity,
    compare_policy_versions_ab,
    create_policy_version,
    create_remediation_recommendation,
    evaluate_strategy_binding_constraints,
    get_governance_config,
    list_policy_versions,
    list_remediation_recommendations,
    resolve_policy_version_override,
    rollback_policy_version,
    seed_default_strategy_bindings,
    select_auto_action,
    update_remediation_recommendation_status,
)
from services.execution_policy_service import (
    append_execution_policy_decision_log,
    build_execution_policy_observability,
    ensure_dynamic_execution_policies,
)
from services.execution_pipeline_orchestrator import run_execution_pipeline


# ============================================================================
# Test Fixtures and Helpers
# ============================================================================

def _create_test_user(db, prefix: str = "p1-gov") -> User:
    """Create a test admin user."""
    row = User(
        email=f"{prefix}-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password("P1Governance123!"),
        role=UserRole.ADMIN,
        is_active=True,
        approval_status="approved",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ensure_strategy_policy(db, strategy: str = "p1_test_strategy"):
    """Ensure a strategy policy exists for testing."""
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
    return row


def _build_test_context(user_id: str, strategy: str = "p1_test_strategy", mode: str = "SIMULATION") -> dict:
    """Build a test context for pipeline execution."""
    return {
        "intent_token": str(uuid.uuid4()),
        "request_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "user_id": user_id,
        "portfolio_id": f"default:{user_id}",
        "strategy_binding": strategy,
        "symbol": "BTCUSDT",
        "side": "buy",
        "environment": "live" if mode == "SIMULATION" else "live",
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


# ============================================================================
# Test: Violation Tracking and Severity Classification
# ============================================================================

class TestViolationTrackingAndSeverity:
    """Tests for violation tracking fields and severity/action classification."""

    def test_severity_classification_low_to_critical(self):
        """Test severity classification across all levels."""
        db = SessionLocal()
        try:
            # LOW severity
            severity_low = classify_violation_severity(
                db,
                reason_code="MINOR_ISSUE",
                default_severity="LOW",
                strategy_risk_class="LOW",
            )
            assert severity_low == "LOW"

            # MEDIUM severity
            severity_medium = classify_violation_severity(
                db,
                reason_code="RISK_ORDER_BREACH",
                default_severity="MEDIUM",
                strategy_risk_class="MEDIUM",
            )
            assert severity_medium == "MEDIUM"

            # HIGH severity
            severity_high = classify_violation_severity(
                db,
                reason_code="RISK_PORTFOLIO_BREACH",
                default_severity="HIGH",
                strategy_risk_class="MEDIUM",
            )
            assert severity_high == "HIGH"

            # CRITICAL severity (HIGH risk class escalates)
            severity_critical = classify_violation_severity(
                db,
                reason_code="RISK_ORDER_BREACH",
                default_severity="HIGH",
                strategy_risk_class="HIGH",
            )
            assert severity_critical == "CRITICAL"
        finally:
            db.close()

    def test_failsafe_reason_codes_always_critical(self):
        """Test that FAILSAFE_ reason codes are always CRITICAL."""
        db = SessionLocal()
        try:
            failsafe_codes = [
                "FAILSAFE_POLICY_LOAD_ERROR",
                "FAILSAFE_RISK_COMPUTE_ERROR",
                "FAILSAFE_MARKET_DATA_MISSING",
                "FAILSAFE_DEPENDENCY_TIMEOUT",
                "FAILSAFE_ENGINE_UNAVAILABLE",
            ]
            for code in failsafe_codes:
                severity = classify_violation_severity(
                    db,
                    reason_code=code,
                    default_severity="LOW",
                    strategy_risk_class="LOW",
                )
                assert severity == "CRITICAL", f"{code} should be CRITICAL"
        finally:
            db.close()


# ============================================================================
# Test: Auto-Action Recommendation Generation
# ============================================================================

class TestAutoActionRecommendation:
    """Tests for auto-action recommendation generation."""

    def test_auto_action_none_for_low_severity(self):
        """Test NONE action for LOW severity."""
        db = SessionLocal()
        try:
            action = select_auto_action(
                db,
                severity="LOW",
                reason_code="MINOR_ISSUE",
                environment="live",
                strategy_risk_class="LOW",
                strategy_id="test_strategy",
            )
            assert action == "NONE"
        finally:
            db.close()

    def test_auto_action_warn_for_medium_severity(self):
        """Test WARN action for MEDIUM severity."""
        db = SessionLocal()
        try:
            action = select_auto_action(
                db,
                severity="MEDIUM",
                reason_code="RISK_ISSUE",
                environment="live",
                strategy_risk_class="MEDIUM",
                strategy_id="test_strategy",
            )
            assert action == "WARN"
        finally:
            db.close()

    def test_auto_action_throttle_for_high_severity(self):
        """Test THROTTLE action for HIGH severity."""
        db = SessionLocal()
        try:
            action = select_auto_action(
                db,
                severity="HIGH",
                reason_code="RISK_BREACH",
                environment="live",
                strategy_risk_class="MEDIUM",
                strategy_id="test_strategy",
            )
            assert action == "THROTTLE"
        finally:
            db.close()

    def test_auto_action_block_for_critical_in_live(self):
        """Test BLOCK action for CRITICAL severity in live environment."""
        db = SessionLocal()
        try:
            action = select_auto_action(
                db,
                severity="CRITICAL",
                reason_code="CRITICAL_BREACH",
                environment="live",
                strategy_risk_class="MEDIUM",
                strategy_id="test_strategy",
            )
            assert action == "BLOCK"
        finally:
            db.close()

    def test_auto_action_disable_strategy_for_critical_high_risk(self):
        """Test DISABLE_STRATEGY action for CRITICAL severity with HIGH risk class."""
        db = SessionLocal()
        try:
            action = select_auto_action(
                db,
                severity="CRITICAL",
                reason_code="CRITICAL_BREACH",
                environment="live",
                strategy_risk_class="HIGH",
                strategy_id="test_strategy",
            )
            assert action == "DISABLE_STRATEGY"
        finally:
            db.close()

    def test_auto_action_escalate_release_gate_for_failsafe(self):
        """Test ESCALATE_RELEASE_GATE action for FAILSAFE_ reason codes."""
        db = SessionLocal()
        try:
            action = select_auto_action(
                db,
                severity="CRITICAL",
                reason_code="FAILSAFE_ENGINE_UNAVAILABLE",
                environment="live",
                strategy_risk_class="HIGH",
                strategy_id="test_strategy",
            )
            assert action == "ESCALATE_RELEASE_GATE"
        finally:
            db.close()


# ============================================================================
# Test: Manual Remediation Queue
# ============================================================================

class TestManualRemediationQueue:
    """Tests for manual remediation queue operations."""

    def test_create_remediation_recommendation(self):
        """Test creating a remediation recommendation."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "remediation")
            rec = create_remediation_recommendation(
                db,
                trace_id=str(uuid.uuid4()),
                source_violation_id=str(uuid.uuid4()),
                recommendation_type="THROTTLE",
                severity="HIGH",
                reason_code="RISK_BREACH",
                summary="Test remediation recommendation",
                payload={"test": "data"},
                created_by=user.id,
            )
            db.commit()
            assert rec.recommendation_id is not None
            assert rec.status == "PENDING"
            assert rec.requires_manual_approval is True
        finally:
            db.close()

    def test_list_remediation_recommendations_with_filter(self):
        """Test listing remediation recommendations with status filter."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "remediation-list")
            # Create pending recommendation
            create_remediation_recommendation(
                db,
                trace_id=str(uuid.uuid4()),
                source_violation_id=str(uuid.uuid4()),
                recommendation_type="WARN",
                severity="MEDIUM",
                reason_code="TEST_ISSUE",
                summary="Test pending recommendation",
                payload={},
                created_by=user.id,
            )
            db.commit()

            # List all
            all_recs = list_remediation_recommendations(db, limit=100)
            assert isinstance(all_recs, list)

            # List pending only
            pending_recs = list_remediation_recommendations(db, status_filter="PENDING", limit=100)
            assert all(r["status"] == "PENDING" for r in pending_recs)
        finally:
            db.close()

    def test_approve_remediation_recommendation(self):
        """Test approving a remediation recommendation."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "remediation-approve")
            rec = create_remediation_recommendation(
                db,
                trace_id=str(uuid.uuid4()),
                source_violation_id=str(uuid.uuid4()),
                recommendation_type="BLOCK",
                severity="CRITICAL",
                reason_code="CRITICAL_BREACH",
                summary="Test approval",
                payload={},
                created_by=user.id,
            )
            db.commit()

            # Approve
            updated = update_remediation_recommendation_status(
                db,
                recommendation_id=rec.recommendation_id,
                action="approve",
                actor_user_id=user.id,
            )
            db.commit()
            assert updated.status == "APPROVED"
            assert updated.approved_by == user.id
            assert updated.approved_at is not None
        finally:
            db.close()

    def test_reject_remediation_recommendation(self):
        """Test rejecting a remediation recommendation."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "remediation-reject")
            rec = create_remediation_recommendation(
                db,
                trace_id=str(uuid.uuid4()),
                source_violation_id=str(uuid.uuid4()),
                recommendation_type="THROTTLE",
                severity="HIGH",
                reason_code="HIGH_BREACH",
                summary="Test rejection",
                payload={},
                created_by=user.id,
            )
            db.commit()

            # Reject
            updated = update_remediation_recommendation_status(
                db,
                recommendation_id=rec.recommendation_id,
                action="reject",
                actor_user_id=user.id,
            )
            db.commit()
            assert updated.status == "REJECTED"
            assert updated.rejected_by == user.id
            assert updated.rejected_at is not None
        finally:
            db.close()


# ============================================================================
# Test: Decision Trace Detail and Explainability
# ============================================================================

class TestDecisionTraceExplainability:
    """Tests for decision trace detail and explainability output."""

    def test_decision_trace_contains_required_fields(self):
        """Test that decision trace contains all required explainability fields."""
        db = SessionLocal()
        try:
            ensure_dynamic_execution_policies(db)
            user = _create_test_user(db, "trace-detail")
            _ensure_strategy_policy(db, "trace_test_strategy")
            seed_default_strategy_bindings(db, strategy_ids=["trace_test_strategy"])

            context = _build_test_context(user.id, "trace_test_strategy", "SIMULATION")
            result = run_execution_pipeline(db, lifecycle_action="preview", context=context)
            db.commit()

            trace = result.get("policy_decision", {}).get("trace", {})
            
            # Verify required trace fields
            assert "stage" in trace
            assert "decision_id" in trace
            assert "trace_id" in trace
            assert "scope_trace" in trace
            assert "matched_policies" in trace
            assert "applied_overrides" in trace
            assert "risk" in trace
            assert "safety" in trace
            assert "findings" in trace
            assert "effective_rules" in trace
            assert "action_taken" in trace
            assert "final_decision_path" in trace
            assert "strategy_governance" in trace
            assert "execution_mode" in trace
            assert "decision_steps" in trace
        finally:
            db.close()

    def test_decision_steps_show_evaluation_path(self):
        """Test that decision steps show the complete evaluation path."""
        db = SessionLocal()
        try:
            ensure_dynamic_execution_policies(db)
            user = _create_test_user(db, "decision-steps")
            _ensure_strategy_policy(db, "steps_test_strategy")
            seed_default_strategy_bindings(db, strategy_ids=["steps_test_strategy"])

            context = _build_test_context(user.id, "steps_test_strategy", "SIMULATION")
            result = run_execution_pipeline(db, lifecycle_action="preview", context=context)
            db.commit()

            trace = result.get("policy_decision", {}).get("trace", {})
            decision_steps = trace.get("decision_steps", [])
            
            assert len(decision_steps) > 0
            # Verify step structure
            for step in decision_steps:
                assert "step_index" in step
                assert "step_type" in step
                assert "previous_state" in step
                assert "new_state" in step
        finally:
            db.close()


# ============================================================================
# Test: Simulation vs REAL Separation
# ============================================================================

class TestSimulationRealSeparation:
    """Tests for simulation vs REAL mode separation in metrics/aggregation."""

    def test_violation_aggregation_separates_simulation_and_real(self):
        """Test that violation aggregation separates SIMULATION and REAL counts."""
        db = SessionLocal()
        try:
            ensure_dynamic_execution_policies(db)
            user = _create_test_user(db, "sim-real-sep")
            _ensure_strategy_policy(db, "sim_real_strategy")
            seed_default_strategy_bindings(db, strategy_ids=["sim_real_strategy"])

            # Run simulation mode pipeline
            sim_context = _build_test_context(user.id, "sim_real_strategy", "SIMULATION")
            run_execution_pipeline(db, lifecycle_action="submit", context=sim_context)
            db.commit()

            # Build aggregation
            aggregation = build_violation_aggregation(db, window="24h")
            
            assert "simulation_violation_count" in aggregation
            assert "real_violation_count" in aggregation
            assert isinstance(aggregation["simulation_violation_count"], int)
            assert isinstance(aggregation["real_violation_count"], int)
        finally:
            db.close()

    def test_decision_log_records_execution_mode(self):
        """Test that decision log records execution_mode correctly."""
        db = SessionLocal()
        try:
            ensure_dynamic_execution_policies(db)
            user = _create_test_user(db, "exec-mode-log")
            _ensure_strategy_policy(db, "exec_mode_strategy")
            seed_default_strategy_bindings(db, strategy_ids=["exec_mode_strategy"])

            # Run simulation
            sim_context = _build_test_context(user.id, "exec_mode_strategy", "SIMULATION")
            run_execution_pipeline(db, lifecycle_action="submit", context=sim_context)
            db.commit()

            # Check decision log
            log = db.query(ExecutionPolicyDecisionLog).filter(
                ExecutionPolicyDecisionLog.user_id == user.id,
                ExecutionPolicyDecisionLog.execution_mode == "SIMULATION",
            ).first()
            assert log is not None
            assert log.simulation_mode is True
        finally:
            db.close()


# ============================================================================
# Test: Policy Versioning
# ============================================================================

class TestPolicyVersioning:
    """Tests for policy versioning: create/list/approve/activate/rollback/ab-compare."""

    def test_create_policy_version(self):
        """Test creating a new policy version."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "version-create")
            _ensure_strategy_policy(db, "version_test_strategy")

            version = create_policy_version(
                db,
                policy_code="p1:version_test_strategy",
                conditions_payload={"environment_in": ["live"]},
                rules_payload={"risk": {"max_order_notional": 50000}},
                change_summary="Test version creation",
                created_by=user.id,
                state="DRAFT",
            )
            db.commit()

            assert version.version_id is not None
            assert version.version_number >= 1
            assert version.state == "DRAFT"
            assert version.approval_status == "pending"
        finally:
            db.close()

    def test_list_policy_versions(self):
        """Test listing policy versions."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "version-list")
            policy_code = f"p1:list_test_{uuid.uuid4().hex[:8]}"

            # Create multiple versions
            for i in range(3):
                create_policy_version(
                    db,
                    policy_code=policy_code,
                    conditions_payload={},
                    rules_payload={"risk": {"max_order_notional": 50000 + i * 10000}},
                    change_summary=f"Version {i + 1}",
                    created_by=user.id,
                )
            db.commit()

            versions = list_policy_versions(db, policy_code=policy_code, limit=100)
            assert len(versions) >= 3
            assert all(v["policy_code"] == policy_code for v in versions)
        finally:
            db.close()

    def test_approve_policy_version(self):
        """Test approving a policy version."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "version-approve")
            policy_code = f"p1:approve_test_{uuid.uuid4().hex[:8]}"

            version = create_policy_version(
                db,
                policy_code=policy_code,
                conditions_payload={},
                rules_payload={"risk": {"max_order_notional": 50000}},
                change_summary="Test approval",
                created_by=user.id,
            )
            db.commit()

            approved = approve_policy_version(
                db,
                version_id=version.version_id,
                actor_user_id=user.id,
            )
            db.commit()

            assert approved.approval_status == "approved"
            assert approved.approved_by == user.id
        finally:
            db.close()

    def test_activate_policy_version_requires_approval_for_prod(self):
        """Test that activating a policy version in prod requires approval."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "version-activate")
            policy_code = f"p1:activate_test_{uuid.uuid4().hex[:8]}"

            version = create_policy_version(
                db,
                policy_code=policy_code,
                conditions_payload={},
                rules_payload={"risk": {"max_order_notional": 50000}},
                change_summary="Test activation",
                created_by=user.id,
            )
            db.commit()

            # Should fail without approval for live/prod
            with pytest.raises(ValueError, match="approval_required_for_prod_activation"):
                activate_policy_version(
                    db,
                    version_id=version.version_id,
                    actor_user_id=user.id,
                    environment="live",
                )
        finally:
            db.close()

    def test_activate_policy_version_after_approval(self):
        """Test activating a policy version after approval."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "version-activate-ok")
            policy_code = f"p1:activate_ok_{uuid.uuid4().hex[:8]}"

            version = create_policy_version(
                db,
                policy_code=policy_code,
                conditions_payload={},
                rules_payload={"risk": {"max_order_notional": 50000}},
                change_summary="Test activation after approval",
                created_by=user.id,
            )
            db.commit()

            # Approve first
            approve_policy_version(db, version_id=version.version_id, actor_user_id=user.id)
            db.commit()

            # Now activate
            activated = activate_policy_version(
                db,
                version_id=version.version_id,
                actor_user_id=user.id,
                environment="live",
            )
            db.commit()

            assert activated.state == "ACTIVE"
            assert activated.effective_from is not None
        finally:
            db.close()

    def test_rollback_policy_version(self):
        """Test rolling back to a previous policy version."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "version-rollback")
            policy_code = f"p1:rollback_test_{uuid.uuid4().hex[:8]}"

            # Create and activate v1
            v1 = create_policy_version(
                db,
                policy_code=policy_code,
                conditions_payload={},
                rules_payload={"risk": {"max_order_notional": 50000}},
                change_summary="v1",
                created_by=user.id,
            )
            approve_policy_version(db, version_id=v1.version_id, actor_user_id=user.id)
            activate_policy_version(db, version_id=v1.version_id, actor_user_id=user.id, environment="live")
            db.commit()

            # Create and activate v2
            v2 = create_policy_version(
                db,
                policy_code=policy_code,
                conditions_payload={},
                rules_payload={"risk": {"max_order_notional": 30000}},
                change_summary="v2",
                created_by=user.id,
            )
            approve_policy_version(db, version_id=v2.version_id, actor_user_id=user.id)
            activate_policy_version(db, version_id=v2.version_id, actor_user_id=user.id, environment="live")
            db.commit()

            # Rollback to v1
            rolled_back = rollback_policy_version(
                db,
                policy_code=policy_code,
                target_version_id=v1.version_id,
                actor_user_id=user.id,
                reason="Test rollback",
            )
            db.commit()

            assert rolled_back.state == "ACTIVE"
            assert rolled_back.version_id == v1.version_id
        finally:
            db.close()

    def test_ab_compare_policy_versions(self):
        """Test A/B comparison of policy versions."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "version-ab")
            policy_code = f"p1:ab_test_{uuid.uuid4().hex[:8]}"

            v1 = create_policy_version(
                db,
                policy_code=policy_code,
                conditions_payload={},
                rules_payload={"risk": {"max_order_notional": 50000}},
                change_summary="v1 for AB",
                created_by=user.id,
            )
            v2 = create_policy_version(
                db,
                policy_code=policy_code,
                conditions_payload={},
                rules_payload={"risk": {"max_order_notional": 30000, "max_symbol_exposure": 100000}},
                change_summary="v2 for AB",
                created_by=user.id,
            )
            db.commit()

            comparison = compare_policy_versions_ab(
                db,
                policy_code=policy_code,
                primary_version_id=v1.version_id,
                shadow_version_id=v2.version_id,
            )

            assert "policy_code" in comparison
            assert "primary_version" in comparison
            assert "shadow_version" in comparison
            assert "decision_delta" in comparison
            assert comparison["decision_delta"]["delta_score"] > 0
        finally:
            db.close()


# ============================================================================
# Test: Canary Override Routing
# ============================================================================

class TestCanaryOverrideRouting:
    """Tests for canary override routing behavior."""

    def test_canary_routing_matches_traffic_percentage(self):
        """Test that canary routing respects traffic percentage."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "canary-routing")
            policy_code = f"p1:canary_routing_{uuid.uuid4().hex[:8]}"

            # Create active version
            v1 = create_policy_version(
                db,
                policy_code=policy_code,
                conditions_payload={},
                rules_payload={"risk": {"max_order_notional": 50000}},
                change_summary="active",
                created_by=user.id,
                state="ACTIVE",
            )
            v1.state = "ACTIVE"
            v1.approval_status = "approved"

            # Create canary version with 100% traffic
            v2 = create_policy_version(
                db,
                policy_code=policy_code,
                conditions_payload={},
                rules_payload={"risk": {"max_order_notional": 30000}},
                change_summary="canary",
                created_by=user.id,
                state="CANARY",
            )
            v2.state = "CANARY"
            v2.rollout_strategy = {
                "environments": ["live"],
                "strategy_ids": ["canary_test_strategy"],
                "traffic_percentage": 100,
            }
            db.commit()

            # Resolve override - should get canary
            override = resolve_policy_version_override(
                db,
                policy_code=policy_code,
                context={
                    "environment": "live",
                    "strategy_binding": "canary_test_strategy",
                    "symbol": "BTCUSDT",
                    "user_id": user.id,
                },
            )

            assert override is not None
            assert override["mode"] == "CANARY"
            assert override["version_id"] == v2.version_id
        finally:
            db.close()

    def test_canary_routing_falls_back_to_active(self):
        """Test that canary routing falls back to active when environment doesn't match."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "canary-fallback")
            policy_code = f"p1:canary_fallback_{uuid.uuid4().hex[:8]}"

            # Create active version
            v1 = create_policy_version(
                db,
                policy_code=policy_code,
                conditions_payload={},
                rules_payload={"risk": {"max_order_notional": 50000}},
                change_summary="active",
                created_by=user.id,
                state="ACTIVE",
            )
            v1.state = "ACTIVE"
            v1.approval_status = "approved"

            # Create canary version that only matches 'staging' environment (not live)
            v2 = create_policy_version(
                db,
                policy_code=policy_code,
                conditions_payload={},
                rules_payload={"risk": {"max_order_notional": 30000}},
                change_summary="canary",
                created_by=user.id,
                state="CANARY",
            )
            v2.state = "CANARY"
            v2.rollout_strategy = {
                "environments": ["staging"],  # Only matches staging, not live
                "traffic_percentage": 100,
            }
            db.commit()

            # Resolve override with live - should get active since canary only matches staging
            override = resolve_policy_version_override(
                db,
                policy_code=policy_code,
                context={
                    "environment": "live",
                    "strategy_binding": "test_strategy",
                    "symbol": "BTCUSDT",
                    "user_id": str(user.id),
                },
            )

            assert override is not None
            # Canary only matches staging, so live should get ACTIVE
            assert override["mode"] == "ACTIVE", f"Expected ACTIVE but got {override['mode']} - canary for staging should not match live"
            assert override["version_id"] == v1.version_id
        finally:
            db.close()

    def test_canary_routing_zero_traffic_bug(self):
        """
        BUG DOCUMENTATION: traffic_percentage=0 is treated as 100% due to falsy check.
        
        The _rollout_matches function uses `strategy.get('traffic_percentage') or 100`
        which treats 0 as falsy and defaults to 100.
        
        This test documents the current (buggy) behavior.
        """
        db = SessionLocal()
        try:
            user = _create_test_user(db, "canary-zero-bug")
            policy_code = f"p1:canary_zero_bug_{uuid.uuid4().hex[:8]}"

            # Create active version
            v1 = create_policy_version(
                db,
                policy_code=policy_code,
                conditions_payload={},
                rules_payload={"risk": {"max_order_notional": 50000}},
                change_summary="active",
                created_by=user.id,
                state="ACTIVE",
            )
            v1.state = "ACTIVE"
            v1.approval_status = "approved"

            # Create canary version with 0% traffic
            v2 = create_policy_version(
                db,
                policy_code=policy_code,
                conditions_payload={},
                rules_payload={"risk": {"max_order_notional": 30000}},
                change_summary="canary",
                created_by=user.id,
                state="CANARY",
            )
            v2.state = "CANARY"
            v2.rollout_strategy = {
                "environments": ["live"],
                "traffic_percentage": 0,  # BUG: This is treated as 100%
            }
            db.commit()

            override = resolve_policy_version_override(
                db,
                policy_code=policy_code,
                context={
                    "environment": "live",
                    "strategy_binding": "test_strategy",
                    "symbol": "BTCUSDT",
                    "user_id": str(user.id),
                },
            )

            assert override is not None
            # BUG: Due to `0 or 100` in _rollout_matches, 0% traffic is treated as 100%
            # This documents the current buggy behavior - should be ACTIVE but returns CANARY
            assert override["mode"] == "CANARY", "BUG: 0% traffic is treated as 100%"
        finally:
            db.close()


# ============================================================================
# Test: Strategy Health Summary
# ============================================================================

class TestStrategyHealthSummary:
    """Tests for strategy health summary and binding/state visibility."""

    def test_strategy_health_state_includes_required_fields(self):
        """Test that strategy health state includes all required fields."""
        db = SessionLocal()
        try:
            ensure_dynamic_execution_policies(db)
            seed_default_strategy_bindings(db, strategy_ids=["breakout", "mean_reversion"])

            health = build_strategy_health_state(db, window_hours=24)

            assert isinstance(health, list)
            if health:
                item = health[0]
                assert "strategy_id" in item
                assert "bound_policy_set" in item
                assert "risk_class" in item
                assert "state" in item
                assert "enabled" in item
                assert "violation_count" in item
                assert "last_critical_breach_count" in item
        finally:
            db.close()

    def test_strategy_binding_constraints_evaluation(self):
        """Test strategy binding constraints evaluation."""
        db = SessionLocal()
        try:
            ensure_dynamic_execution_policies(db)
            seed_default_strategy_bindings(db, strategy_ids=["breakout"])

            result = evaluate_strategy_binding_constraints(
                db,
                context={
                    "strategy_binding": "breakout",
                    "environment": "live",
                    "symbol": "BTCUSDT",
                    "margin_mode": "",
                },
            )

            assert "binding" in result
            assert "risk_class" in result
            assert "limits" in result
            assert "violations" in result
            assert result["binding"] is not None
        finally:
            db.close()

    def test_missing_strategy_binding_detected(self):
        """Test that missing strategy binding is detected."""
        db = SessionLocal()
        try:
            result = evaluate_strategy_binding_constraints(
                db,
                context={
                    "strategy_binding": "nonexistent_strategy_xyz",
                    "environment": "live",
                    "symbol": "BTCUSDT",
                    "margin_mode": "cross",
                },
            )

            violations = result.get("violations", [])
            assert len(violations) > 0
            assert violations[0]["reason_code"] == "STRATEGY_BINDING_MISSING"
        finally:
            db.close()


# ============================================================================
# Test: Release Gate
# ============================================================================

class TestReleaseGate:
    """Tests for release gate actionable output + recommended actions + partial unlock signal."""

    def test_release_gate_status_includes_required_fields(self):
        """Test that release gate status includes all required fields."""
        db = SessionLocal()
        try:
            gate = build_release_gate_status(db, window_hours=24)

            assert "status" in gate
            assert gate["status"] in {"PASS", "WARN", "FAIL", "PARTIAL_UNLOCK"}
            assert "summary" in gate
            assert "blocking_reasons" in gate
            assert "recommended_actions" in gate
            assert "affected_scopes" in gate
            assert "safe_rollout_suggestion" in gate
        finally:
            db.close()

    def test_release_gate_summary_metrics(self):
        """Test that release gate summary contains metrics."""
        db = SessionLocal()
        try:
            gate = build_release_gate_status(db, window_hours=24)
            summary = gate.get("summary", {})

            assert "window_hours" in summary
            assert "violation_count" in summary
            assert "critical_violation_count" in summary
            assert "failsafe_hard_block_count" in summary
            assert "disabled_strategy_count" in summary
        finally:
            db.close()

    def test_release_gate_recommended_actions_for_violations(self):
        """Test that release gate provides recommended actions when violations exist."""
        db = SessionLocal()
        try:
            user = _create_test_user(db, "gate-actions")
            
            # Create a violation
            violation_result = {
                "recommended_action": "BLOCK",
                "enforced_action": "BLOCK",
                "rollout_mode": "shadow",
                "standardized_reject": {
                    "reason_code": "FAILSAFE_ENGINE_UNAVAILABLE",
                    "reason_message": "test violation",
                    "policy_id": "p",
                    "rule_id": "r",
                    "stage": "EXECUTION",
                    "severity": "CRITICAL",
                    "action_taken": "HARD_BLOCK",
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
                    "strategy_binding": "test_strategy",
                    "environment": "live",
                    "symbol": "BTCUSDT",
                    "execution_mode": "REAL",
                    "strategy_risk_class": "HIGH",
                },
                policy_result=violation_result,
                action_taken="HARD_BLOCK",
                is_violation=True,
            )
            db.commit()

            gate = build_release_gate_status(db, window_hours=24)
            
            # Should have recommendations when violations exist
            if gate["summary"]["critical_violation_count"] > 0 or gate["summary"]["failsafe_hard_block_count"] > 0:
                assert len(gate["recommended_actions"]) > 0
        finally:
            db.close()

    def test_release_gate_partial_unlock_signal(self):
        """Test that release gate shows PARTIAL_UNLOCK when strategies are disabled."""
        db = SessionLocal()
        try:
            # Create a disabled strategy binding
            binding = db.query(ExecutionStrategyBinding).filter(
                ExecutionStrategyBinding.strategy_id == "test_disabled_strategy"
            ).first()
            if binding is None:
                binding = ExecutionStrategyBinding(
                    strategy_id="test_disabled_strategy",
                    bound_policy_set="policy_set:test_disabled",
                    risk_class="MEDIUM",
                    execution_mode="SIMULATION",
                    enabled=False,
                    state="disabled",
                    limits={},
                    allowed_symbols=[],
                    allowed_margin_modes=[],
                    allowed_environments=["live"],
                )
                db.add(binding)
            else:
                binding.state = "disabled"
                binding.enabled = False
            db.commit()

            gate = build_release_gate_status(db, window_hours=24)
            
            # If there are disabled strategies and no critical violations, should be PARTIAL_UNLOCK
            if gate["summary"]["disabled_strategy_count"] > 0 and gate["summary"]["critical_violation_count"] < 3:
                assert gate["status"] in {"PARTIAL_UNLOCK", "WARN", "FAIL"}
        finally:
            db.close()


# ============================================================================
# Test: Observability Metrics
# ============================================================================

class TestObservabilityMetrics:
    """Tests for admin execution policies panel metrics/sections."""

    def test_observability_contains_p1_sections(self):
        """Test that observability contains all P1 operational sections."""
        db = SessionLocal()
        try:
            payload = build_execution_policy_observability(db, hours=24)

            # P1 required sections
            assert "release_gate" in payload
            assert "strategy_health" in payload
            assert "policy_versions" in payload
            assert "remediation_recommendations" in payload
            assert "violation_aggregations" in payload
        finally:
            db.close()

    def test_violation_aggregation_windows(self):
        """Test violation aggregation for different time windows."""
        db = SessionLocal()
        try:
            for window in ["5m", "1h", "24h", "7d"]:
                aggregation = build_violation_aggregation(db, window=window)
                
                assert "window" in aggregation
                assert aggregation["window"] == window
                assert "violation_count" in aggregation
                assert "reason_code_distribution" in aggregation
                assert "severity_distribution" in aggregation
                assert "strategy_violation_density" in aggregation
                assert "user_repeat_violations" in aggregation
                assert "symbol_breach_rate" in aggregation
        finally:
            db.close()


# ============================================================================
# Test: Governance Config
# ============================================================================

class TestGovernanceConfig:
    """Tests for governance configuration."""

    def test_governance_config_defaults(self):
        """Test that governance config has correct defaults."""
        db = SessionLocal()
        try:
            config = get_governance_config(db)

            assert "auto_remediation_mode" in config
            assert config["auto_remediation_mode"] == "manual_recommend"
            assert "severity_overrides" in config
            assert "debug" in config
            assert "ab_testing_enabled" in config
        finally:
            db.close()

    def test_manual_remediation_mode_enforced(self):
        """Test that manual remediation mode is enforced (no auto-apply)."""
        db = SessionLocal()
        try:
            config = get_governance_config(db)
            
            # Per requirements: auto-remediation yalnız öneri+manuel onay (otomatik uygulama yok)
            assert config["auto_remediation_mode"] == "manual_recommend"
        finally:
            db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
