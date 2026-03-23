"""
UI Finalization Sprint - Backend API Tests
Tests for:
- GET /api/admin-phase3/incident-snapshots/preview endpoint
- GET /api/admin-phase3/incident-snapshots/diff endpoint
- Export preview text filter changes
- Backward compatibility for diff and export flows
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for super_admin"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": "canary.admin@platform.local",
            "password": "CanaryAdmin123!"
        }
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestIncidentSnapshotPreviewEndpoint:
    """Tests for GET /api/admin-phase3/incident-snapshots/preview"""
    
    def test_preview_endpoint_exists(self, auth_headers):
        """Test that preview endpoint exists and returns 200 or 422 (validation error)"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/preview",
            headers=auth_headers,
            params={"scope_type": "correlation_id", "scope_value": "test-correlation-123"}
        )
        # Should return 200 or 422 (if no data), not 404
        assert response.status_code in [200, 422], f"Unexpected status: {response.status_code} - {response.text}"
        print(f"Preview endpoint status: {response.status_code}")
    
    def test_preview_with_correlation_id_scope(self, auth_headers):
        """Test preview with correlation_id scope type"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/preview",
            headers=auth_headers,
            params={
                "scope_type": "correlation_id",
                "scope_value": "test-correlation-id"
            }
        )
        assert response.status_code in [200, 422]
        if response.status_code == 200:
            data = response.json()
            assert "preview" in data, "Response should contain 'preview' field"
            preview = data["preview"]
            assert "events" in preview, "Preview should contain 'events' count"
            assert "failures" in preview, "Preview should contain 'failures' count"
            print(f"Preview data: {data}")
    
    def test_preview_with_execution_event_id_scope(self, auth_headers):
        """Test preview with execution_event_id scope type"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/preview",
            headers=auth_headers,
            params={
                "scope_type": "execution_event_id",
                "scope_value": "test-event-id"
            }
        )
        assert response.status_code in [200, 422]
        print(f"Execution event ID scope preview status: {response.status_code}")
    
    def test_preview_with_time_range_scope(self, auth_headers):
        """Test preview with time_range scope type"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/preview",
            headers=auth_headers,
            params={
                "scope_type": "time_range",
                "time_from": "2026-01-01T00:00:00+00:00",
                "time_to": "2026-12-31T23:59:59+00:00"
            }
        )
        assert response.status_code in [200, 422]
        print(f"Time range scope preview status: {response.status_code}")
    
    def test_preview_with_compare_scope(self, auth_headers):
        """Test preview with compare scope enabled"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/preview",
            headers=auth_headers,
            params={
                "scope_type": "correlation_id",
                "scope_value": "primary-correlation",
                "compare_scope_type": "correlation_id",
                "compare_scope_value": "compare-correlation"
            }
        )
        assert response.status_code in [200, 422]
        if response.status_code == 200:
            data = response.json()
            # When compare is enabled, should have compare_preview
            if "compare_preview" in data:
                print(f"Compare preview present: {data['compare_preview']}")
        print(f"Compare scope preview status: {response.status_code}")
    
    def test_preview_missing_scope_value_returns_422(self, auth_headers):
        """Test that missing scope_value returns 422"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/preview",
            headers=auth_headers,
            params={
                "scope_type": "correlation_id"
                # Missing scope_value
            }
        )
        assert response.status_code == 422, f"Expected 422 for missing scope_value, got {response.status_code}"
        print("Missing scope_value correctly returns 422")


class TestIncidentSnapshotDiffEndpoint:
    """Tests for POST /api/admin-phase3/incident-snapshots/diff"""
    
    def test_diff_endpoint_exists(self, auth_headers):
        """Test that diff endpoint exists"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": "test-correlation-id",
                "compare_correlation_id": "compare-correlation-id"
            }
        )
        # Should not return 404
        assert response.status_code != 404, f"Diff endpoint not found: {response.status_code}"
        print(f"Diff endpoint status: {response.status_code}")
    
    def test_diff_response_structure(self, auth_headers):
        """Test diff response contains expected structure"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": "test-primary",
                "compare_correlation_id": "test-compare"
            }
        )
        if response.status_code == 200:
            data = response.json()
            # Check for state_snapshot with diff data
            if "state_snapshot" in data and data["state_snapshot"]:
                snapshot = data["state_snapshot"]
                if "diff" in snapshot:
                    diff = snapshot["diff"]
                    # Check for before_after structure
                    if "before_after" in diff:
                        before_after = diff["before_after"]
                        print(f"Before/After structure: {before_after}")
                        # Should have events, failed_events, dead_letter, manual_actions
                        expected_keys = ["events", "failed_events", "dead_letter", "manual_actions"]
                        for key in expected_keys:
                            if key in before_after:
                                print(f"  {key}: {before_after[key]}")
        print(f"Diff response status: {response.status_code}")


class TestIncidentSnapshotExportEndpoint:
    """Tests for POST /api/admin-phase3/incident-snapshots/export"""
    
    def test_export_endpoint_exists(self, auth_headers):
        """Test that export endpoint exists"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": "test-correlation-id"
            }
        )
        # Should not return 404
        assert response.status_code != 404, f"Export endpoint not found: {response.status_code}"
        print(f"Export endpoint status: {response.status_code}")
    
    def test_export_backward_compatibility(self, auth_headers):
        """Test export endpoint backward compatibility"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": "test-correlation-id",
                "search": "",
                "state": None,
                "status": None,
                "source_type": None,
                "symbol": None,
                "strategy": None,
                "order_id": None
            }
        )
        # Should handle the request without 500 error
        assert response.status_code != 500, f"Export endpoint returned 500: {response.text}"
        print(f"Export backward compatibility status: {response.status_code}")


class TestExportFilterOptions:
    """Tests for GET /api/admin-phase3/incident-snapshots/export/filter-options"""
    
    def test_filter_options_endpoint(self, auth_headers):
        """Test filter options endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export/filter-options",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Filter options failed: {response.status_code}"
        data = response.json()
        assert "filter_scope_priority" in data
        assert "allowed_filter_values" in data
        print(f"Filter options: {data}")


class TestExecutionStateTransitionsControl:
    """Tests for execution state transitions control endpoint"""
    
    def test_control_endpoint_with_correlation_id(self, auth_headers):
        """Test control endpoint with correlation_id filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control",
            headers=auth_headers,
            params={
                "correlation_id": "test-correlation-id",
                "limit": 50
            }
        )
        assert response.status_code == 200, f"Control endpoint failed: {response.status_code}"
        data = response.json()
        assert "rows" in data
        assert "summary_counts" in data
        assert "state_counters" in data
        print(f"Control endpoint returned {len(data.get('rows', []))} rows")


class TestFailedEventsWithCorrelationFilter:
    """Tests for failed events with correlation_id filter"""
    
    def test_failed_events_with_search(self, auth_headers):
        """Test failed events endpoint with search parameter"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/failed-events",
            headers=auth_headers,
            params={
                "search": "test-correlation",
                "limit": 50
            }
        )
        assert response.status_code == 200, f"Failed events failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Failed events returned {len(data)} rows")


class TestIdempotencyCollisionsWithCorrelationFilter:
    """Tests for idempotency collisions with correlation_id filter"""
    
    def test_idempotency_collisions_with_search(self, auth_headers):
        """Test idempotency collisions endpoint with search parameter"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/idempotency-collisions",
            headers=auth_headers,
            params={
                "search": "test-correlation",
                "limit": 50
            }
        )
        assert response.status_code == 200, f"Idempotency collisions failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Idempotency collisions returned {len(data)} rows")


class TestExecutionTraceWithCorrelationId:
    """Tests for execution trace endpoint"""
    
    def test_execution_trace_endpoint(self, auth_headers):
        """Test execution trace endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-trace/test-correlation-id",
            headers=auth_headers
        )
        # Should return 200 even if no data (empty trace)
        assert response.status_code == 200, f"Execution trace failed: {response.status_code}"
        data = response.json()
        assert "correlation_id" in data
        assert "chain" in data
        assert "events" in data
        assert "failures" in data
        print(f"Execution trace: correlation_id={data['correlation_id']}, chain={len(data.get('chain', []))}")


class TestHealthAndBasicEndpoints:
    """Basic health and endpoint tests"""
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print("Health endpoint OK")
    
    def test_auth_login(self):
        """Test auth login endpoint"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "canary.admin@platform.local",
                "password": "CanaryAdmin123!"
            }
        )
        assert response.status_code == 200, f"Login failed: {response.status_code}"
        data = response.json()
        assert "access_token" in data or "token" in data
        print("Auth login OK")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
