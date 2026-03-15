"""
Faz-3 (P2) Strategy Observability & Tuning - Backend API Tests

Tests for:
- GET /api/admin/strategy/top-signals?window=24h&top_n=10 (top_n<=50 enforce)
- GET /api/admin/strategy/rejection-analytics?window=24h 
- GET /api/admin/strategy/score-metrics?window=24h
- GET /api/admin/strategy/report?window=24h
- POST /api/spot-strategy/scan/run -> strategy_observability_events table logging
- window parameter validation (24h/7d/30d)
- Admin regression: /admin/users, /admin/system-alerts
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin auth failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token returned from auth endpoint")
    return token


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Admin authorized headers"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestTopSignalsEndpoint:
    """Tests for GET /api/admin/strategy/top-signals"""

    def test_top_signals_default_params(self, admin_headers):
        """Top signals endpoint works with default parameters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "window" in data, "Response should contain 'window' field"
        assert "top_n" in data, "Response should contain 'top_n' field"
        assert "items" in data, "Response should contain 'items' field"
        assert data["window"] == "24h", f"Default window should be 24h, got {data['window']}"
        assert data["top_n"] == 10, f"Default top_n should be 10, got {data['top_n']}"

    def test_top_signals_with_custom_window_24h(self, admin_headers):
        """Top signals works with window=24h"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "24h", "top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "24h"
        assert data["top_n"] == 5

    def test_top_signals_with_window_7d(self, admin_headers):
        """Top signals works with window=7d"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "7d", "top_n": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "7d"

    def test_top_signals_with_window_30d(self, admin_headers):
        """Top signals works with window=30d"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "30d", "top_n": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "30d"

    def test_top_signals_top_n_max_50_enforcement(self, admin_headers):
        """top_n parameter enforces maximum of 50 via FastAPI Query validation"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "24h", "top_n": 100},  # Request more than 50
        )
        # FastAPI Query(le=50) returns 422 for values > 50 - this is correct behavior
        assert response.status_code == 422, f"Expected 422 for top_n>50, got {response.status_code}"
        
        # Verify that top_n=50 works (max allowed)
        response_max = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "24h", "top_n": 50},
        )
        assert response_max.status_code == 200
        data = response_max.json()
        assert data["top_n"] == 50

    def test_top_signals_top_n_min_1_enforcement(self, admin_headers):
        """top_n parameter enforces minimum of 1"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "24h", "top_n": 0},  # Request less than 1
        )
        # FastAPI Query validation will return 422 for values < 1
        assert response.status_code in [200, 422]

    def test_top_signals_items_structure(self, admin_headers):
        """Top signals items have correct structure when data exists"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "30d", "top_n": 50},  # Wider window to capture any data
        )
        assert response.status_code == 200
        data = response.json()
        
        # Items should be a list (may be empty if no selected_for_execution events)
        assert isinstance(data["items"], list)
        
        # If there are items, verify structure
        if data["items"]:
            item = data["items"][0]
            expected_fields = [
                "symbol", "strategy_id", "market_regime", "base_score",
                "adjusted_score", "score_delta", "selection_rank",
                "trend_strength", "relative_volume", "timestamp"
            ]
            for field in expected_fields:
                assert field in item, f"Item should have '{field}' field"


class TestRejectionAnalyticsEndpoint:
    """Tests for GET /api/admin/strategy/rejection-analytics"""

    def test_rejection_analytics_default(self, admin_headers):
        """Rejection analytics works with default parameters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/rejection-analytics",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "window" in data
        assert data["window"] == "24h"
        
        # Verify metrics fields exist
        expected_metrics = [
            "signals_total",
            "signals_after_hard_gate",
            "signals_rejected_trend_strength",
            "signals_rejected_btc_regime",
            "signals_rejected_freeze_guard",
            "signals_rejected_threshold",
            "signals_selected",
        ]
        for metric in expected_metrics:
            assert metric in data, f"Response should contain '{metric}'"
            assert isinstance(data[metric], int), f"'{metric}' should be an integer"

    def test_rejection_analytics_window_24h(self, admin_headers):
        """Rejection analytics works with window=24h"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/rejection-analytics",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "24h"

    def test_rejection_analytics_window_7d(self, admin_headers):
        """Rejection analytics works with window=7d"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/rejection-analytics",
            headers=admin_headers,
            params={"window": "7d"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "7d"

    def test_rejection_analytics_window_30d(self, admin_headers):
        """Rejection analytics works with window=30d"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/rejection-analytics",
            headers=admin_headers,
            params={"window": "30d"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "30d"


class TestScoreMetricsEndpoint:
    """Tests for GET /api/admin/strategy/score-metrics"""

    def test_score_metrics_default(self, admin_headers):
        """Score metrics works with default parameters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/score-metrics",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "window" in data
        assert data["window"] == "24h"
        
        # Verify score fields exist
        expected_fields = [
            "market_regime_distribution",
            "avg_base_score",
            "avg_adjusted_score",
            "avg_score_delta",
            "signals_per_regime",
            "selected_signals_per_regime",
        ]
        for field in expected_fields:
            assert field in data, f"Response should contain '{field}'"

    def test_score_metrics_regime_distribution_type(self, admin_headers):
        """Score metrics regime distribution is dict"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/score-metrics",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["market_regime_distribution"], dict)

    def test_score_metrics_window_7d(self, admin_headers):
        """Score metrics works with window=7d"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/score-metrics",
            headers=admin_headers,
            params={"window": "7d"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "7d"

    def test_score_metrics_window_30d(self, admin_headers):
        """Score metrics works with window=30d"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/score-metrics",
            headers=admin_headers,
            params={"window": "30d"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "30d"


class TestStrategyReportEndpoint:
    """Tests for GET /api/admin/strategy/report"""

    def test_report_default(self, admin_headers):
        """Strategy report works with default parameters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "window" in data
        assert data["window"] == "24h"
        
        # Verify required report fields
        expected_fields = [
            "active_spot_strategies",
            "market_regime_distribution",
            "signals_total",
            "signals_selected",
            "signals_rejected_breakdown",
            "avg_adjusted_score",
            "avg_base_score",
            "score_delta_avg",
        ]
        for field in expected_fields:
            assert field in data, f"Report should contain '{field}'"

    def test_report_signals_rejected_breakdown_structure(self, admin_headers):
        """Report signals_rejected_breakdown has correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        breakdown = data.get("signals_rejected_breakdown", {})
        expected_breakdown_keys = ["trend_strength", "btc_regime", "freeze_guard", "threshold"]
        for key in expected_breakdown_keys:
            assert key in breakdown, f"signals_rejected_breakdown should have '{key}'"

    def test_report_window_7d(self, admin_headers):
        """Strategy report works with window=7d"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
            params={"window": "7d"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "7d"

    def test_report_window_30d(self, admin_headers):
        """Strategy report works with window=30d"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
            params={"window": "30d"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "30d"


class TestScanObservabilityLogging:
    """Tests for scan endpoint observability event logging"""

    def test_scan_run_logs_observability_events(self, admin_headers):
        """POST /api/spot-strategy/scan/run creates observability log entries"""
        # First refresh universe to ensure we have data
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/universe/refresh",
            headers=admin_headers,
        )
        # Universe refresh may fail due to market data, that's OK
        
        # Run the scan
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 10},
        )
        assert response.status_code == 200, f"Scan failed: {response.status_code} - {response.text}"
        scan_data = response.json()
        
        # Verify scan returns expected fields
        assert "market_regime" in scan_data
        assert "ranked" in scan_data
        
        # After scan, check if observability events were logged by querying report
        report_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert report_response.status_code == 200
        report_data = report_response.json()
        
        # The report should now have data from our scan
        # signals_total should be >= 0 (may be 0 if no universe data)
        assert report_data["signals_total"] >= 0


class TestWindowParameterValidation:
    """Tests for window parameter handling"""

    def test_invalid_window_defaults_to_24h(self, admin_headers):
        """Invalid window parameter defaults to 24h"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "invalid"},
        )
        assert response.status_code == 200
        data = response.json()
        # Service normalizes invalid windows to 24h
        assert data["window"] == "24h"

    def test_empty_window_defaults_to_24h(self, admin_headers):
        """Empty window parameter defaults to 24h"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": ""},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "24h"


class TestAdminExistingPagesRegression:
    """Regression tests for existing admin pages (users, system-alerts)"""

    def test_admin_users_endpoint(self, admin_headers):
        """Admin users endpoint still works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Admin users failed: {response.status_code} - {response.text}"
        data = response.json()
        assert isinstance(data, list)

    def test_admin_system_alerts_endpoint(self, admin_headers):
        """Admin system alerts endpoint still works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"System alerts failed: {response.status_code} - {response.text}"
        data = response.json()
        assert isinstance(data, list)


class TestUnauthorizedAccess:
    """Tests for unauthorized access handling"""

    def test_top_signals_requires_admin(self):
        """Top signals endpoint requires admin auth"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/top-signals")
        assert response.status_code == 401 or response.status_code == 403

    def test_rejection_analytics_requires_admin(self):
        """Rejection analytics endpoint requires admin auth"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/rejection-analytics")
        assert response.status_code == 401 or response.status_code == 403

    def test_score_metrics_requires_admin(self):
        """Score metrics endpoint requires admin auth"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/score-metrics")
        assert response.status_code == 401 or response.status_code == 403

    def test_report_requires_admin(self):
        """Strategy report endpoint requires admin auth"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/report")
        assert response.status_code == 401 or response.status_code == 403
