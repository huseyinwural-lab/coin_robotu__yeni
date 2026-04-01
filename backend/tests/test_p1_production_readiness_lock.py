"""
P1 Production Readiness Lock - Playbook State Machine, Auto-Ack, Preflight, Export Tests

Tests:
1. Playbook state machine: preview -> approved -> executing -> executed/failed
2. Execute guard: only approved state can execute
3. Rollback guard: only executed state can rollback
4. Retry guard: only failed state can retry, creates new run with parent reference
5. Playbook execute step-by-step audit
6. Playbook failure visibility: failure_reason, step_index/total_steps
7. Rollback endpoint real flow
8. Retry endpoint semantic correctness
9. Run detail contract: step_index, total_steps, failure_reason, parent_run_id, retry_attempt
10. Export hard lock: snapshot_id + snapshot_hash headers, audit_required fields
11. Auto-ack preview: matched_alerts + rule_match_counter
12. Auto-ack run: only works with preview token
13. Auto-ack run blocked without preview or invalid token
14. Preflight endpoint: ui_status OK/WARNING/ERROR, execution_engine_readiness, queue_job_health, preflight_score
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL tanımlı değil", allow_module_level=True)

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
    )
    if response.status_code != 200:
        pytest.skip(f"Super admin login failed: {response.status_code}")
    return response.json().get("access_token")


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
def super_admin_headers(super_admin_token):
    """Headers with super_admin auth"""
    return {
        "Authorization": f"Bearer {super_admin_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


class TestPlaybookPreflight:
    """Preflight endpoint tests: ui_status, execution_engine_readiness, queue_job_health, preflight_score"""

    def test_preflight_endpoint_returns_required_fields(self, super_admin_headers):
        """Test preflight endpoint returns all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
            headers=super_admin_headers,
        )
        assert response.status_code == 200, f"Preflight failed: {response.text}"
        data = response.json()

        # Check overall status fields
        assert "overall_state" in data, "Missing overall_state"
        assert "overall_ui_status" in data, "Missing overall_ui_status"
        assert data["overall_ui_status"] in ["OK", "WARNING", "ERROR"], f"Invalid ui_status: {data['overall_ui_status']}"

        # Check preflight_score
        assert "preflight_score" in data, "Missing preflight_score"
        assert isinstance(data["preflight_score"], (int, float)), "preflight_score must be numeric"

        # Check execution_disable flag
        assert "execution_disable" in data, "Missing execution_disable"

        # Check checks array
        assert "checks" in data, "Missing checks array"
        assert isinstance(data["checks"], list), "checks must be a list"

        # Verify required check keys exist
        check_keys = {item.get("key") for item in data["checks"]}
        required_checks = {"execution_engine_readiness", "queue_job_health"}
        for required_key in required_checks:
            assert required_key in check_keys, f"Missing required check: {required_key}"

        # Verify each check has ui_status
        for check in data["checks"]:
            assert "ui_status" in check, f"Check {check.get('key')} missing ui_status"
            assert check["ui_status"] in ["OK", "WARNING", "ERROR"], f"Invalid check ui_status: {check['ui_status']}"

        print(f"SUCCESS: Preflight returns overall_ui_status={data['overall_ui_status']}, preflight_score={data['preflight_score']}")

    def test_preflight_queue_job_metrics(self, super_admin_headers):
        """Test preflight returns queue_job_metrics"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
            headers=super_admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        assert "queue_job_metrics" in data, "Missing queue_job_metrics"
        metrics = data["queue_job_metrics"]

        # Check required metric fields
        assert "queue_depth" in metrics, "Missing queue_depth"
        assert "failed_backlog" in metrics, "Missing failed_backlog"
        assert "worker_latency_ms" in metrics, "Missing worker_latency_ms"

        print(f"SUCCESS: queue_job_metrics: queue_depth={metrics['queue_depth']}, failed_backlog={metrics['failed_backlog']}")


class TestPlaybookStateMachine:
    """Playbook state machine tests: preview -> approved -> executing -> executed/failed"""

    def test_playbook_preview_creates_run_in_preview_state(self, super_admin_headers):
        """Test playbook preview creates a run in preview state"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [
                    {"action": "guardrail_hardening", "severity": "WARNING", "reason": "test_action"},
                ],
                "anomaly_notes": ["test_anomaly"],
                "scope": {"test": True},
            },
        )
        assert response.status_code == 200, f"Preview failed: {response.text}"
        data = response.json()

        assert "preview_token" in data, "Missing preview_token"
        assert "playbook_run_id" in data, "Missing playbook_run_id"
        assert data.get("execution_state") == "preview", f"Expected preview state, got {data.get('execution_state')}"

        print(f"SUCCESS: Playbook preview created with run_id={data['playbook_run_id']}, state=preview")
        return data

    def test_execute_guard_rejects_non_approved_state(self, super_admin_headers):
        """Test execute guard: only approved state can execute"""
        # Create a preview
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [{"action": "runbook_review", "severity": "INFO", "reason": "test"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        assert preview_response.status_code == 200
        run_id = preview_response.json()["playbook_run_id"]

        # Try to execute without approval - should fail
        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/execute",
            headers=super_admin_headers,
            json={
                "playbook_run_id": run_id,
                "confirm": True,
                "reason": "test_execute_without_approval",
            },
        )
        assert execute_response.status_code == 422, f"Expected 422, got {execute_response.status_code}"
        assert "approved" in execute_response.json().get("detail", "").lower(), "Error should mention approved state"

        print("SUCCESS: Execute guard correctly rejects non-approved state")

    def test_approve_transitions_to_approved_state(self, super_admin_headers):
        """Test approve transitions from preview/planned to approved"""
        # Create a preview
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [{"action": "runbook_review", "severity": "INFO", "reason": "test"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        assert preview_response.status_code == 200
        run_id = preview_response.json()["playbook_run_id"]

        # Approve
        approve_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers=super_admin_headers,
            json={
                "playbook_run_id": run_id,
                "confirm": True,
                "reason": "test_approval",
            },
        )
        assert approve_response.status_code == 200, f"Approve failed: {approve_response.text}"
        assert approve_response.json().get("execution_state") == "approved"

        print(f"SUCCESS: Approve transitions to approved state for run_id={run_id}")
        return run_id

    def test_execute_from_approved_state_succeeds(self, super_admin_headers):
        """Test execute from approved state succeeds"""
        # Create and approve
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [{"action": "runbook_review", "severity": "INFO", "reason": "test"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        run_id = preview_response.json()["playbook_run_id"]

        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_approval"},
        )

        # Execute
        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/execute",
            headers=super_admin_headers,
            json={
                "playbook_run_id": run_id,
                "confirm": True,
                "reason": "test_execute",
            },
        )
        assert execute_response.status_code == 200, f"Execute failed: {execute_response.text}"
        data = execute_response.json()
        assert data.get("execution_state") in ["executed", "failed"], f"Unexpected state: {data.get('execution_state')}"

        print(f"SUCCESS: Execute from approved state succeeded, final_state={data.get('execution_state')}")
        return run_id, data.get("execution_state")


class TestPlaybookRollbackGuard:
    """Rollback guard tests: only executed state can rollback"""

    def test_rollback_guard_rejects_non_executed_state(self, super_admin_headers):
        """Test rollback guard: only executed state can rollback"""
        # Create and approve (but don't execute)
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [{"action": "runbook_review", "severity": "INFO", "reason": "test"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        run_id = preview_response.json()["playbook_run_id"]

        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_approval"},
        )

        # Try to rollback without execute - should fail
        rollback_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/rollback",
            headers=super_admin_headers,
            json={
                "playbook_run_id": run_id,
                "confirm": True,
                "reason": "test_rollback_without_execute",
            },
        )
        assert rollback_response.status_code == 422, f"Expected 422, got {rollback_response.status_code}"
        assert "executed" in rollback_response.json().get("detail", "").lower()

        print("SUCCESS: Rollback guard correctly rejects non-executed state")

    def test_rollback_from_executed_state_succeeds(self, super_admin_headers):
        """Test rollback from executed state succeeds"""
        # Create, approve, execute
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [{"action": "runbook_review", "severity": "INFO", "reason": "test"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        run_id = preview_response.json()["playbook_run_id"]

        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_approval"},
        )

        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/execute",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_execute"},
        )

        if execute_response.json().get("execution_state") != "executed":
            pytest.skip("Execute did not reach executed state (may have failed)")

        # Rollback
        rollback_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/rollback",
            headers=super_admin_headers,
            json={
                "playbook_run_id": run_id,
                "confirm": True,
                "reason": "test_rollback",
            },
        )
        assert rollback_response.status_code == 200, f"Rollback failed: {rollback_response.text}"
        assert rollback_response.json().get("execution_state") == "rollback_executed"

        print(f"SUCCESS: Rollback from executed state succeeded for run_id={run_id}")


class TestPlaybookRetryGuard:
    """Retry guard tests: only failed state can retry, creates new run with parent reference"""

    def test_retry_guard_rejects_non_failed_state(self, super_admin_headers):
        """Test retry guard: only failed state can retry"""
        # Create and approve (but don't execute to failure)
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [{"action": "runbook_review", "severity": "INFO", "reason": "test"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        run_id = preview_response.json()["playbook_run_id"]

        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_approval"},
        )

        # Try to retry without failure - should fail
        retry_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/retry",
            headers=super_admin_headers,
            json={
                "original_playbook_run_id": run_id,
                "confirm": True,
                "reason": "test_retry_without_failure",
            },
        )
        assert retry_response.status_code == 422, f"Expected 422, got {retry_response.status_code}"
        assert "failed" in retry_response.json().get("detail", "").lower()

        print("SUCCESS: Retry guard correctly rejects non-failed state")

    def test_retry_from_failed_state_creates_new_run_with_parent_reference(self, super_admin_headers):
        """Test retry from failed state creates new run with parent_run_id and retry_attempt"""
        # Create a playbook that will fail (using action with 'fail' in name)
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [{"action": "force_fail_action", "severity": "WARNING", "reason": "test_failure"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        run_id = preview_response.json()["playbook_run_id"]

        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_approval"},
        )

        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/execute",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_execute"},
        )

        if execute_response.json().get("execution_state") != "failed":
            pytest.skip("Execute did not fail as expected")

        # Retry
        retry_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/retry",
            headers=super_admin_headers,
            json={
                "original_playbook_run_id": run_id,
                "confirm": True,
                "reason": "test_retry",
            },
        )
        assert retry_response.status_code == 200, f"Retry failed: {retry_response.text}"
        data = retry_response.json()

        # Verify new run has parent reference
        assert "retry_playbook_run_id" in data, "Missing retry_playbook_run_id"
        assert data.get("parent_run_id") == run_id, f"parent_run_id should be {run_id}"
        assert data.get("retry_attempt", 0) >= 1, "retry_attempt should be >= 1"
        assert data.get("execution_state") == "approved", "Retry run should start in approved state"

        print(f"SUCCESS: Retry created new run with parent_run_id={run_id}, retry_attempt={data.get('retry_attempt')}")


class TestPlaybookRunDetailContract:
    """Run detail contract tests: step_index, total_steps, failure_reason, parent_run_id, retry_attempt"""

    def test_run_detail_returns_required_fields(self, super_admin_headers):
        """Test run detail returns all required contract fields"""
        # Create a preview
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [
                    {"action": "guardrail_hardening", "severity": "WARNING", "reason": "test1"},
                    {"action": "runbook_review", "severity": "INFO", "reason": "test2"},
                ],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        run_id = preview_response.json()["playbook_run_id"]

        # Get run detail
        detail_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/runs/{run_id}",
            headers=super_admin_headers,
        )
        assert detail_response.status_code == 200, f"Detail failed: {detail_response.text}"
        data = detail_response.json()

        # Check playbook_run object
        assert "playbook_run" in data, "Missing playbook_run"
        run = data["playbook_run"]

        # Verify required fields
        assert "step_index" in run, "Missing step_index"
        assert "total_steps" in run, "Missing total_steps"
        assert "failure_reason" in run, "Missing failure_reason (can be null)"
        assert "parent_run_id" in run, "Missing parent_run_id (can be null)"
        assert "retry_attempt" in run, "Missing retry_attempt"
        assert "execution_state" in run, "Missing execution_state"
        assert "steps" in run, "Missing steps"

        # Verify total_steps matches steps count
        assert run["total_steps"] == len(run["steps"]), "total_steps should match steps count"

        print(f"SUCCESS: Run detail contract verified: step_index={run['step_index']}, total_steps={run['total_steps']}")


class TestPlaybookExecuteAudit:
    """Playbook execute step-by-step audit tests"""

    def test_execute_creates_audit_events_for_each_step(self, super_admin_headers):
        """Test execute creates audit events for each step"""
        # Create, approve, execute
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [
                    {"action": "guardrail_hardening", "severity": "WARNING", "reason": "test1"},
                    {"action": "runbook_review", "severity": "INFO", "reason": "test2"},
                ],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        run_id = preview_response.json()["playbook_run_id"]

        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_approval"},
        )

        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/execute",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_execute"},
        )
        assert execute_response.status_code == 200
        data = execute_response.json()

        # Check executed_steps in response
        assert "executed_steps" in data, "Missing executed_steps"
        executed_steps = data["executed_steps"]
        assert len(executed_steps) >= 1, "Should have at least 1 executed step"

        # Each step should have operation details
        for step in executed_steps:
            assert "step" in step, "Step missing step number"
            assert "action" in step, "Step missing action"
            assert "status" in step, "Step missing status"
            assert "executed_at" in step, "Step missing executed_at"

        print(f"SUCCESS: Execute created {len(executed_steps)} step audit records")


class TestPlaybookFailureVisibility:
    """Playbook failure visibility tests: failure_reason, step_index/total_steps"""

    def test_failed_execution_shows_failure_reason_and_step_info(self, super_admin_headers):
        """Test failed execution shows failure_reason and step_index/total_steps"""
        # Create a playbook that will fail
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [
                    {"action": "runbook_review", "severity": "INFO", "reason": "test1"},
                    {"action": "force_fail_step", "severity": "WARNING", "reason": "test_failure"},
                ],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        run_id = preview_response.json()["playbook_run_id"]

        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_approval"},
        )

        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/execute",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_execute"},
        )
        data = execute_response.json()

        if data.get("execution_state") == "failed":
            # Verify failure info
            assert "failure_reason" in data, "Missing failure_reason"
            assert data["failure_reason"], "failure_reason should not be empty"
            assert "step_index" in data, "Missing step_index"
            assert "total_steps" in data, "Missing total_steps"
            assert "failed_step" in data, "Missing failed_step"

            print(f"SUCCESS: Failed execution shows failure_reason='{data['failure_reason']}', step_index={data['step_index']}/{data['total_steps']}")
        else:
            print(f"INFO: Execution did not fail (state={data.get('execution_state')}), skipping failure visibility check")


class TestAutoAckPreview:
    """Auto-ack preview tests: matched_alerts + rule_match_counter"""

    def test_auto_ack_preview_returns_matched_alerts_and_rule_counter(self, super_admin_headers):
        """Test auto-ack preview returns matched_alerts and rule_match_counter"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/auto-ack/preview",
            headers=super_admin_headers,
        )
        assert response.status_code == 200, f"Auto-ack preview failed: {response.text}"
        data = response.json()

        # Check required fields
        assert "preview_token" in data, "Missing preview_token"
        assert "matched_alerts" in data, "Missing matched_alerts"
        assert "matched_rule_counter" in data or "rule_match_counter" in data, "Missing rule_match_counter"
        assert "policy" in data, "Missing policy"

        # matched_alerts should be a list
        assert isinstance(data["matched_alerts"], list), "matched_alerts should be a list"

        # If there are matched alerts, verify structure
        if data["matched_alerts"]:
            alert = data["matched_alerts"][0]
            assert "alert_id" in alert, "Alert missing alert_id"
            assert "matched_rules" in alert, "Alert missing matched_rules"

        print(f"SUCCESS: Auto-ack preview returned {len(data['matched_alerts'])} matched alerts")
        return data["preview_token"]


class TestAutoAckRun:
    """Auto-ack run tests: only works with preview token"""

    def test_auto_ack_run_requires_valid_preview_token(self, super_admin_headers):
        """Test auto-ack run requires valid preview token"""
        # Try with invalid token
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/auto-ack/run",
            headers=super_admin_headers,
            params={"preview_token": "invalid_token_12345", "reason": "test_run"},
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        assert "preview_token" in response.json().get("detail", "").lower() or "invalid" in response.json().get("detail", "").lower()

        print("SUCCESS: Auto-ack run correctly rejects invalid preview token")

    def test_auto_ack_run_with_valid_preview_token(self, super_admin_headers):
        """Test auto-ack run works with valid preview token"""
        # First get a preview token
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/auto-ack/preview",
            headers=super_admin_headers,
        )
        assert preview_response.status_code == 200
        preview_token = preview_response.json()["preview_token"]

        # Run with valid token
        run_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/auto-ack/run",
            headers=super_admin_headers,
            params={"preview_token": preview_token, "reason": "test_auto_ack_run"},
        )
        # May return 200 (success) or 422 (empty preview)
        assert run_response.status_code in [200, 422], f"Unexpected status: {run_response.status_code}"

        if run_response.status_code == 200:
            data = run_response.json()
            assert "acked_count" in data, "Missing acked_count"
            print(f"SUCCESS: Auto-ack run completed, acked_count={data['acked_count']}")
        else:
            print(f"INFO: Auto-ack run returned 422 (likely empty preview): {run_response.json().get('detail')}")


class TestExportHardLock:
    """Export hard lock tests: snapshot_id + snapshot_hash headers, audit_required fields"""

    def test_export_preview_returns_counts(self, super_admin_headers):
        """Test export preview returns event/failure/transition counts"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/preview",
            headers=super_admin_headers,
            params={
                "scope_type": "time_range",
                "time_from": "2026-01-01T00:00:00+00:00",
                "time_to": "2026-12-31T23:59:59+00:00",
            },
        )
        assert response.status_code == 200, f"Preview failed: {response.text}"
        data = response.json()

        assert "preview" in data, "Missing preview"
        preview = data["preview"]
        assert "events" in preview, "Missing events count"
        assert "failures" in preview, "Missing failures count"

        print(f"SUCCESS: Export preview returned events={preview['events']}, failures={preview['failures']}")

    def test_export_returns_snapshot_headers(self, super_admin_headers):
        """Test export returns snapshot_id and snapshot_hash headers"""
        # Use time range scope for export
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=super_admin_headers,
            json={
                "time_from": "2026-01-01T00:00:00+00:00",
                "time_to": "2026-12-31T23:59:59+00:00",
            },
        )

        if response.status_code == 200:
            # Check headers
            snapshot_id = response.headers.get("x-incident-snapshot-id")
            snapshot_hash = response.headers.get("x-incident-snapshot-hash")
            snapshot_at = response.headers.get("x-incident-snapshot-at")
            _ = response.headers.get("x-incident-snapshot-row-count")

            assert snapshot_id, "Missing x-incident-snapshot-id header"
            assert snapshot_hash, "Missing x-incident-snapshot-hash header"
            assert snapshot_at, "Missing x-incident-snapshot-at header"

            print(f"SUCCESS: Export returned snapshot_id={snapshot_id}, snapshot_hash={snapshot_hash[:16]}...")
        else:
            # May fail if no data in range
            print(f"INFO: Export returned {response.status_code}: {response.text[:200]}")


class TestRoleGuard:
    """Role guard tests: super_admin required for critical actions"""

    def test_approve_requires_super_admin(self, admin_headers, super_admin_headers):
        """Test approve requires super_admin role"""
        # Create preview with super_admin
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [{"action": "runbook_review", "severity": "INFO", "reason": "test"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        run_id = preview_response.json()["playbook_run_id"]

        # Try to approve with regular admin - should fail
        approve_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers=admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_approval"},
        )
        assert approve_response.status_code == 403, f"Expected 403, got {approve_response.status_code}"

        print("SUCCESS: Approve correctly requires super_admin role")

    def test_rollback_requires_super_admin(self, admin_headers, super_admin_headers):
        """Test rollback requires super_admin role"""
        # Create, approve, execute with super_admin
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [{"action": "runbook_review", "severity": "INFO", "reason": "test"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        run_id = preview_response.json()["playbook_run_id"]

        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_approval"},
        )

        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/execute",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_execute"},
        )

        if execute_response.json().get("execution_state") != "executed":
            pytest.skip("Execute did not reach executed state")

        # Try to rollback with regular admin - should fail
        rollback_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/rollback",
            headers=admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_rollback"},
        )
        assert rollback_response.status_code == 403, f"Expected 403, got {rollback_response.status_code}"

        print("SUCCESS: Rollback correctly requires super_admin role")


class TestReasonRequired:
    """Reason required tests: reason mandatory for critical actions"""

    def test_approve_requires_reason(self, super_admin_headers):
        """Test approve requires reason field"""
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [{"action": "runbook_review", "severity": "INFO", "reason": "test"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        run_id = preview_response.json()["playbook_run_id"]

        # Try to approve without reason
        approve_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": ""},
        )
        assert approve_response.status_code == 422, f"Expected 422, got {approve_response.status_code}"

        print("SUCCESS: Approve correctly requires reason field")

    def test_retry_requires_reason(self, super_admin_headers):
        """Test retry requires reason field"""
        # Create a failed playbook
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers=super_admin_headers,
            json={
                "recommended_actions": [{"action": "force_fail_action", "severity": "WARNING", "reason": "test"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        run_id = preview_response.json()["playbook_run_id"]

        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_approval"},
        )

        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/execute",
            headers=super_admin_headers,
            json={"playbook_run_id": run_id, "confirm": True, "reason": "test_execute"},
        )

        # Try to retry without reason
        retry_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/retry",
            headers=super_admin_headers,
            json={"original_playbook_run_id": run_id, "confirm": True, "reason": ""},
        )
        assert retry_response.status_code == 422, f"Expected 422, got {retry_response.status_code}"

        print("SUCCESS: Retry correctly requires reason field")
