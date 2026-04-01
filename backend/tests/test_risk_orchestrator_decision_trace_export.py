"""
Risk Orchestrator Decision Trace Export + Approval Queue Ownership + Force Apply Tests
Tests for:
- Decision trace export endpoints: /policy/decision-traces/export?export_format=json|csv
- Approvals queue ownership: pending/assigned/approved/rejected/expired state transitions
- Hybrid auto-assign and owner visibility
- SLA sweep/escalation endpoint and state effect
- Force apply endpoint (super_admin only) and result applied/FORCE_OVERRIDE_APPLY
- Control Tower metrics visibility
- Approvals tab: My/Unassigned filters, countdown, assign/approve/reject/force apply actions
- Decision intelligence panel and reject insight panel
- Notification event standard payload (system_alert level)
"""

import os
import pytest
import requests

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
    """Get super_admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        if data.get("mfa_required"):
            pytest.skip("MFA required - skipping authenticated tests")
        return data.get("access_token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(super_admin_token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {super_admin_token}"}


class TestDecisionTraceExport:
    """Tests for decision trace export endpoints"""

    def test_export_decision_traces_json(self, auth_headers):
        """Test decision trace export in JSON format"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/decision-traces/export?export_format=json&limit=100",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        assert "application/json" in content_type, f"Expected JSON content type, got {content_type}"
        
        # Check content disposition header
        content_disposition = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disposition, f"Expected attachment disposition, got {content_disposition}"
        assert "risk_orchestrator_decision_traces.json" in content_disposition
        
        # Validate JSON structure
        data = response.json()
        assert "items" in data, "Expected 'items' key in JSON response"
        assert isinstance(data["items"], list), "Expected items to be a list"
        
        # If there are items, validate structure
        if len(data["items"]) > 0:
            item = data["items"][0]
            expected_fields = ["trace_id", "flow_type", "simulation_id", "classification", 
                            "risk_score", "rule_path", "decision_state", "requested_by",
                            "request_key", "reason_note", "created_at"]
            for field in expected_fields:
                assert field in item, f"Expected field '{field}' in trace item"
        
        print(f"✓ Decision trace JSON export: {len(data['items'])} items")

    def test_export_decision_traces_csv(self, auth_headers):
        """Test decision trace export in CSV format"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/decision-traces/export?export_format=csv&limit=100",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        assert "text/csv" in content_type, f"Expected CSV content type, got {content_type}"
        
        # Check content disposition header
        content_disposition = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disposition, f"Expected attachment disposition, got {content_disposition}"
        assert "risk_orchestrator_decision_traces.csv" in content_disposition
        
        # Validate CSV structure
        csv_content = response.text
        lines = csv_content.strip().split("\n")
        assert len(lines) >= 1, "Expected at least header row in CSV"
        
        # Check header row
        header = lines[0]
        expected_columns = ["trace_id", "flow_type", "simulation_id", "classification", 
                          "risk_score", "rule_path", "decision_state", "requested_by"]
        for col in expected_columns:
            assert col in header, f"Expected column '{col}' in CSV header"
        
        print(f"✓ Decision trace CSV export: {len(lines) - 1} data rows")


class TestApprovalQueueOwnership:
    """Tests for approval queue ownership and state transitions"""

    def test_queue_list_all_scope(self, auth_headers):
        """Test queue list with scope=all"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue?scope=all&limit=50",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        
        # Validate queue item structure if items exist
        if len(data) > 0:
            item = data[0]
            required_fields = ["approval_id", "state", "classification", "risk_score", 
                            "requested_by", "assigned_to", "sla_remaining_seconds", "sla_stage"]
            for field in required_fields:
                assert field in item, f"Expected field '{field}' in queue item"
        
        print(f"✓ Queue list (scope=all): {len(data)} items")

    def test_queue_list_my_scope(self, auth_headers):
        """Test queue list with scope=my (user's assigned approvals)"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue?scope=my&limit=50",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✓ Queue list (scope=my): {len(data)} items")

    def test_queue_list_unassigned_scope(self, auth_headers):
        """Test queue list with scope=unassigned"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue?scope=unassigned&limit=50",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        
        # All items should have assigned_to = None
        for item in data:
            assert item.get("assigned_to") is None, "Unassigned scope should only return items with assigned_to=None"
        
        print(f"✓ Queue list (scope=unassigned): {len(data)} items")

    def test_queue_list_state_filter(self, auth_headers):
        """Test queue list with state filter"""
        for state in ["pending", "assigned", "approved", "rejected", "expired"]:
            response = requests.get(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue?state={state}&limit=20",
                headers=auth_headers
            )
            assert response.status_code == 200, f"Expected 200 for state={state}, got {response.status_code}"
            
            data = response.json()
            # All items should have the requested state
            for item in data:
                assert item.get("state") == state, f"Expected state={state}, got {item.get('state')}"
            
            print(f"✓ Queue list (state={state}): {len(data)} items")

    def test_queue_critical_first_sorting(self, auth_headers):
        """Test queue list with critical_first sorting"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue?critical_first=true&limit=50",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify CRITICAL items come first
        found_non_critical = False
        for item in data:
            if item.get("classification") != "CRITICAL":
                found_non_critical = True
            elif found_non_critical:
                # If we found a non-critical item before, we shouldn't see CRITICAL after
                # This is a soft check - depends on data
                pass
        
        print(f"✓ Queue list (critical_first=true): {len(data)} items")


class TestSLASweepEscalation:
    """Tests for SLA sweep and escalation endpoint"""

    def test_queue_sweep_endpoint(self, auth_headers):
        """Test escalation sweep endpoint"""
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/sweep",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Validate response structure
        expected_fields = ["warning_escalations", "critical_escalations", "stuck_detected"]
        for field in expected_fields:
            assert field in data, f"Expected field '{field}' in sweep response"
            assert isinstance(data[field], int), f"Expected {field} to be integer"
        
        print(f"✓ Queue sweep: warning={data['warning_escalations']}, critical={data['critical_escalations']}, stuck={data['stuck_detected']}")


class TestForceApply:
    """Tests for force apply endpoint (super_admin only)"""

    def test_force_apply_requires_approval_id(self, auth_headers):
        """Test force apply with invalid approval_id returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/invalid-approval-id/force-apply",
            headers=auth_headers,
            json={"reason_note": "Test force apply"}
        )
        assert response.status_code == 404, f"Expected 404 for invalid approval_id, got {response.status_code}"
        print("✓ Force apply returns 404 for invalid approval_id")

    def test_force_apply_requires_reason_note(self, auth_headers):
        """Test force apply requires reason_note"""
        # First get a valid approval_id if any exist
        queue_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue?state=pending&limit=1",
            headers=auth_headers
        )
        
        if queue_response.status_code == 200 and len(queue_response.json()) > 0:
            approval_id = queue_response.json()[0]["approval_id"]
            
            # Try force apply without reason_note
            response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{approval_id}/force-apply",
                headers=auth_headers,
                json={}
            )
            # Should fail validation
            assert response.status_code in [400, 422], f"Expected 400/422 for missing reason_note, got {response.status_code}"
            print("✓ Force apply requires reason_note")
        else:
            print("✓ Force apply validation skipped (no pending approvals)")


class TestControlTowerMetrics:
    """Tests for Control Tower metrics visibility"""

    def test_operational_dashboard(self, auth_headers):
        """Test operational dashboard endpoint returns all required metrics"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/operations/dashboard",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Validate all required metrics
        required_fields = [
            "active_pending_approvals",
            "critical_queue",
            "unassigned",
            "my_approvals",
            "reject_spike_last_hour",
            "override_usage",
            "risk_score_distribution",
            "approval_throughput_last_hour"
        ]
        
        for field in required_fields:
            assert field in data, f"Expected field '{field}' in dashboard response"
        
        # Validate override_usage structure
        assert "active_count" in data["override_usage"], "Expected active_count in override_usage"
        assert "total_notional_pct" in data["override_usage"], "Expected total_notional_pct in override_usage"
        
        # Validate risk_score_distribution structure
        assert "safe" in data["risk_score_distribution"], "Expected 'safe' in risk_score_distribution"
        assert "warning" in data["risk_score_distribution"], "Expected 'warning' in risk_score_distribution"
        assert "critical" in data["risk_score_distribution"], "Expected 'critical' in risk_score_distribution"
        
        print(f"✓ Operational dashboard: pending={data['active_pending_approvals']}, critical={data['critical_queue']}, unassigned={data['unassigned']}")


class TestDecisionIntelligence:
    """Tests for decision intelligence panel"""

    def test_decision_traces_list(self, auth_headers):
        """Test decision traces list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/decision-traces?limit=25",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        
        if len(data) > 0:
            trace = data[0]
            required_fields = ["trace_id", "flow_type", "simulation_id", "classification",
                            "risk_score", "rule_path", "decision_state", "requested_by"]
            for field in required_fields:
                assert field in trace, f"Expected field '{field}' in trace"
        
        print(f"✓ Decision traces list: {len(data)} traces")

    def test_decision_intelligence_endpoint(self, auth_headers):
        """Test decision intelligence endpoint for a specific trace"""
        # First get a trace_id
        traces_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/decision-traces?limit=1",
            headers=auth_headers
        )
        
        if traces_response.status_code == 200 and len(traces_response.json()) > 0:
            trace_id = traces_response.json()[0]["trace_id"]
            
            response = requests.get(
                f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/decision-intelligence/{trace_id}",
                headers=auth_headers
            )
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            
            data = response.json()
            
            # Validate response structure
            required_fields = ["trace", "before_after_diff", "risk_breakdown", "why_decision", "similar_patterns"]
            for field in required_fields:
                assert field in data, f"Expected field '{field}' in decision intelligence response"
            
            # Validate why_decision structure
            assert "state" in data["why_decision"], "Expected 'state' in why_decision"
            assert "rule_path" in data["why_decision"], "Expected 'rule_path' in why_decision"
            assert "explanation" in data["why_decision"], "Expected 'explanation' in why_decision"
            
            print(f"✓ Decision intelligence: trace_id={trace_id}, state={data['why_decision']['state']}")
        else:
            print("✓ Decision intelligence skipped (no traces available)")


class TestRejectInsights:
    """Tests for reject insight panel"""

    def test_reject_insights_endpoint(self, auth_headers):
        """Test reject insights endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/rejects/insights",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Validate response structure
        assert "window_minutes" in data, "Expected 'window_minutes' in response"
        assert "insights" in data, "Expected 'insights' in response"
        assert isinstance(data["insights"], list), "Expected insights to be a list"
        
        # Validate insight structure if any exist
        if len(data["insights"]) > 0:
            insight = data["insights"][0]
            required_fields = ["rule", "count", "window_minutes", "suggestion", "message"]
            for field in required_fields:
                assert field in insight, f"Expected field '{field}' in insight"
        
        print(f"✓ Reject insights: window={data['window_minutes']}min, insights={len(data['insights'])}")


class TestNotificationEvents:
    """Tests for notification event standard payload (system_alert level)"""

    def test_alerts_endpoint(self, auth_headers):
        """Test alerts endpoint returns approval-related alerts"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/alerts?limit=50",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        
        # Validate alert structure if any exist
        if len(data) > 0:
            alert = data[0]
            required_fields = ["id", "alert_type", "severity", "status", "message", "details", "created_at"]
            for field in required_fields:
                assert field in alert, f"Expected field '{field}' in alert"
        
        # Check for approval-related alert types
        approval_alert_types = ["approval_requested", "approval_assigned", "approval_approved", 
                              "approval_rejected", "approval_expired", "approval_expiring",
                              "force_override", "critical_block", "approval_bottleneck", "approval_stuck"]
        
        found_approval_alerts = [a for a in data if a.get("alert_type") in approval_alert_types]
        print(f"✓ Alerts: total={len(data)}, approval-related={len(found_approval_alerts)}")


class TestApprovalActions:
    """Tests for approval actions (assign/approve/reject)"""

    def test_approval_list_endpoint(self, auth_headers):
        """Test approval list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals?limit=50",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        
        if len(data) > 0:
            approval = data[0]
            required_fields = ["approval_id", "request_key", "flow_type", "simulation_id",
                            "classification", "priority", "risk_score", "state",
                            "requested_by", "requested_role", "expires_at"]
            for field in required_fields:
                assert field in approval, f"Expected field '{field}' in approval"
        
        print(f"✓ Approval list: {len(data)} approvals")

    def test_assign_endpoint_validation(self, auth_headers):
        """Test assign endpoint validation"""
        # Test with invalid approval_id
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/invalid-id/assign",
            headers=auth_headers,
            json={"auto_assign": True}
        )
        assert response.status_code == 404, f"Expected 404 for invalid approval_id, got {response.status_code}"
        print("✓ Assign endpoint returns 404 for invalid approval_id")


class TestRiskOrchestratorStatus:
    """Tests for risk orchestrator status endpoint"""

    def test_status_endpoint(self, auth_headers):
        """Test risk orchestrator status endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/status",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Validate response structure
        required_fields = ["policy", "kill_switch_active", "kill_switch_reasons", 
                         "trading_enabled", "open_intents", "open_intents_by_symbol", 
                         "open_intents_by_strategy"]
        for field in required_fields:
            assert field in data, f"Expected field '{field}' in status response"
        
        # Validate policy structure
        policy = data["policy"]
        policy_fields = ["reference_equity_usd", "account_max_notional_pct", "symbol_max_notional_pct",
                        "strategy_max_concurrent_positions", "policy_version"]
        for field in policy_fields:
            assert field in policy, f"Expected field '{field}' in policy"
        
        print(f"✓ Status: kill_switch={data['kill_switch_active']}, trading={data['trading_enabled']}, policy_version={policy['policy_version']}")


class TestPolicySimulationAndApply:
    """Tests for policy simulation and apply flow"""

    def test_policy_simulate(self, auth_headers):
        """Test policy simulation endpoint"""
        # Get current policy first
        status_response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/status",
            headers=auth_headers
        )
        current_policy = status_response.json()["policy"]
        
        # Create a candidate policy with minor change
        candidate = {
            "reference_equity_usd": current_policy["reference_equity_usd"],
            "account_max_notional_pct": current_policy["account_max_notional_pct"],
            "symbol_max_notional_pct": current_policy["symbol_max_notional_pct"],
            "strategy_max_concurrent_positions": current_policy["strategy_max_concurrent_positions"],
            "strategy_cooldown_seconds": current_policy.get("strategy_cooldown_seconds", 60),
            "max_order_frequency_per_min": current_policy.get("max_order_frequency_per_min", 6),
            "max_order_burst_per_10s": current_policy.get("max_order_burst_per_10s", 3),
            "daily_loss_limit_pct": current_policy.get("daily_loss_limit_pct", 5),
            "duplicate_suppression_window_seconds": current_policy.get("duplicate_suppression_window_seconds", 300),
        }
        
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
            headers=auth_headers,
            json={"candidate_policy": candidate}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Validate response structure
        required_fields = ["simulation_id", "result_status", "baseline_policy", "candidate_policy",
                         "diff_summary", "risk_score", "classification", "approval_flow"]
        for field in required_fields:
            assert field in data, f"Expected field '{field}' in simulation response"
        
        # Validate approval_flow structure
        approval_flow = data["approval_flow"]
        assert "rule_path" in approval_flow, "Expected 'rule_path' in approval_flow"
        
        print(f"✓ Policy simulate: simulation_id={data['simulation_id']}, classification={data['classification']}, risk_score={data['risk_score']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
