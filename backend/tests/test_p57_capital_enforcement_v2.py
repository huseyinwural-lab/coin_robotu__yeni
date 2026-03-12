"""
Phase 5.7 Capital Enforcement v2 Comprehensive Test Suite
---------------------------------------------------------
Tests for:
- Portfolio Capital Registry calculations
- Strategy Capital Allocator (max=0.20, soft_warning=0.15)
- Capital Drift Detector (CAPITAL_BUDGET_DRIFT + severity)
- Capital Risk Governor (CAPITAL_LIMIT_HIT enforcement)
- Position Size Policy modifiers
- Capital Order Guard (pipeline enforcement)
- Capital governance audit events
- New capital endpoints contract validation
- Regression: existing endpoints not broken
"""

import os
import sys
from pathlib import Path

import pytest
import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


# ===== FIXTURES =====
@pytest.fixture(scope="module")
def admin_headers():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL tanımlı değil")
    login_response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if login_response.status_code != 200:
        pytest.skip(f"Admin login başarısız: {login_response.text}")
    token = login_response.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ===== ENDPOINT CONTRACT TESTS =====
class TestCapitalBudgetEndpoint:
    """GET /api/admin/futures/capital-budget contract validation"""

    def test_capital_budget_returns_200(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-budget", headers=admin_headers, timeout=20)
        assert response.status_code == 200

    def test_capital_budget_has_portfolio_capital_registry(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-budget", headers=admin_headers, timeout=20)
        payload = response.json()
        assert "portfolio_capital_registry" in payload
        registry = payload["portfolio_capital_registry"]
        # Verify registry structure
        assert "portfolio_equity" in registry
        assert "available_capital" in registry
        assert "allocated_capital" in registry
        assert "used_margin" in registry
        assert "risk_budget_total" in registry
        assert "updated_at" in registry

    def test_capital_budget_has_strategy_capital_budget(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-budget", headers=admin_headers, timeout=20)
        payload = response.json()
        assert "strategy_capital_budget" in payload
        assert isinstance(payload["strategy_capital_budget"], list)

    def test_capital_budget_strategy_row_structure(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-budget", headers=admin_headers, timeout=20)
        payload = response.json()
        budget_rows = payload.get("strategy_capital_budget", [])
        if budget_rows:
            row = budget_rows[0]
            assert "strategy_id" in row
            assert "strategy_capital_budget" in row
            assert "strategy_capital_used" in row
            assert "strategy_capital_available" in row
            assert "warning_threshold" in row
            assert "risk_state" in row

    def test_capital_budget_risk_state_values(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-budget", headers=admin_headers, timeout=20)
        payload = response.json()
        budget_rows = payload.get("strategy_capital_budget", [])
        valid_states = {"NORMAL", "WARNING", "LIMIT_HIT"}
        for row in budget_rows:
            assert row.get("risk_state") in valid_states


class TestCapitalUsageEndpoint:
    """GET /api/admin/futures/capital-usage contract validation"""

    def test_capital_usage_returns_200(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-usage", headers=admin_headers, timeout=20)
        assert response.status_code == 200

    def test_capital_usage_has_strategy_capital_usage(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-usage", headers=admin_headers, timeout=20)
        payload = response.json()
        assert "strategy_capital_usage" in payload
        assert isinstance(payload["strategy_capital_usage"], list)

    def test_capital_usage_has_portfolio_risk_budget(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-usage", headers=admin_headers, timeout=20)
        payload = response.json()
        assert "portfolio_risk_budget" in payload
        assert isinstance(payload["portfolio_risk_budget"], (int, float))

    def test_capital_usage_has_capital_risk_actions(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-usage", headers=admin_headers, timeout=20)
        payload = response.json()
        assert "capital_risk_actions" in payload
        assert isinstance(payload["capital_risk_actions"], list)

    def test_capital_usage_row_structure(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-usage", headers=admin_headers, timeout=20)
        payload = response.json()
        usage_rows = payload.get("strategy_capital_usage", [])
        if usage_rows:
            row = usage_rows[0]
            assert "strategy_id" in row
            assert "capital_used" in row
            assert "capital_remaining" in row
            assert "risk_state" in row

    def test_capital_risk_actions_row_structure(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-usage", headers=admin_headers, timeout=20)
        payload = response.json()
        actions = payload.get("capital_risk_actions", [])
        valid_actions = {"ALLOW", "REDUCE_POSITION_SIZE", "REJECT_TRADE"}
        for action in actions:
            assert "strategy_id" in action
            assert "action" in action
            assert action["action"] in valid_actions
            assert "position_size_multiplier" in action
            assert "risk_downshift" in action


class TestCapitalDriftEndpoint:
    """GET /api/admin/futures/capital-drift contract validation"""

    def test_capital_drift_returns_200(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-drift", headers=admin_headers, timeout=20)
        assert response.status_code == 200

    def test_capital_drift_has_drift_state(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-drift", headers=admin_headers, timeout=20)
        payload = response.json()
        assert "drift_state" in payload
        assert payload["drift_state"] in {"NORMAL", "ALERT"}

    def test_capital_drift_has_capital_drift_events(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-drift", headers=admin_headers, timeout=20)
        payload = response.json()
        assert "capital_drift_events" in payload
        assert isinstance(payload["capital_drift_events"], list)

    def test_capital_drift_has_capital_drift_by_strategy(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-drift", headers=admin_headers, timeout=20)
        payload = response.json()
        assert "capital_drift_by_strategy" in payload
        assert isinstance(payload["capital_drift_by_strategy"], dict)

    def test_capital_drift_by_strategy_structure(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-drift", headers=admin_headers, timeout=20)
        payload = response.json()
        drift_map = payload.get("capital_drift_by_strategy", {})
        for strategy_id, data in drift_map.items():
            assert "capital_used" in data
            assert "capital_budget" in data
            assert "growth_ratio" in data
            assert "drift_state" in data
            assert "reasons" in data


# ===== UNIT TESTS FOR CORE MODULES =====
class TestPortfolioCapitalRegistry:
    """Unit tests for portfolio_capital_registry.py"""

    def test_builds_deterministic_snapshot(self):
        from core.risk.capital.portfolio_capital_registry import build_portfolio_capital_registry

        payload = build_portfolio_capital_registry(
            portfolio_equity=10000,
            used_margin=1300,
            allocated_capital=4500,
            risk_budget_ratio=0.8,
        )
        assert payload["portfolio_equity"] == 10000
        assert payload["used_margin"] == 1300
        assert payload["allocated_capital"] == 4500
        assert payload["risk_budget_total"] == 8000  # 10000 * 0.8
        assert payload["available_capital"] == 4200  # 10000 - 1300 - 4500

    def test_clamps_negative_values(self):
        from core.risk.capital.portfolio_capital_registry import build_portfolio_capital_registry

        payload = build_portfolio_capital_registry(
            portfolio_equity=-1000,
            used_margin=-100,
            allocated_capital=-500,
            risk_budget_ratio=0.8,
        )
        assert payload["portfolio_equity"] >= 0
        assert payload["used_margin"] >= 0
        assert payload["allocated_capital"] >= 0

    def test_clamps_risk_budget_ratio(self):
        from core.risk.capital.portfolio_capital_registry import build_portfolio_capital_registry

        payload = build_portfolio_capital_registry(
            portfolio_equity=10000,
            used_margin=0,
            allocated_capital=0,
            risk_budget_ratio=1.5,  # Should be clamped to 1.0
        )
        assert payload["risk_budget_total"] == 10000


class TestStrategyCapitalAllocator:
    """Unit tests for strategy_capital_allocator.py"""

    def test_applies_max_ratio_0_20(self):
        from core.risk.capital.strategy_capital_allocator import allocate_strategy_capital

        payload = allocate_strategy_capital(
            strategy_ids=["trend_follow_v1"],
            portfolio_equity=10000,
            capital_usage_by_strategy={},
            max_strategy_capital_ratio=0.20,
            soft_warning_ratio=0.15,
        )
        row = payload["strategy_allocation"][0]
        assert row["strategy_capital_budget"] == 2000  # 10000 * 0.20
        assert row["warning_threshold"] == 1500  # 10000 * 0.15

    def test_warning_state_when_exceeds_soft_warning(self):
        from core.risk.capital.strategy_capital_allocator import allocate_strategy_capital

        payload = allocate_strategy_capital(
            strategy_ids=["trend_follow_v1"],
            portfolio_equity=10000,
            capital_usage_by_strategy={"trend_follow_v1": 1700},
            max_strategy_capital_ratio=0.20,
            soft_warning_ratio=0.15,
        )
        row = payload["strategy_allocation"][0]
        assert row["risk_state"] == "WARNING"

    def test_limit_hit_state_when_exceeds_budget(self):
        from core.risk.capital.strategy_capital_allocator import allocate_strategy_capital

        payload = allocate_strategy_capital(
            strategy_ids=["breakout_v1"],
            portfolio_equity=10000,
            capital_usage_by_strategy={"breakout_v1": 2300},
            max_strategy_capital_ratio=0.20,
            soft_warning_ratio=0.15,
        )
        row = payload["strategy_allocation"][0]
        assert row["risk_state"] == "LIMIT_HIT"


class TestCapitalDriftDetector:
    """Unit tests for capital_drift_detector.py"""

    def test_detects_budget_exceeds_drift(self):
        from core.risk.capital.capital_drift_detector import detect_capital_drift

        allocation = [
            {
                "strategy_id": "mean_reversion_v1",
                "strategy_capital_budget": 2000,
                "strategy_capital_used": 2300,
                "warning_threshold": 1500,
            }
        ]
        payload = detect_capital_drift(allocation, previous_usage={})
        assert len(payload["capital_drift_events"]) == 1
        event = payload["capital_drift_events"][0]
        assert event["event"] == "CAPITAL_BUDGET_DRIFT"
        assert "CAPITAL_USAGE_EXCEEDS_BUDGET" in event["reasons"]
        assert event["drift_severity"] == "HIGH"

    def test_detects_growth_anomaly(self):
        from core.risk.capital.capital_drift_detector import detect_capital_drift

        allocation = [
            {
                "strategy_id": "trend_follow_v1",
                "strategy_capital_budget": 2000,
                "strategy_capital_used": 1400,
                "warning_threshold": 1500,
            }
        ]
        payload = detect_capital_drift(allocation, previous_usage={"trend_follow_v1": 800})
        # Growth ratio = (1400 - 800) / 800 = 0.75 > 0.35
        events = payload["capital_drift_events"]
        assert len(events) >= 1
        assert "CAPITAL_USAGE_GROWTH_ANOMALY" in events[0]["reasons"]


class TestCapitalRiskGovernor:
    """Unit tests for capital_risk_governor.py"""

    def test_rejects_trade_on_limit_hit(self):
        from core.risk.capital.capital_risk_governor import enforce_capital_risk

        allocation = [
            {
                "strategy_id": "trend_follow_v1",
                "strategy_capital_used": 2600,
                "strategy_capital_budget": 2000,
                "risk_state": "LIMIT_HIT",
            }
        ]
        payload = enforce_capital_risk(allocation, [])
        assert payload["capital_risk_actions"][0]["action"] == "REJECT_TRADE"
        assert payload["capital_risk_actions"][0]["position_size_multiplier"] == 0.0

    def test_generates_limit_events(self):
        from core.risk.capital.capital_risk_governor import enforce_capital_risk

        allocation = [
            {
                "strategy_id": "mean_reversion_v1",
                "strategy_capital_used": 2300,
                "strategy_capital_budget": 2000,
                "risk_state": "LIMIT_HIT",
            }
        ]
        payload = enforce_capital_risk(allocation, [])
        assert len(payload["capital_limit_events"]) == 1
        event = payload["capital_limit_events"][0]
        assert event["event"] == "CAPITAL_LIMIT_HIT"
        assert "CAPITAL_LIMIT_BREACH" in event["reason"]


class TestPositionSizePolicy:
    """Unit tests for position_size_policy.py"""

    def test_applies_capital_factor(self):
        from core.risk.capital.position_size_policy import apply_position_size_policy

        payload = apply_position_size_policy(
            strategy_capital_available=800,
            strategy_capital_budget=2000,
            base_position_size_ratio=1.0,
            strategy_risk_weight=1.0,
            market_volatility_modifier=1.0,
            cluster_risk_modifier=1.0,
        )
        assert payload["capital_factor"] == 0.4  # 800 / 2000

    def test_applies_all_modifiers(self):
        from core.risk.capital.position_size_policy import apply_position_size_policy

        payload = apply_position_size_policy(
            strategy_capital_available=800,
            strategy_capital_budget=2000,
            base_position_size_ratio=0.9,
            strategy_risk_weight=0.8,
            market_volatility_modifier=0.9,
            cluster_risk_modifier=0.7,
        )
        # adjusted = 0.9 * 0.4 * 0.8 * 0.9 * 0.7 = ~0.18144
        assert payload["adjusted_position_size_ratio"] < 0.9
        assert payload["adjusted_position_size_ratio"] >= 0.05  # Minimum


class TestCapitalOrderGuard:
    """Unit tests for capital_order_guard.py"""

    def test_rejects_when_budget_exceeded(self):
        from core.risk.capital.capital_order_guard import evaluate_capital_order_guard

        payload = evaluate_capital_order_guard(
            strategy_id="breakout_v1",
            projected_order_notional=700,
            strategy_budget_row={"strategy_capital_budget": 2000, "strategy_capital_used": 1500, "warning_threshold": 1500},
            portfolio_registry={"available_capital": 5000},
            cluster_risk_state="NORMAL",
        )
        assert payload["action"] == "REJECT"
        assert payload["event"]["event"] == "CAPITAL_TRADE_REJECTED"

    def test_reduces_size_on_warning(self):
        from core.risk.capital.capital_order_guard import evaluate_capital_order_guard

        payload = evaluate_capital_order_guard(
            strategy_id="trend_follow_v1",
            projected_order_notional=200,
            strategy_budget_row={"strategy_capital_budget": 2000, "strategy_capital_used": 1400, "warning_threshold": 1500},
            portfolio_registry={"available_capital": 5000},
            cluster_risk_state="NORMAL",
        )
        assert payload["action"] == "REDUCE_SIZE"
        assert payload["size_multiplier"] < 1.0

    def test_reduces_size_on_cluster_risk_alert(self):
        from core.risk.capital.capital_order_guard import evaluate_capital_order_guard

        payload = evaluate_capital_order_guard(
            strategy_id="mean_reversion_v1",
            projected_order_notional=100,
            strategy_budget_row={"strategy_capital_budget": 2000, "strategy_capital_used": 500, "warning_threshold": 1500},
            portfolio_registry={"available_capital": 5000},
            cluster_risk_state="ALERT",
        )
        assert payload["action"] == "REDUCE_SIZE"
        assert "CLUSTER_RISK_ALIGNMENT" in payload["reason"]


# ===== REGRESSION TESTS =====
class TestRegressionEndpoints:
    """Ensure existing endpoints are not broken"""

    def test_strategy_governance_returns_200(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-governance", headers=admin_headers, timeout=20)
        assert response.status_code == 200

    def test_cluster_risk_returns_200(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/cluster-risk", headers=admin_headers, timeout=20)
        assert response.status_code == 200

    def test_strategy_performance_returns_200(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-performance", headers=admin_headers, timeout=20)
        assert response.status_code == 200

    def test_strategy_execution_quality_returns_200(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-execution-quality", headers=admin_headers, timeout=20)
        assert response.status_code == 200

    def test_strategy_health_returns_200(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-health", headers=admin_headers, timeout=20)
        assert response.status_code == 200


# ===== INTEGRATION TESTS =====
class TestCapitalGovernanceIntegration:
    """Integration tests for capital governance flow"""

    def test_capital_budget_matches_usage_strategy_count(self, admin_headers):
        budget_response = requests.get(f"{BASE_URL}/api/admin/futures/capital-budget", headers=admin_headers, timeout=20)
        usage_response = requests.get(f"{BASE_URL}/api/admin/futures/capital-usage", headers=admin_headers, timeout=20)
        budget_payload = budget_response.json()
        usage_payload = usage_response.json()
        assert len(budget_payload["strategy_capital_budget"]) == len(usage_payload["strategy_capital_usage"])

    def test_capital_drift_by_strategy_matches_budget_strategies(self, admin_headers):
        budget_response = requests.get(f"{BASE_URL}/api/admin/futures/capital-budget", headers=admin_headers, timeout=20)
        drift_response = requests.get(f"{BASE_URL}/api/admin/futures/capital-drift", headers=admin_headers, timeout=20)
        budget_payload = budget_response.json()
        drift_payload = drift_response.json()
        budget_strategies = {row["strategy_id"] for row in budget_payload["strategy_capital_budget"]}
        drift_strategies = set(drift_payload["capital_drift_by_strategy"].keys())
        assert budget_strategies == drift_strategies

    def test_portfolio_risk_budget_calculated_correctly(self, admin_headers):
        budget_response = requests.get(f"{BASE_URL}/api/admin/futures/capital-budget", headers=admin_headers, timeout=20)
        usage_response = requests.get(f"{BASE_URL}/api/admin/futures/capital-usage", headers=admin_headers, timeout=20)
        budget_payload = budget_response.json()
        usage_payload = usage_response.json()
        # Risk budget should be portfolio_equity * risk_budget_ratio (0.8)
        portfolio_equity = budget_payload["portfolio_capital_registry"]["portfolio_equity"]
        risk_budget = usage_payload["portfolio_risk_budget"]
        assert risk_budget == portfolio_equity * 0.8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
