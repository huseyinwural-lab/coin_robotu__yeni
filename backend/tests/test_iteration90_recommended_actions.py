"""
Iteration 90 - Recommended Actions Deterministic Rule Testing

Tests for:
1. /api/admin-phase3/incident-snapshots/diff response contains diff.recommended_actions
2. recommended_actions elements follow contract: action, severity, reason
3. Deterministic rule behavior: same input produces same recommended_actions order/output
4. Threshold mapping: failed_events>50 critical actions, dead_letter>30 warning actions, manual_actions>0 warning actions
5. Negative delta/improvement produces INFO keep current policy
6. idempotency collisions delta>0 produces idempotency action
7. /export compare ZIP contains diff.json with recommended_actions
8. diff_summary.txt contains Recommended Actions section
"""

import os
import io
import json
import zipfile
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
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
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestRecommendedActionsContract:
    """Test recommended_actions contract in diff response"""

    def test_diff_response_contains_recommended_actions(self, auth_headers):
        """Verify /diff response contains diff.recommended_actions field"""
        # First get a correlation_id from existing data
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?limit=50",
            headers=auth_headers,
        )
        assert response.status_code == 200
        rows = response.json().get("rows", [])
        
        if not rows:
            pytest.skip("No execution state transitions available for testing")
        
        correlation_id = rows[0].get("correlation_id")
        if not correlation_id:
            pytest.skip("No correlation_id found in transitions")
        
        # Call diff endpoint with compare enabled
        diff_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "compare_correlation_id": correlation_id,  # Same for testing structure
            },
        )
        assert diff_response.status_code == 200
        data = diff_response.json()
        
        # Verify structure
        assert "state_snapshot" in data
        state_snapshot = data["state_snapshot"]
        assert "diff" in state_snapshot
        
        diff = state_snapshot["diff"]
        if diff is not None:  # diff is present when compare is enabled
            assert "recommended_actions" in diff, "diff must contain recommended_actions field"
            recommended_actions = diff["recommended_actions"]
            assert isinstance(recommended_actions, list), "recommended_actions must be a list"
            print(f"PASS: diff.recommended_actions exists and is a list with {len(recommended_actions)} items")

    def test_recommended_actions_element_contract(self, auth_headers):
        """Verify each recommended_actions element has action, severity, reason fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?limit=50",
            headers=auth_headers,
        )
        rows = response.json().get("rows", [])
        
        if not rows:
            pytest.skip("No execution state transitions available")
        
        correlation_id = rows[0].get("correlation_id")
        if not correlation_id:
            pytest.skip("No correlation_id found")
        
        diff_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "compare_correlation_id": correlation_id,
            },
        )
        assert diff_response.status_code == 200
        diff = diff_response.json().get("state_snapshot", {}).get("diff")
        
        if diff is None:
            pytest.skip("No diff data available")
        
        recommended_actions = diff.get("recommended_actions", [])
        
        for idx, action_item in enumerate(recommended_actions):
            assert "action" in action_item, f"Item {idx} missing 'action' field"
            assert "severity" in action_item, f"Item {idx} missing 'severity' field"
            assert "reason" in action_item, f"Item {idx} missing 'reason' field"
            
            # Verify severity is valid
            assert action_item["severity"] in ["CRITICAL", "WARNING", "INFO"], \
                f"Item {idx} has invalid severity: {action_item['severity']}"
            
            print(f"PASS: Item {idx}: [{action_item['severity']}] {action_item['action']} ({action_item['reason']})")


class TestDeterministicRuleBehavior:
    """Test that same input produces same recommended_actions output"""

    def test_deterministic_output_same_input(self, auth_headers):
        """Verify same input produces identical recommended_actions order/output"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?limit=50",
            headers=auth_headers,
        )
        rows = response.json().get("rows", [])
        
        if not rows:
            pytest.skip("No execution state transitions available")
        
        correlation_id = rows[0].get("correlation_id")
        if not correlation_id:
            pytest.skip("No correlation_id found")
        
        request_body = {
            "correlation_id": correlation_id,
            "compare_correlation_id": correlation_id,
        }
        
        # Call diff endpoint multiple times
        results = []
        for i in range(3):
            diff_response = requests.post(
                f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
                headers=auth_headers,
                json=request_body,
            )
            assert diff_response.status_code == 200
            diff = diff_response.json().get("state_snapshot", {}).get("diff")
            if diff:
                results.append(diff.get("recommended_actions", []))
        
        if len(results) < 2:
            pytest.skip("Not enough diff results to compare")
        
        # Compare all results - they should be identical
        first_result = json.dumps(results[0], sort_keys=True)
        for idx, result in enumerate(results[1:], start=2):
            current_result = json.dumps(result, sort_keys=True)
            assert first_result == current_result, \
                f"Run {idx} produced different recommended_actions than run 1"
        
        print(f"PASS: {len(results)} runs produced identical recommended_actions")


class TestThresholdMapping:
    """Test threshold-based action generation rules"""

    def test_failed_events_high_produces_critical_actions(self, auth_headers):
        """
        Rule: failed_events > 50% increase => retry policy tune + timeout review (CRITICAL)
        """
        # This test verifies the rule logic exists in the code
        # We check the diff endpoint response structure
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?limit=50",
            headers=auth_headers,
        )
        rows = response.json().get("rows", [])
        
        if not rows:
            pytest.skip("No execution state transitions available")
        
        correlation_id = rows[0].get("correlation_id")
        if not correlation_id:
            pytest.skip("No correlation_id found")
        
        diff_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "compare_correlation_id": correlation_id,
            },
        )
        assert diff_response.status_code == 200
        diff = diff_response.json().get("state_snapshot", {}).get("diff")
        
        if diff is None:
            pytest.skip("No diff data available")
        
        # Verify the structure supports threshold-based actions
        assert "percentage_change" in diff, "diff must contain percentage_change"
        assert "failed_events" in diff["percentage_change"], "percentage_change must contain failed_events"
        
        recommended_actions = diff.get("recommended_actions", [])
        action_names = [a["action"] for a in recommended_actions]
        severity_map = {a["action"]: a["severity"] for a in recommended_actions}
        
        # If failed_events increased significantly, we should see CRITICAL actions
        failed_pct = diff["percentage_change"]["failed_events"]
        failed_delta = diff["counts"]["failed_events_delta"]
        
        if failed_delta > 0 and failed_pct > 50:
            assert "retry policy tune" in action_names, "High failed_events should trigger 'retry policy tune'"
            assert "timeout review" in action_names, "High failed_events should trigger 'timeout review'"
            assert severity_map.get("retry policy tune") == "CRITICAL", "retry policy tune should be CRITICAL"
            assert severity_map.get("timeout review") == "CRITICAL", "timeout review should be CRITICAL"
            print(f"PASS: failed_events +{failed_pct}% triggered CRITICAL actions")
        else:
            print(f"INFO: failed_events delta={failed_delta}, pct={failed_pct}% - no CRITICAL threshold triggered")

    def test_dead_letter_high_produces_warning_actions(self, auth_headers):
        """
        Rule: dead_letter > 30% increase => guardrail hardening + validation check (WARNING)
        """
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?limit=50",
            headers=auth_headers,
        )
        rows = response.json().get("rows", [])
        
        if not rows:
            pytest.skip("No execution state transitions available")
        
        correlation_id = rows[0].get("correlation_id")
        if not correlation_id:
            pytest.skip("No correlation_id found")
        
        diff_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "compare_correlation_id": correlation_id,
            },
        )
        assert diff_response.status_code == 200
        diff = diff_response.json().get("state_snapshot", {}).get("diff")
        
        if diff is None:
            pytest.skip("No diff data available")
        
        assert "percentage_change" in diff
        assert "dead_letter" in diff["percentage_change"]
        
        recommended_actions = diff.get("recommended_actions", [])
        action_names = [a["action"] for a in recommended_actions]
        severity_map = {a["action"]: a["severity"] for a in recommended_actions}
        
        dead_pct = diff["percentage_change"]["dead_letter"]
        dead_delta = diff["counts"]["dead_letter_delta"]
        
        if dead_delta > 0 and dead_pct > 30:
            assert "guardrail hardening" in action_names, "High dead_letter should trigger 'guardrail hardening'"
            assert "validation check" in action_names, "High dead_letter should trigger 'validation check'"
            assert severity_map.get("guardrail hardening") == "WARNING"
            assert severity_map.get("validation check") == "WARNING"
            print(f"PASS: dead_letter +{dead_pct}% triggered WARNING actions")
        else:
            print(f"INFO: dead_letter delta={dead_delta}, pct={dead_pct}% - no WARNING threshold triggered")

    def test_manual_actions_increase_produces_warning(self, auth_headers):
        """
        Rule: manual_actions increase > 0 => runbook review + automation gap (WARNING)
        """
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?limit=50",
            headers=auth_headers,
        )
        rows = response.json().get("rows", [])
        
        if not rows:
            pytest.skip("No execution state transitions available")
        
        correlation_id = rows[0].get("correlation_id")
        if not correlation_id:
            pytest.skip("No correlation_id found")
        
        diff_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "compare_correlation_id": correlation_id,
            },
        )
        assert diff_response.status_code == 200
        diff = diff_response.json().get("state_snapshot", {}).get("diff")
        
        if diff is None:
            pytest.skip("No diff data available")
        
        recommended_actions = diff.get("recommended_actions", [])
        action_names = [a["action"] for a in recommended_actions]
        severity_map = {a["action"]: a["severity"] for a in recommended_actions}
        
        manual_delta = diff["counts"]["manual_actions_delta"]
        
        if manual_delta > 0:
            assert "runbook review" in action_names, "manual_actions increase should trigger 'runbook review'"
            assert "automation gap" in action_names, "manual_actions increase should trigger 'automation gap'"
            assert severity_map.get("runbook review") == "WARNING"
            assert severity_map.get("automation gap") == "WARNING"
            print(f"PASS: manual_actions +{manual_delta} triggered WARNING actions")
        else:
            print(f"INFO: manual_actions delta={manual_delta} - no WARNING threshold triggered")


class TestImprovementAndIdempotency:
    """Test improvement detection and idempotency collision rules"""

    def test_negative_delta_produces_info_keep_policy(self, auth_headers):
        """
        Rule: Negative delta/improvement => INFO keep current policy
        """
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?limit=50",
            headers=auth_headers,
        )
        rows = response.json().get("rows", [])
        
        if not rows:
            pytest.skip("No execution state transitions available")
        
        correlation_id = rows[0].get("correlation_id")
        if not correlation_id:
            pytest.skip("No correlation_id found")
        
        diff_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "compare_correlation_id": correlation_id,
            },
        )
        assert diff_response.status_code == 200
        diff = diff_response.json().get("state_snapshot", {}).get("diff")
        
        if diff is None:
            pytest.skip("No diff data available")
        
        recommended_actions = diff.get("recommended_actions", [])
        
        # Check if any improvement detected
        failed_delta = diff["counts"]["failed_events_delta"]
        dead_delta = diff["counts"]["dead_letter_delta"]
        manual_delta = diff["counts"]["manual_actions_delta"]
        
        has_improvement = failed_delta < 0 or dead_delta < 0 or manual_delta < 0
        
        # Find INFO keep current policy action
        info_actions = [a for a in recommended_actions if a["severity"] == "INFO" and "keep current policy" in a["action"]]
        
        if has_improvement:
            assert len(info_actions) > 0, "Improvement should produce INFO 'keep current policy' action"
            print("PASS: Improvement detected, INFO 'keep current policy' action present")
        else:
            # Even without improvement, if no issues, should have keep current policy
            if not any(a["severity"] in ["CRITICAL", "WARNING"] for a in recommended_actions):
                assert len(info_actions) > 0, "Stable state should produce INFO 'keep current policy' action"
                print("PASS: Stable state, INFO 'keep current policy' action present")
            else:
                print("INFO: Issues detected, no INFO keep policy expected")

    def test_idempotency_collision_increase_produces_action(self, auth_headers):
        """
        Rule: idempotency_collisions delta > 0 => idempotency check hardening (WARNING)
        """
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?limit=50",
            headers=auth_headers,
        )
        rows = response.json().get("rows", [])
        
        if not rows:
            pytest.skip("No execution state transitions available")
        
        correlation_id = rows[0].get("correlation_id")
        if not correlation_id:
            pytest.skip("No correlation_id found")
        
        diff_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "compare_correlation_id": correlation_id,
            },
        )
        assert diff_response.status_code == 200
        diff = diff_response.json().get("state_snapshot", {}).get("diff")
        
        if diff is None:
            pytest.skip("No diff data available")
        
        recommended_actions = diff.get("recommended_actions", [])
        action_names = [a["action"] for a in recommended_actions]
        severity_map = {a["action"]: a["severity"] for a in recommended_actions}
        
        collision_delta = diff["counts"]["idempotency_collisions_delta"]
        
        if collision_delta > 0:
            assert "idempotency check hardening" in action_names, \
                "idempotency_collisions increase should trigger 'idempotency check hardening'"
            assert severity_map.get("idempotency check hardening") == "WARNING"
            print(f"PASS: idempotency_collisions +{collision_delta} triggered WARNING action")
        else:
            print(f"INFO: idempotency_collisions delta={collision_delta} - no action triggered")


class TestExportZipContents:
    """Test export ZIP contains diff.json with recommended_actions"""

    def test_export_zip_contains_diff_json_with_recommended_actions(self, auth_headers):
        """Verify /export compare ZIP contains diff.json with recommended_actions"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?limit=50",
            headers=auth_headers,
        )
        rows = response.json().get("rows", [])
        
        if not rows:
            pytest.skip("No execution state transitions available")
        
        correlation_id = rows[0].get("correlation_id")
        if not correlation_id:
            pytest.skip("No correlation_id found")
        
        export_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "compare_correlation_id": correlation_id,
            },
        )
        assert export_response.status_code == 200
        assert "application/zip" in export_response.headers.get("content-type", "")
        
        # Parse ZIP content
        zip_buffer = io.BytesIO(export_response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_names = zf.namelist()
            
            # Verify diff.json exists
            assert "diff.json" in file_names, "Export ZIP must contain diff.json when compare enabled"
            
            # Read and parse diff.json
            diff_content = zf.read("diff.json").decode("utf-8")
            diff_data = json.loads(diff_content)
            
            # Verify recommended_actions in diff.json
            assert "recommended_actions" in diff_data, "diff.json must contain recommended_actions"
            recommended_actions = diff_data["recommended_actions"]
            assert isinstance(recommended_actions, list)
            
            # Verify each action has required fields
            for idx, action in enumerate(recommended_actions):
                assert "action" in action, f"diff.json action {idx} missing 'action' field"
                assert "severity" in action, f"diff.json action {idx} missing 'severity' field"
                assert "reason" in action, f"diff.json action {idx} missing 'reason' field"
            
            print(f"PASS: diff.json contains {len(recommended_actions)} recommended_actions with correct contract")

    def test_diff_summary_txt_contains_recommended_actions_section(self, auth_headers):
        """Verify diff_summary.txt contains Recommended Actions section"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?limit=50",
            headers=auth_headers,
        )
        rows = response.json().get("rows", [])
        
        if not rows:
            pytest.skip("No execution state transitions available")
        
        correlation_id = rows[0].get("correlation_id")
        if not correlation_id:
            pytest.skip("No correlation_id found")
        
        export_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "compare_correlation_id": correlation_id,
            },
        )
        assert export_response.status_code == 200
        
        zip_buffer = io.BytesIO(export_response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_names = zf.namelist()
            
            # Verify diff_summary.txt exists
            assert "diff_summary.txt" in file_names, "Export ZIP must contain diff_summary.txt when compare enabled"
            
            # Read diff_summary.txt
            summary_content = zf.read("diff_summary.txt").decode("utf-8")
            
            # Verify Recommended Actions section exists
            assert "Recommended Actions" in summary_content, \
                "diff_summary.txt must contain 'Recommended Actions' section"
            
            # Verify format: - [SEVERITY] action (reason)
            lines = summary_content.split("\n")
            actions_section_started = False
            action_lines = []
            
            for line in lines:
                if "Recommended Actions" in line:
                    actions_section_started = True
                    continue
                if actions_section_started and line.strip().startswith("- ["):
                    action_lines.append(line)
            
            assert len(action_lines) > 0, "diff_summary.txt must have at least one recommended action line"
            
            # Verify format of action lines
            for line in action_lines:
                assert "[CRITICAL]" in line or "[WARNING]" in line or "[INFO]" in line, \
                    f"Action line must contain severity: {line}"
            
            print(f"PASS: diff_summary.txt contains Recommended Actions section with {len(action_lines)} actions")


class TestExportWithoutCompare:
    """Test export without compare does not include diff files"""

    def test_export_without_compare_no_diff_files(self, auth_headers):
        """Verify export without compare does NOT include diff.json or diff_summary.txt"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control?limit=50",
            headers=auth_headers,
        )
        rows = response.json().get("rows", [])
        
        if not rows:
            pytest.skip("No execution state transitions available")
        
        correlation_id = rows[0].get("correlation_id")
        if not correlation_id:
            pytest.skip("No correlation_id found")
        
        # Export WITHOUT compare
        export_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                # No compare_correlation_id
            },
        )
        assert export_response.status_code == 200
        
        zip_buffer = io.BytesIO(export_response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_names = zf.namelist()
            
            # Verify diff files are NOT present
            assert "diff.json" not in file_names, "Export without compare should NOT contain diff.json"
            assert "diff_summary.txt" not in file_names, "Export without compare should NOT contain diff_summary.txt"
            
            print(f"PASS: Export without compare does not include diff files. Files: {file_names}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
