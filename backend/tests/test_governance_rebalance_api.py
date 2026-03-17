"""
Test suite for Strategy Intelligence Governance Features (P1 Priority)
Tests rebalance cadence governance (time-window + max-shift caps) under strategy intelligence.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Admin credentials for auth
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token for authenticated requests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")


@pytest.fixture
def auth_headers(admin_token):
    """Return headers with Bearer token"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestStrategyIntelligenceGovernanceAPI:
    """Tests for GET /api/admin/strategy-intelligence governance_summary object"""

    def test_strategy_intelligence_endpoint_returns_200(self, auth_headers):
        """Verify endpoint returns 200 OK"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: /api/admin/strategy-intelligence returns 200 OK")

    def test_strategy_intelligence_has_governance_summary(self, auth_headers):
        """Verify governance_summary object is present in response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert "governance_summary" in data, "governance_summary field missing"
        print(f"PASS: governance_summary present: {data['governance_summary']}")

    def test_governance_summary_has_required_fields(self, auth_headers):
        """Verify governance_summary has all required governance fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        governance = data.get("governance_summary", {})

        required_fields = [
            "cadence_window_minutes",
            "max_weight_shift_per_cycle",
            "max_capital_shift_pct",
            "drift_threshold",
            "cadence_blocked_strategies",
            "weight_shift_capped_strategies",
            "capital_shift_capped_strategies",
        ]

        for field in required_fields:
            assert field in governance, f"Missing governance field: {field}"
            print(f"PASS: governance_summary.{field} = {governance[field]}")

    def test_governance_values_are_numeric(self, auth_headers):
        """Verify governance values are correct numeric types"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        governance = data.get("governance_summary", {})

        # Integer fields
        assert isinstance(governance.get("cadence_window_minutes"), int), "cadence_window_minutes must be int"
        assert isinstance(governance.get("cadence_blocked_strategies"), int), "cadence_blocked_strategies must be int"
        assert isinstance(governance.get("weight_shift_capped_strategies"), int), "weight_shift_capped_strategies must be int"
        assert isinstance(governance.get("capital_shift_capped_strategies"), int), "capital_shift_capped_strategies must be int"

        # Float fields
        assert isinstance(governance.get("max_weight_shift_per_cycle"), (int, float)), "max_weight_shift_per_cycle must be numeric"
        assert isinstance(governance.get("max_capital_shift_pct"), (int, float)), "max_capital_shift_pct must be numeric"
        assert isinstance(governance.get("drift_threshold"), (int, float)), "drift_threshold must be numeric"

        print("PASS: All governance values have correct types")


class TestCapitalRebalanceEventsGovernance:
    """Tests for capital_rebalance_events governance fields"""

    def test_rebalance_events_include_governance_fields(self, auth_headers):
        """Verify capital_rebalance_events include target_strategy_weight, cadence_window_blocked, max_weight_shift_applied, max_capital_shift_applied"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()

        events = data.get("capital_rebalance_events", [])
        print(f"Found {len(events)} capital_rebalance_events")

        if len(events) == 0:
            print("WARNING: No capital_rebalance_events found - cannot verify governance fields")
            pytest.skip("No rebalance events to test governance fields")

        # Check governance fields on first event
        event = events[0]
        governance_fields = [
            "target_strategy_weight",
            "cadence_window_blocked",
            "max_weight_shift_applied",
            "max_capital_shift_applied",
        ]

        for field in governance_fields:
            assert field in event, f"Missing governance field in rebalance event: {field}"
            print(f"PASS: capital_rebalance_events[0].{field} = {event[field]}")

    def test_rebalance_event_has_all_expected_fields(self, auth_headers):
        """Verify rebalance event schema is complete"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        events = data.get("capital_rebalance_events", [])

        if len(events) == 0:
            pytest.skip("No rebalance events to verify")

        event = events[0]
        expected_fields = [
            "strategy_id",
            "old_strategy_weight",
            "new_strategy_weight",
            "target_strategy_weight",
            "capital_shift",
            "throttle_signal",
            "allocation_drift",
            "strategy_performance_delta",
            "risk_adjusted_return",
            "cadence_window_blocked",
            "max_weight_shift_applied",
            "max_capital_shift_applied",
        ]

        for field in expected_fields:
            assert field in event, f"Missing field in rebalance event: {field}"

        print(f"PASS: capital_rebalance_event has all expected fields: {list(event.keys())}")


class TestRegressionExistingFields:
    """Regression: existing strategy intelligence response fields still present"""

    def test_strategy_conflicts_field_present(self, auth_headers):
        """Verify strategy_conflicts field is still present"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert "strategy_conflicts" in data, "strategy_conflicts field missing (regression)"
        assert isinstance(data["strategy_conflicts"], list), "strategy_conflicts should be list"
        print(f"PASS: strategy_conflicts present ({len(data['strategy_conflicts'])} items)")

    def test_hedge_suggestions_field_present(self, auth_headers):
        """Verify hedge_suggestions field is still present"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert "hedge_suggestions" in data, "hedge_suggestions field missing (regression)"
        assert isinstance(data["hedge_suggestions"], list), "hedge_suggestions should be list"
        print(f"PASS: hedge_suggestions present ({len(data['hedge_suggestions'])} items)")

    def test_allocation_drift_field_present(self, auth_headers):
        """Verify allocation_drift field is still present"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert "allocation_drift" in data, "allocation_drift field missing (regression)"
        assert isinstance(data["allocation_drift"], (int, float)), "allocation_drift should be numeric"
        print(f"PASS: allocation_drift present: {data['allocation_drift']}")

    def test_risk_adjusted_return_field_present(self, auth_headers):
        """Verify risk_adjusted_return field is still present"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert "risk_adjusted_return" in data, "risk_adjusted_return field missing (regression)"
        assert isinstance(data["risk_adjusted_return"], (int, float)), "risk_adjusted_return should be numeric"
        print(f"PASS: risk_adjusted_return present: {data['risk_adjusted_return']}")

    def test_strategy_performance_delta_field_present(self, auth_headers):
        """Verify strategy_performance_delta field is still present"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert "strategy_performance_delta" in data, "strategy_performance_delta field missing (regression)"
        assert isinstance(data["strategy_performance_delta"], (int, float)), "strategy_performance_delta should be numeric"
        print(f"PASS: strategy_performance_delta present: {data['strategy_performance_delta']}")

    def test_generated_at_field_present(self, auth_headers):
        """Verify generated_at timestamp field is present"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert "generated_at" in data, "generated_at field missing"
        print(f"PASS: generated_at present: {data['generated_at']}")

    def test_capital_rebalance_events_field_present(self, auth_headers):
        """Verify capital_rebalance_events field is present"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert "capital_rebalance_events" in data, "capital_rebalance_events field missing"
        assert isinstance(data["capital_rebalance_events"], list), "capital_rebalance_events should be list"
        print(f"PASS: capital_rebalance_events present ({len(data['capital_rebalance_events'])} items)")


class TestUnitEngineLogic:
    """Unit tests for run_dynamic_capital_rebalance engine logic"""

    def test_engine_returns_governance_summary(self):
        """Verify engine returns governance_summary in result"""
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path("/app/backend")))
        from services.capital_rebalance_engine import run_dynamic_capital_rebalance

        payload = [
            {
                "strategy_id": "test_strat_1",
                "capital_weight": 0.5,
                "max_capital": 10000,
                "current_capital": 5000,
                "performance_score": 80,
                "confidence_score": 60,
                "signal_decay": 0.2,
                "execution_quality_score": 85,
                "realized_return": 2.5,
                "risk_score": 0.3,
            }
        ]

        result = run_dynamic_capital_rebalance(payload)
        assert "governance_summary" in result, "governance_summary missing from engine output"
        governance = result["governance_summary"]
        assert "cadence_window_minutes" in governance
        assert "max_weight_shift_per_cycle" in governance
        assert "max_capital_shift_pct" in governance
        assert "drift_threshold" in governance
        assert "cadence_blocked_strategies" in governance
        assert "weight_shift_capped_strategies" in governance
        assert "capital_shift_capped_strategies" in governance
        print(f"PASS: Engine returns governance_summary: {governance}")

    def test_events_include_governance_fields(self):
        """Verify events include governance fields"""
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path("/app/backend")))
        from services.capital_rebalance_engine import run_dynamic_capital_rebalance

        payload = [
            {
                "strategy_id": "gov_test_strat",
                "capital_weight": 0.5,
                "max_capital": 10000,
                "current_capital": 5000,
                "performance_score": 80,
                "confidence_score": 60,
                "signal_decay": 0.2,
                "execution_quality_score": 85,
                "realized_return": 2.5,
                "risk_score": 0.3,
            }
        ]

        result = run_dynamic_capital_rebalance(payload)
        events = result.get("events", [])
        assert len(events) > 0, "No events returned"

        event = events[0]
        governance_fields = [
            "target_strategy_weight",
            "cadence_window_blocked",
            "max_weight_shift_applied",
            "max_capital_shift_applied",
        ]

        for field in governance_fields:
            assert field in event, f"Missing field in event: {field}"

        print(f"PASS: Event includes governance fields: {list(event.keys())}")
