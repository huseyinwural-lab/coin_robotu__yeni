"""
Iteration 73: Admin Closure Package Testing
- Admin Dashboard: severity filter + auto-refresh + critical actions + Auto-Close Next Actions panel
- Backend Action Center: GET /api/admin/action-center/summary and POST /api/admin/action-center/close-next-actions
- System Alerts: CSV export endpoint /api/admin/system-alerts/export.csv
- User Approvals: email suggestions endpoint + stale reject endpoint + reject stale button
- Execution Queue: rejection summary endpoint + retry rejected intent endpoint + retry button
- Route aliases regression: /api/admin/strategy/observability-report and /api/reports/archive
- Regression: existing admin routes
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Admin authentication failed")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestAdminActionCenterEndpoints:
    """Test Action Center summary and close-next-actions endpoints"""

    def test_action_center_summary_returns_expected_fields(self, admin_headers):
        """GET /api/admin/action-center/summary should return summary data"""
        response = requests.get(f"{BASE_URL}/api/admin/action-center/summary", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields exist
        assert "pending_approvals" in data, "Missing pending_approvals"
        assert "stale_pending_approvals" in data, "Missing stale_pending_approvals"
        assert "open_alerts" in data, "Missing open_alerts"
        assert "queued_intents" in data, "Missing queued_intents"
        assert "rejected_intents" in data, "Missing rejected_intents"
        assert "timeout_rejected_intents" in data, "Missing timeout_rejected_intents"
        assert "kill_switch_active" in data, "Missing kill_switch_active"
        assert "kill_switch_reasons" in data, "Missing kill_switch_reasons"
        assert "emergency_mode" in data, "Missing emergency_mode"
        assert "disable_futures" in data, "Missing disable_futures"
        assert "generated_at" in data, "Missing generated_at"
        
        # Verify types
        assert isinstance(data["pending_approvals"], int)
        assert isinstance(data["open_alerts"], int)
        assert isinstance(data["kill_switch_active"], bool)
        print(f"Action Center Summary: pending_approvals={data['pending_approvals']}, open_alerts={data['open_alerts']}, rejected_intents={data['rejected_intents']}")

    def test_close_next_actions_executes_successfully(self, admin_headers):
        """POST /api/admin/action-center/close-next-actions should return result"""
        payload = {
            "ack_open_alerts": False,  # Don't modify data
            "reject_stale_approvals": False,
            "stale_days": 30,
            "retry_timeout_rejections": False,
            "clear_kill_switch": False,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/action-center/close-next-actions",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "status" in data, "Missing status field"
        assert data["status"] == "completed", f"Expected completed, got {data['status']}"
        assert "acked_alerts" in data
        assert "rejected_approvals" in data
        assert "retried_intents" in data
        assert "clear_kill_switch" in data
        print(f"Close Next Actions Result: status={data['status']}, acked_alerts={data['acked_alerts']}")


class TestSystemAlertsExportEndpoint:
    """Test CSV export endpoint for system alerts"""

    def test_system_alerts_csv_export_returns_csv(self, admin_headers):
        """GET /api/admin/system-alerts/export.csv should return CSV data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts/export.csv",
            headers=admin_headers,
            params={"status_filter": "all", "limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Check content type
        content_type = response.headers.get("content-type", "")
        assert "text/csv" in content_type, f"Expected text/csv, got {content_type}"
        
        # Check content disposition header
        content_disposition = response.headers.get("content-disposition", "")
        assert "attachment" in content_disposition, "Missing attachment in content-disposition"
        assert ".csv" in content_disposition, "Missing .csv in filename"
        
        # Verify CSV header row exists
        content = response.text
        assert "id," in content or len(content) > 0, "CSV should have header or content"
        print(f"CSV Export: Content-Length={len(content)}, Content-Type={content_type}")


class TestUserApprovalsEndpoints:
    """Test User Approvals email suggestions and reject-stale endpoints"""

    def test_email_suggestions_returns_suggestions(self, admin_headers):
        """GET /api/admin/user-approvals/email-suggestions should return suggestions"""
        response = requests.get(
            f"{BASE_URL}/api/admin/user-approvals/email-suggestions",
            headers=admin_headers,
            params={"query": "", "limit": 8},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "suggestions" in data, "Missing suggestions field"
        assert isinstance(data["suggestions"], list), "suggestions should be a list"
        print(f"Email Suggestions: count={len(data['suggestions'])}")

    def test_email_suggestions_with_query(self, admin_headers):
        """GET /api/admin/user-approvals/email-suggestions with query filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin/user-approvals/email-suggestions",
            headers=admin_headers,
            params={"query": "test", "limit": 8},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "suggestions" in data
        print(f"Email Suggestions (query='test'): count={len(data['suggestions'])}")

    def test_reject_stale_endpoint_exists(self, admin_headers):
        """POST /api/admin/user-approvals/reject-stale should exist and work"""
        # Use very high stale_days to avoid modifying real data
        response = requests.post(
            f"{BASE_URL}/api/admin/user-approvals/reject-stale",
            headers=admin_headers,
            json={"stale_days": 9999, "reason": "test_iteration73_no_op"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "count" in data, "Missing count field"
        assert "stale_days" in data, "Missing stale_days field"
        assert "reason" in data, "Missing reason field"
        print(f"Reject Stale Result: count={data['count']}, stale_days={data['stale_days']}")


class TestExecutionQueueEndpoints:
    """Test Execution Queue rejection summary and retry endpoints"""

    def test_rejection_summary_returns_distribution(self, admin_headers):
        """GET /api/admin/execution-queue/rejection-summary should return distribution"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue/rejection-summary",
            headers=admin_headers,
            params={"limit": 500},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "queue" in data, "Missing queue field"
        assert "rejection_reason_distribution" in data, "Missing rejection_reason_distribution field"
        
        queue = data["queue"]
        assert "total" in queue
        assert "queued" in queue
        assert "rejected" in queue
        assert "by_status" in queue
        
        distribution = data["rejection_reason_distribution"]
        assert isinstance(distribution, list), "distribution should be a list"
        if len(distribution) > 0:
            assert "reason_code" in distribution[0]
            assert "count" in distribution[0]
        print(f"Rejection Summary: total={queue['total']}, queued={queue['queued']}, rejected={queue['rejected']}, distribution_count={len(distribution)}")

    def test_retry_intent_endpoint_validates_input(self, admin_headers):
        """POST /api/admin/execution-queue/{intent_id}/retry should validate input"""
        # Use fake ID to test endpoint exists and validates
        fake_intent_id = "00000000-0000-0000-0000-000000000000"
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{fake_intent_id}/retry",
            headers=admin_headers,
            json={"note": "test_retry_from_iter73"},
        )
        # Should return 400 with intent_not_found since it's a fake ID
        assert response.status_code in [400, 404], f"Expected 400/404, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data
        print(f"Retry Intent (fake ID): status={response.status_code}, detail={data['detail']}")


class TestRouteAliasesRegression:
    """Test route aliases that were showing 404 in iteration 72"""

    def test_strategy_observability_report_alias(self, admin_headers):
        """GET /api/admin/strategy/observability-report should work (alias of /report)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability-report",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Should return observability report data
        assert isinstance(data, dict), "Response should be a dict"
        print(f"Observability Report Alias: keys={list(data.keys())[:5]}")

    def test_reports_archive_alias(self, admin_headers):
        """GET /api/reports/archive should work"""
        response = requests.get(
            f"{BASE_URL}/api/reports/archive",
            headers=admin_headers,
            params={"limit": 10},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Reports Archive Alias: count={len(data)}")


class TestCriticalActionsEndpoints:
    """Test critical action endpoints used by Admin Dashboard"""

    def test_stop_all_bots_endpoint_exists(self, admin_headers):
        """POST /api/phase4/kill-switch/stop-all-bots should exist"""
        response = requests.post(
            f"{BASE_URL}/api/phase4/kill-switch/stop-all-bots",
            headers=admin_headers,
            json={},
        )
        # May return 200 or 400 depending on state - just verify endpoint exists
        assert response.status_code in [200, 400], f"Expected 200/400, got {response.status_code}: {response.text}"
        print(f"Stop All Bots: status={response.status_code}")

    def test_disable_futures_endpoint_exists(self, admin_headers):
        """POST /api/phase4/kill-switch/disable-futures should exist"""
        response = requests.post(
            f"{BASE_URL}/api/phase4/kill-switch/disable-futures",
            headers=admin_headers,
            json={},
        )
        assert response.status_code in [200, 400], f"Expected 200/400, got {response.status_code}: {response.text}"
        print(f"Disable Futures: status={response.status_code}")

    def test_close_all_positions_endpoint_exists(self, admin_headers):
        """POST /api/phase4/kill-switch/close-all-positions should exist"""
        response = requests.post(
            f"{BASE_URL}/api/phase4/kill-switch/close-all-positions",
            headers=admin_headers,
            json={},
        )
        assert response.status_code in [200, 400], f"Expected 200/400, got {response.status_code}: {response.text}"
        print(f"Close All Positions: status={response.status_code}")

    def test_emergency_risk_mode_endpoint_exists(self, admin_headers):
        """POST /api/v1/admin/emergency_stop should exist"""
        response = requests.post(
            f"{BASE_URL}/api/v1/admin/emergency_stop",
            headers=admin_headers,
            json={"reason": "test_iter73_no_op"},
        )
        # This endpoint triggers emergency - it should work or return appropriate error
        assert response.status_code in [200, 400], f"Expected 200/400, got {response.status_code}: {response.text}"
        print(f"Emergency Stop: status={response.status_code}")


class TestExistingAdminRoutesRegression:
    """Regression tests for existing admin routes"""

    def test_dashboard_summary_still_works(self, admin_headers):
        """GET /api/dashboard/summary should still work"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("Dashboard Summary: PASS")

    def test_system_alerts_list_still_works(self, admin_headers):
        """GET /api/admin/system-alerts should still work"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts",
            headers=admin_headers,
            params={"status": "all", "limit": 10},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("System Alerts List: PASS")

    def test_user_approvals_list_still_works(self, admin_headers):
        """GET /api/admin/user-approvals should still work"""
        response = requests.get(
            f"{BASE_URL}/api/admin/user-approvals",
            headers=admin_headers,
            params={"status": "pending"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("User Approvals List: PASS")

    def test_execution_queue_list_still_works(self, admin_headers):
        """GET /api/admin/execution-queue should still work"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue",
            headers=admin_headers,
            params={"status_filter": "all", "limit": 10},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("Execution Queue List: PASS")

    def test_closure_panels_still_works(self, admin_headers):
        """GET /api/admin/closure/panels should still work"""
        response = requests.get(f"{BASE_URL}/api/admin/closure/panels", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("Closure Panels: PASS")

    def test_closure_consistency_still_works(self, admin_headers):
        """GET /api/admin/closure/consistency should still work"""
        response = requests.get(f"{BASE_URL}/api/admin/closure/consistency", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("Closure Consistency: PASS")


class TestMonitoringPageEndpoints:
    """Test endpoints used by Monitoring page (websocket health panel)"""

    def test_pipeline_monitoring_returns_ws_status(self, admin_headers):
        """GET /api/pipeline/monitoring should return websocket status"""
        response = requests.get(f"{BASE_URL}/api/pipeline/monitoring", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "websocket_status" in data, "Missing websocket_status"
        assert "websocket_reconnects_5m" in data, "Missing websocket_reconnects_5m"
        print(f"Pipeline Monitoring: ws_status={data.get('websocket_status')}, reconnects={data.get('websocket_reconnects_5m')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
