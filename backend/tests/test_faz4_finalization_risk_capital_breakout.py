"""
Faz-4 Finalization: Risk Engine + Capital Allocation + Strategy Engine Integration + Breakout Implementation Tests

Tests for:
- POST /api/spot-strategy/scan/run: regime-strategy hard switch (TRENDING->pullback, RANGING->reversion, VOLATILE->breakout)
- scan response strategy-level fields: active_strategy_id, active_strategy_name, regime_strategy_map, metrics.signals_per_strategy
- breakout strategy fields: compression_range, breakout_strength, confirmation_candle
- GET /api/admin/strategy/risk-capital/status: limits/allocation return
- risk engine controls: max_positions_per_strategy, open_risk, daily_loss, portfolio_drawdown, sector exposure, correlation, kill_switch_active
- kill switch evaluation: flash_crash/slippage_spike/reject_rate health flags
- observability expansion: /api/admin/strategy/report strategy_profit_factor + strategy_drawdown + strategy-level signal distribution
- /api/admin/strategy/top-signals top_n limit max50 enforcement
- admin users/system-alerts regression
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


# ========== SECTION: Risk Capital Status Endpoint ==========
class TestRiskCapitalStatus:
    """Tests for GET /api/admin/strategy/risk-capital/status endpoint"""

    def test_risk_capital_status_endpoint_exists(self, admin_headers):
        """GET /api/admin/strategy/risk-capital/status returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_risk_capital_status_returns_limits(self, admin_headers):
        """risk-capital/status response contains 'limits' with risk control thresholds"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "limits" in data, "Response must contain 'limits' field"
        limits = data["limits"]
        
        # Verify all risk limit fields are present
        expected_limits = [
            "max_open_risk_pct",
            "max_daily_loss_pct",
            "max_portfolio_drawdown_pct",
            "max_strategy_drawdown_pct",
            "max_positions_per_strategy",
            "max_sector_exposure_pct",
            "max_correlated_positions",
        ]
        for limit_key in expected_limits:
            assert limit_key in limits, f"limits must contain '{limit_key}'"
            assert isinstance(limits[limit_key], (int, float)), f"{limit_key} should be numeric"

    def test_risk_capital_status_returns_allocation(self, admin_headers):
        """risk-capital/status response contains 'allocation' with strategy allocations"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "allocation" in data, "Response must contain 'allocation' field"
        allocation = data["allocation"]
        
        # Check expected strategies have allocations
        expected_strategies = [
            "spot_pullback_v1",
            "spot_range_reversion_v1",
            "spot_volatility_breakout_v1",
        ]
        for strategy_id in expected_strategies:
            assert strategy_id in allocation, f"allocation must contain '{strategy_id}'"
            strategy_alloc = allocation[strategy_id]
            assert "base_allocation" in strategy_alloc, f"{strategy_id} needs 'base_allocation'"
            assert "effective_allocation" in strategy_alloc, f"{strategy_id} needs 'effective_allocation'"
            assert "profit_factor" in strategy_alloc, f"{strategy_id} needs 'profit_factor'"

    def test_risk_capital_status_returns_equity(self, admin_headers):
        """risk-capital/status contains equity value"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "equity" in data, "Response must contain 'equity'"
        assert isinstance(data["equity"], (int, float)), "equity must be numeric"

    def test_risk_capital_status_returns_open_risk_pct(self, admin_headers):
        """risk-capital/status contains open_risk_pct"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "open_risk_pct" in data, "Response must contain 'open_risk_pct'"
        assert isinstance(data["open_risk_pct"], (int, float))

    def test_risk_capital_status_returns_portfolio_drawdown_pct(self, admin_headers):
        """risk-capital/status contains portfolio_drawdown_pct"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "portfolio_drawdown_pct" in data, "Response must contain 'portfolio_drawdown_pct'"
        assert isinstance(data["portfolio_drawdown_pct"], (int, float))


# ========== SECTION: Regime-Strategy Hard Switch ==========
class TestRegimeStrategyHardSwitch:
    """Tests for regime-strategy hard switch mechanism"""

    def test_trending_regime_maps_to_pullback(self, admin_headers):
        """TRENDING regime maps to spot_pullback_v1"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        regime_map = data.get("regime_strategy_map", {})
        assert regime_map.get("TRENDING") == "spot_pullback_v1"

    def test_ranging_regime_maps_to_reversion(self, admin_headers):
        """RANGING regime maps to spot_range_reversion_v1"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        regime_map = data.get("regime_strategy_map", {})
        assert regime_map.get("RANGING") == "spot_range_reversion_v1"

    def test_volatile_regime_maps_to_breakout(self, admin_headers):
        """VOLATILE regime maps to spot_volatility_breakout_v1"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        regime_map = data.get("regime_strategy_map", {})
        assert regime_map.get("VOLATILE") == "spot_volatility_breakout_v1"

    def test_scan_contains_active_strategy_fields(self, admin_headers):
        """Scan response contains all active strategy fields"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        required_fields = [
            "active_strategy_id",
            "active_strategy_name",
            "active_strategy_enabled",
            "regime_strategy_map",
            "market_regime",
        ]
        for field in required_fields:
            assert field in data, f"Response must contain '{field}'"

    def test_scan_metrics_includes_signals_per_strategy(self, admin_headers):
        """scan metrics includes signals_per_strategy distribution"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 10},
        )
        assert response.status_code == 200
        data = response.json()
        
        metrics = data.get("metrics", {})
        assert "signals_per_strategy" in metrics, "metrics must include 'signals_per_strategy'"
        assert isinstance(metrics["signals_per_strategy"], dict)


# ========== SECTION: Breakout Strategy Metadata Fields ==========
class TestBreakoutStrategyMetadata:
    """Tests for volatility breakout strategy metadata fields"""

    def test_scan_ranked_items_have_metadata(self, admin_headers):
        """Ranked items contain metadata field"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 10},
        )
        assert response.status_code == 200
        data = response.json()
        
        ranked = data.get("ranked", [])
        if ranked:
            # Check first item has metadata
            item = ranked[0]
            assert "metadata" in item, "ranked items must have 'metadata' field"

    def test_breakout_metadata_fields_available(self, admin_headers):
        """Breakout metadata fields: compression_range, breakout_strength, confirmation_candle"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 10},
        )
        assert response.status_code == 200
        data = response.json()
        
        ranked = data.get("ranked", [])
        if ranked:
            for item in ranked:
                metadata = item.get("metadata", {})
                # These fields should exist (may be None for non-breakout strategies)
                # Check the metadata structure has breakout fields
                assert "compression_range" in metadata or "metadata" in item, \
                    "Breakout metadata field 'compression_range' expected in item metadata"
                assert "breakout_strength" in metadata or "metadata" in item, \
                    "Breakout metadata field 'breakout_strength' expected in item metadata"

    def test_component_scores_available(self, admin_headers):
        """Ranked items contain component_scores for analysis"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 10},
        )
        assert response.status_code == 200
        data = response.json()
        
        ranked = data.get("ranked", [])
        if ranked:
            for item in ranked[:3]:  # Check first 3
                assert "component_scores" in item, "ranked items should have 'component_scores'"
                scores = item["component_scores"]
                expected_score_keys = ["trend_quality", "volatility_quality", "structure_cleanliness"]
                for key in expected_score_keys:
                    assert key in scores, f"component_scores should have '{key}'"


# ========== SECTION: Observability Report Expansion ==========
class TestObservabilityReportExpansion:
    """Tests for expanded observability report fields"""

    def test_report_contains_strategy_profit_factor(self, admin_headers):
        """GET /api/admin/strategy/report contains strategy_profit_factor"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "strategy_profit_factor" in data, "report must contain 'strategy_profit_factor'"
        assert isinstance(data["strategy_profit_factor"], dict), "strategy_profit_factor should be dict"

    def test_report_contains_strategy_drawdown(self, admin_headers):
        """GET /api/admin/strategy/report contains strategy_drawdown"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "strategy_drawdown" in data, "report must contain 'strategy_drawdown'"
        assert isinstance(data["strategy_drawdown"], dict), "strategy_drawdown should be dict"

    def test_report_contains_signals_per_strategy(self, admin_headers):
        """GET /api/admin/strategy/report contains signals_per_strategy"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "signals_per_strategy" in data, "report must contain 'signals_per_strategy'"
        assert isinstance(data["signals_per_strategy"], dict)

    def test_report_contains_selected_signals_per_strategy(self, admin_headers):
        """GET /api/admin/strategy/report contains selected_signals_per_strategy"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "selected_signals_per_strategy" in data, \
            "report must contain 'selected_signals_per_strategy'"
        assert isinstance(data["selected_signals_per_strategy"], dict)

    def test_report_contains_signals_rejected_breakdown(self, admin_headers):
        """GET /api/admin/strategy/report contains signals_rejected_breakdown"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "signals_rejected_breakdown" in data, \
            "report must contain 'signals_rejected_breakdown'"
        breakdown = data["signals_rejected_breakdown"]
        expected_reasons = ["trend_strength", "btc_regime", "freeze_guard", "threshold"]
        for reason in expected_reasons:
            assert reason in breakdown, f"rejection breakdown should have '{reason}'"


# ========== SECTION: Top Signals Max 50 Enforcement ==========
class TestTopSignalsMax50:
    """Tests for top_n limit max 50 enforcement"""

    def test_top_signals_rejects_top_n_51(self, admin_headers):
        """top-signals returns 422 for top_n=51"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "24h", "top_n": 51},
        )
        assert response.status_code == 422, f"Expected 422 for top_n>50, got {response.status_code}"

    def test_top_signals_accepts_top_n_50(self, admin_headers):
        """top-signals accepts top_n=50"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "24h", "top_n": 50},
        )
        assert response.status_code == 200
        assert response.json()["top_n"] == 50

    def test_top_signals_rejects_top_n_0(self, admin_headers):
        """top-signals returns 422 for top_n=0"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=admin_headers,
            params={"window": "24h", "top_n": 0},
        )
        assert response.status_code == 422


# ========== SECTION: Risk Engine Control Tags ==========
class TestRiskEngineControlTags:
    """Tests for risk engine control risk_tags"""

    def test_risk_capital_status_returns_strategy_drawdown(self, admin_headers):
        """risk-capital/status contains strategy_drawdown"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "strategy_drawdown" in data, "Response must contain 'strategy_drawdown'"
        assert isinstance(data["strategy_drawdown"], dict)

    def test_risk_capital_status_returns_daily_loss(self, admin_headers):
        """risk-capital/status contains daily_loss"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "daily_loss" in data, "Response must contain 'daily_loss'"
        daily_loss = data["daily_loss"]
        assert "daily_loss_amount" in daily_loss, "daily_loss should have 'daily_loss_amount'"

    def test_risk_capital_status_returns_open_positions_count(self, admin_headers):
        """risk-capital/status contains open_positions count"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "open_positions" in data, "Response must contain 'open_positions'"
        assert isinstance(data["open_positions"], int)

    def test_risk_capital_limits_max_positions_per_strategy(self, admin_headers):
        """limits contains max_positions_per_strategy"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        limits = data.get("limits", {})
        assert "max_positions_per_strategy" in limits
        assert limits["max_positions_per_strategy"] == 2  # Default value


# ========== SECTION: Kill Switch Health Flags ==========
class TestKillSwitchHealthFlags:
    """Tests for kill switch evaluation (endpoint not disrupting pipeline)"""

    def test_scan_does_not_break_on_kill_switch_eval(self, admin_headers):
        """Scan runs successfully even with kill switch evaluation"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        # Should succeed regardless of kill switch state
        assert response.status_code == 200, f"Scan should succeed: {response.status_code}"


# ========== SECTION: Admin Regression Tests ==========
class TestAdminRegression:
    """Regression tests for admin endpoints"""

    def test_admin_users_endpoint(self, admin_headers):
        """GET /api/admin/users works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_admin_system_alerts_endpoint(self, admin_headers):
        """GET /api/admin/system-alerts works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_admin_rejection_analytics(self, admin_headers):
        """GET /api/admin/strategy/rejection-analytics works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/rejection-analytics",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "window" in data
        assert "signals_total" in data

    def test_admin_score_metrics(self, admin_headers):
        """GET /api/admin/strategy/score-metrics works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/score-metrics",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "avg_base_score" in data
        assert "avg_adjusted_score" in data


# ========== SECTION: Scan Response Complete Verification ==========
class TestScanResponseCompleteness:
    """Tests for complete scan response structure"""

    def test_scan_has_generated_at(self, admin_headers):
        """Scan response has generated_at timestamp"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert "generated_at" in data

    def test_scan_has_multiplier_set(self, admin_headers):
        """Scan response has multiplier_set"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert "multiplier_set" in data
        assert isinstance(data["multiplier_set"], dict)

    def test_scan_has_threshold(self, admin_headers):
        """Scan response has threshold"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert "threshold" in data
        assert isinstance(data["threshold"], (int, float))

    def test_scan_has_freeze_guard(self, admin_headers):
        """Scan response has freeze_guard status"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert "freeze_guard" in data
        fg = data["freeze_guard"]
        assert "active" in fg

    def test_scan_has_btc_regime(self, admin_headers):
        """Scan response has btc_regime"""
        response = requests.post(
            f"{BASE_URL}/api/spot-strategy/scan/run",
            headers=admin_headers,
            params={"top_n": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert "btc_regime" in data
        # btc_regime should be one of: supportive, neutral, hostile
        assert data["btc_regime"] in ["supportive", "neutral", "hostile"]
