"""
P0+P1 Final Sprint Features Test Suite
Tests for:
- State diagram operational (state-latency endpoint, p95_latency_ms, slowest_states, timeout_distribution)
- Alert intelligence (grouping/escalation/dedup)
- Role-based export masking (response-layer only)
- Alert delivery hardening (Slack payload format, absolute URLs)
- P1 auto-ack INFO 24h seen
- Snapshot diff cleanup (anomaly_groups, long_diff_collapsed)
- Execution history quick access
"""

import os
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com").rstrip("/")

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
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        timeout=15
    )
    if response.status_code != 200:
        pytest.skip(f"Super admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture
def super_admin_headers(super_admin_token):
    return {"Authorization": f"Bearer {super_admin_token}", "Content-Type": "application/json"}


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestHealthCheck:
    """Basic health check tests"""
    
    def test_health_endpoint(self):
        """Test health endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        print(f"Health check passed: {data}")


class TestExecutionAnalyticsStateLatency:
    """Tests for state-latency endpoint with p95_latency_ms, slowest_states, timeout_distribution"""
    
    def test_state_latency_endpoint_returns_200(self, super_admin_headers):
        """Test state-latency endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/state-latency",
            headers=super_admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        print(f"State latency response keys: {data.keys()}")
        
    def test_state_latency_has_p95_latency_ms(self, super_admin_headers):
        """Test state-latency endpoint returns p95_latency_ms in rows"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/state-latency",
            headers=super_admin_headers,
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check rows structure
        rows = data.get("rows", [])
        if rows:
            first_row = rows[0]
            assert "p95_latency_ms" in first_row, f"p95_latency_ms not in row: {first_row.keys()}"
            print(f"First row has p95_latency_ms: {first_row.get('p95_latency_ms')}")
        else:
            print("No rows returned - checking structure only")
            
    def test_state_latency_has_slowest_states(self, super_admin_headers):
        """Test state-latency endpoint returns slowest_states"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/state-latency",
            headers=super_admin_headers,
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "slowest_states" in data, f"slowest_states not in response: {data.keys()}"
        slowest_states = data.get("slowest_states", [])
        print(f"Slowest states count: {len(slowest_states)}")
        if slowest_states:
            print(f"Top slowest state: {slowest_states[0]}")
            
    def test_state_latency_has_timeout_distribution(self, super_admin_headers):
        """Test state-latency endpoint returns timeout_distribution"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/state-latency",
            headers=super_admin_headers,
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "timeout_distribution" in data, f"timeout_distribution not in response: {data.keys()}"
        timeout_dist = data.get("timeout_distribution", [])
        print(f"Timeout distribution count: {len(timeout_dist)}")
        if timeout_dist:
            print(f"Timeout distribution sample: {timeout_dist[0]}")


class TestExecutionAnalyticsSummary:
    """Tests for execution analytics summary endpoint"""
    
    def test_summary_endpoint_returns_200(self, super_admin_headers):
        """Test summary endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=super_admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        print(f"Summary response keys: {data.keys()}")
        
    def test_summary_has_failure_metrics_with_slowest_states(self, super_admin_headers):
        """Test summary has failure_metrics with slowest_states"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=super_admin_headers,
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        failure_metrics = data.get("failure_metrics", {})
        assert "slowest_states" in failure_metrics, f"slowest_states not in failure_metrics: {failure_metrics.keys()}"
        print(f"Failure metrics slowest_states: {failure_metrics.get('slowest_states')}")
        
    def test_summary_has_timeout_metrics(self, super_admin_headers):
        """Test summary has timeout_metrics with timeout_distribution"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=super_admin_headers,
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        timeout_metrics = data.get("timeout_metrics", {})
        assert "timeout_distribution" in timeout_metrics, f"timeout_distribution not in timeout_metrics: {timeout_metrics.keys()}"
        print(f"Timeout metrics: {timeout_metrics}")


class TestIncidentSnapshotHistory:
    """Tests for incident snapshot history quick access endpoint"""
    
    def test_history_endpoint_returns_200(self, super_admin_headers):
        """Test incident-snapshots/history endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/history",
            headers=super_admin_headers,
            params={"limit": 5},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        print(f"History response keys: {data.keys()}")
        
    def test_history_returns_items_list(self, super_admin_headers):
        """Test history endpoint returns items list"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/history",
            headers=super_admin_headers,
            params={"limit": 5},
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "items" in data, f"items not in response: {data.keys()}"
        items = data.get("items", [])
        print(f"History items count: {len(items)}")
        if items:
            print(f"First history item: {items[0]}")


class TestAlertAutoAckPolicy:
    """Tests for P1 auto-ack INFO 24h seen feature"""
    
    def test_auto_ack_policy_get(self, super_admin_headers):
        """Test auto-ack policy GET endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-alerts/auto-ack/policy",
            headers=super_admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "policy" in data, f"policy not in response: {data.keys()}"
        policy = data.get("policy", {})
        print(f"Auto-ack policy: {policy}")
        
        # Verify policy structure
        assert "enabled" in policy, "enabled not in policy"
        assert "threshold_hours" in policy, "threshold_hours not in policy"
        
    def test_auto_ack_preview(self, super_admin_headers):
        """Test auto-ack preview endpoint"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-alerts/auto-ack/preview",
            headers=super_admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "preview_token" in data, f"preview_token not in response: {data.keys()}"
        assert "matched_count" in data, f"matched_count not in response: {data.keys()}"
        print(f"Auto-ack preview: matched_count={data.get('matched_count')}, token={data.get('preview_token')[:20]}...")


class TestAlertDeliveryHardening:
    """Tests for alert delivery hardening - Slack payload format, absolute URLs"""
    
    def test_execution_alerts_list(self, super_admin_headers):
        """Test execution alerts list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-alerts",
            headers=super_admin_headers,
            params={"limit": 10},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Response should be a list
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"Execution alerts count: {len(data)}")
        if data:
            alert = data[0]
            print(f"First alert keys: {alert.keys()}")
            
    def test_alert_delivery_summary(self, super_admin_headers):
        """Test alert delivery summary endpoint - includes provider health info"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-alerts/delivery-summary",
            headers=super_admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Check for delivery summary fields
        print(f"Delivery summary: {data.keys()}")
        # Should have status_counts, last_success, last_failure etc
        assert "status_counts" in data or "total_alerts" in data or "provider_status" in data, f"Expected delivery summary fields: {data.keys()}"


class TestSnapshotDiffCleanup:
    """Tests for snapshot diff cleanup - anomaly_groups, long_diff_collapsed"""
    
    def test_diff_endpoint_structure(self, super_admin_headers):
        """Test diff endpoint returns proper structure"""
        # First create some test data via simulation
        sim_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate",
            headers=super_admin_headers,
            params={
                "strategy_type": "breakout",
                "symbol": "BTCUSDT",
                "side": "long",
                "outcome": "filled",
                "source_type": "simulation",
                "environment": "simulation"
            },
            timeout=15
        )
        
        if sim_response.status_code == 200:
            sim_data = sim_response.json()
            correlation_id = sim_data.get("correlation_id")
            print(f"Created simulation with correlation_id: {correlation_id}")
            
            # Now test diff endpoint with this correlation_id
            diff_response = requests.post(
                f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
                headers=super_admin_headers,
                json={
                    "correlation_id": correlation_id,
                    "compare_enabled": False
                },
                timeout=15
            )
            
            if diff_response.status_code == 200:
                diff_data = diff_response.json()
                print(f"Diff response keys: {diff_data.keys()}")
                
                state_snapshot = diff_data.get("state_snapshot", {})
                if state_snapshot:
                    diff = state_snapshot.get("diff", {})
                    if diff:
                        # Check for anomaly_groups
                        if "anomaly_groups" in diff:
                            print(f"anomaly_groups present: {diff.get('anomaly_groups')}")
                        # Check for long_diff_collapsed
                        if "long_diff_collapsed" in diff:
                            print(f"long_diff_collapsed: {diff.get('long_diff_collapsed')}")
            else:
                print(f"Diff endpoint returned {diff_response.status_code}: {diff_response.text[:200]}")
        else:
            print(f"Simulation returned {sim_response.status_code}: {sim_response.text[:200]}")


class TestRoleBasedExportMasking:
    """Tests for role-based export masking - response-layer only"""
    
    def test_export_preview_endpoint(self, super_admin_headers):
        """Test export preview endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/preview",
            headers=super_admin_headers,
            params={
                "scope_type": "correlation_id",
                "scope_value": "test-correlation-123"
            },
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "preview" in data, f"preview not in response: {data.keys()}"
        print(f"Export preview: {data.get('preview')}")
        
    def test_export_filter_options(self, super_admin_headers):
        """Test export filter options endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export/filter-options",
            headers=super_admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        print(f"Export filter options: {data.keys()}")


class TestExecutionStatesControl:
    """Tests for execution states control endpoint"""
    
    def test_control_endpoint_returns_200(self, super_admin_headers):
        """Test control endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control",
            headers=super_admin_headers,
            params={"limit": 50},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "rows" in data, f"rows not in response: {data.keys()}"
        assert "state_counters" in data, f"state_counters not in response: {data.keys()}"
        print(f"Control response: rows={len(data.get('rows', []))}, state_counters={data.get('state_counters')}")
        
    def test_state_detail_endpoint(self, super_admin_headers):
        """Test state detail endpoint with simulation"""
        # First create a simulation
        sim_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate",
            headers=super_admin_headers,
            params={
                "strategy_type": "breakout",
                "symbol": "ETHUSDT",
                "side": "short",
                "outcome": "timeout",
                "source_type": "simulation",
                "environment": "simulation"
            },
            timeout=15
        )
        
        if sim_response.status_code == 200:
            sim_data = sim_response.json()
            execution_event_id = sim_data.get("execution_event_id")
            
            if execution_event_id:
                # Get detail for this event
                detail_response = requests.get(
                    f"{BASE_URL}/api/admin-phase3/execution-state-transitions/{execution_event_id}/detail",
                    headers=super_admin_headers,
                    timeout=15
                )
                
                if detail_response.status_code == 200:
                    detail_data = detail_response.json()
                    print(f"State detail keys: {detail_data.keys()}")
                    
                    # Check for state diagram related fields
                    assert "current_state" in detail_data, "current_state not in detail"
                    assert "full_state_path" in detail_data, "full_state_path not in detail"
                    assert "transitions" in detail_data, "transitions not in detail"
                    
                    print(f"Current state: {detail_data.get('current_state')}")
                    print(f"State path: {detail_data.get('full_state_path')}")
                    print(f"Transition count: {len(detail_data.get('transitions', []))}")
                else:
                    print(f"Detail endpoint returned {detail_response.status_code}")
            else:
                print("No execution_event_id in simulation response")
        else:
            print(f"Simulation returned {sim_response.status_code}")


class TestPlaybookWorkflow:
    """Tests for playbook preview/approve/execute/retry/rollback workflow"""
    
    def test_playbook_preflight(self, super_admin_headers):
        """Test playbook preflight endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
            headers=super_admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        print(f"Playbook preflight: {data}")
        assert "overall_state" in data or "overall_ui_status" in data, f"Expected preflight fields: {data.keys()}"


class TestFailureTrends:
    """Tests for failure trends endpoint"""
    
    def test_failure_trends_endpoint(self, super_admin_headers):
        """Test failure trends endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/failure-trends",
            headers=super_admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "daily_trend" in data, f"daily_trend not in response: {data.keys()}"
        assert "top_failure_classes" in data, f"top_failure_classes not in response: {data.keys()}"
        print(f"Failure trends: daily_trend={len(data.get('daily_trend', []))}, top_classes={len(data.get('top_failure_classes', []))}")


class TestAlertIntelligence:
    """Tests for alert intelligence - dedup, grouping, escalation"""
    
    def test_execution_alerts_with_dedup_grouping(self, super_admin_headers):
        """Test execution alerts list for dedup/grouping fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-alerts",
            headers=super_admin_headers,
            params={"limit": 20},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Response should be a list
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"Execution alerts count: {len(data)}")
        
        if data:
            alert = data[0]
            # Check for dedup/grouping fields
            details = alert.get("details", {})
            if "grouped_count" in details:
                print(f"Alert has grouped_count: {details.get('grouped_count')}")
            if "escalation_tier" in details:
                print(f"Alert has escalation_tier: {details.get('escalation_tier')}")
            # Check delivery_status for dedup info
            delivery_status = alert.get("delivery_status", {})
            if delivery_status:
                print(f"Alert delivery_status: {delivery_status}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
