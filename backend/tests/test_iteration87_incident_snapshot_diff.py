"""
Iteration 87 - Incident Snapshot JSON Diff + Human-Readable Summary Tests

Tests for P1 sprint features:
- POST /api/admin-phase3/incident-snapshots/export single snapshot flow
- POST export compare mode with diff.json and diff_summary.txt in ZIP
- diff.json scope_comparison and count_delta fields
- count_delta keys: events, transitions, failed_events, manual_actions, idempotency_collisions
- trend values: arttı/azaldı/değişmedi
- summary.json compare_scope metadata
- incompatible scope (e.g., primary correlation_id + compare time_range) returns 422
- Execution analytics regression tests
"""

import io
import json
import os
import zipfile
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://unified-orchestrator.preview.emergentagent.com"

TEST_CREDENTIALS = {
    "email": "canary.admin@platform.local",
    "password": "CanaryAdmin123!"
}


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=TEST_CREDENTIALS
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code}")
    data = response.json()
    token = data.get("access_token")
    if not token:
        pytest.skip("No access_token in response")
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestIncidentSnapshotExportSingleSnapshot:
    """Test single snapshot export flow (no compare)"""

    def test_export_with_time_range_scope_returns_zip(self, auth_headers):
        """Single snapshot export with time_range scope should return ZIP"""
        now = datetime.now(timezone.utc)
        time_from = (now - timedelta(days=7)).isoformat()
        time_to = now.isoformat()
        
        payload = {
            "time_from": time_from,
            "time_to": time_to
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert "application/zip" in response.headers.get("Content-Type", "") or \
               "application/x-zip" in response.headers.get("Content-Type", "")
        
        # Verify ZIP contents
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_list = zf.namelist()
            assert "summary.json" in file_list
            assert "trace.json" in file_list
            assert "events.csv" in file_list
            assert "transitions.csv" in file_list
            assert "failed_events.csv" in file_list
            assert "manual_actions.csv" in file_list
            assert "idempotency_collisions.csv" in file_list
            assert "README.txt" in file_list
            # No diff files in single snapshot mode
            assert "diff.json" not in file_list
            assert "diff_summary.txt" not in file_list
            
            # Verify summary.json structure
            summary_content = zf.read("summary.json").decode("utf-8")
            summary = json.loads(summary_content)
            assert "exported_at" in summary
            assert "filter_scope" in summary
            assert summary["filter_scope"] == "time_range"
            assert "row_counts" in summary
            assert "compare_scope" not in summary  # No compare in single mode

    def test_export_requires_scope(self, auth_headers):
        """Export without any scope should return 400"""
        payload = {}
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "correlation_id" in data["detail"] or "scope" in data["detail"].lower()


class TestIncidentSnapshotExportCompareMode:
    """Test compare mode with diff.json and diff_summary.txt"""

    def test_compare_mode_adds_diff_files_to_zip(self, auth_headers):
        """Compare mode should add diff.json and diff_summary.txt to ZIP"""
        now = datetime.now(timezone.utc)
        
        # Primary scope: last 7 days
        time_from_primary = (now - timedelta(days=7)).isoformat()
        time_to_primary = now.isoformat()
        
        # Compare scope: previous 7 days
        time_from_compare = (now - timedelta(days=14)).isoformat()
        time_to_compare = (now - timedelta(days=7)).isoformat()
        
        payload = {
            "time_from": time_from_primary,
            "time_to": time_to_primary,
            "compare_time_from": time_from_compare,
            "compare_time_to": time_to_compare
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify ZIP contains diff files
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_list = zf.namelist()
            assert "diff.json" in file_list, f"diff.json not in ZIP. Files: {file_list}"
            assert "diff_summary.txt" in file_list, f"diff_summary.txt not in ZIP. Files: {file_list}"

    def test_diff_json_has_scope_comparison_field(self, auth_headers):
        """diff.json should contain scope_comparison field"""
        now = datetime.now(timezone.utc)
        
        payload = {
            "time_from": (now - timedelta(days=7)).isoformat(),
            "time_to": now.isoformat(),
            "compare_time_from": (now - timedelta(days=14)).isoformat(),
            "compare_time_to": (now - timedelta(days=7)).isoformat()
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            diff_content = zf.read("diff.json").decode("utf-8")
            diff = json.loads(diff_content)
            
            assert "scope_comparison" in diff, f"scope_comparison not in diff.json: {diff.keys()}"
            assert "primary" in diff["scope_comparison"]
            assert "compare" in diff["scope_comparison"]
            assert "scope_type" in diff["scope_comparison"]["primary"]
            assert "scope_identifiers" in diff["scope_comparison"]["primary"]

    def test_diff_json_has_count_delta_with_required_keys(self, auth_headers):
        """diff.json count_delta should have all required keys"""
        now = datetime.now(timezone.utc)
        
        payload = {
            "time_from": (now - timedelta(days=7)).isoformat(),
            "time_to": now.isoformat(),
            "compare_time_from": (now - timedelta(days=14)).isoformat(),
            "compare_time_to": (now - timedelta(days=7)).isoformat()
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            diff_content = zf.read("diff.json").decode("utf-8")
            diff = json.loads(diff_content)
            
            assert "count_delta" in diff, f"count_delta not in diff.json: {diff.keys()}"
            
            required_keys = ["events", "transitions", "failed_events", "manual_actions", "idempotency_collisions"]
            for key in required_keys:
                assert key in diff["count_delta"], f"Key '{key}' not in count_delta: {diff['count_delta'].keys()}"
                
                # Each key should have current, compare, delta, trend
                item = diff["count_delta"][key]
                assert "current" in item, f"'current' not in count_delta[{key}]"
                assert "compare" in item, f"'compare' not in count_delta[{key}]"
                assert "delta" in item, f"'delta' not in count_delta[{key}]"
                assert "trend" in item, f"'trend' not in count_delta[{key}]"

    def test_trend_values_are_valid(self, auth_headers):
        """trend values should be arttı/azaldı/değişmedi"""
        now = datetime.now(timezone.utc)
        
        payload = {
            "time_from": (now - timedelta(days=7)).isoformat(),
            "time_to": now.isoformat(),
            "compare_time_from": (now - timedelta(days=14)).isoformat(),
            "compare_time_to": (now - timedelta(days=7)).isoformat()
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            diff_content = zf.read("diff.json").decode("utf-8")
            diff = json.loads(diff_content)
            
            valid_trends = {"arttı", "azaldı", "değişmedi"}
            for key, item in diff["count_delta"].items():
                trend = item.get("trend")
                assert trend in valid_trends, f"Invalid trend '{trend}' for key '{key}'. Expected one of {valid_trends}"

    def test_summary_json_has_compare_scope_metadata(self, auth_headers):
        """summary.json should have compare_scope metadata in compare mode"""
        now = datetime.now(timezone.utc)
        
        payload = {
            "time_from": (now - timedelta(days=7)).isoformat(),
            "time_to": now.isoformat(),
            "compare_time_from": (now - timedelta(days=14)).isoformat(),
            "compare_time_to": (now - timedelta(days=7)).isoformat()
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary_content = zf.read("summary.json").decode("utf-8")
            summary = json.loads(summary_content)
            
            assert "compare_scope" in summary, f"compare_scope not in summary.json: {summary.keys()}"
            assert "filter_scope" in summary["compare_scope"]
            assert "scope_identifiers" in summary["compare_scope"]
            assert "row_counts" in summary["compare_scope"]

    def test_diff_summary_txt_is_human_readable(self, auth_headers):
        """diff_summary.txt should be human-readable text"""
        now = datetime.now(timezone.utc)
        
        payload = {
            "time_from": (now - timedelta(days=7)).isoformat(),
            "time_to": now.isoformat(),
            "compare_time_from": (now - timedelta(days=14)).isoformat(),
            "compare_time_to": (now - timedelta(days=7)).isoformat()
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary_text = zf.read("diff_summary.txt").decode("utf-8")
            
            # Should contain header
            assert "Snapshot Diff Summary" in summary_text
            
            # Should contain key names
            assert "events" in summary_text
            assert "transitions" in summary_text
            assert "failed_events" in summary_text
            
            # Should contain trend words
            assert any(trend in summary_text for trend in ["arttı", "azaldı", "değişmedi"])


class TestIncompatibleScopeError:
    """Test incompatible scope returns 422 error"""

    def test_incompatible_scope_correlation_vs_time_range_returns_422(self, auth_headers):
        """Primary correlation_id + compare time_range should return 422"""
        now = datetime.now(timezone.utc)
        
        payload = {
            "correlation_id": "test-correlation-id-123",
            "compare_time_from": (now - timedelta(days=7)).isoformat(),
            "compare_time_to": now.isoformat()
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert "detail" in data
        assert "incompatible_scope" in data["detail"]
        assert "primary=" in data["detail"]
        assert "compare=" in data["detail"]

    def test_incompatible_scope_time_range_vs_correlation_returns_422(self, auth_headers):
        """Primary time_range + compare correlation_id should return 422"""
        now = datetime.now(timezone.utc)
        
        payload = {
            "time_from": (now - timedelta(days=7)).isoformat(),
            "time_to": now.isoformat(),
            "compare_correlation_id": "test-compare-correlation-id"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert "incompatible_scope" in data["detail"]

    def test_incompatible_scope_execution_event_vs_time_range_returns_422(self, auth_headers):
        """Primary execution_event_id + compare time_range should return 422"""
        now = datetime.now(timezone.utc)
        
        payload = {
            "execution_event_id": "test-event-id-123",
            "compare_time_from": (now - timedelta(days=7)).isoformat(),
            "compare_time_to": now.isoformat()
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert "incompatible_scope" in data["detail"]


class TestExecutionAnalyticsRegression:
    """Regression tests for execution analytics endpoints"""

    def test_execution_analytics_summary_works(self, auth_headers):
        """GET /api/admin-phase3/execution-analytics/summary should work"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "snapshot_at" in data
        assert "filters" in data
        assert "totals" in data
        assert "latency_per_state" in data
        assert "timeout_metrics" in data
        assert "retry_metrics" in data
        assert "failure_metrics" in data

    def test_execution_analytics_state_latency_works(self, auth_headers):
        """GET /api/admin-phase3/execution-analytics/state-latency should work"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/state-latency",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "snapshot_at" in data
        assert "filters" in data
        assert "totals" in data
        assert "rows" in data

    def test_execution_analytics_failure_trends_works(self, auth_headers):
        """GET /api/admin-phase3/execution-analytics/failure-trends should work"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/failure-trends",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "snapshot_at" in data
        assert "filters" in data
        assert "totals" in data
        assert "daily_trend" in data
        assert "top_failure_classes" in data

    def test_execution_alerts_list_works(self, auth_headers):
        """GET /api/admin-phase3/execution-alerts should work"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-alerts",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)


class TestExecutionStatesControlRegression:
    """Regression tests for execution states control endpoint"""

    def test_execution_state_transitions_control_works(self, auth_headers):
        """GET /api/admin-phase3/execution-state-transitions/control should work"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "rows" in data
        assert "summary_counts" in data
        assert "state_counters" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
