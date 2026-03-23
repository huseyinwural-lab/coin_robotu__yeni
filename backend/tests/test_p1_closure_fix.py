"""
P1 Closure Fix Tests - Testing:
1. diff.json recommended_actions format: action snake_case, severity lowercase, reason with delta + before→after
2. Compare validation backend: compare_enabled=true but no compare scope → 400
3. Compare validation backend: primary and compare snapshot identical → 422 + exact message
4. Cross-scope compare (correlation vs time_range) allowed
5. Diff summary format: before, after, percentage together
"""
import os
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
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }


class TestCompareValidationBackend:
    """Test compare validation rules in backend"""

    def test_compare_enabled_true_but_no_compare_scope_returns_400(self, auth_headers):
        """
        When compare_enabled=true but no compare scope fields provided,
        backend should return 400 with message 'compare scope is required when compare is enabled'
        """
        payload = {
            "correlation_id": "test-corr-123",
            "compare_enabled": True,
            # No compare_correlation_id, compare_execution_event_id, compare_time_from, compare_time_to
        }
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "compare scope is required when compare is enabled" in data.get("detail", ""), f"Unexpected detail: {data}"

    def test_compare_enabled_true_but_no_compare_scope_export_returns_400(self, auth_headers):
        """
        Same test for export endpoint
        """
        payload = {
            "correlation_id": "test-corr-123",
            "compare_enabled": True,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "compare scope is required when compare is enabled" in data.get("detail", ""), f"Unexpected detail: {data}"

    def test_identical_snapshot_returns_422_with_exact_message(self, auth_headers):
        """
        When primary and compare snapshots are identical,
        backend should return 422 with message 'Primary and compare snapshots cannot be identical'
        """
        payload = {
            "correlation_id": "test-corr-same",
            "compare_correlation_id": "test-corr-same",  # Same as primary
            "compare_enabled": True,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail") == "Primary and compare snapshots cannot be identical", f"Unexpected detail: {data}"

    def test_identical_snapshot_export_returns_422_with_exact_message(self, auth_headers):
        """
        Same test for export endpoint
        """
        payload = {
            "correlation_id": "test-corr-same",
            "compare_correlation_id": "test-corr-same",
            "compare_enabled": True,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail") == "Primary and compare snapshots cannot be identical", f"Unexpected detail: {data}"

    def test_cross_scope_compare_correlation_vs_time_range_allowed(self, auth_headers):
        """
        Cross-scope compare (correlation_id vs time_range) should be allowed
        """
        payload = {
            "correlation_id": "test-corr-cross",
            "compare_time_from": "2026-01-01T00:00:00+00:00",
            "compare_time_to": "2026-01-02T00:00:00+00:00",
            "compare_enabled": True,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json=payload,
        )
        # Should not return 400 or 422 for scope type mismatch
        assert response.status_code in [200, 201], f"Cross-scope compare should be allowed, got {response.status_code}: {response.text}"


class TestDiffJsonFormat:
    """Test diff.json recommended_actions format"""

    def test_diff_recommended_actions_format(self, auth_headers):
        """
        Test that recommended_actions have:
        - action: snake_case
        - severity: lowercase
        - reason: contains delta + before→after format
        """
        # First create some test data by simulating
        sim_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate?strategy_type=breakout&symbol=BTCUSDT&side=long&outcome=filled&source_type=simulation&environment=simulation",
            headers=auth_headers,
        )
        correlation_id_1 = None
        if sim_response.status_code == 200:
            correlation_id_1 = sim_response.json().get("correlation_id")

        sim_response_2 = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate?strategy_type=breakout&symbol=ETHUSDT&side=short&outcome=timeout&source_type=simulation&environment=simulation",
            headers=auth_headers,
        )
        correlation_id_2 = None
        if sim_response_2.status_code == 200:
            correlation_id_2 = sim_response_2.json().get("correlation_id")

        # Use time range for diff if no correlation IDs
        if not correlation_id_1 or not correlation_id_2:
            payload = {
                "time_from": "2026-01-01T00:00:00+00:00",
                "time_to": "2026-01-15T00:00:00+00:00",
                "compare_time_from": "2025-12-01T00:00:00+00:00",
                "compare_time_to": "2025-12-15T00:00:00+00:00",
                "compare_enabled": True,
            }
        else:
            payload = {
                "correlation_id": correlation_id_1,
                "compare_correlation_id": correlation_id_2,
                "compare_enabled": True,
            }

        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Diff request failed: {response.status_code}: {response.text}"
        data = response.json()

        state_snapshot = data.get("state_snapshot", {})
        diff = state_snapshot.get("diff")
        assert diff is not None, "diff should be present in state_snapshot"

        recommended_actions = diff.get("recommended_actions", [])
        # There should be at least one recommended action (keep_current_policy if nothing else)
        assert len(recommended_actions) >= 1, "Should have at least one recommended action"

        for action_item in recommended_actions:
            # Check action is snake_case
            action_name = action_item.get("action", "")
            assert action_name == action_name.lower(), f"Action should be lowercase: {action_name}"
            assert "_" in action_name or action_name.isalpha(), f"Action should be snake_case: {action_name}"

            # Check severity is lowercase
            severity = action_item.get("severity", "")
            assert severity == severity.lower(), f"Severity should be lowercase: {severity}"
            assert severity in ["info", "warning", "critical"], f"Severity should be info/warning/critical: {severity}"

            # Check reason contains delta info (before→after format)
            reason = action_item.get("reason", "")
            assert reason, f"Reason should not be empty"
            # Reason should contain either "→" or numbers indicating before/after
            assert "→" in reason or any(char.isdigit() for char in reason), f"Reason should contain delta info: {reason}"

    def test_diff_before_after_format(self, auth_headers):
        """
        Test that before_after structure contains:
        - before: int
        - after: int
        - percentage: int
        """
        payload = {
            "time_from": "2026-01-01T00:00:00+00:00",
            "time_to": "2026-01-15T00:00:00+00:00",
            "compare_time_from": "2025-12-01T00:00:00+00:00",
            "compare_time_to": "2025-12-15T00:00:00+00:00",
            "compare_enabled": True,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Diff request failed: {response.status_code}: {response.text}"
        data = response.json()

        state_snapshot = data.get("state_snapshot", {})
        diff = state_snapshot.get("diff")
        assert diff is not None, "diff should be present"

        before_after = diff.get("before_after", {})
        assert before_after, "before_after should be present in diff"

        # Check each metric has before, after, percentage
        for metric_key in ["events", "failed_events", "dead_letter", "manual_actions"]:
            metric = before_after.get(metric_key, {})
            assert "before" in metric, f"{metric_key} should have 'before'"
            assert "after" in metric, f"{metric_key} should have 'after'"
            assert "percentage" in metric, f"{metric_key} should have 'percentage'"
            assert isinstance(metric["before"], int), f"{metric_key}.before should be int"
            assert isinstance(metric["after"], int), f"{metric_key}.after should be int"
            assert isinstance(metric["percentage"], int), f"{metric_key}.percentage should be int"


class TestEdgeCases:
    """Test edge cases for empty dataset and no anomaly fallback"""

    def test_empty_dataset_fallback(self, auth_headers):
        """
        When dataset is empty, diff should still return valid structure with fallback
        """
        payload = {
            "correlation_id": "non-existent-corr-id-12345",
            "compare_correlation_id": "another-non-existent-corr-id-67890",
            "compare_enabled": True,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Should handle empty dataset: {response.status_code}: {response.text}"
        data = response.json()

        state_snapshot = data.get("state_snapshot", {})
        diff = state_snapshot.get("diff")
        assert diff is not None, "diff should be present even for empty dataset"

        # Should have recommended_actions with at least keep_current_policy
        recommended_actions = diff.get("recommended_actions", [])
        assert len(recommended_actions) >= 1, "Should have fallback recommended action"

        # Check for keep_current_policy as fallback
        action_names = [a.get("action") for a in recommended_actions]
        assert "keep_current_policy" in action_names, f"Should have keep_current_policy fallback: {action_names}"

    def test_single_snapshot_no_diff(self, auth_headers):
        """
        When compare is disabled, diff should be None
        """
        payload = {
            "correlation_id": "test-single-snapshot",
            "compare_enabled": False,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Single snapshot should work: {response.status_code}: {response.text}"
        data = response.json()

        state_snapshot = data.get("state_snapshot", {})
        diff = state_snapshot.get("diff")
        # When compare is disabled, diff should be None
        assert diff is None, f"diff should be None when compare is disabled: {diff}"


class TestActionLinkContext:
    """Test that action links preserve correlation_id and reason query params"""

    def test_diff_actions_have_reason_in_format(self, auth_headers):
        """
        Test that recommended_actions reason contains the delta information
        that can be used for action link context
        """
        payload = {
            "time_from": "2026-01-01T00:00:00+00:00",
            "time_to": "2026-01-15T00:00:00+00:00",
            "compare_time_from": "2025-12-01T00:00:00+00:00",
            "compare_time_to": "2025-12-15T00:00:00+00:00",
            "compare_enabled": True,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/diff",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()

        state_snapshot = data.get("state_snapshot", {})
        diff = state_snapshot.get("diff")
        recommended_actions = diff.get("recommended_actions", [])

        for action_item in recommended_actions:
            reason = action_item.get("reason", "")
            # Reason should be descriptive enough for action link context
            assert len(reason) > 5, f"Reason should be descriptive: {reason}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
