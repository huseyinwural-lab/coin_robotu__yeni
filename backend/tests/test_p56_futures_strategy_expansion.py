"""
Phase 5.6: Futures Strategy Expansion - Backend Tests
Tests for: mean_reversion_v1, breakout_v1, multi-strategy orchestration,
strategy-level execution analytics endpoints, strategy drift alerts.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token for authenticated requests."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Admin authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def admin_client(admin_token):
    """Return a requests session with admin auth header."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}",
    })
    return session


# =============================================================================
# 1. POST /api/admin/futures/strategy/run-paper-cycle - Strategy Registry Check
# =============================================================================
class TestRunPaperCycle:
    """Verify run-paper-cycle returns strategy_registry with all 3 strategies."""

    def test_run_paper_cycle_returns_200(self, admin_client):
        """POST run-paper-cycle should return 200."""
        response = admin_client.post(f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_run_paper_cycle_contains_strategy_registry(self, admin_client):
        """Response should contain strategy_registry list."""
        response = admin_client.post(f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle")
        assert response.status_code == 200
        data = response.json()
        assert "strategy_registry" in data, "strategy_registry key missing"
        assert isinstance(data["strategy_registry"], list), "strategy_registry should be list"

    def test_strategy_registry_contains_trend_follow_v1(self, admin_client):
        """strategy_registry should contain trend_follow_v1."""
        response = admin_client.post(f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle")
        data = response.json()
        registry = data.get("strategy_registry", [])
        assert "trend_follow_v1" in registry, f"trend_follow_v1 not in registry: {registry}"

    def test_strategy_registry_contains_mean_reversion_v1(self, admin_client):
        """strategy_registry should contain mean_reversion_v1."""
        response = admin_client.post(f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle")
        data = response.json()
        registry = data.get("strategy_registry", [])
        assert "mean_reversion_v1" in registry, f"mean_reversion_v1 not in registry: {registry}"

    def test_strategy_registry_contains_breakout_v1(self, admin_client):
        """strategy_registry should contain breakout_v1."""
        response = admin_client.post(f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle")
        data = response.json()
        registry = data.get("strategy_registry", [])
        assert "breakout_v1" in registry, f"breakout_v1 not in registry: {registry}"


# =============================================================================
# 2. GET /api/admin/futures/strategy-performance - Contract Validation
# =============================================================================
class TestStrategyPerformance:
    """Verify strategy-performance endpoint returns correct contract fields."""

    def test_strategy_performance_returns_200(self, admin_client):
        """GET strategy-performance should return 200."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-performance")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_strategy_performance_has_strategy_pnl_contribution(self, admin_client):
        """Response should have strategy_pnl_contribution field."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-performance")
        data = response.json()
        assert "strategy_pnl_contribution" in data, "strategy_pnl_contribution missing"
        assert isinstance(data["strategy_pnl_contribution"], list)

    def test_strategy_performance_has_strategy_signal_distribution(self, admin_client):
        """Response should have strategy_signal_distribution field."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-performance")
        data = response.json()
        assert "strategy_signal_distribution" in data, "strategy_signal_distribution missing"
        assert isinstance(data["strategy_signal_distribution"], list)

    def test_strategy_performance_has_exposure_tracking(self, admin_client):
        """Response should have exposure_tracking field."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-performance")
        data = response.json()
        assert "exposure_tracking" in data, "exposure_tracking missing"

    def test_strategy_performance_has_interaction_guard(self, admin_client):
        """Response should have interaction_guard field."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-performance")
        data = response.json()
        assert "interaction_guard" in data, "interaction_guard missing"

    def test_strategy_performance_has_strategy_attribution(self, admin_client):
        """Response should have strategy_attribution field."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-performance")
        data = response.json()
        assert "strategy_attribution" in data, "strategy_attribution missing"
        assert isinstance(data["strategy_attribution"], list)

    def test_strategy_performance_has_strategy_drift_alerts(self, admin_client):
        """Response should have strategy_drift_alerts field."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-performance")
        data = response.json()
        assert "strategy_drift_alerts" in data, "strategy_drift_alerts missing"
        assert isinstance(data["strategy_drift_alerts"], list)


# =============================================================================
# 3. GET /api/admin/futures/strategy-execution-quality - Contract Validation
# =============================================================================
class TestStrategyExecutionQuality:
    """Verify strategy-execution-quality endpoint returns correct contract."""

    def test_strategy_execution_quality_returns_200(self, admin_client):
        """GET strategy-execution-quality should return 200."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-execution-quality")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_has_strategy_execution_quality(self, admin_client):
        """Response should have strategy_execution_quality list."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-execution-quality")
        data = response.json()
        assert "strategy_execution_quality" in data
        assert isinstance(data["strategy_execution_quality"], list)

    def test_has_strategy_slippage(self, admin_client):
        """Response should have strategy_slippage list."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-execution-quality")
        data = response.json()
        assert "strategy_slippage" in data
        assert isinstance(data["strategy_slippage"], list)

    def test_has_strategy_latency(self, admin_client):
        """Response should have strategy_latency list."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-execution-quality")
        data = response.json()
        assert "strategy_latency" in data
        assert isinstance(data["strategy_latency"], list)

    def test_has_strategy_reject_rate(self, admin_client):
        """Response should have strategy_reject_rate list."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-execution-quality")
        data = response.json()
        assert "strategy_reject_rate" in data
        assert isinstance(data["strategy_reject_rate"], list)

    def test_has_strategy_confidence_vs_result(self, admin_client):
        """Response should have strategy_confidence_vs_result list."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-execution-quality")
        data = response.json()
        assert "strategy_confidence_vs_result" in data
        assert isinstance(data["strategy_confidence_vs_result"], list)

    def test_has_rolling_7d_tuning_score(self, admin_client):
        """Response should have rolling_7d_tuning_score object."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-execution-quality")
        data = response.json()
        assert "rolling_7d_tuning_score" in data
        tuning = data["rolling_7d_tuning_score"]
        assert "latest_score" in tuning or "days" in tuning

    def test_gate_reason_trend_7d_has_7_days(self, admin_client):
        """gate_reason_trend_7d should have exactly 7 day entries."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-execution-quality")
        data = response.json()
        assert "gate_reason_trend_7d" in data
        trend = data["gate_reason_trend_7d"]
        assert len(trend) == 7, f"Expected 7 days, got {len(trend)}"

    def test_architecture_checklist_15_has_15_items(self, admin_client):
        """architecture_checklist_15 should have exactly 15 items."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-execution-quality")
        data = response.json()
        assert "architecture_checklist_15" in data
        checklist = data["architecture_checklist_15"]
        assert len(checklist) == 15, f"Expected 15 items, got {len(checklist)}"


# =============================================================================
# 4. Multi-Strategy Orchestration - Interaction Guard + Exposure Tracker
# =============================================================================
class TestMultiStrategyOrchestration:
    """Test interaction guard and exposure tracker blocking decisions."""

    def test_paper_cycle_has_interaction_guard_blocked_total(self, admin_client):
        """interaction_guard should have blocked_total field."""
        response = admin_client.post(f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle")
        data = response.json()
        guard = data.get("interaction_guard", {})
        assert "blocked_total" in guard, "blocked_total missing in interaction_guard"
        assert isinstance(guard["blocked_total"], int)

    def test_paper_cycle_has_exposure_blocked_total(self, admin_client):
        """interaction_guard should have exposure_blocked_total field."""
        response = admin_client.post(f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle")
        data = response.json()
        guard = data.get("interaction_guard", {})
        assert "exposure_blocked_total" in guard, "exposure_blocked_total missing"
        assert isinstance(guard["exposure_blocked_total"], int)

    def test_paper_cycle_has_exposure_tracking(self, admin_client):
        """exposure_tracking should contain symbol_exposure dict."""
        response = admin_client.post(f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle")
        data = response.json()
        tracking = data.get("exposure_tracking", {})
        assert "symbol_exposure" in tracking or "exposure_limits" in tracking


# =============================================================================
# 5. Strategy Drift Alert Event Contract
# =============================================================================
class TestStrategyDriftAlerts:
    """Verify strategy_drift_alerts event contract."""

    def test_drift_alerts_event_is_strategy_drift_alert(self, admin_client):
        """All drift alerts should have event == STRATEGY_DRIFT_ALERT."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-performance")
        data = response.json()
        alerts = data.get("strategy_drift_alerts", [])
        for alert in alerts:
            assert alert.get("event") == "STRATEGY_DRIFT_ALERT", f"Unexpected event: {alert.get('event')}"

    def test_drift_alerts_have_strategy_field(self, admin_client):
        """Each drift alert should have strategy field."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-performance")
        data = response.json()
        alerts = data.get("strategy_drift_alerts", [])
        for alert in alerts:
            assert "strategy" in alert, "strategy field missing in drift alert"

    def test_drift_alerts_have_severity_field(self, admin_client):
        """Each drift alert should have severity field."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-performance")
        data = response.json()
        alerts = data.get("strategy_drift_alerts", [])
        for alert in alerts:
            assert "severity" in alert, "severity field missing in drift alert"


# =============================================================================
# 6. Regression Tests - Existing Endpoints Should Not Be Broken
# =============================================================================
class TestRegressionEndpoints:
    """Ensure existing endpoints still work after Phase 5.6 changes."""

    def test_strategy_status_returns_200(self, admin_client):
        """GET /api/admin/futures/strategy/status should return 200."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy/status")
        assert response.status_code == 200, f"Regression: strategy/status broken: {response.text}"

    def test_strategy_status_has_metrics(self, admin_client):
        """strategy/status should have metrics field."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy/status")
        data = response.json()
        assert "metrics" in data, "metrics field missing in strategy/status"

    def test_decision_diagnostics_returns_200(self, admin_client):
        """GET /api/admin/futures/decision-diagnostics should return 200."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/decision-diagnostics")
        assert response.status_code == 200, f"Regression: decision-diagnostics broken: {response.text}"

    def test_decision_diagnostics_has_false_counts(self, admin_client):
        """decision-diagnostics should have false_allow_count and false_reject_count."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/decision-diagnostics")
        data = response.json()
        assert "false_allow_count" in data, "false_allow_count missing"
        assert "false_reject_count" in data, "false_reject_count missing"

    def test_leverage_status_returns_200(self, admin_client):
        """GET /api/admin/futures/leverage/status should return 200."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/leverage/status")
        assert response.status_code == 200, f"Regression: leverage/status broken: {response.text}"

    def test_leverage_status_has_final_leverage(self, admin_client):
        """leverage/status should have final_leverage field."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/leverage/status")
        data = response.json()
        assert "final_leverage" in data, "final_leverage missing in leverage/status"


# =============================================================================
# 7. Data Validation Tests - Verify Response Structure and Values
# =============================================================================
class TestDataValidation:
    """Validate response data structure and field values."""

    def test_pnl_contribution_structure(self, admin_client):
        """Each pnl_contribution item should have strategy, pnl_attribution, etc."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-performance")
        data = response.json()
        for item in data.get("strategy_pnl_contribution", []):
            assert "strategy" in item
            assert "pnl_attribution" in item
            assert "pnl_contribution_ratio" in item
            assert "trade_count" in item

    def test_signal_distribution_structure(self, admin_client):
        """Each signal_distribution item should have signal_total, allowed_total, etc."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-performance")
        data = response.json()
        for item in data.get("strategy_signal_distribution", []):
            assert "strategy" in item
            assert "signal_total" in item
            assert "allowed_total" in item
            assert "rejected_total" in item

    def test_execution_quality_structure(self, admin_client):
        """Each execution_quality item should have strategy and execution_quality."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-execution-quality")
        data = response.json()
        for item in data.get("strategy_execution_quality", []):
            assert "strategy" in item
            assert "execution_quality" in item

    def test_checklist_item_structure(self, admin_client):
        """Each checklist item should have id, check, pass, evidence."""
        response = admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-execution-quality")
        data = response.json()
        for item in data.get("architecture_checklist_15", []):
            assert "id" in item
            assert "check" in item
            assert "pass" in item
            assert "evidence" in item
