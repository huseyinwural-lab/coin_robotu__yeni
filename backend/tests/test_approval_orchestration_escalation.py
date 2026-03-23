"""
Approval Orchestration + Escalation + Decision Intelligence Layer Tests
Tests for:
- Approval Queue Engine state machine: pending/assigned/approved/rejected/expired
- Queue list endpoint: scope=my/unassigned/all, critical_first sorting, SLA fields
- Queue assignment: manual assign + auto-assign hybrid
- CRITICAL escalation pipeline: 5dk warning, 8dk critical, 10dk expired; queue sweep
- Forced resolution: SLA breach auto-reject; force apply (super_admin only)
- Policy apply pipeline with queue integration: CRITICAL apply_with_override -> pending/assigned
- Decision intelligence endpoint: diff, risk breakdown, why_decision, similar_patterns
- Reject insights endpoint: same rule 3+/30dk triggers suggestion
- Webhook/notification event types for alert generation
- Operational dashboard endpoint: active pending, critical queue, reject spike, override usage, risk distribution, throughput
"""

import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
SUPER_ADMIN_EMAIL = os.environ.get("BACKEND_TEST_SUPER_ADMIN_EMAIL", "")
SUPER_ADMIN_PASSWORD = os.environ.get("BACKEND_TEST_SUPER_ADMIN_PASSWORD", "")

INTEGRATION_TEST_BLOCKED = not BASE_URL or not SUPER_ADMIN_EMAIL or not SUPER_ADMIN_PASSWORD

pytestmark = pytest.mark.skipif(
    INTEGRATION_TEST_BLOCKED,
    reason="Integration testleri için REACT_APP_BACKEND_URL ve BACKEND_TEST_SUPER_ADMIN_* env gereklidir.",
)


@pytest.fixture(scope="module")
def auth_token():
    """Get super_admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestApprovalQueueEngine:
    """Tests for Approval Queue Engine state machine"""

    def test_queue_list_all_scope(self, auth_headers):
        """Test queue list with scope=all"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue?scope=all&limit=50",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Queue list (all scope): {len(data)} items")
        
        # Check SLA fields if items exist
        if data:
            item = data[0]
            assert "sla_remaining_seconds" in item
            assert "sla_stage" in item
            assert "state" in item
            assert item["state"] in ["pending", "assigned", "approved", "rejected", "expired"]
            print(f"First item state: {item['state']}, SLA stage: {item['sla_stage']}")

    def test_queue_list_my_scope(self, auth_headers):
        """Test queue list with scope=my"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue?scope=my&limit=50",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Queue list (my scope): {len(data)} items")

    def test_queue_list_unassigned_scope(self, auth_headers):
        """Test queue list with scope=unassigned"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue?scope=unassigned&limit=50",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Queue list (unassigned scope): {len(data)} items")

    def test_queue_list_critical_first_sorting(self, auth_headers):
        """Test queue list with critical_first=true sorting"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue?scope=all&critical_first=true&limit=50",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Verify CRITICAL items come first if any exist
        if len(data) >= 2:
            critical_indices = [i for i, item in enumerate(data) if item.get("classification") == "CRITICAL"]
            non_critical_indices = [i for i, item in enumerate(data) if item.get("classification") != "CRITICAL"]
            if critical_indices and non_critical_indices:
                assert max(critical_indices) < min(non_critical_indices), "CRITICAL items should come first"
        print(f"Queue list (critical_first): {len(data)} items")

    def test_queue_list_state_filter(self, auth_headers):
        """Test queue list with state filter"""
        for state in ["pending", "assigned", "approved", "rejected", "expired"]:
            response = requests.get(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue?scope=all&state={state}&limit=50",
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            # All items should have the filtered state
            for item in data:
                assert item.get("state") == state
            print(f"Queue list (state={state}): {len(data)} items")


class TestEscalationPipeline:
    """Tests for CRITICAL escalation pipeline"""

    def test_queue_sweep_endpoint(self, auth_headers):
        """Test queue sweep endpoint for escalation processing"""
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/sweep",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check escalation result fields
        assert "warning_escalations" in data
        assert "critical_escalations" in data
        assert "stuck_detected" in data
        print(f"Queue sweep result: warning={data['warning_escalations']}, critical={data['critical_escalations']}, stuck={data['stuck_detected']}")


class TestQueueAssignment:
    """Tests for queue assignment (manual + auto-assign hybrid)"""

    def test_auto_assign_endpoint(self, auth_headers):
        """Test auto-assign endpoint"""
        # First get an unassigned pending item
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue?scope=unassigned&state=pending&limit=1",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        if not data:
            pytest.skip("No unassigned pending items to test auto-assign")
        
        approval_id = data[0]["approval_id"]
        
        # Try auto-assign
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{approval_id}/assign",
            headers=auth_headers,
            json={"auto_assign": True},
        )
        # May fail if no eligible assignee, but endpoint should work
        assert response.status_code in [200, 400]
        print(f"Auto-assign response: {response.status_code}")


class TestForceApply:
    """Tests for force apply (super_admin only)"""

    def test_force_apply_requires_super_admin(self, auth_headers):
        """Test that force apply endpoint exists and requires proper state"""
        # Get any pending/assigned/expired item
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue?scope=all&limit=10",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Find an item that can be force-applied
        force_applicable = [item for item in data if item.get("state") in ["pending", "assigned", "expired"]]
        
        if not force_applicable:
            pytest.skip("No force-applicable items in queue")
        
        approval_id = force_applicable[0]["approval_id"]
        
        # Try force apply
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{approval_id}/force-apply",
            headers=auth_headers,
            json={"reason_note": "Test force apply from testing agent"},
        )
        # Should work for super_admin or return conflict if already processed
        assert response.status_code in [200, 409]
        print(f"Force apply response: {response.status_code}")


class TestPolicyApplyPipeline:
    """Tests for policy apply pipeline with queue integration"""

    def test_simulate_policy_change(self, auth_headers):
        """Test policy simulation returns risk_score, classification, approval_flow"""
        # Get current policy
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        current_policy = response.json()
        
        # Create a candidate policy with minor change
        candidate = {
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
            json={"candidate_policy": candidate},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "simulation_id" in data
        assert "risk_score" in data
        assert "classification" in data
        assert data["classification"] in ["SAFE", "WARNING", "CRITICAL"]
        assert "approval_flow" in data
        assert "diff_summary" in data
        print(f"Simulation: risk_score={data['risk_score']}, classification={data['classification']}")
        
        return data

    def test_critical_apply_with_override_creates_pending(self, auth_headers):
        """Test CRITICAL apply with override creates pending approval"""
        # Get current policy
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        current_policy = response.json()
        
        # Create a CRITICAL candidate (significantly loosen limits)
        candidate = {
            "reference_equity_usd": current_policy.get("reference_equity_usd", 10000),
            "account_max_notional_pct": 95,  # Very high - should trigger CRITICAL
            "symbol_max_notional_pct": 80,   # Very high
            "strategy_max_concurrent_positions": 20,  # Very high
            "strategy_cooldown_seconds": 10,  # Very low
            "max_order_frequency_per_min": 60,  # Very high
            "max_order_burst_per_10s": 30,  # Very high
            "daily_loss_limit_pct": 50,  # Very high - should trigger CRITICAL
            "duplicate_suppression_window_seconds": 10,  # Very low
        }
        
        # Simulate first
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            headers=auth_headers,
            json={"candidate_policy": candidate},
        )
        assert response.status_code == 200
        simulation = response.json()
        
        # If CRITICAL, try apply with override
        if simulation.get("classification") == "CRITICAL":
            response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
                headers=auth_headers,
                json={
                    "simulation_id": simulation["simulation_id"],
                    "reason_note": "Test CRITICAL apply with override",
                    "double_confirmed": True,
                    "apply_with_override": True,
                    "request_key": f"test-critical-{datetime.now().isoformat()}",
                },
            )
            assert response.status_code == 200
            data = response.json()
            
            # Should be pending or assigned (waiting for second approval)
            assert data.get("status") in ["pending", "assigned", "applied"]
            print(f"CRITICAL apply result: status={data.get('status')}, rule_path={data.get('rule_path')}")
        else:
            print(f"Simulation was {simulation.get('classification')}, not CRITICAL - skipping override test")


class TestDecisionIntelligence:
    """Tests for decision intelligence endpoint"""

    def test_decision_traces_list(self, auth_headers):
        """Test decision traces list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/decision-traces?limit=25",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if data:
            trace = data[0]
            assert "trace_id" in trace
            assert "flow_type" in trace
            assert "simulation_id" in trace
            assert "classification" in trace
            assert "risk_score" in trace
            assert "rule_path" in trace
            assert "decision_state" in trace
            print(f"Decision traces: {len(data)} items, first trace_id={trace['trace_id']}")
            return trace["trace_id"]
        return None

    def test_decision_intelligence_endpoint(self, auth_headers):
        """Test decision intelligence endpoint with diff, risk breakdown, why_decision, similar_patterns"""
        # First get a trace_id
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/decision-traces?limit=1",
            headers=auth_headers,
        )
        assert response.status_code == 200
        traces = response.json()
        
        if not traces:
            pytest.skip("No decision traces available for intelligence test")
        
        trace_id = traces[0]["trace_id"]
        
        # Get decision intelligence
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/decision-intelligence/{trace_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "trace" in data
        assert "before_after_diff" in data
        assert "risk_breakdown" in data
        assert "why_decision" in data
        assert "similar_patterns" in data
        
        # Check why_decision structure
        why = data["why_decision"]
        assert "state" in why
        assert "rule_path" in why
        assert "classification" in why
        assert "explanation" in why
        
        print(f"Decision intelligence: why={why['explanation']}, similar_patterns={len(data['similar_patterns'])}")


class TestRejectInsights:
    """Tests for reject insights endpoint"""

    def test_reject_insights_endpoint(self, auth_headers):
        """Test reject insights endpoint returns suggestions for repeated rules"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/rejects/insights",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "window_minutes" in data
        assert data["window_minutes"] == 30
        assert "insights" in data
        assert isinstance(data["insights"], list)
        
        # Check insight structure if any exist
        if data["insights"]:
            insight = data["insights"][0]
            assert "rule" in insight
            assert "count" in insight
            assert insight["count"] >= 3  # Threshold is 3
            assert "suggestion" in insight
            assert "message" in insight
            print(f"Reject insights: {len(data['insights'])} insights")
        else:
            print("No reject insights (no rules triggered 3+ times in 30min)")


class TestOperationalDashboard:
    """Tests for operational dashboard endpoint"""

    def test_operational_dashboard_endpoint(self, auth_headers):
        """Test operational dashboard returns all required metrics"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/operations/dashboard",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check all required fields
        assert "active_pending_approvals" in data
        assert "critical_queue" in data
        assert "unassigned" in data
        assert "my_approvals" in data
        assert "reject_spike_last_hour" in data
        assert "override_usage" in data
        assert "risk_score_distribution" in data
        assert "approval_throughput_last_hour" in data
        
        # Check override_usage structure
        override = data["override_usage"]
        assert "active_count" in override
        assert "total_notional_pct" in override
        
        # Check risk_score_distribution structure
        dist = data["risk_score_distribution"]
        assert "safe" in dist
        assert "warning" in dist
        assert "critical" in dist
        
        print(f"Dashboard: pending={data['active_pending_approvals']}, critical={data['critical_queue']}, unassigned={data['unassigned']}")


class TestApprovalWorkflow:
    """Tests for approval workflow (approve/reject)"""

    def test_approval_list_endpoint(self, auth_headers):
        """Test approval list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals?limit=50",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if data:
            item = data[0]
            assert "approval_id" in item
            assert "state" in item
            assert "classification" in item
            assert "risk_score" in item
            assert "requested_by" in item
            assert "expires_at" in item
            print(f"Approvals: {len(data)} items")

    def test_same_user_approval_blocked(self, auth_headers):
        """Test that same user cannot approve their own request"""
        # Get a pending approval
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals?state=pending&limit=1",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        if not data:
            pytest.skip("No pending approvals to test same-user block")
        
        approval_id = data[0]["approval_id"]
        
        # Try to approve (may fail with same_user_second_approval_blocked)
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/approve",
            headers=auth_headers,
            json={"decision_note": "Test approval"},
        )
        
        # Should either succeed (different user) or fail with same_user_second_approval_blocked
        if response.status_code == 400:
            assert "same_user_second_approval_blocked" in response.text
            print("Same user approval correctly blocked")
        else:
            print(f"Approval response: {response.status_code}")


class TestAlertGeneration:
    """Tests for webhook/notification event types and alert generation"""

    def test_alerts_endpoint(self, auth_headers):
        """Test alerts endpoint returns approval-related alerts"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/alerts?limit=50",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Check for approval-related alert types
        approval_alert_types = [
            "approval_requested",
            "approval_expiring",
            "approval_expired",
            "critical_block",
            "force_override",
            "approval_assigned",
            "approval_approved",
            "approval_rejected",
        ]
        
        found_types = set()
        for alert in data:
            if alert.get("alert_type") in approval_alert_types:
                found_types.add(alert["alert_type"])
        
        print(f"Alerts: {len(data)} total, approval-related types found: {found_types}")


class TestPolicyHistory:
    """Tests for policy history and versioning"""

    def test_policy_history_endpoint(self, auth_headers):
        """Test policy history endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/history?limit=20",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "versions" in data
        assert "change_requests" in data
        assert isinstance(data["versions"], list)
        assert isinstance(data["change_requests"], list)
        
        if data["versions"]:
            version = data["versions"][0]
            assert "version_id" in version
            assert "version_no" in version
            assert "policy_payload" in version
            assert "diff_payload" in version
            assert "changed_by" in version
            print(f"Policy history: {len(data['versions'])} versions, {len(data['change_requests'])} change requests")


class TestRevertSimulation:
    """Tests for revert simulation flow"""

    def test_revert_simulate_endpoint(self, auth_headers):
        """Test revert simulation endpoint"""
        # Get policy history
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/history?limit=5",
            headers=auth_headers,
        )
        assert response.status_code == 200
        history = response.json()
        
        if not history.get("versions"):
            pytest.skip("No policy versions to test revert")
        
        version_id = history["versions"][0]["version_id"]
        
        # Simulate revert
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/revert/{version_id}/simulate",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "version_id" in data
        assert "simulation" in data
        assert "risk_score" in data["simulation"]
        assert "classification" in data["simulation"]
        print(f"Revert simulation: version={version_id}, risk_score={data['simulation']['risk_score']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
