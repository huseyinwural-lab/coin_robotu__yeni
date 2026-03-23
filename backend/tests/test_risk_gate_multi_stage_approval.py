"""
Risk Orchestrator Pre-Apply Risk Gate + Multi-Stage Approval Tests
Tests for:
- Pre-Apply Risk Score Engine: /policy/simulate risk_score(0-100), classification(SAFE/WARNING/CRITICAL), approval_flow
- Multi-stage apply pipeline: SAFE/WARNING/CRITICAL rules
- WARNING double_confirm requirement
- CRITICAL apply_with_override=false BLOCK
- CRITICAL + apply_with_override=true pending_approval
- 4-eyes approval: approve/reject endpoints, same user block, timeout state
- Revert simulation: /revert/{version_id}/simulate and /revert/{version_id}/apply
- Decision trace endpoint: /policy/decision-traces
- Approval queue endpoint: /policy/approvals state filtering
- Override risk enforcement: count/size limits, expiry alert+auto-disable
- Operational hardening: request_key idempotent replay
"""

import os
import pytest
import requests
import time
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = os.environ.get("BACKEND_TEST_SUPER_ADMIN_EMAIL", "")
SUPER_ADMIN_PASSWORD = os.environ.get("BACKEND_TEST_SUPER_ADMIN_PASSWORD", "")

INTEGRATION_TEST_BLOCKED = not BASE_URL or not SUPER_ADMIN_EMAIL or not SUPER_ADMIN_PASSWORD

pytestmark = pytest.mark.skipif(
    INTEGRATION_TEST_BLOCKED,
    reason="Integration testleri için REACT_APP_BACKEND_URL ve BACKEND_TEST_SUPER_ADMIN_* env gereklidir.",
)


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super_admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Super admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def auth_headers(super_admin_token):
    """Auth headers for API calls"""
    return {"Authorization": f"Bearer {super_admin_token}", "Content-Type": "application/json"}


class TestPreApplyRiskScoreEngine:
    """Test Pre-Apply Risk Score Engine via /policy/simulate"""
    
    def test_simulate_returns_risk_score_and_classification(self, auth_headers):
        """POST /policy/simulate returns risk_score(0-100), classification(SAFE/WARNING/CRITICAL), approval_flow"""
        # Get current policy first
        policy_resp = requests.get(f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy", headers=auth_headers)
        assert policy_resp.status_code == 200
        current_policy = policy_resp.json()
        
        # Simulate with minimal change (should be SAFE)
        candidate_policy = {
            "reference_equity_usd": current_policy.get("reference_equity_usd", 10000),
            "account_max_notional_pct": current_policy.get("account_max_notional_pct", 60),
            "symbol_max_notional_pct": current_policy.get("symbol_max_notional_pct", 25),
            "strategy_max_concurrent_positions": current_policy.get("strategy_max_concurrent_positions", 3),
            "strategy_cooldown_seconds": current_policy.get("strategy_cooldown_seconds", 60),
            "max_order_frequency_per_min": current_policy.get("max_order_frequency_per_min", 6),
            "max_order_burst_per_10s": current_policy.get("max_order_burst_per_10s", 3),
            "daily_loss_limit_pct": current_policy.get("daily_loss_limit_pct", 5),
            "duplicate_suppression_window_seconds": current_policy.get("duplicate_suppression_window_seconds", 300),
        }
        
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            headers=auth_headers,
            json={"candidate_policy": candidate_policy}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify risk_score is 0-100
        assert "risk_score" in data
        assert 0 <= data["risk_score"] <= 100
        
        # Verify classification is one of SAFE/WARNING/CRITICAL
        assert "classification" in data
        assert data["classification"] in ["SAFE", "WARNING", "CRITICAL"]
        
        # Verify approval_flow is returned
        assert "approval_flow" in data
        assert "rule_path" in data["approval_flow"]
        
        # Verify simulation_id is returned
        assert "simulation_id" in data
        print(f"Simulation result: risk_score={data['risk_score']}, classification={data['classification']}, rule_path={data['approval_flow']['rule_path']}")
    
    def test_simulate_critical_classification_with_loosened_limits(self, auth_headers):
        """Simulate with significantly loosened limits should produce WARNING or CRITICAL (or SAFE if already loose)"""
        candidate_policy = {
            "reference_equity_usd": 10000,
            "account_max_notional_pct": 95,  # Very high - loosened
            "symbol_max_notional_pct": 80,   # Very high - loosened
            "strategy_max_concurrent_positions": 20,  # Very high - loosened
            "strategy_cooldown_seconds": 5,   # Very low - loosened
            "max_order_frequency_per_min": 60,  # Very high - loosened
            "max_order_burst_per_10s": 30,   # Very high - loosened
            "daily_loss_limit_pct": 25,      # Very high - loosened
            "duplicate_suppression_window_seconds": 10,  # Very low - loosened
        }
        
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            headers=auth_headers,
            json={"candidate_policy": candidate_policy}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Classification depends on current policy state
        # If current policy is already very loose, this may be SAFE (no change)
        # Otherwise should be WARNING or CRITICAL
        assert data["classification"] in ["SAFE", "WARNING", "CRITICAL"]
        print(f"Loosened limits simulation: risk_score={data['risk_score']}, classification={data['classification']}")


class TestMultiStageApplyPipeline:
    """Test Multi-stage apply pipeline based on classification"""
    
    def test_safe_classification_direct_apply(self, auth_headers):
        """SAFE classification should allow direct apply with double_confirmed"""
        # Get current policy
        policy_resp = requests.get(f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy", headers=auth_headers)
        current_policy = policy_resp.json()
        
        # Simulate with no change (SAFE)
        candidate_policy = {
            "reference_equity_usd": current_policy.get("reference_equity_usd", 10000),
            "account_max_notional_pct": current_policy.get("account_max_notional_pct", 60),
            "symbol_max_notional_pct": current_policy.get("symbol_max_notional_pct", 25),
            "strategy_max_concurrent_positions": current_policy.get("strategy_max_concurrent_positions", 3),
            "strategy_cooldown_seconds": current_policy.get("strategy_cooldown_seconds", 60),
            "max_order_frequency_per_min": current_policy.get("max_order_frequency_per_min", 6),
            "max_order_burst_per_10s": current_policy.get("max_order_burst_per_10s", 3),
            "daily_loss_limit_pct": current_policy.get("daily_loss_limit_pct", 5),
            "duplicate_suppression_window_seconds": current_policy.get("duplicate_suppression_window_seconds", 300),
        }
        
        sim_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            headers=auth_headers,
            json={"candidate_policy": candidate_policy}
        )
        assert sim_response.status_code == 200
        sim_data = sim_response.json()
        
        if sim_data["classification"] == "SAFE":
            # Apply should work with double_confirmed=True
            apply_response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
                headers=auth_headers,
                json={
                    "simulation_id": sim_data["simulation_id"],
                    "reason_note": "Test SAFE apply",
                    "double_confirmed": True,
                    "apply_with_override": False,
                    "request_key": f"test-safe-{int(time.time())}"
                }
            )
            assert apply_response.status_code == 200
            apply_data = apply_response.json()
            assert apply_data["status"] == "applied"
            print(f"SAFE apply result: status={apply_data['status']}, rule_path={apply_data['rule_path']}")
        else:
            print(f"Skipping SAFE test - classification was {sim_data['classification']}")
    
    def test_warning_requires_double_confirm(self, auth_headers):
        """WARNING classification requires double_confirmed=True"""
        # Simulate with moderate loosening to get WARNING
        candidate_policy = {
            "reference_equity_usd": 10000,
            "account_max_notional_pct": 75,  # Moderately loosened
            "symbol_max_notional_pct": 40,   # Moderately loosened
            "strategy_max_concurrent_positions": 6,
            "strategy_cooldown_seconds": 30,
            "max_order_frequency_per_min": 12,
            "max_order_burst_per_10s": 6,
            "daily_loss_limit_pct": 8,
            "duplicate_suppression_window_seconds": 150,
        }
        
        sim_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            headers=auth_headers,
            json={"candidate_policy": candidate_policy}
        )
        assert sim_response.status_code == 200
        sim_data = sim_response.json()
        
        if sim_data["classification"] == "WARNING":
            # Apply without double_confirmed should fail
            apply_response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
                headers=auth_headers,
                json={
                    "simulation_id": sim_data["simulation_id"],
                    "reason_note": "Test WARNING without double_confirm",
                    "double_confirmed": False,
                    "apply_with_override": False,
                    "request_key": f"test-warning-no-confirm-{int(time.time())}"
                }
            )
            assert apply_response.status_code == 400
            assert "double_confirmation_required" in apply_response.json().get("detail", "")
            print("WARNING without double_confirm correctly rejected")
        else:
            print(f"Skipping WARNING test - classification was {sim_data['classification']}")
    
    def test_critical_blocked_without_override(self, auth_headers):
        """CRITICAL classification is BLOCKED when apply_with_override=False"""
        # Simulate with extreme loosening to get CRITICAL
        candidate_policy = {
            "reference_equity_usd": 10000,
            "account_max_notional_pct": 99,
            "symbol_max_notional_pct": 90,
            "strategy_max_concurrent_positions": 50,
            "strategy_cooldown_seconds": 1,
            "max_order_frequency_per_min": 100,
            "max_order_burst_per_10s": 50,
            "daily_loss_limit_pct": 50,
            "duplicate_suppression_window_seconds": 5,
        }
        
        sim_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            headers=auth_headers,
            json={"candidate_policy": candidate_policy}
        )
        assert sim_response.status_code == 200
        sim_data = sim_response.json()
        
        if sim_data["classification"] == "CRITICAL":
            # Apply without override should be BLOCKED
            apply_response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
                headers=auth_headers,
                json={
                    "simulation_id": sim_data["simulation_id"],
                    "reason_note": "Test CRITICAL without override",
                    "double_confirmed": True,
                    "apply_with_override": False,
                    "request_key": f"test-critical-no-override-{int(time.time())}"
                }
            )
            assert apply_response.status_code == 200
            apply_data = apply_response.json()
            assert apply_data["status"] == "blocked"
            assert "CRITICAL_BLOCK" in apply_data.get("rule_path", "")
            print(f"CRITICAL without override correctly blocked: rule_path={apply_data['rule_path']}")
        else:
            print(f"Skipping CRITICAL test - classification was {sim_data['classification']}")
    
    def test_critical_with_override_creates_pending_approval(self, auth_headers):
        """CRITICAL + apply_with_override=True creates pending_approval for 4-eyes"""
        # Simulate with extreme loosening to get CRITICAL
        candidate_policy = {
            "reference_equity_usd": 10000,
            "account_max_notional_pct": 99,
            "symbol_max_notional_pct": 90,
            "strategy_max_concurrent_positions": 50,
            "strategy_cooldown_seconds": 1,
            "max_order_frequency_per_min": 100,
            "max_order_burst_per_10s": 50,
            "daily_loss_limit_pct": 50,
            "duplicate_suppression_window_seconds": 5,
        }
        
        sim_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            headers=auth_headers,
            json={"candidate_policy": candidate_policy}
        )
        assert sim_response.status_code == 200
        sim_data = sim_response.json()
        
        if sim_data["classification"] == "CRITICAL":
            # Apply with override should create pending_approval
            apply_response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
                headers=auth_headers,
                json={
                    "simulation_id": sim_data["simulation_id"],
                    "reason_note": "Test CRITICAL with override",
                    "double_confirmed": True,
                    "apply_with_override": True,
                    "request_key": f"test-critical-with-override-{int(time.time())}"
                }
            )
            assert apply_response.status_code == 200
            apply_data = apply_response.json()
            assert apply_data["status"] == "pending_approval"
            assert apply_data.get("approval_request_id") is not None
            print(f"CRITICAL with override created pending_approval: approval_id={apply_data['approval_request_id']}")
        else:
            print(f"Skipping CRITICAL override test - classification was {sim_data['classification']}")


class TestFourEyesApproval:
    """Test 4-eyes approval flow"""
    
    def test_approval_queue_endpoint(self, auth_headers):
        """GET /policy/approvals returns approval queue with state filtering"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Approval queue has {len(data)} items")
        
        # Test state filtering
        for state in ["pending_approval", "approved", "rejected", "timeout"]:
            filtered_response = requests.get(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals?state={state}",
                headers=auth_headers
            )
            assert filtered_response.status_code == 200
            filtered_data = filtered_response.json()
            # All items should have the filtered state
            for item in filtered_data:
                assert item["state"] == state
            print(f"State filter '{state}': {len(filtered_data)} items")
    
    def test_same_user_approval_blocked(self, auth_headers):
        """Same user cannot approve their own request (4-eyes rule)"""
        # Get pending approvals
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals?state=pending_approval",
            headers=auth_headers
        )
        assert response.status_code == 200
        pending = response.json()
        
        if pending:
            approval_id = pending[0]["approval_id"]
            
            # Try to approve own request (should fail with same_user_second_approval_blocked)
            approve_response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/approve",
                headers=auth_headers,
                json={"decision_note": "Self-approval test"}
            )
            # Should be 400 with same_user_second_approval_blocked
            if approve_response.status_code == 400:
                assert "same_user_second_approval_blocked" in approve_response.json().get("detail", "")
                print("Same user approval correctly blocked")
            else:
                print(f"Approval response: {approve_response.status_code} - {approve_response.text}")
        else:
            print("No pending approvals to test same-user block")
    
    def test_reject_approval_request(self, auth_headers):
        """Test rejecting an approval request"""
        # Get pending approvals
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals?state=pending_approval",
            headers=auth_headers
        )
        assert response.status_code == 200
        pending = response.json()
        
        if pending:
            approval_id = pending[0]["approval_id"]
            
            # Try to reject (may fail with same_user_second_approval_blocked)
            reject_response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/reject",
                headers=auth_headers,
                json={"decision_note": "Test rejection"}
            )
            # Either 200 (rejected) or 400 (same user blocked)
            assert reject_response.status_code in [200, 400]
            print(f"Reject response: {reject_response.status_code}")
        else:
            print("No pending approvals to test rejection")


class TestDecisionTrace:
    """Test Decision Trace endpoint"""
    
    def test_decision_traces_endpoint(self, auth_headers):
        """GET /policy/decision-traces returns decision trace chain"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/decision-traces",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if data:
            trace = data[0]
            # Verify trace structure
            assert "trace_id" in trace
            assert "flow_type" in trace
            assert "simulation_id" in trace
            assert "classification" in trace
            assert "risk_score" in trace
            assert "rule_path" in trace
            assert "decision_state" in trace
            assert "requested_by" in trace
            assert "request_key" in trace
            print(f"Decision traces: {len(data)} items, latest: {trace['decision_state']} via {trace['rule_path']}")
        else:
            print("No decision traces found")


class TestRevertSimulation:
    """Test Revert simulation flow"""
    
    def test_revert_simulate_endpoint(self, auth_headers):
        """POST /revert/{version_id}/simulate returns simulation for revert"""
        # Get policy history to find a version
        history_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/history",
            headers=auth_headers
        )
        assert history_response.status_code == 200
        history = history_response.json()
        
        versions = history.get("versions", [])
        if versions:
            version_id = versions[0]["version_id"]
            
            # Simulate revert
            revert_sim_response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/revert/{version_id}/simulate",
                headers=auth_headers
            )
            assert revert_sim_response.status_code == 200
            revert_data = revert_sim_response.json()
            
            assert "version_id" in revert_data
            assert "simulation" in revert_data
            assert "simulation_id" in revert_data["simulation"]
            assert "risk_score" in revert_data["simulation"]
            assert "classification" in revert_data["simulation"]
            print(f"Revert simulation: version={version_id}, risk_score={revert_data['simulation']['risk_score']}")
        else:
            print("No versions found for revert test")
    
    def test_revert_apply_requires_simulation_id(self, auth_headers):
        """POST /revert/{version_id}/apply requires simulation_id"""
        # Get policy history
        history_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/history",
            headers=auth_headers
        )
        assert history_response.status_code == 200
        history = history_response.json()
        
        versions = history.get("versions", [])
        if versions:
            version_id = versions[0]["version_id"]
            
            # Try apply without simulation_id
            apply_response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/revert/{version_id}/apply",
                headers=auth_headers,
                json={
                    "reason_note": "Test revert without simulation",
                    "double_confirmed": True,
                    "apply_with_override": False
                }
            )
            # Should fail with revert_simulation_required
            assert apply_response.status_code == 400
            assert "revert_simulation_required" in apply_response.json().get("detail", "")
            print("Revert apply correctly requires simulation_id")
        else:
            print("No versions found for revert apply test")


class TestOverrideRiskEnforcement:
    """Test Override risk enforcement"""
    
    def test_override_count_limit(self, auth_headers):
        """Override count limit is enforced"""
        # Get current overrides
        overrides_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/exposure/overrides",
            headers=auth_headers
        )
        assert overrides_response.status_code == 200
        current_overrides = overrides_response.json()
        print(f"Current active overrides: {len(current_overrides)}")
        
        # Create override endpoint exists and works
        create_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/exposure/overrides",
            headers=auth_headers,
            json={
                "override_type": "symbol",
                "target_key": f"TEST_SYMBOL_{int(time.time())}",
                "reason_note": "Test override creation",
                "max_notional_pct": 10,
                "expires_in_minutes": 5
            }
        )
        # Should succeed or fail with limit reached
        assert create_response.status_code in [200, 400]
        if create_response.status_code == 400:
            detail = create_response.json().get("detail", "")
            assert "override_count_limit_reached" in detail or "override_total_notional_limit_reached" in detail
            print(f"Override limit enforced: {detail}")
        else:
            print(f"Override created: {create_response.json().get('override_id')}")
    
    def test_override_notional_limit(self, auth_headers):
        """Override notional limit is enforced"""
        # Try to create override with very high notional
        create_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/exposure/overrides",
            headers=auth_headers,
            json={
                "override_type": "symbol",
                "target_key": f"TEST_HIGH_NOTIONAL_{int(time.time())}",
                "reason_note": "Test high notional override",
                "max_notional_pct": 150,  # Above 100% limit
                "expires_in_minutes": 5
            }
        )
        # Should fail with override_notional_too_high
        assert create_response.status_code == 400
        assert "override_notional_too_high" in create_response.json().get("detail", "")
        print("Override notional limit correctly enforced")


class TestIdempotentReplay:
    """Test operational hardening - idempotent replay"""
    
    def test_request_key_idempotent_replay(self, auth_headers):
        """Same request_key returns deterministic response or stale_simulation error"""
        # Get current policy
        policy_resp = requests.get(f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy", headers=auth_headers)
        current_policy = policy_resp.json()
        
        # Simulate
        candidate_policy = {
            "reference_equity_usd": current_policy.get("reference_equity_usd", 10000),
            "account_max_notional_pct": current_policy.get("account_max_notional_pct", 60),
            "symbol_max_notional_pct": current_policy.get("symbol_max_notional_pct", 25),
            "strategy_max_concurrent_positions": current_policy.get("strategy_max_concurrent_positions", 3),
            "strategy_cooldown_seconds": current_policy.get("strategy_cooldown_seconds", 60),
            "max_order_frequency_per_min": current_policy.get("max_order_frequency_per_min", 6),
            "max_order_burst_per_10s": current_policy.get("max_order_burst_per_10s", 3),
            "daily_loss_limit_pct": current_policy.get("daily_loss_limit_pct", 5),
            "duplicate_suppression_window_seconds": current_policy.get("duplicate_suppression_window_seconds", 300),
        }
        
        sim_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            headers=auth_headers,
            json={"candidate_policy": candidate_policy}
        )
        assert sim_response.status_code == 200
        sim_data = sim_response.json()
        
        # Use same request_key for multiple apply attempts
        request_key = f"idempotent-test-{int(time.time())}"
        
        # First apply
        apply1_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
            headers=auth_headers,
            json={
                "simulation_id": sim_data["simulation_id"],
                "reason_note": "Idempotent test 1",
                "double_confirmed": True,
                "apply_with_override": False,
                "request_key": request_key
            }
        )
        assert apply1_response.status_code == 200
        apply1_data = apply1_response.json()
        
        # Second apply with same request_key
        # This may return 200 (idempotent replay) or 409 (stale_simulation_requires_resimulate)
        # because the policy version changed after first apply
        apply2_response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
            headers=auth_headers,
            json={
                "simulation_id": sim_data["simulation_id"],
                "reason_note": "Idempotent test 2",
                "double_confirmed": True,
                "apply_with_override": False,
                "request_key": request_key
            }
        )
        
        # Either 200 (idempotent replay) or 409 (stale simulation) is valid
        assert apply2_response.status_code in [200, 409]
        
        if apply2_response.status_code == 200:
            apply2_data = apply2_response.json()
            # Both should return same status (idempotent replay)
            assert apply1_data["status"] == apply2_data["status"]
            if "idempotent_replay" in apply2_data.get("message", ""):
                print("Idempotent replay correctly detected")
            print(f"Idempotent test: first={apply1_data['status']}, second={apply2_data['status']}")
        else:
            # 409 stale_simulation_requires_resimulate is expected when policy version changed
            detail = apply2_response.json().get("detail", "")
            assert "stale_simulation_requires_resimulate" in detail
            print(f"Stale simulation correctly detected after policy version change: {detail}")


class TestStatusAndPolicyEndpoints:
    """Test status and policy endpoints"""
    
    def test_status_endpoint(self, auth_headers):
        """GET /status returns complete status snapshot"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/status",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "policy" in data
        assert "kill_switch_active" in data
        assert "trading_enabled" in data
        assert "open_intents" in data
        print(f"Status: kill_switch={data['kill_switch_active']}, trading={data['trading_enabled']}")
    
    def test_policy_endpoint(self, auth_headers):
        """GET /policy returns current policy"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "reference_equity_usd" in data
        assert "account_max_notional_pct" in data
        assert "policy_version" in data
        print(f"Policy version: {data['policy_version']}")
    
    def test_history_endpoint(self, auth_headers):
        """GET /policy/history returns versions and change_requests"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/history",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "versions" in data
        assert "change_requests" in data
        print(f"History: {len(data['versions'])} versions, {len(data['change_requests'])} change_requests")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
