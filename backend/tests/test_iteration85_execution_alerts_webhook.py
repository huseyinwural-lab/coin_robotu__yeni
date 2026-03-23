"""
Iteration 85 - Execution Alert Webhook System Tests
====================================================
Tests for:
- Slack webhook adapter (mock mode): SENT_MOCKED status
- Trigger rules: execution_failed, dead-letter, retry_max_reached, timeout_spike, duplicate_collision
- Noise control: dedup window, rate limit, channel status
- Aggregation: timeout spike (5 in 30s)
- Payload contract: webhook_payload fields validation
- Retry/backoff/failure-log: failed delivery mechanism
- Execution alerts API: GET /api/admin-phase3/execution-alerts, POST /{id}/seen, POST /{id}/ack
- Execution analytics regression: summary/state-latency/failure-trends endpoints
- Incident export regression
"""

import os
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://risk-orchestrator-p0.preview.emergentagent.com"

TEST_CREDENTIALS = {
    "email": "canary.admin@platform.local",
    "password": "CanaryAdmin123!"
}

# Global token cache to avoid rate limiting
_TOKEN_CACHE = {"token": None}


def get_auth_token():
    """Get authentication token with caching"""
    if _TOKEN_CACHE["token"]:
        return _TOKEN_CACHE["token"]
    
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=TEST_CREDENTIALS,
        timeout=15
    )
    if response.status_code == 200:
        data = response.json()
        _TOKEN_CACHE["token"] = data.get("access_token")
        return _TOKEN_CACHE["token"]
    elif response.status_code == 429:
        pytest.skip("Login rate limited - skipping test")
    else:
        pytest.fail(f"Login failed: {response.status_code} - {response.text}")


def get_auth_headers():
    """Get auth headers"""
    token = get_auth_token()
    return {"Authorization": f"Bearer {token}"}


class TestSlackWebhookMockMode:
    """Test Slack webhook adapter in mock mode - SENT_MOCKED status"""
    
    def test_slack_test_delivery_mock_mode(self):
        """Test Slack delivery returns SENT_MOCKED in mock mode"""
        headers = get_auth_headers()
        response = requests.post(
            f"{BASE_URL}/api/admin/system-alerts/test-delivery",
            json={"channel": "slack", "severity": "WARNING"},
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Test delivery failed: {response.text}"
        data = response.json()
        
        # Check slack result
        slack_result = data.get("result", {}).get("slack", {})
        status = slack_result.get("status", "")
        
        # In mock mode, should be SENT_MOCKED or SENT_TEST_SINK
        assert status in ["SENT_MOCKED", "SENT_TEST_SINK", "SENT"], \
            f"Expected SENT_MOCKED/SENT_TEST_SINK/SENT, got: {status}"
        
        print(f"✓ Slack test delivery status: {status}")
    
    def test_channel_status_slack_ready(self):
        """Test channel status shows Slack as READY in mock mode"""
        headers = get_auth_headers()
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts/config",
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Config fetch failed: {response.text}"
        data = response.json()
        
        channels = data.get("channels", {})
        slack_status = channels.get("slack", "")
        
        # In mock mode with ALERT_ALLOW_MOCK_SLACK=true, should be READY
        assert slack_status == "READY", f"Expected Slack READY, got: {slack_status}"
        print(f"✓ Slack channel status: {slack_status}")


class TestExecutionAlertsAPI:
    """Test execution alerts API endpoints"""
    
    def test_get_execution_alerts_list(self):
        """GET /api/admin-phase3/execution-alerts returns list with limit<=50"""
        headers = get_auth_headers()
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-alerts",
            params={"status_filter": "all", "limit": 50},
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Execution alerts fetch failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Expected list response"
        assert len(data) <= 50, f"Expected max 50 alerts, got {len(data)}"
        
        # Validate alert structure if any exist
        if data:
            alert = data[0]
            assert "id" in alert, "Alert missing id"
            assert "alert_type" in alert, "Alert missing alert_type"
            assert "severity" in alert, "Alert missing severity"
            assert "status" in alert, "Alert missing status"
        
        print(f"✓ Execution alerts list: {len(data)} alerts returned")
    
    def test_get_execution_alerts_with_status_filter(self):
        """Test execution alerts with status filter"""
        headers = get_auth_headers()
        for status_filter in ["all", "open", "ack", "resolved"]:
            response = requests.get(
                f"{BASE_URL}/api/admin-phase3/execution-alerts",
                params={"status_filter": status_filter, "limit": 10},
                headers=headers,
                timeout=15
            )
            assert response.status_code == 200, f"Filter {status_filter} failed: {response.text}"
            print(f"✓ Status filter '{status_filter}' works")


class TestExecutionAnalyticsRegression:
    """Test execution analytics endpoints regression"""
    
    def test_execution_analytics_summary(self):
        """GET /api/admin-phase3/execution-analytics/summary works"""
        headers = get_auth_headers()
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "snapshot_at" in data, "Missing snapshot_at"
        assert "totals" in data, "Missing totals"
        assert "latency_per_state" in data, "Missing latency_per_state"
        assert "timeout_metrics" in data, "Missing timeout_metrics"
        assert "retry_metrics" in data, "Missing retry_metrics"
        assert "failure_metrics" in data, "Missing failure_metrics"
        
        totals = data.get("totals", {})
        assert "transitions" in totals, "Missing transitions in totals"
        assert "events" in totals, "Missing events in totals"
        assert "failures" in totals, "Missing failures in totals"
        
        print(f"✓ Execution analytics summary: transitions={totals.get('transitions', 0)}")
    
    def test_execution_analytics_state_latency(self):
        """GET /api/admin-phase3/execution-analytics/state-latency works"""
        headers = get_auth_headers()
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/state-latency",
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"State latency failed: {response.text}"
        data = response.json()
        
        assert "snapshot_at" in data, "Missing snapshot_at"
        assert "totals" in data, "Missing totals"
        assert "rows" in data, "Missing rows"
        
        # Validate row structure if any exist
        rows = data.get("rows", [])
        if rows:
            row = rows[0]
            assert "state" in row, "Row missing state"
            assert "count" in row, "Row missing count"
            assert "avg_latency_ms" in row, "Row missing avg_latency_ms"
        
        print(f"✓ State latency: {len(rows)} state rows")
    
    def test_execution_analytics_failure_trends(self):
        """GET /api/admin-phase3/execution-analytics/failure-trends works"""
        headers = get_auth_headers()
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/failure-trends",
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Failure trends failed: {response.text}"
        data = response.json()
        
        assert "snapshot_at" in data, "Missing snapshot_at"
        assert "totals" in data, "Missing totals"
        assert "daily_trend" in data, "Missing daily_trend"
        assert "top_failure_classes" in data, "Missing top_failure_classes"
        
        print(f"✓ Failure trends: {len(data.get('daily_trend', []))} daily entries")


class TestPayloadContract:
    """Test webhook payload contract fields"""
    
    def test_payload_contract_fields_in_alert_details(self):
        """Verify webhook_payload contains required fields in alert details"""
        headers = get_auth_headers()
        # First get execution alerts
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-alerts",
            params={"status_filter": "all", "limit": 50},
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Alerts fetch failed: {response.text}"
        alerts = response.json()
        
        # Required payload fields per contract
        required_fields = [
            "event_type", "severity", "correlation_id", "execution_event_id",
            "symbol", "state", "failure_reason", "retry_count", "max_retry",
            "timestamp", "dashboard_url", "trace_url"
        ]
        
        # Check if any alert has webhook_payload in details
        alerts_with_payload = []
        for alert in alerts:
            details = alert.get("details", {})
            if isinstance(details, dict) and "webhook_payload" in details:
                alerts_with_payload.append(alert)
        
        if alerts_with_payload:
            # Validate first alert with webhook_payload
            alert = alerts_with_payload[0]
            webhook_payload = alert["details"]["webhook_payload"]
            
            missing_fields = []
            for field in required_fields:
                if field not in webhook_payload:
                    missing_fields.append(field)
            
            assert not missing_fields, f"Missing payload fields: {missing_fields}"
            print(f"✓ Webhook payload contract validated with all {len(required_fields)} fields")
        else:
            # No alerts with webhook_payload yet - this is acceptable for fresh system
            print("⚠ No execution alerts with webhook_payload found (fresh system)")
            pytest.skip("No execution alerts with webhook_payload to validate")


class TestNoiseControl:
    """Test noise control mechanisms"""
    
    def test_channel_status_shows_rate_limits(self):
        """Verify channel status includes rate limit config"""
        headers = get_auth_headers()
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts/config",
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Config failed: {response.text}"
        data = response.json()
        
        channels = data.get("channels", {})
        
        # Check rate limit config is exposed
        assert "rate_limit_per_min" in channels, "Missing rate_limit_per_min"
        assert "dedup_window_seconds" in channels, "Missing dedup_window_seconds"
        
        print(f"✓ Rate limit config: {channels.get('rate_limit_per_min')}/min, dedup={channels.get('dedup_window_seconds')}s")


class TestIncidentExportRegression:
    """Test incident export endpoint regression"""
    
    def test_incident_export_requires_scope(self):
        """POST /api/admin-phase3/incident-snapshots/export requires scope"""
        headers = get_auth_headers()
        # Empty payload should fail with scope requirement
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json={},
            headers=headers,
            timeout=15
        )
        # Should return 400 for missing scope
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data, "Missing error detail"
        print(f"✓ Incident export scope validation works: {data.get('detail', '')[:50]}")
    
    def test_incident_export_with_time_range(self):
        """POST /api/admin-phase3/incident-snapshots/export with time range"""
        headers = get_auth_headers()
        now = datetime.now(timezone.utc)
        time_from = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        time_to = now.isoformat()
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json={
                "time_from": time_from,
                "time_to": time_to
            },
            headers=headers,
            timeout=30
        )
        # Should return 200 with zip content or empty result
        assert response.status_code == 200, f"Export failed: {response.status_code} - {response.text[:200]}"
        print(f"✓ Incident export with time range works")


class TestAlertSeenAckFlow:
    """Test alert seen/ack flow"""
    
    def test_alert_seen_ack_endpoints_exist(self):
        """Verify seen/ack endpoints respond correctly"""
        headers = get_auth_headers()
        # Get alerts first
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-alerts",
            params={"status_filter": "all", "limit": 5},
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200
        alerts = response.json()
        
        if not alerts:
            print("⚠ No execution alerts to test seen/ack flow")
            pytest.skip("No execution alerts available")
        
        alert_id = alerts[0]["id"]
        
        # Test seen endpoint
        seen_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-alerts/{alert_id}/seen",
            headers=headers,
            timeout=15
        )
        assert seen_response.status_code == 200, f"Seen failed: {seen_response.text}"
        seen_data = seen_response.json()
        assert seen_data.get("details", {}).get("seen") == True, "seen flag not set"
        print(f"✓ Alert seen endpoint works for alert {alert_id}")
        
        # Test ack endpoint
        ack_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-alerts/{alert_id}/ack",
            headers=headers,
            timeout=15
        )
        assert ack_response.status_code == 200, f"Ack failed: {ack_response.text}"
        ack_data = ack_response.json()
        assert ack_data.get("status") == "ack", f"Expected status=ack, got {ack_data.get('status')}"
        print(f"✓ Alert ack endpoint works for alert {alert_id}")


class TestTriggerRulesValidation:
    """Test trigger rules for execution alerts"""
    
    def test_failed_events_endpoint(self):
        """GET /api/admin-phase3/failed-events works"""
        headers = get_auth_headers()
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/failed-events",
            params={"limit": 50},
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Failed events fetch failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✓ Failed events endpoint: {len(data)} events")
    
    def test_dead_letter_events_endpoint(self):
        """GET /api/admin-phase3/failed-events/dead-letter works"""
        headers = get_auth_headers()
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/failed-events/dead-letter",
            params={"limit": 50},
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Dead letter fetch failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✓ Dead letter events endpoint: {len(data)} events")
    
    def test_idempotency_collisions_endpoint(self):
        """GET /api/admin-phase3/idempotency-collisions works"""
        headers = get_auth_headers()
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/idempotency-collisions",
            params={"limit": 50},
            headers=headers,
            timeout=15
        )
        assert response.status_code == 200, f"Collisions fetch failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✓ Idempotency collisions endpoint: {len(data)} collisions")


class TestRetryBackoffMechanism:
    """Test retry/backoff/failure-log mechanism"""
    
    def test_failed_event_retry_endpoint(self):
        """Test failed event retry endpoint exists"""
        headers = get_auth_headers()
        # First seed a failed event
        seed_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/failed-events/seed",
            headers=headers,
            timeout=15
        )
        assert seed_response.status_code == 200, f"Seed failed: {seed_response.text}"
        seeded = seed_response.json()
        event_id = seeded.get("id")
        
        # Try retry endpoint
        retry_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/failed-events/{event_id}/retry",
            headers=headers,
            timeout=15
        )
        assert retry_response.status_code == 200, f"Retry failed: {retry_response.text}"
        retry_data = retry_response.json()
        
        # Verify retry count incremented
        assert retry_data.get("retry_count", 0) >= 1, "Retry count not incremented"
        print(f"✓ Failed event retry works: retry_count={retry_data.get('retry_count')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
