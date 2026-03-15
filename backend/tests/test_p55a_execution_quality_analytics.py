"""
Phase 5.5A Execution Quality Analytics - Test Suite

Tests for:
1. GET /api/admin/futures/testnet/execution-quality - contract fields
2. GET /api/admin/futures/testnet/execution-quality/rolling-7d - 7 points + latest_score
3. GET /api/admin/futures/testnet/status - execution_quality and architecture_checklist_15
4. GET /api/admin/futures/testnet/release-gate - regression PASS
5. Regression endpoints: strategy/status, decision-diagnostics, leverage/status
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Admin credentials
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    assert "access_token" in data, "No access_token in login response"
    return data["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Get admin headers with auth"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestExecutionQualityEndpoint:
    """Tests for GET /api/admin/futures/testnet/execution-quality"""

    def test_execution_quality_returns_200(self, admin_headers):
        """Verify endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_execution_quality_has_required_fields(self, admin_headers):
        """Verify all required contract fields are present"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality",
            headers=admin_headers,
        )
        data = response.json()
        
        required_fields = [
            "days",
            "total_orders",
            "placement_success_ratio",
            "reject_rate",
            "partial_fill_quality",
            "slippage_summary",
            "fill_latency_ms",
            "execution_quality_score",
            "symbol_execution_quality",
            "gate_reason_distribution",
            "gate_reason_trend_7d",
            "symbol_drift_alerts",
            "rolling_7d_tuning_score",
            "updated_at",
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_execution_quality_rolling_tuning_score_structure(self, admin_headers):
        """Verify rolling_7d_tuning_score has correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality",
            headers=admin_headers,
        )
        data = response.json()
        
        tuning = data.get("rolling_7d_tuning_score", {})
        assert "score" in tuning, "Missing score in rolling_7d_tuning_score"
        assert "components" in tuning, "Missing components in rolling_7d_tuning_score"
        assert isinstance(tuning["score"], (int, float)), "score should be numeric"
        
        components = tuning.get("components", {})
        assert "fill_ratio" in components, "Missing fill_ratio in components"
        assert "reject_penalty" in components, "Missing reject_penalty in components"
        assert "false_allow_penalty" in components, "Missing false_allow_penalty in components"
        assert "false_reject_penalty" in components, "Missing false_reject_penalty in components"

    def test_execution_quality_gate_reason_trend_is_list(self, admin_headers):
        """Verify gate_reason_trend_7d is a list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality",
            headers=admin_headers,
        )
        data = response.json()
        
        trend = data.get("gate_reason_trend_7d", [])
        assert isinstance(trend, list), "gate_reason_trend_7d should be a list"

    def test_execution_quality_symbol_drift_alerts_is_list(self, admin_headers):
        """Verify symbol_drift_alerts is a list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality",
            headers=admin_headers,
        )
        data = response.json()
        
        alerts = data.get("symbol_drift_alerts", [])
        assert isinstance(alerts, list), "symbol_drift_alerts should be a list"

    def test_execution_quality_false_compare_present(self, admin_headers):
        """Verify false_allow_reject_comparison_by_layer is present"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality",
            headers=admin_headers,
        )
        data = response.json()
        
        assert "false_allow_reject_comparison_by_layer" in data, "Missing false_allow_reject_comparison_by_layer"
        assert isinstance(data["false_allow_reject_comparison_by_layer"], list), "false_allow_reject_comparison_by_layer should be a list"


class TestRolling7dEndpoint:
    """Tests for GET /api/admin/futures/testnet/execution-quality/rolling-7d"""

    def test_rolling_7d_returns_200(self, admin_headers):
        """Verify endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality/rolling-7d",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_rolling_7d_has_7_points(self, admin_headers):
        """Verify points array has 7 items"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality/rolling-7d",
            headers=admin_headers,
        )
        data = response.json()
        
        points = data.get("points", [])
        assert len(points) == 7, f"Expected 7 points, got {len(points)}"

    def test_rolling_7d_has_latest_score(self, admin_headers):
        """Verify latest_score field is present"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality/rolling-7d",
            headers=admin_headers,
        )
        data = response.json()
        
        assert "latest_score" in data, "Missing latest_score field"
        assert isinstance(data["latest_score"], (int, float)), "latest_score should be numeric"

    def test_rolling_7d_points_structure(self, admin_headers):
        """Verify each point has required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality/rolling-7d",
            headers=admin_headers,
        )
        data = response.json()
        
        for point in data.get("points", []):
            assert "date" in point, "Missing date in point"
            assert "tuning_score" in point, "Missing tuning_score in point"
            assert "order_count" in point, "Missing order_count in point"

    def test_rolling_7d_has_days_field(self, admin_headers):
        """Verify days field equals 7"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality/rolling-7d",
            headers=admin_headers,
        )
        data = response.json()
        
        assert data.get("days") == 7, f"Expected days=7, got {data.get('days')}"


class TestStatusEndpoint:
    """Tests for GET /api/admin/futures/testnet/status"""

    def test_status_returns_200(self, admin_headers):
        """Verify endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/status",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_status_has_execution_quality(self, admin_headers):
        """Verify execution_quality field is present"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/status",
            headers=admin_headers,
        )
        data = response.json()
        
        assert "execution_quality" in data, "Missing execution_quality field"
        eq = data["execution_quality"]
        assert isinstance(eq, dict), "execution_quality should be a dict"

    def test_status_execution_quality_has_new_fields(self, admin_headers):
        """Verify execution_quality contains Phase 5.5A fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/status",
            headers=admin_headers,
        )
        data = response.json()
        eq = data.get("execution_quality", {})
        
        required_5_5a_fields = [
            "rolling_7d_tuning_score",
            "symbol_drift_alerts",
            "gate_reason_trend_7d",
            "false_allow_reject_comparison_by_layer",
        ]
        
        for field in required_5_5a_fields:
            assert field in eq, f"Missing {field} in execution_quality"

    def test_status_has_architecture_checklist_15(self, admin_headers):
        """Verify architecture_checklist_15 has 15 items"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/status",
            headers=admin_headers,
        )
        data = response.json()
        
        checklist = data.get("architecture_checklist_15", [])
        assert len(checklist) == 15, f"Expected 15 checklist items, got {len(checklist)}"

    def test_status_checklist_item_structure(self, admin_headers):
        """Verify checklist items have required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/status",
            headers=admin_headers,
        )
        data = response.json()
        
        for item in data.get("architecture_checklist_15", []):
            assert "id" in item, "Missing id in checklist item"
            assert "check" in item, "Missing check in checklist item"
            assert "pass" in item, "Missing pass in checklist item"
            assert "evidence" in item, "Missing evidence in checklist item"
            assert "severity" in item, "Missing severity in checklist item"


class TestReleaseGateEndpoint:
    """Tests for GET /api/admin/futures/testnet/release-gate"""

    def test_release_gate_returns_200(self, admin_headers):
        """Verify endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/release-gate",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_release_gate_has_required_fields(self, admin_headers):
        """Verify required fields are present"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/release-gate",
            headers=admin_headers,
        )
        data = response.json()
        
        required_fields = [
            "status",
            "order_path_open",
            "reasons",
            "base_release_gate",
            "secret_isolation",
            "testnet_enabled",
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_release_gate_default_blocked(self, admin_headers):
        """Verify default status is BLOCKED (testnet disabled)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/release-gate",
            headers=admin_headers,
        )
        data = response.json()
        
        # Default should be BLOCKED since testnet is disabled
        assert data.get("status") == "BLOCKED", f"Expected BLOCKED, got {data.get('status')}"
        assert data.get("order_path_open") is False, "order_path_open should be False"


class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""

    def test_strategy_status_returns_200(self, admin_headers):
        """Verify strategy/status endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/status",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "strategy" in data or "metrics" in data, "Missing expected fields in strategy/status"

    def test_decision_diagnostics_returns_200(self, admin_headers):
        """Verify decision-diagnostics endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/decision-diagnostics",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "false_allow_count" in data, "Missing false_allow_count"
        assert "false_reject_count" in data, "Missing false_reject_count"
        assert "decision_layer_distribution" in data, "Missing decision_layer_distribution"

    def test_leverage_status_returns_200(self, admin_headers):
        """Verify leverage/status endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/leverage/status",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "final_leverage" in data or "leverage_distribution" in data, "Missing expected fields"


class TestExecutionQualityServiceLogic:
    """Unit tests for execution quality service logic"""

    def test_tuning_score_default_is_50(self, admin_headers):
        """Verify default tuning score is 50 (baseline)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality",
            headers=admin_headers,
        )
        data = response.json()
        
        # With no orders, score should be 50.0 (default)
        tuning = data.get("rolling_7d_tuning_score", {})
        assert tuning.get("score") == 50.0, f"Expected default score 50.0, got {tuning.get('score')}"

    def test_slippage_summary_structure(self, admin_headers):
        """Verify slippage_summary has required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality",
            headers=admin_headers,
        )
        data = response.json()
        
        slippage = data.get("slippage_summary", {})
        assert "expected_slippage" in slippage, "Missing expected_slippage"
        assert "realized_slippage" in slippage, "Missing realized_slippage"
        assert "delta" in slippage, "Missing delta"

    def test_partial_fill_quality_structure(self, admin_headers):
        """Verify partial_fill_quality has required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/testnet/execution-quality",
            headers=admin_headers,
        )
        data = response.json()
        
        pfq = data.get("partial_fill_quality", {})
        assert "partial_fill_rate" in pfq, "Missing partial_fill_rate"
        assert "partial_fill_count" in pfq, "Missing partial_fill_count"
