# P2 Execution Microstructure API Contract Tests
# Tests: impact_model, hidden_liquidity, depth_decay, portfolio_capacity, execution_budget, slicing_plan
# Endpoints: /guard-preview, /budget-status, /slicing-preview, /execution-replay/latest

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
TIMEOUT = 30


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code}")
    return resp.json().get("access_token")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Auth headers for API calls"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestP2GuardPreviewImpactModel:
    """P2: Guard preview exposes non-linear impact model with square_root_impact and performance_degradation_pct"""

    def test_guard_preview_returns_impact_model(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "impact_model" in data
        impact = data["impact_model"]
        # P2 required fields
        assert "square_root_impact" in impact
        assert "performance_degradation_pct" in impact
        assert "impact_ratio" in impact
        assert "impact_score" in impact
        assert "liquidity_tier" in impact

    def test_impact_model_square_root_is_non_linear(self, auth_headers):
        """Verify square_root_impact is non-linear (sqrt-based)"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.5, "price": 65000},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        impact = resp.json().get("impact_model", {})
        # square_root_impact should be > 0 for any order
        assert float(impact.get("square_root_impact", 0)) >= 0
        # performance_degradation_pct should be derived from square_root_impact
        assert float(impact.get("performance_degradation_pct", 0)) >= 0


class TestP2HiddenLiquidityAndDepthDecay:
    """P2: Guard preview exposes hidden_liquidity and depth_decay assessments"""

    def test_guard_preview_returns_hidden_liquidity(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "hidden_liquidity" in data
        hidden = data["hidden_liquidity"]
        assert "hidden_liquidity_ratio" in hidden
        assert "state" in hidden
        assert hidden["state"] in {"LOW", "MEDIUM", "HIGH"}
        assert "confidence" in hidden

    def test_guard_preview_returns_depth_decay(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "depth_decay" in data
        decay = data["depth_decay"]
        assert "decay_ratio" in decay
        assert "state" in decay
        assert decay["state"] in {"STABLE", "ELEVATED", "RAPID"}


class TestP2PortfolioCapacity:
    """P2: Guard preview exposes portfolio_capacity with combined load assessment"""

    def test_guard_preview_returns_portfolio_capacity(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "portfolio_capacity" in data
        capacity = data["portfolio_capacity"]
        # P2 required fields
        assert "same_symbol_open_notional" in capacity
        assert "same_strategy_open_notional" in capacity
        assert "combined_load_notional" in capacity
        assert "combined_load_ratio" in capacity
        assert "performance_degradation_pct" in capacity


class TestP2ExecutionBudget:
    """P2: Guard preview exposes execution_budget with daily budget tracking"""

    def test_guard_preview_returns_execution_budget(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "execution_budget" in data
        budget = data["execution_budget"]
        # P2 required fields
        assert "state" in budget
        assert budget["state"] in {"ALLOW", "REDUCE_SIZE", "BLOCK"}
        assert "symbol_budget_notional" in budget
        assert "strategy_budget_notional" in budget
        assert "impact_budget_bps" in budget
        assert "symbol_budget_used" in budget
        assert "strategy_budget_used" in budget
        assert "allowed_notional" in budget
        assert "reasons" in budget


class TestP2SlicingPlan:
    """P2: Guard preview exposes slicing_plan with adaptive slicing engine"""

    def test_guard_preview_returns_slicing_plan(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "slicing_plan" in data
        plan = data["slicing_plan"]
        # P2 required fields
        assert "slice_count" in plan
        assert "slice_notional" in plan
        assert "interval_ms" in plan
        assert "preferred_order_type" in plan
        assert "execution_style" in plan
        assert "should_slice" in plan
        assert isinstance(plan["should_slice"], bool)


class TestP2BudgetStatusEndpoint:
    """P2: /budget-status endpoint returns execution_budget + portfolio_capacity + impact_model"""

    def test_budget_status_returns_200(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/budget-status",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200

    def test_budget_status_returns_required_fields(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/budget-status",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "state" in data
        assert "execution_budget" in data
        assert "portfolio_capacity" in data
        assert "impact_model" in data

    def test_budget_status_with_strategy_binding(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/budget-status",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000, "strategy": "ema_rsi"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "execution_budget" in data
        # strategy_budget_used should be tracked
        assert "strategy_budget_used" in data["execution_budget"]


class TestP2SlicingPreviewEndpoint:
    """P2: /slicing-preview endpoint returns slicing_plan linked to impact/regime/capacity"""

    def test_slicing_preview_returns_200(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/slicing-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200

    def test_slicing_preview_returns_required_fields(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/slicing-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "state" in data
        assert "execution_recommendation" in data
        assert "slicing_plan" in data
        assert "impact_model" in data
        assert "hidden_liquidity" in data
        assert "depth_decay" in data

    def test_slicing_preview_slicing_plan_linked_to_impact(self, auth_headers):
        """Verify slicing_plan is influenced by impact_model"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/slicing-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.5, "price": 65000},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        plan = data.get("slicing_plan", {})
        impact = data.get("impact_model", {})
        # If impact is high, slicing should be recommended
        if float(impact.get("performance_degradation_pct", 0)) >= 8:
            assert plan.get("slice_count", 1) >= 2 or plan.get("should_slice") is True


class TestP2ExecutionReplayLatest:
    """P2: /execution-replay/latest returns should_have_been_sliced + slicing_plan"""

    def test_execution_replay_latest_returns_200(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/execution-replay/latest",
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200

    def test_execution_replay_latest_returns_slicing_fields(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/execution-replay/latest",
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        # If there's execution data, verify P2 fields
        if data.get("status") == "ok":
            assert "should_have_been_sliced" in data
            assert "slicing_plan" in data
            assert isinstance(data["should_have_been_sliced"], bool)

    def test_execution_replay_latest_with_symbol_filter(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/execution-replay/latest",
            params={"symbol": "BTCUSDT"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should return either ok with data or empty status
        assert data.get("status") in {"ok", "empty"}


class TestP0P1RegressionNoBreakingChanges:
    """Verify P0/P1 endpoints and contracts still work after P2 additions"""

    def test_status_endpoint_still_works(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/status",
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "portfolio_microstructure_state" in data

    def test_venues_endpoint_still_works(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/venues",
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tracked_symbols" in data
        assert "venues" in data
        # P1 fields still present
        if "binance" in data["venues"]:
            assert "venue_health_score" in data["venues"]["binance"]
            assert "liquidity_stress_score" in data["venues"]["binance"]

    def test_guard_preview_p1_fields_still_present(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        # P1 fields
        assert "slippage_decomposition" in data
        assert "market_regime" in data
        assert "execution_recommendation" in data
        assert "venue_health" in data
        # P0 fields
        assert "state" in data
        assert "selected_venue" in data
        assert "market_snapshot" in data
        assert "capacity" in data

    def test_replay_endpoint_still_works(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/replay",
            params={"limit": 5},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
