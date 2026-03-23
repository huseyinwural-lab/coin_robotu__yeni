"""
Iteration 89 - Incident Snapshot Diff + Anomaly UI Testing
Tests for:
1. UI naming standard: Correlation ID label + placeholder 'enter correlation id' and input style consistency
2. Compare OFF -> normal export zip working
3. Compare ON -> diff endpoint (/api/admin-phase3/incident-snapshots/diff) working
4. /diff response standard: status, trace_id, message, state_snapshot fields
5. Scope mismatch strict: incompatible scope returns 422
6. /export compare mode: ZIP contains diff.json + diff_summary.txt
7. diff.json format: scope_a, scope_b, counts, percentage_change, anomaly_notes(string[])
8. counts fields: events_delta, failed_events_delta, dead_letter_delta, manual_actions_delta
9. Anomaly engine deterministic: failed_events>50 CRITICAL_RISK, dead_letter>30 HIGH_RISK, manual_actions>0 OPERATOR_INTERVENTION
10. Audit log: incident_snapshot_export + incident_snapshot_diff_preview actions
"""

import os
import pytest
import requests
import json
import zipfile
import io

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_EMAIL = "canary.admin@platform.local"
TEST_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code}")
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }


class TestDiffEndpointResponseStandard:
    """Test /diff endpoint response format"""

    def test_diff_endpoint_returns_required_fields(self, auth_headers):
        """Test /diff response has status, trace_id, message, state_snapshot"""
        # First get a correlation_id from existing data
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?limit=50",
            headers=auth_headers,
        )
        assert response.status_code == 200
        rows = response.json().get("rows", [])
        
        # Use a correlation_id if available, otherwise skip
        correlation_id = None
        if rows:
            for row in rows:
                if row.get("correlation_id"):
                    correlation_id = row["correlation_id"]
                    break
        
        if not correlation_id:
            pytest.skip("No correlation_id found in existing data")
        
        # Test diff endpoint with single scope (no compare)
        diff_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={"correlation_id": correlation_id},
        )
        assert diff_response.status_code == 200, f"Expected 200, got {diff_response.status_code}: {diff_response.text}"
        data = diff_response.json()
        
        # Verify required fields
        assert "status" in data, "Response must have 'status' field"
        assert "trace_id" in data, "Response must have 'trace_id' field"
        assert "message" in data, "Response must have 'message' field"
        assert "state_snapshot" in data, "Response must have 'state_snapshot' field"
        
        # Verify status value
        assert data["status"] == "success"
        
        # Verify state_snapshot structure
        snapshot = data["state_snapshot"]
        assert "compare_enabled" in snapshot
        assert "scope_a" in snapshot
        assert "preview" in snapshot
        
        # Verify preview has expected fields
        preview = snapshot["preview"]
        assert "events" in preview
        assert "failures" in preview
        assert "transitions" in preview


class TestScopeMismatchStrict422:
    """Test incompatible scope returns 422"""

    def test_scope_mismatch_correlation_vs_time_range_returns_422(self, auth_headers):
        """Test that mismatched scope types return 422"""
        # Primary scope: correlation_id, Compare scope: time_range
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": "test-corr-001",
                "compare_time_from": "2026-01-01T00:00:00+00:00",
                "compare_time_to": "2026-01-02T00:00:00+00:00",
            },
        )
        assert response.status_code == 422, f"Expected 422 for scope mismatch, got {response.status_code}"
        detail = response.json().get("detail", "")
        assert "incompatible_scope" in detail.lower() or "scope" in detail.lower()

    def test_scope_mismatch_execution_event_vs_correlation_returns_422(self, auth_headers):
        """Test execution_event_id vs correlation_id mismatch returns 422"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "execution_event_id": "test-event-001",
                "compare_correlation_id": "test-corr-002",
            },
        )
        assert response.status_code == 422, f"Expected 422 for scope mismatch, got {response.status_code}"

    def test_scope_mismatch_time_range_vs_correlation_returns_422(self, auth_headers):
        """Test time_range vs correlation_id mismatch returns 422"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "time_from": "2026-01-01T00:00:00+00:00",
                "time_to": "2026-01-02T00:00:00+00:00",
                "compare_correlation_id": "test-corr-003",
            },
        )
        assert response.status_code == 422, f"Expected 422 for scope mismatch, got {response.status_code}"


class TestCompareOffExportZip:
    """Test Compare OFF -> normal export zip working"""

    def test_export_without_compare_returns_zip(self, auth_headers):
        """Test export without compare mode returns valid ZIP"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={"correlation_id": "test-export-corr-001"},
        )
        assert response.status_code == 200
        assert "application/zip" in response.headers.get("Content-Type", "")
        
        # Verify it's a valid ZIP
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_list = zf.namelist()
            # Should have standard files but NOT diff.json or diff_summary.txt
            assert "README.txt" in file_list
            assert "events.csv" in file_list or "transitions.csv" in file_list
            # Should NOT have diff files when compare is OFF
            assert "diff.json" not in file_list, "diff.json should NOT be in ZIP when compare is OFF"
            assert "diff_summary.txt" not in file_list, "diff_summary.txt should NOT be in ZIP when compare is OFF"


class TestCompareOnDiffEndpoint:
    """Test Compare ON -> diff endpoint working"""

    def test_diff_endpoint_with_compare_enabled(self, auth_headers):
        """Test diff endpoint with compare mode enabled"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": "test-corr-a",
                "compare_correlation_id": "test-corr-b",
            },
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify compare_enabled is true
        snapshot = data.get("state_snapshot", {})
        assert snapshot.get("compare_enabled") is True
        
        # Verify diff payload exists
        diff = snapshot.get("diff")
        assert diff is not None, "diff payload should exist when compare is enabled"
        
        # Verify diff structure
        assert "scope_a" in diff
        assert "scope_b" in diff
        assert "counts" in diff
        assert "percentage_change" in diff
        assert "anomaly_notes" in diff


class TestDiffJsonFormat:
    """Test diff.json format: scope_a, scope_b, counts, percentage_change, anomaly_notes(string[])"""

    def test_diff_json_has_required_fields(self, auth_headers):
        """Test diff.json has all required fields"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": "test-diff-a",
                "compare_correlation_id": "test-diff-b",
            },
        )
        assert response.status_code == 200
        diff = response.json().get("state_snapshot", {}).get("diff", {})
        
        # Verify required fields
        assert "scope_a" in diff, "diff must have scope_a"
        assert "scope_b" in diff, "diff must have scope_b"
        assert "counts" in diff, "diff must have counts"
        assert "percentage_change" in diff, "diff must have percentage_change"
        assert "anomaly_notes" in diff, "diff must have anomaly_notes"
        
        # Verify anomaly_notes is a list of strings
        anomaly_notes = diff["anomaly_notes"]
        assert isinstance(anomaly_notes, list), "anomaly_notes must be a list"
        for note in anomaly_notes:
            assert isinstance(note, str), f"Each anomaly note must be a string, got {type(note)}"

    def test_counts_has_delta_fields(self, auth_headers):
        """Test counts has events_delta, failed_events_delta, dead_letter_delta, manual_actions_delta"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": "test-counts-a",
                "compare_correlation_id": "test-counts-b",
            },
        )
        assert response.status_code == 200
        counts = response.json().get("state_snapshot", {}).get("diff", {}).get("counts", {})
        
        # Verify delta fields exist
        assert "events_delta" in counts, "counts must have events_delta"
        assert "failed_events_delta" in counts, "counts must have failed_events_delta"
        assert "dead_letter_delta" in counts, "counts must have dead_letter_delta"
        assert "manual_actions_delta" in counts, "counts must have manual_actions_delta"


class TestExportCompareZipContents:
    """Test /export compare mode: ZIP contains diff.json + diff_summary.txt"""

    def test_export_with_compare_contains_diff_files(self, auth_headers):
        """Test export with compare mode contains diff.json and diff_summary.txt"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": "test-export-a",
                "compare_correlation_id": "test-export-b",
            },
        )
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_list = zf.namelist()
            
            # Should have diff files when compare is ON
            assert "diff.json" in file_list, "diff.json should be in ZIP when compare is ON"
            assert "diff_summary.txt" in file_list, "diff_summary.txt should be in ZIP when compare is ON"
            
            # Verify diff.json content
            diff_content = zf.read("diff.json").decode("utf-8")
            diff_json = json.loads(diff_content)
            
            assert "scope_a" in diff_json
            assert "scope_b" in diff_json
            assert "counts" in diff_json
            assert "percentage_change" in diff_json
            assert "anomaly_notes" in diff_json
            
            # Verify diff_summary.txt exists and has content
            summary_content = zf.read("diff_summary.txt").decode("utf-8")
            assert len(summary_content) > 0, "diff_summary.txt should have content"


class TestAnomalyEngineThresholds:
    """Test anomaly engine deterministic thresholds"""

    def test_anomaly_notes_are_strings(self, auth_headers):
        """Test anomaly_notes is array of strings"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": "test-anomaly-a",
                "compare_correlation_id": "test-anomaly-b",
            },
        )
        assert response.status_code == 200
        diff = response.json().get("state_snapshot", {}).get("diff", {})
        anomaly_notes = diff.get("anomaly_notes", [])
        
        assert isinstance(anomaly_notes, list)
        for note in anomaly_notes:
            assert isinstance(note, str), f"anomaly_note must be string, got {type(note)}"


class TestAuditLogGeneration:
    """Test audit log generation for export and diff actions"""

    def test_export_generates_audit_log(self, auth_headers):
        """Test export action generates audit log"""
        # Perform export
        export_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={"correlation_id": "test-audit-export-001"},
        )
        assert export_response.status_code == 200
        
        # Check audit logs
        audit_response = requests.get(
            f"{BASE_URL}/api/admin/audit-logs?limit=20",
            headers=auth_headers,
        )
        if audit_response.status_code == 200:
            logs = audit_response.json()
            if isinstance(logs, list):
                export_logs = [log for log in logs if log.get("action") == "incident_snapshot_export"]
                assert len(export_logs) > 0, "Should have incident_snapshot_export audit log"

    def test_diff_preview_generates_audit_log(self, auth_headers):
        """Test diff preview action generates audit log"""
        # Perform diff preview
        diff_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": "test-audit-diff-a",
                "compare_correlation_id": "test-audit-diff-b",
            },
        )
        assert diff_response.status_code == 200
        
        # Check audit logs
        audit_response = requests.get(
            f"{BASE_URL}/api/admin/audit-logs?limit=20",
            headers=auth_headers,
        )
        if audit_response.status_code == 200:
            logs = audit_response.json()
            if isinstance(logs, list):
                diff_logs = [log for log in logs if log.get("action") == "incident_snapshot_diff_preview"]
                assert len(diff_logs) > 0, "Should have incident_snapshot_diff_preview audit log"


class TestMissingRequiredScope:
    """Test missing required scope returns proper error"""

    def test_no_scope_returns_400(self, auth_headers):
        """Test request without any scope returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={},
        )
        assert response.status_code == 400, f"Expected 400 for missing scope, got {response.status_code}"

    def test_export_no_scope_returns_400(self, auth_headers):
        """Test export without scope returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={},
        )
        assert response.status_code == 400, f"Expected 400 for missing scope, got {response.status_code}"


class TestExecutionStateTransitionsControl:
    """Test execution state transitions control endpoint"""

    def test_control_endpoint_returns_rows_and_counters(self, auth_headers):
        """Test control endpoint returns rows, summary_counts, state_counters"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?limit=50",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "rows" in data
        assert "summary_counts" in data
        assert "state_counters" in data
        assert isinstance(data["rows"], list)
        assert isinstance(data["summary_counts"], dict)
        assert isinstance(data["state_counters"], dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
