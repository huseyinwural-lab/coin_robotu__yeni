"""
Phase 5.6A Strategy Decay & Lifecycle Governance - Comprehensive Tests
Tests for: health monitor, decay detector, auto throttle/disable, lifecycle registry, governance audit, admin endpoints
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


@pytest.fixture(scope="module")
def admin_headers():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not defined")
    login_response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if login_response.status_code != 200:
        pytest.skip(f"Admin login failed: {login_response.text}")
    token = login_response.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def warm_up_paper_cycle(admin_headers):
    """Run paper cycle to populate governance data before tests."""
    requests.post(
        f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
        headers=admin_headers,
        timeout=30,
    )
    return True


class TestStrategyHealthEndpoint:
    """GET /api/admin/futures/strategy-health endpoint contract tests."""

    def test_health_endpoint_returns_200(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-health",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_health_endpoint_has_strategy_health_score(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-health",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "strategy_health_score" in payload
        assert isinstance(payload["strategy_health_score"], list)

    def test_health_endpoint_has_health_components(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-health",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "health_components" in payload

    def test_health_endpoint_has_lifecycle_state(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-health",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "lifecycle_state" in payload

    def test_health_endpoint_has_drawdown_state(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-health",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "drawdown_state" in payload

    def test_health_score_row_structure(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-health",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        health_rows = payload.get("strategy_health_score", [])
        if health_rows:
            row = health_rows[0]
            assert "strategy" in row
            assert "strategy_health_score" in row
            assert 0 <= row["strategy_health_score"] <= 100


class TestStrategyGovernanceEndpoint:
    """GET /api/admin/futures/strategy-governance endpoint contract tests."""

    def test_governance_endpoint_returns_200(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200

    def test_governance_has_strategy_health_score(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "strategy_health_score" in payload

    def test_governance_has_throttle_state(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "throttle_state" in payload

    def test_governance_has_disable_state(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "disable_state" in payload

    def test_governance_has_decay_events(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "decay_events" in payload

    def test_governance_has_health_components(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "health_components" in payload

    def test_governance_has_decay_reason_codes(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "decay_reason_codes" in payload

    def test_governance_has_lifecycle_state(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "lifecycle_state" in payload

    def test_governance_has_last_transition_at(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "last_transition_at" in payload

    def test_governance_has_drawdown_state(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "drawdown_state" in payload

    def test_governance_has_strategy_compare_mode(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "strategy_compare_mode" in payload

    def test_strategy_compare_mode_has_weekly_auto_summary(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        compare_mode = payload.get("strategy_compare_mode", {})
        assert "weekly_auto_summary" in compare_mode

    def test_strategy_compare_mode_has_metrics(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        compare_mode = payload.get("strategy_compare_mode", {})
        assert "metrics" in compare_mode

    def test_weekly_summary_structure(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        weekly_summary = payload.get("strategy_compare_mode", {}).get("weekly_auto_summary", {})
        assert "window_days" in weekly_summary
        assert "strategy_summaries" in weekly_summary
        assert "comparative_deltas" in weekly_summary


class TestGovernanceCompareMode:
    """Tests for strategy compare mode with query params."""

    def test_compare_mode_with_params(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            params={"compare_a": "trend_follow_v1", "compare_b": "mean_reversion_v1"},
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        payload = response.json()
        compare_mode = payload.get("strategy_compare_mode", {})
        selected = compare_mode.get("selected_strategies", [])
        assert len(selected) >= 1


class TestRegressionStrategyPerformance:
    """Regression tests: GET /api/admin/futures/strategy-performance."""

    def test_strategy_performance_returns_200(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-performance",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200

    def test_strategy_performance_has_strategy_registry(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-performance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "strategy_registry" in payload
        assert len(payload["strategy_registry"]) >= 1


class TestRegressionStrategyExecutionQuality:
    """Regression tests: GET /api/admin/futures/strategy-execution-quality."""

    def test_strategy_execution_quality_returns_200(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-execution-quality",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200

    def test_strategy_execution_quality_has_rolling_7d_tuning_score(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-execution-quality",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "rolling_7d_tuning_score" in payload

    def test_strategy_execution_quality_has_gate_reason_trend_7d(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-execution-quality",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "gate_reason_trend_7d" in payload
        # Should be 7 days of data
        assert len(payload["gate_reason_trend_7d"]) == 7


class TestGovernanceAuditSchema:
    """Verify governance audit events follow schema."""

    def test_governance_audit_events_present(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert "governance_audit_events" in payload

    def test_governance_audit_event_schema(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        events = payload.get("governance_audit_events", [])
        for event in events[:5]:
            assert "event" in event
            assert event["event"] in [
                "STRATEGY_DECAY_DETECTED",
                "STRATEGY_THROTTLED",
                "STRATEGY_DISABLED",
                "STRATEGY_RECOVERED",
            ]
            assert "strategy" in event
            assert "trigger_reason" in event


class TestDecayEventContract:
    """Verify decay event structure."""

    def test_decay_events_is_list(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert isinstance(payload.get("decay_events"), list)

    def test_decay_event_structure_if_present(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        decay_events = payload.get("decay_events", [])
        for event in decay_events[:3]:
            assert "strategy" in event
            assert "event" in event
            assert event["event"] == "STRATEGY_DECAY_DETECTED"


class TestThrottleStateContract:
    """Verify throttle state structure."""

    def test_throttle_state_is_list(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert isinstance(payload.get("throttle_state"), list)

    def test_throttle_state_row_structure(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        throttle_state = payload.get("throttle_state", [])
        for row in throttle_state[:3]:
            assert "strategy" in row
            assert "throttle_level" in row
            assert row["throttle_level"] in ["NONE", "L1", "L2", "L3"]
            assert "confidence_clamp" in row
            assert "max_position_ratio" in row
            assert "max_signals_per_cycle" in row


class TestDisableStateContract:
    """Verify disable state structure."""

    def test_disable_state_is_list(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert isinstance(payload.get("disable_state"), list)

    def test_disable_state_row_structure(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        disable_state = payload.get("disable_state", [])
        for row in disable_state[:3]:
            assert "strategy" in row
            assert "disable_state" in row
            assert row["disable_state"] in ["ACTIVE", "DISABLED"]


class TestLifecycleStateContract:
    """Verify lifecycle state structure."""

    def test_lifecycle_state_is_list(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        assert isinstance(payload.get("lifecycle_state"), list)

    def test_lifecycle_state_row_structure(self, admin_headers, warm_up_paper_cycle):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=20,
        )
        payload = response.json()
        lifecycle_state = payload.get("lifecycle_state", [])
        for row in lifecycle_state[:3]:
            assert "strategy" in row
            assert "lifecycle_state" in row
            assert row["lifecycle_state"] in ["ACTIVE", "THROTTLED", "DISABLED"]
