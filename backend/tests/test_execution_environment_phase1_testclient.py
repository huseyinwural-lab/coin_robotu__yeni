# ruff: noqa: E402
"""
P2 Phase-1 Backend Tests using TestClient:
- Environment-aware evaluation (DEV/STAGING/PROD normalization)
- Environment override deterministic application
- Safe mode auto trigger on thresholds and enforcement override
- Safe mode active/inactive visibility in admin endpoint
- New admin endpoints: environment-overrides CRUD-lite, safe-mode list/deactivate
- Trace contains environment override and safe mode details
"""
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from server import app
from db import SessionLocal
from core.security import hash_password
from models import User, UserRole


@pytest.fixture(scope="module")
def client():
    """Create TestClient"""
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(client):
    """Get admin token"""
    # Try login with existing admin
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
    )
    if login_resp.status_code == 200:
        return login_resp.json().get("access_token")
    
    # Create admin if not exists
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "canary.admin@platform.local").first()
        if not user:
            user = User(
                email="canary.admin@platform.local",
                password_hash=hash_password("CanaryAdmin123!"),
                role=UserRole.SUPER_ADMIN,
                is_active=True,
                approval_status="approved",
            )
            db.add(user)
            db.commit()
        
        login_resp = client.post(
            "/api/auth/login",
            json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        return login_resp.json().get("access_token")
    finally:
        db.close()


@pytest.fixture
def admin_headers(admin_token):
    """Get admin headers"""
    return {"Authorization": f"Bearer {admin_token}"}


# ========== Environment Normalization Tests ==========
class TestEnvironmentNormalization:
    """Test environment normalization"""

    def test_dev_variants(self):
        """Test DEV environment variants"""
        from services.execution_environment_control_service import normalize_environment

        assert normalize_environment("dev") == "DEV"
        assert normalize_environment("development") == "DEV"
        assert normalize_environment("live") == "DEV"
        assert normalize_environment("DEV") == "DEV"

    def test_staging_variants(self):
        """Test STAGING environment variants"""
        from services.execution_environment_control_service import normalize_environment

        assert normalize_environment("staging") == "STAGING"
        assert normalize_environment("stage") == "STAGING"
        assert normalize_environment("STAGING") == "STAGING"

    def test_prod_variants(self):
        """Test PROD environment variants"""
        from services.execution_environment_control_service import normalize_environment

        assert normalize_environment("prod") == "PROD"
        assert normalize_environment("production") == "PROD"
        assert normalize_environment("live") == "PROD"
        assert normalize_environment("PROD") == "PROD"

    def test_edge_cases(self):
        """Test edge cases"""
        from services.execution_environment_control_service import normalize_environment

        assert normalize_environment(None) == "DEV"
        assert normalize_environment("") == "DEV"
        assert normalize_environment("  ") == "DEV"
        assert normalize_environment("unknown") == "UNKNOWN"


# ========== Environment Overrides CRUD-lite Tests ==========
class TestEnvironmentOverridesAPI:
    """Test environment overrides API endpoints"""

    def test_list_environment_overrides(self, client, admin_headers):
        """Test GET /api/admin/execution-policies/environment-overrides"""
        resp = client.get(
            "/api/admin/execution-policies/environment-overrides",
            headers=admin_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        # Each item should have required fields
        if data:
            item = data[0]
            assert "override_id" in item
            assert "environment" in item
            assert "scope_type" in item
            assert "scope_value" in item
            assert "priority" in item
            assert "is_active" in item
            assert "override_payload" in item

    def test_list_environment_overrides_with_filter(self, client, admin_headers):
        """Test GET /api/admin/execution-policies/environment-overrides?environment=DEV"""
        resp = client.get(
            "/api/admin/execution-policies/environment-overrides",
            params={"environment": "DEV"},
            headers=admin_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        # All items should be for DEV environment
        for item in data:
            assert item.get("environment") == "DEV"

    def test_upsert_environment_override(self, client, admin_headers):
        """Test POST /api/admin/execution-policies/environment-overrides"""
        unique_scope = f"TEST_strategy_{uuid.uuid4().hex[:8]}"
        payload = {
            "environment": "DEV",
            "scope_type": "STRATEGY",
            "scope_value": unique_scope,
            "priority": 50,
            "override_payload": {
                "set_rules": {
                    "risk.max_order_notional": 1000,
                }
            },
            "change_summary": "Test override for P2 Phase-1",
        }
        resp = client.post(
            "/api/admin/execution-policies/environment-overrides",
            json=payload,
            headers=admin_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "override_id" in data
        assert data.get("environment") == "DEV"
        assert data.get("scope_type") == "STRATEGY"
        assert data.get("scope_value") == unique_scope
        assert data.get("priority") == 50
        assert data.get("is_active") is True

    def test_upsert_environment_override_updates_existing(self, client, admin_headers):
        """Test that upsert updates existing override with same environment/scope"""
        unique_scope = f"TEST_upsert_{uuid.uuid4().hex[:8]}"
        
        # Create first
        payload1 = {
            "environment": "STAGING",
            "scope_type": "GLOBAL",
            "scope_value": unique_scope,
            "priority": 100,
            "override_payload": {"set_rules": {"risk.max_order_notional": 500}},
            "change_summary": "Initial override",
        }
        resp1 = client.post(
            "/api/admin/execution-policies/environment-overrides",
            json=payload1,
            headers=admin_headers,
        )
        assert resp1.status_code == 200
        override_id_1 = resp1.json().get("override_id")

        # Update with same environment/scope_type/scope_value
        payload2 = {
            "environment": "STAGING",
            "scope_type": "GLOBAL",
            "scope_value": unique_scope,
            "priority": 200,  # Changed priority
            "override_payload": {"set_rules": {"risk.max_order_notional": 1000}},
            "change_summary": "Updated override",
        }
        resp2 = client.post(
            "/api/admin/execution-policies/environment-overrides",
            json=payload2,
            headers=admin_headers,
        )
        assert resp2.status_code == 200
        override_id_2 = resp2.json().get("override_id")

        # Should be same override_id (upsert behavior)
        assert override_id_1 == override_id_2
        assert resp2.json().get("priority") == 200


# ========== Safe Mode List/Deactivate Tests ==========
class TestSafeModeAPI:
    """Test safe mode API endpoints"""

    def test_list_safe_mode_states(self, client, admin_headers):
        """Test GET /api/admin/execution-policies/safe-mode"""
        resp = client.get(
            "/api/admin/execution-policies/safe-mode",
            headers=admin_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        # Each item should have required fields
        if data:
            item = data[0]
            assert "safe_mode_id" in item
            assert "environment" in item
            assert "scope_type" in item
            assert "scope_value" in item
            assert "is_active" in item
            assert "trigger_reason" in item
            assert "trigger_source" in item
            assert "activated_at" in item
            assert "override_payload" in item

    def test_list_safe_mode_states_with_environment_filter(self, client, admin_headers):
        """Test GET /api/admin/execution-policies/safe-mode?environment=DEV"""
        resp = client.get(
            "/api/admin/execution-policies/safe-mode",
            params={"environment": "DEV"},
            headers=admin_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        # All items should be for DEV environment
        for item in data:
            assert item.get("environment") == "DEV"

    def test_list_safe_mode_states_active_only_filter(self, client, admin_headers):
        """Test GET /api/admin/execution-policies/safe-mode?active_only=true"""
        resp = client.get(
            "/api/admin/execution-policies/safe-mode",
            params={"active_only": "true"},
            headers=admin_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        # All items should be active
        for item in data:
            assert item.get("is_active") is True

    def test_deactivate_safe_mode_not_found(self, client, admin_headers):
        """Test deactivate with non-existent safe_mode_id returns error"""
        fake_id = f"fake-safe-mode-{uuid.uuid4().hex}"
        resp = client.post(
            f"/api/admin/execution-policies/safe-mode/{fake_id}/deactivate",
            json={"reason": "Test deactivation"},
            headers=admin_headers,
        )
        # Should return 404 with error (ValueError raised)
        assert resp.status_code == 404, f"Expected 404, got: {resp.status_code}"
        assert "safe_mode_not_found" in resp.text


# ========== Admin Visibility Tests ==========
class TestAdminVisibility:
    """Test admin visibility of safe mode and environment overrides"""

    def test_execution_policies_includes_safe_mode_states(self, client, admin_headers):
        """Test GET /api/admin/execution-policies includes safe_mode_states"""
        resp = client.get(
            "/api/admin/execution-policies",
            headers=admin_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Should include safe_mode_states
        assert "safe_mode_states" in data, "safe_mode_states missing from response"
        assert isinstance(data["safe_mode_states"], list)

    def test_execution_policies_includes_environment_overrides(self, client, admin_headers):
        """Test GET /api/admin/execution-policies includes environment_overrides"""
        resp = client.get(
            "/api/admin/execution-policies",
            headers=admin_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "environment_overrides" in data, "environment_overrides missing from response"
        overrides = data["environment_overrides"]
        assert isinstance(overrides, list)
        
        # Each override should have required fields
        if overrides:
            item = overrides[0]
            assert "override_id" in item
            assert "environment" in item
            assert "is_active" in item


# ========== Trace Contains Environment Override and Safe Mode Details ==========
class TestTraceDetails:
    """Test that traces contain environment and safe mode details"""

    def test_policy_evaluation_trace_contains_environment_details(self):
        """Test that policy evaluation trace contains environment override and safe mode details"""
        from services.execution_policy_service import (
            ensure_dynamic_execution_policies,
            evaluate_execution_policy_engine,
        )
        from services.execution_governance_service import seed_default_strategy_bindings

        db = SessionLocal()
        try:
            ensure_dynamic_execution_policies(db)
            
            # Create test user
            user = User(
                email=f"trace-test-{uuid.uuid4().hex[:10]}@example.com",
                password_hash=hash_password("TraceTest123!"),
                role=UserRole.ADMIN,
                is_active=True,
                approval_status="approved",
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            strategy = "trend_following"
            seed_default_strategy_bindings(db, strategy_ids=[strategy])

            # Evaluate policy
            result = evaluate_execution_policy_engine(
                db,
                {
                    "user_id": user.id,
                    "portfolio_id": f"default:{user.id}",
                    "strategy_binding": strategy,
                    "symbol": "BTCUSDT",
                    "environment": "live",
                    "market_type": "spot",
                    "intent_type": "CLOSE_POSITION",
                    "reduce_only": True,
                    "proposed_notional": 100.0,
                    "market_data_available": True,
                },
                stage="PRE_TRADE",
            )

            # Verify trace structure
            trace = result.get("trace", {})
            assert "environment" in trace, "trace.environment missing"
            env_trace = trace["environment"]
            assert "input" in env_trace, "trace.environment.input missing"
            assert "normalized" in env_trace, "trace.environment.normalized missing"
            assert "override_trace" in env_trace, "trace.environment.override_trace missing"
            assert env_trace["normalized"] == "DEV"  # live normalizes to DEV

            # Verify safe_mode in trace
            assert "safe_mode" in trace, "trace.safe_mode missing"
            safe_mode_trace = trace["safe_mode"]
            assert "active" in safe_mode_trace, "trace.safe_mode.active missing"
            assert "scopes" in safe_mode_trace, "trace.safe_mode.scopes missing"

        finally:
            db.close()

    def test_environment_override_applied_in_trace(self):
        """Test that environment overrides are applied and visible in trace"""
        from services.execution_policy_service import (
            ensure_dynamic_execution_policies,
            evaluate_execution_policy_engine,
        )
        from services.execution_environment_control_service import upsert_environment_override
        from services.execution_governance_service import seed_default_strategy_bindings
        from models import ExecutionPolicy

        db = SessionLocal()
        try:
            ensure_dynamic_execution_policies(db)
            
            # Create test user
            user = User(
                email=f"override-trace-{uuid.uuid4().hex[:10]}@example.com",
                password_hash=hash_password("OverrideTrace123!"),
                role=UserRole.ADMIN,
                is_active=True,
                approval_status="approved",
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            strategy = f"TEST_override_trace_{uuid.uuid4().hex[:8]}"
            
            # Create policy for strategy
            policy = ExecutionPolicy(
                strategy_type=strategy,
                execution_style="balanced",
                order_preference="limit_first",
                timeout_seconds=8,
                fallback_behavior="market_fallback",
                partial_fill_tolerance_pct=60,
                execution_urgency="medium",
                retry_limit=1,
                is_active=True,
                policy_code=f"test:{strategy}",
                policy_scope="strategy",
                scope_key=strategy,
                rules_payload={
                    "runtime": {"require_market_data": True},
                    "risk": {
                        "max_order_notional": 100000,
                        "max_symbol_exposure": 500000,
                        "max_strategy_exposure": 500000,
                        "max_user_exposure": 500000,
                        "max_portfolio_exposure": 500000,
                    },
                },
            )
            db.add(policy)
            db.commit()

            seed_default_strategy_bindings(db, strategy_ids=[strategy])

            # Create environment override
            upsert_environment_override(
                db,
                environment="DEV",
                scope_type="STRATEGY",
                scope_value=strategy,
                priority=10,
                override_payload={
                    "set_rules": {
                        "risk.max_order_notional": 50,  # Very low limit
                    }
                },
                actor_user_id=user.id,
                change_summary="Test override for trace verification",
            )
            db.commit()

            # Evaluate policy with notional that exceeds override limit
            result = evaluate_execution_policy_engine(
                db,
                {
                    "user_id": user.id,
                    "portfolio_id": f"default:{user.id}",
                    "strategy_binding": strategy,
                    "symbol": "BTCUSDT",
                    "environment": "live",  # Normalizes to DEV
                    "market_type": "spot",
                    "intent_type": "CLOSE_POSITION",
                    "reduce_only": True,
                    "proposed_notional": 100.0,  # Exceeds 50 limit
                    "market_data_available": True,
                },
                stage="PRE_TRADE",
            )

            # Verify override was applied
            trace = result.get("trace", {})
            env_trace = trace.get("environment", {})
            override_trace = env_trace.get("override_trace", [])
            
            # Should have at least one override applied
            assert len(override_trace) > 0, "No environment overrides in trace"
            
            # Verify the override details
            found_override = False
            for override in override_trace:
                if override.get("scope_value") == strategy:
                    found_override = True
                    assert override.get("environment") == "DEV"
                    assert override.get("scope_type") == "STRATEGY"
                    break
            
            assert found_override, f"Expected override for strategy {strategy} not found in trace"

            # Should be blocked due to low limit
            assert result.get("enforced_action") == "BLOCK"

        finally:
            db.close()


# ========== Safe Mode Auto Activation Tests ==========
class TestSafeModeAutoActivation:
    """Tests for safe mode auto-activation on thresholds"""

    def test_safe_mode_auto_triggers_on_critical_violations(self):
        """Test that safe mode auto-activates when critical violation threshold is exceeded"""
        from services.execution_policy_service import (
            append_execution_policy_decision_log,
            ensure_dynamic_execution_policies,
            evaluate_execution_policy_engine,
        )
        from services.execution_governance_service import seed_default_strategy_bindings
        from models import ExecutionPolicy

        db = SessionLocal()
        try:
            ensure_dynamic_execution_policies(db)
            
            # Create test user
            user = User(
                email=f"safe-mode-auto-{uuid.uuid4().hex[:10]}@example.com",
                password_hash=hash_password("SafeModeAuto123!"),
                role=UserRole.ADMIN,
                is_active=True,
                approval_status="approved",
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            strategy = f"TEST_safe_mode_auto_{uuid.uuid4().hex[:8]}"
            
            # Create policy
            policy = ExecutionPolicy(
                strategy_type=strategy,
                execution_style="balanced",
                order_preference="limit_first",
                timeout_seconds=8,
                fallback_behavior="market_fallback",
                partial_fill_tolerance_pct=60,
                execution_urgency="medium",
                retry_limit=1,
                is_active=True,
                policy_code=f"test:{strategy}",
                policy_scope="strategy",
                scope_key=strategy,
                rules_payload={
                    "runtime": {"require_market_data": True},
                    "risk": {
                        "max_order_notional": 100000,
                        "max_symbol_exposure": 500000,
                        "max_strategy_exposure": 500000,
                        "max_user_exposure": 500000,
                        "max_portfolio_exposure": 500000,
                    },
                },
            )
            db.add(policy)
            db.commit()

            seed_default_strategy_bindings(db, strategy_ids=[strategy])

            # Create 6 critical violations to trigger safe mode (threshold is 5)
            for idx in range(6):
                append_execution_policy_decision_log(
                    db,
                    lifecycle_action="submit",
                    stage="VIOLATION",
                    context={
                        "trace_id": f"auto-safe-mode-{uuid.uuid4().hex[:8]}",
                        "pipeline_id": f"auto-pipe-{idx}",
                        "intent_token": str(uuid.uuid4()),
                        "user_id": user.id,
                        "portfolio_id": f"default:{user.id}",
                        "strategy_binding": strategy,
                        "environment": "DEV",
                        "symbol": "BTCUSDT",
                        "execution_mode": "SIMULATION",
                        "strategy_risk_class": "HIGH",
                    },
                    policy_result={
                        "recommended_action": "BLOCK",
                        "enforced_action": "BLOCK",
                        "rollout_mode": "full",
                        "standardized_reject": {
                            "reason_code": "RISK_ORDER_BREACH",
                            "reason_message": "risk breach",
                            "policy_id": "p",
                            "rule_id": "r",
                            "stage": "PRE_TRADE",
                            "severity": "CRITICAL",
                            "action_taken": "BLOCK",
                        },
                        "trace": {"action_taken": "BLOCK", "metrics_snapshot": {}},
                        "metrics_snapshot": {},
                    },
                    action_taken="BLOCK",
                    is_violation=True,
                )
            db.commit()

            # Evaluate policy - should trigger safe mode
            result = evaluate_execution_policy_engine(
                db,
                {
                    "user_id": user.id,
                    "portfolio_id": f"default:{user.id}",
                    "strategy_binding": strategy,
                    "symbol": "BTCUSDT",
                    "environment": "live",
                    "market_type": "spot",
                    "intent_type": "OPEN_POSITION",
                    "reduce_only": False,
                    "proposed_notional": 10.0,
                    "market_data_available": True,
                },
                stage="PRE_TRADE",
            )

            # Verify safe mode is active
            trace = result.get("trace", {})
            safe_mode = trace.get("safe_mode", {})
            assert safe_mode.get("active") is True, "Safe mode should be active"
            
            # Should be blocked due to safe mode
            assert result.get("enforced_action") == "BLOCK"
            
            # Reason code should indicate safe mode
            reject = result.get("standardized_reject", {})
            reason_code = reject.get("reason_code", "")
            assert reason_code.startswith("SAFE_MODE_"), f"Expected SAFE_MODE_ reason, got: {reason_code}"

        finally:
            db.close()

    def test_safe_mode_deactivation_flow(self, client, admin_headers):
        """Test safe mode deactivation flow"""
        # First, get active safe modes
        list_resp = client.get(
            "/api/admin/execution-policies/safe-mode",
            params={"active_only": "true"},
            headers=admin_headers,
        )
        assert list_resp.status_code == 200
        active_modes = list_resp.json()

        if active_modes:
            safe_mode_id = active_modes[0]["safe_mode_id"]
            deactivate_resp = client.post(
                f"/api/admin/execution-policies/safe-mode/{safe_mode_id}/deactivate",
                json={"reason": "Test deactivation for P2 Phase-1"},
                headers=admin_headers,
            )
            assert deactivate_resp.status_code == 200, f"Failed: {deactivate_resp.text}"
            data = deactivate_resp.json()
            assert data.get("safe_mode_id") == safe_mode_id
            assert data.get("is_active") is False
            assert data.get("deactivated_at") is not None
        else:
            pytest.skip("No active safe modes to deactivate")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
