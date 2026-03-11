"""
Faz-4 Step-1: SPOT_RANGE_REVERSION Hard Switch Tests

Tests for:
- POST /api/spot-strategy/scan/run active_strategy_id matches regime
- RANGING regime -> spot_range_reversion_v1 (active and enabled)
- VOLATILE regime -> spot_volatility_breakout_v1 (passive, strategy_not_activated)
- Hard switch: same scan cycle uses single strategy_id
- Strategy-level distribution fields: signals_per_strategy, selected_signals_per_strategy
- top_n max 50 enforcement
- Admin regression: /admin/users, /admin/system-alerts
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


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


class TestHardSwitchRegimeMatching:
    """Tests for hard switch regime-strategy matching"""

    def test_scan_run_returns_active_strategy_id(self, admin_headers):
        """POST /api/spot-strategy/scan/run returns active_strategy_id field"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200, f"Scan failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Must have active_strategy_id field
        assert "active_strategy_id" in data, "Response must contain 'active_strategy_id'"
        assert "active_strategy_name" in data, "Response must contain 'active_strategy_name'"
        assert "active_strategy_enabled" in data, "Response must contain 'active_strategy_enabled'"
        assert "market_regime" in data, "Response must contain 'market_regime'"
        assert "regime_strategy_map" in data, "Response must contain 'regime_strategy_map'"

    def test_regime_strategy_map_is_hard_coded(self, admin_headers):
        """regime_strategy_map has correct hardcoded values"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        regime_map = data.get("regime_strategy_map", {})
        assert regime_map.get("TRENDING") == "spot_pullback_v1", "TRENDING should map to spot_pullback_v1"
        assert regime_map.get("RANGING") == "spot_range_reversion_v1", "RANGING should map to spot_range_reversion_v1"
        assert regime_map.get("VOLATILE") == "spot_volatility_breakout_v1", "VOLATILE should map to spot_volatility_breakout_v1"

    def test_ranging_regime_uses_range_reversion_strategy(self, admin_headers):
        """In RANGING regime, active_strategy_id should be spot_range_reversion_v1"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Current market is RANGING based on indicators
        if data["market_regime"] == "RANGING":
            assert data["active_strategy_id"] == "spot_range_reversion_v1", \
                f"RANGING regime should use spot_range_reversion_v1, got {data['active_strategy_id']}"
            assert data["active_strategy_name"] == "SPOT_RANGE_REVERSION", \
                f"Strategy name should be SPOT_RANGE_REVERSION, got {data['active_strategy_name']}"
            assert data["active_strategy_enabled"] is True, \
                "spot_range_reversion_v1 should be enabled (in active_strategies list)"

    def test_hard_switch_single_strategy_in_cycle(self, admin_headers):
        """Hard switch: all ranked items in same cycle use same strategy_id"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 10},
        )
        assert response.status_code == 200
        data = response.json()
        
        active_strategy = data.get("active_strategy_id")
        top_ranked = data.get("top_ranked", [])
        ranked = data.get("ranked", [])
        
        # All items in top_ranked should have same strategy_id as active_strategy_id
        for item in top_ranked:
            assert item.get("strategy_id") == active_strategy, \
                f"top_ranked item has strategy_id={item.get('strategy_id')}, expected {active_strategy}"
        
        # All items in ranked should have same strategy_id
        unique_strategies = set(item.get("strategy_id") for item in ranked if item.get("strategy_id"))
        assert len(unique_strategies) <= 1, \
            f"Hard switch violated: multiple strategies in same cycle: {unique_strategies}"

    def test_top_ranked_strategy_matches_active_strategy(self, admin_headers):
        """top_ranked.strategy_id matches active_strategy_id for RANGING regime"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        active_strategy = data.get("active_strategy_id")
        top_ranked = data.get("top_ranked", [])
        
        if top_ranked:
            strategies_in_top = list(set(item.get("strategy_id") for item in top_ranked))
            assert len(strategies_in_top) == 1, "All top_ranked should have same strategy_id"
            assert strategies_in_top[0] == active_strategy, \
                f"top_ranked strategy {strategies_in_top[0]} != active {active_strategy}"


class TestVolatileRegimeHandling:
    """Tests for VOLATILE regime handling (breakout strategy not activated)"""

    def test_volatile_would_use_breakout_strategy(self, admin_headers):
        """VOLATILE regime maps to spot_volatility_breakout_v1 in regime_strategy_map"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        regime_map = data.get("regime_strategy_map", {})
        assert "VOLATILE" in regime_map, "VOLATILE should be in regime_strategy_map"
        assert regime_map["VOLATILE"] == "spot_volatility_breakout_v1", \
            "VOLATILE maps to spot_volatility_breakout_v1"

    def test_breakout_not_in_active_strategies(self, admin_headers):
        """spot_volatility_breakout_v1 is NOT in active_strategies (passive)"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        # When VOLATILE, active_strategy_enabled should be False because breakout not in active list
        # This is expected behavior for Faz-4 Step-1 (only range_reversion activated)
        if data["market_regime"] == "VOLATILE":
            # Breakout is not activated yet, so all signals should have strategy_not_activated rejection
            assert data["active_strategy_enabled"] is False, \
                "VOLATILE regime should have active_strategy_enabled=False (breakout not activated)"


class TestStrategyNotActivatedBehavior:
    """Tests for strategy_not_activated rejection handling"""

    def test_scan_metrics_include_strategy_inactive_rejections(self, admin_headers):
        """metrics.signals_rejected_strategy_inactive count is present"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        metrics = data.get("metrics", {})
        # signals_rejected_strategy_inactive should be present (may be 0)
        assert "signals_rejected_strategy_inactive" in metrics, \
            "metrics should include 'signals_rejected_strategy_inactive' count"


class TestStrategyLevelDistribution:
    """Tests for strategy-level distribution fields in observability"""

    def test_score_metrics_has_signals_per_strategy(self, admin_headers):
        """GET /api/admin/strategy/score-metrics returns signals_per_strategy"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/score-metrics",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "signals_per_strategy" in data, "score-metrics must have 'signals_per_strategy'"
        assert isinstance(data["signals_per_strategy"], dict), "signals_per_strategy should be dict"

    def test_score_metrics_has_selected_signals_per_strategy(self, admin_headers):
        """GET /api/admin/strategy/score-metrics returns selected_signals_per_strategy"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/score-metrics",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "selected_signals_per_strategy" in data, \
            "score-metrics must have 'selected_signals_per_strategy'"
        assert isinstance(data["selected_signals_per_strategy"], dict), \
            "selected_signals_per_strategy should be dict"

    def test_report_has_signals_per_strategy(self, admin_headers):
        """GET /api/admin/strategy/report returns signals_per_strategy"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "signals_per_strategy" in data, "report must have 'signals_per_strategy'"
        assert isinstance(data["signals_per_strategy"], dict)

    def test_report_has_selected_signals_per_strategy(self, admin_headers):
        """GET /api/admin/strategy/report returns selected_signals_per_strategy"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "selected_signals_per_strategy" in data, \
            "report must have 'selected_signals_per_strategy'"
        assert isinstance(data["selected_signals_per_strategy"], dict)

    def test_scan_metrics_has_signals_per_strategy(self, admin_headers):
        """POST /api/spot-strategy/scan/run metrics includes signals_per_strategy"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        metrics = data.get("metrics", {})
        assert "signals_per_strategy" in metrics, \
            "scan metrics must include 'signals_per_strategy'"
        assert isinstance(metrics["signals_per_strategy"], dict)

    def test_scan_metrics_has_selected_signals_per_strategy(self, admin_headers):
        """POST /api/spot-strategy/scan/run metrics includes selected_signals_per_strategy"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        metrics = data.get("metrics", {})
        assert "selected_signals_per_strategy" in metrics, \
            "scan metrics must include 'selected_signals_per_strategy'"
        assert isinstance(metrics["selected_signals_per_strategy"], dict)


class TestTopNEnforcement:
    """Tests for top_n parameter enforcement"""

    def test_top_signals_rejects_top_n_above_50(self, admin_headers):
        """GET /api/admin/strategy/top-signals returns 422 for top_n>50"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "24h", "top_n": 51},
        )
        assert response.status_code == 422, f"Expected 422 for top_n>50, got {response.status_code}"

    def test_top_signals_accepts_top_n_50(self, admin_headers):
        """GET /api/admin/strategy/top-signals accepts top_n=50"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "24h", "top_n": 50},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["top_n"] == 50

    def test_top_signals_rejects_top_n_below_1(self, admin_headers):
        """GET /api/admin/strategy/top-signals returns 422 for top_n<1"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "24h", "top_n": 0},
        )
        assert response.status_code == 422, f"Expected 422 for top_n<1, got {response.status_code}"


class TestAdminRegression:
    """Regression tests for admin endpoints"""

    def test_admin_users_endpoint_works(self, admin_headers):
        """GET /api/admin/users still works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"admin/users failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "admin/users should return list"

    def test_admin_system_alerts_endpoint_works(self, admin_headers):
        """GET /api/admin/system-alerts still works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"system-alerts failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "system-alerts should return list"


class TestWindowParameterHandling:
    """Tests for window parameter handling in observability endpoints"""

    def test_score_metrics_window_24h(self, admin_headers):
        """score-metrics handles window=24h"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/score-metrics",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        assert response.json()["window"] == "24h"

    def test_score_metrics_window_7d(self, admin_headers):
        """score-metrics handles window=7d"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/score-metrics",
            headers=admin_headers,
            params={"window": "7d"},
        )
        assert response.status_code == 200
        assert response.json()["window"] == "7d"

    def test_score_metrics_window_30d(self, admin_headers):
        """score-metrics handles window=30d"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/score-metrics",
            headers=admin_headers,
            params={"window": "30d"},
        )
        assert response.status_code == 200
        assert response.json()["window"] == "30d"

    def test_report_window_24h(self, admin_headers):
        """report handles window=24h"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        assert response.json()["window"] == "24h"

    def test_report_window_7d(self, admin_headers):
        """report handles window=7d"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
            params={"window": "7d"},
        )
        assert response.status_code == 200
        assert response.json()["window"] == "7d"

    def test_report_window_30d(self, admin_headers):
        """report handles window=30d"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
            params={"window": "30d"},
        )
        assert response.status_code == 200
        assert response.json()["window"] == "30d"
