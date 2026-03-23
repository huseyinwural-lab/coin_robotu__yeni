"""
P1 Deterministic Model Testing - Iteration 79
Tests for:
- Conflict/Hedge/Rebalance execute sonrası deterministic state change and effect metrics
- Queue response deterministic_effect_preview + recommendation_rank
- Governance Board queue inline impact cards and recommendation rank visibility
- Recommendation Stack ranking
- History compare sparkline + delta badge + exposure/var/liquidity deltas
- Simulation impact panel fields and colored deltas
- Queue hardening regressions (assign-owner, ack, bulk, execute approved)
- Escalation/queue unified tab regressions
"""

import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://deploy-blocker-6.preview.emergentagent.com")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_EMAIL = "canary.requester@platform.local"
ADMIN_PASSWORD = "CanaryRequester123!"


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super_admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Super admin authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def super_admin_user_id(super_admin_token):
    """Get super_admin user ID"""
    response = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {super_admin_token}"}
    )
    if response.status_code == 200:
        return response.json().get("id")
    pytest.skip("Could not get super_admin user ID")


@pytest.fixture(scope="module")
def admin_user_id(admin_token):
    """Get admin user ID"""
    response = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    if response.status_code == 200:
        return response.json().get("id")
    pytest.skip("Could not get admin user ID")


class TestDeterministicEffectPreview:
    """Tests for deterministic_effect_preview in queue responses"""

    def test_simulation_returns_deterministic_fields(self, super_admin_token, super_admin_user_id):
        """Verify simulation returns deterministic effect preview fields"""
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "user_id": super_admin_user_id,
                "intent_payload": {
                    "symbol": "BTCUSDT",
                    "side": "buy",
                    "notional": 100,
                    "strategy_binding": "spot_pullback_v1",
                    "volatility_pct": 3,
                    "position_size_value": 100
                },
                "apply_override": False
            }
        )
        assert response.status_code == 200, f"Simulation failed: {response.text}"
        data = response.json()
        
        # Verify simulation_id exists
        assert "simulation_id" in data, "simulation_id missing"
        
        # Verify before/after state
        assert "before_state" in data, "before_state missing"
        assert "after_state" in data, "after_state missing"
        
        # Verify risk delta fields
        assert "risk_delta" in data, "risk_delta missing"
        assert "decision_delta" in data, "decision_delta missing"
        
        # Verify exposure/var/liquidity fields
        assert "exposure_change" in data, "exposure_change missing"
        assert "var_change" in data, "var_change missing"
        assert "liquidity_impact" in data, "liquidity_impact missing"
        
        # Verify confidence adjusted risk
        assert "confidence_adjusted_risk_score" in data, "confidence_adjusted_risk_score missing"
        
        print(f"Simulation ID: {data['simulation_id']}")
        print(f"Risk delta: {data['risk_delta']}")
        print(f"Decision delta: {data['decision_delta']}")
        print(f"Exposure change: {data['exposure_change']}")
        print(f"VAR change: {data['var_change']}")
        print(f"Liquidity impact: {data['liquidity_impact']}")

    def test_decision_request_contains_deterministic_effect_preview(self, admin_token, admin_user_id, super_admin_token, super_admin_user_id):
        """Verify decision request contains deterministic_effect_preview"""
        # First create a simulation
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "user_id": admin_user_id,
                "intent_payload": {
                    "symbol": "ETHUSDT",
                    "side": "buy",
                    "notional": 50,
                    "strategy_binding": "spot_pullback_v1",
                    "volatility_pct": 4,
                    "position_size_value": 50
                },
                "apply_override": False
            }
        )
        assert sim_response.status_code == 200, f"Simulation failed: {sim_response.text}"
        simulation_id = sim_response.json().get("simulation_id")
        
        # Create a conflict_resolve decision request
        req_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/conflict-resolve",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "target_type": "strategy",
                "target_id": "spot_pullback_v1",
                "reason_note": "TEST_deterministic_effect_preview_test",
                "simulation_run_id": simulation_id
            }
        )
        assert req_response.status_code == 200, f"Decision request failed: {req_response.text}"
        data = req_response.json()
        
        # Verify deterministic_effect_preview exists
        assert "deterministic_effect_preview" in data, "deterministic_effect_preview missing"
        preview = data["deterministic_effect_preview"]
        
        # Verify preview fields
        assert "state_change" in preview, "state_change missing in preview"
        assert "predicted_risk_reduction" in preview, "predicted_risk_reduction missing"
        assert "predicted_after_risk_score" in preview, "predicted_after_risk_score missing"
        assert "predicted_allocation_diff_bps" in preview, "predicted_allocation_diff_bps missing"
        assert "model_type" in preview, "model_type missing"
        
        # Verify model_type is deterministic
        assert preview["model_type"] == "deterministic_fixed_v1", f"Expected deterministic_fixed_v1, got {preview['model_type']}"
        
        print(f"Request ID: {data['request_id']}")
        print(f"State change: {preview['state_change']}")
        print(f"Predicted risk reduction: {preview['predicted_risk_reduction']}")
        print(f"Model type: {preview['model_type']}")


class TestRecommendationRank:
    """Tests for recommendation_rank in queue responses"""

    def test_decision_requests_have_recommendation_rank(self, super_admin_token):
        """Verify decision requests list includes recommendation_rank"""
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200, f"Failed to get decision requests: {response.text}"
        data = response.json()
        
        items = data.get("items", [])
        pending_items = [item for item in items if item.get("status") == "pending"]
        
        if pending_items:
            # Verify recommendation_rank exists for pending items
            for item in pending_items[:5]:
                assert "recommendation_rank" in item, f"recommendation_rank missing for {item.get('request_id')}"
                print(f"Request {item['request_id']}: rank={item['recommendation_rank']}, severity={item.get('severity_band')}")
            
            # Verify ranking values are positive integers
            ranks = [item.get("recommendation_rank") for item in pending_items if item.get("recommendation_rank")]
            if len(ranks) > 1:
                # Ranks should be positive integers
                for rank in ranks:
                    assert isinstance(rank, int) and rank > 0, f"Invalid rank value: {rank}"
                # Verify ranks are unique
                assert len(ranks) == len(set(ranks)), f"Duplicate ranks found: {ranks}"
                print(f"All {len(ranks)} ranks are valid and unique")
        else:
            print("No pending items to verify recommendation_rank")


class TestQueueHardening:
    """Tests for queue hardening features: assign-owner, ack, bulk, execute"""

    def test_assign_owner_endpoint(self, super_admin_token):
        """Test assign-owner endpoint for decision requests"""
        # Get pending requests
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200
        items = response.json().get("items", [])
        pending = [item for item in items if item.get("status") == "pending"]
        
        if pending:
            request_id = pending[0]["request_id"]
            # Assign owner
            assign_response = requests.post(
                f"{BASE_URL}/api/admin/decision-requests/{request_id}/assign-owner",
                headers={"Authorization": f"Bearer {super_admin_token}"},
                json={"assigned_to": "TEST_ops_team"}
            )
            assert assign_response.status_code == 200, f"Assign owner failed: {assign_response.text}"
            data = assign_response.json()
            assert data.get("assigned_to") == "TEST_ops_team", "assigned_to not updated"
            print(f"Assigned owner to {request_id}: {data.get('assigned_to')}")
        else:
            print("No pending requests to test assign-owner")

    def test_ack_endpoint(self, super_admin_token):
        """Test ack endpoint for decision requests"""
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200
        items = response.json().get("items", [])
        pending = [item for item in items if item.get("status") == "pending"]
        
        if pending:
            request_id = pending[0]["request_id"]
            # Ack request
            ack_response = requests.post(
                f"{BASE_URL}/api/admin/decision-requests/{request_id}/ack",
                headers={"Authorization": f"Bearer {super_admin_token}"},
                json={"reason_note": "TEST_ack_note_for_testing"}
            )
            assert ack_response.status_code == 200, f"Ack failed: {ack_response.text}"
            data = ack_response.json()
            assert data.get("ack_by") is not None, "ack_by not set"
            assert data.get("ack_at") is not None, "ack_at not set"
            print(f"Acked {request_id}: ack_by={data.get('ack_by')}, ack_at={data.get('ack_at')}")
        else:
            print("No pending requests to test ack")

    def test_bulk_action_max_25_limit(self, super_admin_token):
        """Test bulk action enforces max 25 limit"""
        # Try with more than 25 IDs
        fake_ids = [f"req_fake_{i}" for i in range(30)]
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/bulk-action",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "action": "approve",
                "request_ids": fake_ids,
                "reason_note": "TEST_bulk_limit_test"
            }
        )
        assert response.status_code == 400, f"Expected 400 for >25 items, got {response.status_code}"
        assert "max 25" in response.text.lower() or "25" in response.text, "Error should mention 25 limit"
        print("Bulk action correctly rejects >25 items")

    def test_execute_requires_approved_status(self, super_admin_token):
        """Test execute endpoint requires approved status"""
        # Get pending requests
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200
        items = response.json().get("items", [])
        pending = [item for item in items if item.get("status") == "pending"]
        
        if pending:
            request_id = pending[0]["request_id"]
            # Try to execute pending (should fail)
            exec_response = requests.post(
                f"{BASE_URL}/api/admin/decision-requests/{request_id}/execute",
                headers={"Authorization": f"Bearer {super_admin_token}"},
                json={
                    "reason_note": "TEST_execute_test",
                    "preview_token": "fake_token"
                }
            )
            assert exec_response.status_code == 400, f"Expected 400 for pending execute, got {exec_response.status_code}"
            print("Execute correctly rejects pending status")
        else:
            print("No pending requests to test execute rejection")


class TestExecuteApprovedFlow:
    """Tests for execute flow on approved requests"""

    def test_full_approve_execute_flow(self, admin_token, admin_user_id, super_admin_token):
        """Test full flow: create -> approve -> execute with state change"""
        # 1. Create simulation
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "user_id": admin_user_id,
                "intent_payload": {
                    "symbol": "BTCUSDT",
                    "side": "buy",
                    "notional": 75,
                    "strategy_binding": "trend_follow_v1",
                    "volatility_pct": 5,
                    "position_size_value": 75
                },
                "apply_override": False
            }
        )
        assert sim_response.status_code == 200
        simulation_id = sim_response.json().get("simulation_id")
        
        # 2. Create hedge_apply decision request
        req_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/hedge-apply",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "target_type": "portfolio",
                "target_id": admin_user_id,
                "reason_note": "TEST_full_execute_flow_test",
                "simulation_run_id": simulation_id
            }
        )
        assert req_response.status_code == 200
        request_id = req_response.json().get("request_id")
        preview_token = req_response.json().get("preview_token")
        
        # 3. Approve the request (super_admin)
        approve_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{request_id}/approve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"reason_note": "TEST_approved_for_execute_test"}
        )
        assert approve_response.status_code == 200
        assert approve_response.json().get("status") == "approved"
        
        # 4. Get preview token if not available
        if not preview_token:
            preview_response = requests.get(
                f"{BASE_URL}/api/admin/decision-requests/{request_id}/preview",
                headers={"Authorization": f"Bearer {super_admin_token}"}
            )
            assert preview_response.status_code == 200
            preview_token = preview_response.json().get("preview_token")
        
        # 5. Execute the approved request
        exec_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{request_id}/execute",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "reason_note": "TEST_execute_approved_request",
                "preview_token": preview_token
            }
        )
        assert exec_response.status_code == 200, f"Execute failed: {exec_response.text}"
        data = exec_response.json()
        
        # Verify executed status
        assert data.get("status") == "executed", f"Expected executed, got {data.get('status')}"
        
        # Verify execution_effect exists
        assert "execution_effect" in data, "execution_effect missing after execute"
        exec_effect = data["execution_effect"]
        
        # Verify state_change in execution_effect
        assert "state_change" in exec_effect, "state_change missing in execution_effect"
        assert exec_effect["state_change"] == "HEDGE_APPLIED", f"Expected HEDGE_APPLIED, got {exec_effect['state_change']}"
        
        # Verify realized_risk_drop for hedge_apply
        assert "realized_risk_drop" in exec_effect, "realized_risk_drop missing for hedge_apply"
        
        print(f"Execute successful: {request_id}")
        print(f"State change: {exec_effect['state_change']}")
        print(f"Realized risk drop: {exec_effect.get('realized_risk_drop')}")


class TestHistoryCompare:
    """Tests for history compare with sparkline and delta badges"""

    def test_simulation_history_returns_data(self, super_admin_token):
        """Verify simulation history endpoint returns data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk-simulation/history",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            params={"limit": 20}
        )
        assert response.status_code == 200, f"History failed: {response.text}"
        data = response.json()
        
        items = data.get("items", [])
        print(f"History items count: {len(items)}")
        
        if items:
            # Verify output_payload contains required fields for sparkline
            for item in items[:3]:
                output = item.get("output_payload", {})
                print(f"Run {item['run_id']}: projected_risk_score={output.get('projected_risk_score')}")

    def test_compare_current_endpoint(self, super_admin_token, super_admin_user_id):
        """Test compare-current endpoint for history replay"""
        # First create a simulation to have history
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "user_id": super_admin_user_id,
                "intent_payload": {
                    "symbol": "BTCUSDT",
                    "side": "buy",
                    "notional": 100,
                    "strategy_binding": "spot_pullback_v1",
                    "volatility_pct": 3,
                    "position_size_value": 100
                },
                "apply_override": False
            }
        )
        assert sim_response.status_code == 200
        run_id = sim_response.json().get("simulation_id")
        
        # Compare with current
        compare_response = requests.get(
            f"{BASE_URL}/api/admin/simulation-runs/{run_id}/compare-current",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert compare_response.status_code == 200, f"Compare failed: {compare_response.text}"
        data = compare_response.json()
        
        # Verify compare_summary fields
        assert "compare_summary" in data, "compare_summary missing"
        summary = data["compare_summary"]
        
        # Verify delta fields for sparkline/badges
        assert "risk_delta_vs_history" in summary, "risk_delta_vs_history missing"
        assert "exposure_change_vs_history" in summary, "exposure_change_vs_history missing"
        assert "var_change_vs_history" in summary, "var_change_vs_history missing"
        assert "liquidity_impact_change_vs_history" in summary, "liquidity_impact_change_vs_history missing"
        assert "confidence_adjusted_risk_delta_vs_history" in summary, "confidence_adjusted_risk_delta_vs_history missing"
        assert "decision_delta_vs_history" in summary, "decision_delta_vs_history missing"
        
        print(f"Compare summary for {run_id}:")
        print(f"  risk_delta_vs_history: {summary['risk_delta_vs_history']}")
        print(f"  exposure_change_vs_history: {summary['exposure_change_vs_history']}")
        print(f"  var_change_vs_history: {summary['var_change_vs_history']}")
        print(f"  liquidity_impact_change_vs_history: {summary['liquidity_impact_change_vs_history']}")


class TestEscalationCenter:
    """Tests for escalation center unified tab"""

    def test_escalation_center_endpoint(self, super_admin_token):
        """Verify escalation center returns structured data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/escalation-center",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200, f"Escalation center failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "active_breaches" in data, "active_breaches missing"
        assert "acknowledged" in data, "acknowledged missing"
        assert "resolved" in data, "resolved missing"
        
        print(f"Escalation center: active={len(data['active_breaches'])}, ack={len(data['acknowledged'])}, resolved={len(data['resolved'])}")

    def test_escalation_assign_owner(self, super_admin_token):
        """Test escalation assign-owner endpoint"""
        # Get escalation items
        response = requests.get(
            f"{BASE_URL}/api/admin/escalation-center",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        active = data.get("active_breaches", [])
        if active:
            escalation_id = active[0]["escalation_id"]
            assign_response = requests.post(
                f"{BASE_URL}/api/admin/escalation-center/{escalation_id}/assign-owner",
                headers={"Authorization": f"Bearer {super_admin_token}"},
                json={
                    "current_owner": "TEST_escalation_owner",
                    "escalation_reason": "TEST_assign_owner_reason"
                }
            )
            assert assign_response.status_code == 200, f"Assign owner failed: {assign_response.text}"
            print(f"Assigned escalation owner: {escalation_id}")
        else:
            print("No active escalations to test assign-owner")

    def test_escalation_ack(self, super_admin_token):
        """Test escalation ack endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/escalation-center",
            headers={"Authorization": f"Bearer {super_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        active = data.get("active_breaches", [])
        if active:
            escalation_id = active[0]["escalation_id"]
            ack_response = requests.post(
                f"{BASE_URL}/api/admin/escalation-center/{escalation_id}/ack",
                headers={"Authorization": f"Bearer {super_admin_token}"},
                json={
                    "escalation_reason": "TEST_ack_reason_for_testing",
                    "current_owner": "TEST_ack_owner"
                }
            )
            assert ack_response.status_code == 200, f"Ack failed: {ack_response.text}"
            print(f"Acked escalation: {escalation_id}")
        else:
            print("No active escalations to test ack")


class TestSimulationImpactPanel:
    """Tests for simulation impact panel fields"""

    def test_simulation_returns_all_impact_fields(self, super_admin_token, super_admin_user_id):
        """Verify simulation returns all required impact panel fields"""
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "user_id": super_admin_user_id,
                "intent_payload": {
                    "symbol": "BTCUSDT",
                    "side": "buy",
                    "notional": 100,
                    "strategy_binding": "spot_pullback_v1",
                    "volatility_pct": 3,
                    "position_size_value": 100
                },
                "apply_override": False
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify all impact panel fields
        required_fields = [
            "projected_risk_score",
            "projected_gate_decision",
            "projected_pnl",
            "projected_drawdown",
            "projected_exposure",
            "projected_var",
            "projected_liquidity_impact",
            "exposure_change",
            "var_change",
            "liquidity_impact",
            "confidence_adjusted_risk_score",
            "risk_delta",
            "decision_delta",
            "before_state",
            "after_state",
            "decision_summary"
        ]
        
        for field in required_fields:
            assert field in data, f"{field} missing from simulation response"
        
        # Verify before_state structure
        before = data["before_state"]
        assert "risk_score" in before, "risk_score missing in before_state"
        assert "gate_decision" in before, "gate_decision missing in before_state"
        assert "exposure" in before, "exposure missing in before_state"
        
        # Verify after_state structure
        after = data["after_state"]
        assert "risk_score" in after, "risk_score missing in after_state"
        assert "gate_decision" in after, "gate_decision missing in after_state"
        assert "exposure" in after, "exposure missing in after_state"
        
        # Verify decision_summary structure
        summary = data["decision_summary"]
        assert "conflict_detected" in summary, "conflict_detected missing in decision_summary"
        assert "hedge_required" in summary, "hedge_required missing in decision_summary"
        assert "decision_delta" in summary, "decision_delta missing in decision_summary"
        
        print("All impact panel fields verified")
        print(f"Before risk: {before['risk_score']}, After risk: {after['risk_score']}")
        print(f"Risk delta: {data['risk_delta']}, Decision delta: {data['decision_delta']}")


class TestRebalanceExecuteStateChange:
    """Tests for rebalance execute state change"""

    def test_rebalance_execute_returns_allocation_diff(self, admin_token, admin_user_id, super_admin_token):
        """Test rebalance execute returns allocation_diff_bps"""
        # 1. Create simulation
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "user_id": admin_user_id,
                "intent_payload": {
                    "symbol": "BTCUSDT",
                    "side": "buy",
                    "notional": 100,
                    "strategy_binding": "spot_pullback_v1",
                    "volatility_pct": 6,
                    "position_size_value": 100
                },
                "apply_override": False
            }
        )
        assert sim_response.status_code == 200
        simulation_id = sim_response.json().get("simulation_id")
        
        # 2. Create rebalance_change decision request
        req_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/rebalance-change",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "target_type": "strategy",
                "target_id": "spot_pullback_v1",
                "reason_note": "TEST_rebalance_allocation_diff_test",
                "simulation_run_id": simulation_id
            }
        )
        assert req_response.status_code == 200
        request_id = req_response.json().get("request_id")
        preview_token = req_response.json().get("preview_token")
        
        # Verify deterministic_effect_preview has allocation_diff_bps
        preview = req_response.json().get("deterministic_effect_preview", {})
        assert "predicted_allocation_diff_bps" in preview, "predicted_allocation_diff_bps missing"
        assert preview["state_change"] == "ALLOCATION_REBALANCED", f"Expected ALLOCATION_REBALANCED, got {preview['state_change']}"
        
        print(f"Rebalance request created: {request_id}")
        print(f"Predicted allocation diff bps: {preview['predicted_allocation_diff_bps']}")
        print(f"State change: {preview['state_change']}")


class TestConflictResolveStateChange:
    """Tests for conflict resolve state change"""

    def test_conflict_resolve_returns_correct_state_change(self, admin_token, admin_user_id):
        """Test conflict resolve returns CONFLICT_RESOLVED state change"""
        # 1. Create simulation
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "user_id": admin_user_id,
                "intent_payload": {
                    "symbol": "ETHUSDT",
                    "side": "sell",
                    "notional": 80,
                    "strategy_binding": "trend_follow_v1",
                    "volatility_pct": 7,
                    "position_size_value": 80
                },
                "apply_override": False
            }
        )
        assert sim_response.status_code == 200
        simulation_id = sim_response.json().get("simulation_id")
        
        # 2. Create conflict_resolve decision request
        req_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/conflict-resolve",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "target_type": "strategy",
                "target_id": "trend_follow_v1",
                "reason_note": "TEST_conflict_resolve_state_change_test",
                "simulation_run_id": simulation_id
            }
        )
        assert req_response.status_code == 200
        
        # Verify deterministic_effect_preview
        preview = req_response.json().get("deterministic_effect_preview", {})
        assert preview["state_change"] == "CONFLICT_RESOLVED", f"Expected CONFLICT_RESOLVED, got {preview['state_change']}"
        
        print(f"Conflict resolve state change: {preview['state_change']}")
        print(f"Predicted risk reduction: {preview['predicted_risk_reduction']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
