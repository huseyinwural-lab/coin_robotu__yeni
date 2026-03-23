"""
Iteration 88 - Anomaly Notes Diff Testing
Tests for diff.json anomaly_notes field and deterministic rule-based notes:
- Rule-1: failed_events delta > 50% => risk note
- Rule-2: dead_letter increase > 50% => risk note
- Rule-3: manual_actions positive delta => 'operator intervention increased'
- Rule-4: negative delta => deterministic 'improved'/'reduced' messages
- diff_summary.txt contains anomaly notes section
- Regression: incompatible_scope 422 behavior preserved
"""

import pytest
import requests
import os
import json
import zipfile
import io
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Auth headers for API requests"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestAnomalyNotesDiffExport:
    """Tests for anomaly_notes in diff.json during compare export"""

    def test_compare_export_contains_diff_json_and_diff_summary(self, auth_headers):
        """Verify compare export ZIP contains diff.json and diff_summary.txt"""
        now = datetime.now(timezone.utc)
        time_from = (now - timedelta(hours=24)).isoformat()
        time_to = now.isoformat()
        
        # Compare with a slightly different time range
        compare_time_from = (now - timedelta(hours=48)).isoformat()
        compare_time_to = (now - timedelta(hours=24)).isoformat()
        
        payload = {
            "time_from": time_from,
            "time_to": time_to,
            "compare_time_from": compare_time_from,
            "compare_time_to": compare_time_to,
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Export failed: {response.text}"
        assert response.headers.get("content-type") == "application/zip"
        
        # Extract ZIP and check for diff files
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_names = zf.namelist()
            print(f"ZIP contains: {file_names}")
            
            assert "diff.json" in file_names, "diff.json missing from compare export"
            assert "diff_summary.txt" in file_names, "diff_summary.txt missing from compare export"

    def test_diff_json_contains_anomaly_notes_field(self, auth_headers):
        """Verify diff.json has anomaly_notes array field"""
        now = datetime.now(timezone.utc)
        time_from = (now - timedelta(hours=24)).isoformat()
        time_to = now.isoformat()
        compare_time_from = (now - timedelta(hours=48)).isoformat()
        compare_time_to = (now - timedelta(hours=24)).isoformat()
        
        payload = {
            "time_from": time_from,
            "time_to": time_to,
            "compare_time_from": compare_time_from,
            "compare_time_to": compare_time_to,
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            diff_content = zf.read("diff.json").decode("utf-8")
            diff_json = json.loads(diff_content)
            
            print(f"diff.json keys: {diff_json.keys()}")
            assert "anomaly_notes" in diff_json, "anomaly_notes field missing from diff.json"
            assert isinstance(diff_json["anomaly_notes"], list), "anomaly_notes should be a list"
            
            # Verify structure
            assert "scope_comparison" in diff_json
            assert "count_delta" in diff_json
            assert "generated_at" in diff_json

    def test_diff_json_count_delta_structure(self, auth_headers):
        """Verify count_delta contains required keys with direction field"""
        now = datetime.now(timezone.utc)
        time_from = (now - timedelta(hours=24)).isoformat()
        time_to = now.isoformat()
        compare_time_from = (now - timedelta(hours=48)).isoformat()
        compare_time_to = (now - timedelta(hours=24)).isoformat()
        
        payload = {
            "time_from": time_from,
            "time_to": time_to,
            "compare_time_from": compare_time_from,
            "compare_time_to": compare_time_to,
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            diff_content = zf.read("diff.json").decode("utf-8")
            diff_json = json.loads(diff_content)
            
            count_delta = diff_json["count_delta"]
            required_keys = ["events", "transitions", "failed_events", "manual_actions", "idempotency_collisions"]
            
            for key in required_keys:
                assert key in count_delta, f"count_delta missing key: {key}"
                item = count_delta[key]
                assert "current" in item, f"{key} missing 'current'"
                assert "compare" in item, f"{key} missing 'compare'"
                assert "delta" in item, f"{key} missing 'delta'"
                assert "trend" in item, f"{key} missing 'trend'"
                assert "direction" in item, f"{key} missing 'direction'"
                
                # Verify trend values are Turkish
                assert item["trend"] in ["arttı", "azaldı", "değişmedi"], f"Invalid trend value: {item['trend']}"
                
                # Verify direction values are deterministic English
                assert item["direction"] in ["increased", "improved", "reduced", "unchanged"], f"Invalid direction: {item['direction']}"
            
            print(f"count_delta structure verified: {json.dumps(count_delta, indent=2)}")

    def test_diff_summary_txt_contains_anomaly_notes_section(self, auth_headers):
        """Verify diff_summary.txt includes Anomaly Notes section"""
        now = datetime.now(timezone.utc)
        time_from = (now - timedelta(hours=24)).isoformat()
        time_to = now.isoformat()
        compare_time_from = (now - timedelta(hours=48)).isoformat()
        compare_time_to = (now - timedelta(hours=24)).isoformat()
        
        payload = {
            "time_from": time_from,
            "time_to": time_to,
            "compare_time_from": compare_time_from,
            "compare_time_to": compare_time_to,
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary_content = zf.read("diff_summary.txt").decode("utf-8")
            
            print(f"diff_summary.txt content:\n{summary_content}")
            
            assert "Snapshot Diff Summary" in summary_content, "Missing 'Snapshot Diff Summary' header"
            assert "Anomaly Notes" in summary_content, "Missing 'Anomaly Notes' section"
            
            # Should have either notes or "- none"
            lines = summary_content.split("\n")
            anomaly_section_found = False
            for i, line in enumerate(lines):
                if "Anomaly Notes" in line:
                    anomaly_section_found = True
                    # Next line should be a note or "- none"
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        assert next_line.startswith("- "), f"Anomaly note line should start with '- ': {next_line}"
            
            assert anomaly_section_found, "Anomaly Notes section not found in summary"


class TestAnomalyNotesRules:
    """Tests for specific anomaly note rules"""

    def test_anomaly_note_structure_when_present(self, auth_headers):
        """Verify anomaly note structure has required fields"""
        now = datetime.now(timezone.utc)
        time_from = (now - timedelta(hours=24)).isoformat()
        time_to = now.isoformat()
        compare_time_from = (now - timedelta(hours=48)).isoformat()
        compare_time_to = (now - timedelta(hours=24)).isoformat()
        
        payload = {
            "time_from": time_from,
            "time_to": time_to,
            "compare_time_from": compare_time_from,
            "compare_time_to": compare_time_to,
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            diff_content = zf.read("diff.json").decode("utf-8")
            diff_json = json.loads(diff_content)
            
            anomaly_notes = diff_json["anomaly_notes"]
            
            if len(anomaly_notes) > 0:
                for note in anomaly_notes:
                    # Verify required fields in each note
                    assert "rule_id" in note, "Note missing rule_id"
                    assert "severity" in note, "Note missing severity"
                    assert "metric" in note, "Note missing metric"
                    assert "message" in note, "Note missing message"
                    assert "current" in note, "Note missing current"
                    assert "compare" in note, "Note missing compare"
                    assert "delta" in note, "Note missing delta"
                    assert "pct_change" in note, "Note missing pct_change"
                    
                    # Verify severity values
                    assert note["severity"] in ["critical", "warning", "info"], f"Invalid severity: {note['severity']}"
                    
                    print(f"Anomaly note: {json.dumps(note, indent=2)}")
            else:
                print("No anomaly notes generated (data may not trigger rules)")

    def test_rule_failed_events_risk_message_format(self, auth_headers):
        """Rule-1: Verify failed_events risk note message format when delta > 50%"""
        now = datetime.now(timezone.utc)
        time_from = (now - timedelta(hours=24)).isoformat()
        time_to = now.isoformat()
        compare_time_from = (now - timedelta(hours=48)).isoformat()
        compare_time_to = (now - timedelta(hours=24)).isoformat()
        
        payload = {
            "time_from": time_from,
            "time_to": time_to,
            "compare_time_from": compare_time_from,
            "compare_time_to": compare_time_to,
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            diff_content = zf.read("diff.json").decode("utf-8")
            diff_json = json.loads(diff_content)
            
            # Check if failed_events rule triggered
            failed_events_notes = [n for n in diff_json["anomaly_notes"] if n["metric"] == "failed_events"]
            
            for note in failed_events_notes:
                if note["rule_id"] == "failed_events_risk_gt_50pct":
                    # Verify critical severity and risk message
                    assert note["severity"] == "critical"
                    assert "risk:" in note["message"]
                    assert "failed_events increased by" in note["message"]
                    print(f"Rule-1 triggered: {note['message']}")
                elif note["rule_id"] == "failed_events_negative_delta":
                    # Verify info severity and improved message
                    assert note["severity"] == "info"
                    assert "improved:" in note["message"]
                    print(f"Rule-1 negative delta: {note['message']}")

    def test_rule_dead_letter_risk_message_format(self, auth_headers):
        """Rule-2: Verify dead_letter risk note message format when increase > 50%"""
        now = datetime.now(timezone.utc)
        time_from = (now - timedelta(hours=24)).isoformat()
        time_to = now.isoformat()
        compare_time_from = (now - timedelta(hours=48)).isoformat()
        compare_time_to = (now - timedelta(hours=24)).isoformat()
        
        payload = {
            "time_from": time_from,
            "time_to": time_to,
            "compare_time_from": compare_time_from,
            "compare_time_to": compare_time_to,
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            diff_content = zf.read("diff.json").decode("utf-8")
            diff_json = json.loads(diff_content)
            
            # Check if dead_letter rule triggered
            dead_letter_notes = [n for n in diff_json["anomaly_notes"] if n["metric"] == "dead_letter"]
            
            for note in dead_letter_notes:
                if note["rule_id"] == "dead_letter_risk_gt_50pct":
                    # Verify critical severity and risk message
                    assert note["severity"] == "critical"
                    assert "risk:" in note["message"]
                    assert "dead_letter increased by" in note["message"]
                    print(f"Rule-2 triggered: {note['message']}")
                elif note["rule_id"] == "dead_letter_negative_delta":
                    # Verify info severity and improved message
                    assert note["severity"] == "info"
                    assert "improved:" in note["message"]
                    print(f"Rule-2 negative delta: {note['message']}")

    def test_rule_manual_actions_operator_intervention_message(self, auth_headers):
        """Rule-3: Verify manual_actions positive delta produces 'operator intervention increased'"""
        now = datetime.now(timezone.utc)
        time_from = (now - timedelta(hours=24)).isoformat()
        time_to = now.isoformat()
        compare_time_from = (now - timedelta(hours=48)).isoformat()
        compare_time_to = (now - timedelta(hours=24)).isoformat()
        
        payload = {
            "time_from": time_from,
            "time_to": time_to,
            "compare_time_from": compare_time_from,
            "compare_time_to": compare_time_to,
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            diff_content = zf.read("diff.json").decode("utf-8")
            diff_json = json.loads(diff_content)
            
            # Check if manual_actions rule triggered
            manual_action_notes = [n for n in diff_json["anomaly_notes"] if n["metric"] == "manual_actions"]
            
            for note in manual_action_notes:
                if note["rule_id"] == "manual_actions_increased":
                    # Verify warning severity and operator intervention message
                    assert note["severity"] == "warning"
                    assert note["message"] == "operator intervention increased"
                    print(f"Rule-3 triggered: {note['message']}")
                elif note["rule_id"] == "manual_actions_negative_delta":
                    # Verify info severity and reduced message
                    assert note["severity"] == "info"
                    assert "reduced:" in note["message"]
                    print(f"Rule-3 negative delta: {note['message']}")

    def test_rule_negative_delta_deterministic_messages(self, auth_headers):
        """Rule-4: Verify negative delta produces deterministic 'improved'/'reduced' messages"""
        now = datetime.now(timezone.utc)
        time_from = (now - timedelta(hours=24)).isoformat()
        time_to = now.isoformat()
        compare_time_from = (now - timedelta(hours=48)).isoformat()
        compare_time_to = (now - timedelta(hours=24)).isoformat()
        
        payload = {
            "time_from": time_from,
            "time_to": time_to,
            "compare_time_from": compare_time_from,
            "compare_time_to": compare_time_to,
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            diff_content = zf.read("diff.json").decode("utf-8")
            diff_json = json.loads(diff_content)
            
            count_delta = diff_json["count_delta"]
            
            # Check direction field for negative deltas
            for key, item in count_delta.items():
                if item["delta"] < 0:
                    if key in ["failed_events", "manual_actions"]:
                        assert item["direction"] == "improved", f"{key} negative delta should have direction='improved'"
                    else:
                        assert item["direction"] == "reduced", f"{key} negative delta should have direction='reduced'"
                    print(f"{key}: delta={item['delta']}, direction={item['direction']}")


class TestIncompatibleScopeRegression:
    """Regression tests for incompatible_scope 422 behavior"""

    def test_incompatible_scope_correlation_vs_time_range_returns_422(self, auth_headers):
        """Verify 422 error when primary=correlation_id and compare=time_range"""
        payload = {
            "correlation_id": "test-corr-123",
            "compare_time_from": "2024-01-01T00:00:00Z",
            "compare_time_to": "2024-01-02T00:00:00Z",
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        
        error_detail = response.json().get("detail", "")
        print(f"422 error detail: {error_detail}")
        
        assert "incompatible_scope" in error_detail.lower() or "scope" in error_detail.lower()

    def test_incompatible_scope_time_range_vs_correlation_returns_422(self, auth_headers):
        """Verify 422 error when primary=time_range and compare=correlation_id"""
        now = datetime.now(timezone.utc)
        
        payload = {
            "time_from": (now - timedelta(hours=24)).isoformat(),
            "time_to": now.isoformat(),
            "compare_correlation_id": "test-corr-456",
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        
        error_detail = response.json().get("detail", "")
        print(f"422 error detail: {error_detail}")

    def test_incompatible_scope_execution_event_vs_time_range_returns_422(self, auth_headers):
        """Verify 422 error when primary=execution_event_id and compare=time_range"""
        payload = {
            "execution_event_id": "test-event-789",
            "compare_time_from": "2024-01-01T00:00:00Z",
            "compare_time_to": "2024-01-02T00:00:00Z",
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    def test_compatible_scope_time_range_vs_time_range_returns_200(self, auth_headers):
        """Verify 200 when both scopes are time_range (compatible)"""
        now = datetime.now(timezone.utc)
        
        payload = {
            "time_from": (now - timedelta(hours=24)).isoformat(),
            "time_to": now.isoformat(),
            "compare_time_from": (now - timedelta(hours=48)).isoformat(),
            "compare_time_to": (now - timedelta(hours=24)).isoformat(),
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestSingleSnapshotExportRegression:
    """Regression tests for single snapshot export (no compare mode)"""

    def test_single_snapshot_does_not_contain_diff_files(self, auth_headers):
        """Verify single snapshot export does NOT contain diff.json or diff_summary.txt"""
        now = datetime.now(timezone.utc)
        
        payload = {
            "time_from": (now - timedelta(hours=24)).isoformat(),
            "time_to": now.isoformat(),
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_names = zf.namelist()
            print(f"Single snapshot ZIP contains: {file_names}")
            
            assert "diff.json" not in file_names, "diff.json should NOT be in single snapshot"
            assert "diff_summary.txt" not in file_names, "diff_summary.txt should NOT be in single snapshot"
            
            # Verify standard files are present
            assert "summary.json" in file_names
            assert "README.txt" in file_names

    def test_single_snapshot_contains_standard_files(self, auth_headers):
        """Verify single snapshot contains all standard files"""
        now = datetime.now(timezone.utc)
        
        payload = {
            "time_from": (now - timedelta(hours=24)).isoformat(),
            "time_to": now.isoformat(),
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_names = zf.namelist()
            
            expected_files = [
                "summary.json",
                "trace.json",
                "events.csv",
                "transitions.csv",
                "failed_events.csv",
                "manual_actions.csv",
                "idempotency_collisions.csv",
                "README.txt",
            ]
            
            for expected in expected_files:
                assert expected in file_names, f"Missing expected file: {expected}"


class TestExecutionAnalyticsRegression:
    """Regression tests for execution analytics endpoints"""

    def test_execution_analytics_summary_endpoint(self, auth_headers):
        """Verify execution analytics summary endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "snapshot_at" in data
        assert "filters" in data
        assert "totals" in data

    def test_execution_state_transitions_control_endpoint(self, auth_headers):
        """Verify execution state transitions control endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "rows" in data
        assert "summary_counts" in data
        assert "state_counters" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
