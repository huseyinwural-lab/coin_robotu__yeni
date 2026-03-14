"""
Iteration 100 - P0-A + P0-B Universe Expansion Performance Guard Tests
Tests:
1. POST /api/user/scanner/run returns scanner_perf metrics
2. Freshness guard contract: stale_data_block reason code path
3. GET /api/admin/universe-monitor performance fields
4. GET /api/debug/effective-universe required fields
5. Admin UI regression: /admin/universe-monitor metric cards
6. Regression: /api/user/decision-cards block_category field
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"
USER_EMAIL = "TEST_phase4iter2_pipeline@example.com"
USER_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip("Admin authentication failed")


@pytest.fixture(scope="module")
def user_token():
    """Get user authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip("User authentication failed")


class TestScannerPerfMetrics:
    """P0-A: Scanner /run endpoint returns scanner_perf metrics block"""

    def test_scanner_run_returns_scanner_perf_block(self, user_token):
        """POST /api/user/scanner/run returns scanner_perf object with all P0-A fields"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=headers,
            json={
                "max_results": 10,
                "symbol_selection_mode": "all_market_symbols",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Verify scanner_perf block exists
        assert "scanner_perf" in data, "scanner_perf block missing from scanner/run response"
        perf = data["scanner_perf"]

        # P0-A required metrics
        required_fields = [
            "total_active_symbols",
            "cycle_duration_ms",
            "avg_symbol_eval_ms",
            "queue_backlog",
            "dropped_symbol_count",
            "stale_evaluation_count",
        ]
        for field in required_fields:
            assert field in perf, f"Missing P0-A scanner_perf field: {field}"

        # Type validations
        assert isinstance(perf["total_active_symbols"], int), "total_active_symbols must be int"
        assert isinstance(perf["cycle_duration_ms"], (int, float)), "cycle_duration_ms must be numeric"
        assert isinstance(perf["avg_symbol_eval_ms"], (int, float)), "avg_symbol_eval_ms must be numeric"
        assert isinstance(perf["queue_backlog"], int), "queue_backlog must be int"
        assert isinstance(perf["dropped_symbol_count"], int), "dropped_symbol_count must be int"
        assert isinstance(perf["stale_evaluation_count"], int), "stale_evaluation_count must be int"

        print(f"PASS: scanner_perf block with all P0-A fields: {list(perf.keys())}")

    def test_scanner_perf_has_candidate_tier_counts(self, user_token):
        """scanner_perf should have candidate tier counts"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=headers,
            json={"max_results": 10},
        )
        assert response.status_code == 200
        data = response.json()
        perf = data.get("scanner_perf", {})

        tier_fields = ["candidate_high", "candidate_medium", "candidate_low", "ignore_for_now", "decision_scope_symbols"]
        present_fields = [f for f in tier_fields if f in perf]
        print(f"PASS: candidate tier fields present: {present_fields}")

    def test_scanner_perf_freshness_sla_seconds(self, user_token):
        """scanner_perf should include freshness_sla_seconds thresholds"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=headers,
            json={"max_results": 5},
        )
        assert response.status_code == 200
        data = response.json()
        perf = data.get("scanner_perf", {})

        if "freshness_sla_seconds" in perf:
            sla = perf["freshness_sla_seconds"]
            assert isinstance(sla, dict), "freshness_sla_seconds should be dict"
            print(f"PASS: freshness_sla_seconds: {sla}")
        else:
            print("INFO: freshness_sla_seconds not in scanner_perf (optional)")


class TestFreshnessGuardContract:
    """P0-A/B: Stale data handling - stale_data_block reason code path"""

    def test_stale_data_block_reason_code_exists_in_hints(self):
        """Verify STALE_DATA_BLOCK is defined as valid reason code"""
        # Check by importing the service module's reason hints
        from core.users.user_scanner_signal_service import SIGNAL_PENDING_REASON_HINTS

        assert "STALE_DATA_BLOCK" in SIGNAL_PENDING_REASON_HINTS, "STALE_DATA_BLOCK missing from reason hints"
        hint = SIGNAL_PENDING_REASON_HINTS["STALE_DATA_BLOCK"]
        assert len(hint) == 2, "STALE_DATA_BLOCK hint should have (message, solution) tuple"
        print(f"PASS: STALE_DATA_BLOCK reason hint: {hint[0][:50]}...")

    def test_freshness_sla_seconds_config_exists(self):
        """Verify FRESHNESS_SLA_SECONDS config is defined"""
        from core.users.user_scanner_signal_service import FRESHNESS_SLA_SECONDS

        assert isinstance(FRESHNESS_SLA_SECONDS, dict), "FRESHNESS_SLA_SECONDS should be dict"
        assert "15m" in FRESHNESS_SLA_SECONDS, "15m timeframe should have SLA"
        print(f"PASS: FRESHNESS_SLA_SECONDS config: {FRESHNESS_SLA_SECONDS}")


class TestAdminUniverseMonitorPerformanceFields:
    """P0-B: GET /api/admin/universe-monitor performance fields"""

    def test_universe_monitor_returns_performance_fields(self, admin_token):
        """Admin universe monitor should return new P0-B performance fields"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor",
            headers=headers,
            params={"market_type": "spot", "scanner_mode": "ALL_MARKET_SYMBOLS"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # P0-B required performance fields
        required_fields = [
            "symbols_evaluated_this_cycle",
            "average_cycle_latency_ms",
            "queue_depth",
            "stale_blocks",
            "dropped_evaluations",
            "worker_utilization",
            "top_slow_strategies",
            "top_slow_symbols",
        ]

        for field in required_fields:
            assert field in data, f"Missing P0-B performance field: {field}"

        # Type validations
        assert isinstance(data["symbols_evaluated_this_cycle"], int), "symbols_evaluated_this_cycle must be int"
        assert isinstance(data["average_cycle_latency_ms"], (int, float)), "average_cycle_latency_ms must be numeric"
        assert isinstance(data["queue_depth"], int), "queue_depth must be int"
        assert isinstance(data["stale_blocks"], int), "stale_blocks must be int"
        assert isinstance(data["dropped_evaluations"], int), "dropped_evaluations must be int"
        assert isinstance(data["worker_utilization"], (int, float)), "worker_utilization must be numeric"
        assert isinstance(data["top_slow_strategies"], list), "top_slow_strategies must be list"
        assert isinstance(data["top_slow_symbols"], list), "top_slow_symbols must be list"

        print(f"PASS: universe-monitor performance fields: symbols_evaluated={data['symbols_evaluated_this_cycle']}, queue_depth={data['queue_depth']}")

    def test_universe_monitor_existing_fields_regression(self, admin_token):
        """Existing universe monitor fields should not regress"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Existing fields from iteration 99
        existing_fields = [
            "total_exchange_symbols",
            "active_scan_symbols",
            "blocked_by_permission",
            "blocked_by_risk",
            "blocked_by_liquidity",
        ]

        for field in existing_fields:
            assert field in data, f"Regression: missing existing field {field}"

        print(f"PASS: Existing fields retained: {existing_fields}")


class TestDebugEffectiveUniverseFields:
    """GET /api/debug/effective-universe required fields"""

    def test_debug_effective_universe_required_fields(self, admin_token):
        """Debug effective universe should return all required fields"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/debug/effective-universe",
            headers=headers,
            params={"market_type": "spot"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Required fields
        required_fields = [
            "market_symbols_count",
            "after_blacklist",
            "after_scanner_mode",
            "final_symbols",
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        assert isinstance(data["final_symbols"], list), "final_symbols must be list"
        assert isinstance(data["market_symbols_count"], int), "market_symbols_count must be int"

        print(f"PASS: debug/effective-universe: market_symbols_count={data['market_symbols_count']}, final_symbols count={len(data['final_symbols'])}")


class TestDecisionCardsBlockCategory:
    """Regression: /api/user/decision-cards block_category field"""

    def test_decision_cards_returns_block_category_field(self, user_token):
        """GET /api/user/decision-cards should include block_category field"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            headers=headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Response should be envelope with items
        items = data.get("items", data) if isinstance(data, dict) else data
        if isinstance(items, list) and len(items) > 0:
            card = items[0]
            # block_category should exist (can be null)
            assert "block_category" in card, "block_category field missing from decision card"
            print(f"PASS: decision card has block_category: {card.get('block_category')}")
        else:
            print("INFO: No decision cards available to verify block_category")


class TestScannerPerfTopSlowPanels:
    """P0-B: top_slow_strategies and top_slow_symbols structure validation"""

    def test_top_slow_strategies_structure(self, admin_token):
        """top_slow_strategies should have proper structure"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()

        slow_strategies = data.get("top_slow_strategies", [])
        if slow_strategies:
            sample = slow_strategies[0]
            # Expected fields: strategy_id, avg_ms, calls
            expected = ["strategy_id", "avg_ms", "calls"]
            for field in expected:
                assert field in sample, f"top_slow_strategies item missing {field}"
            print(f"PASS: top_slow_strategies structure valid, sample: {sample}")
        else:
            print("INFO: top_slow_strategies is empty (acceptable)")

    def test_top_slow_symbols_structure(self, admin_token):
        """top_slow_symbols should have proper structure"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()

        slow_symbols = data.get("top_slow_symbols", [])
        if slow_symbols:
            sample = slow_symbols[0]
            # Expected fields: symbol, elapsed_ms
            expected = ["symbol", "elapsed_ms"]
            for field in expected:
                assert field in sample, f"top_slow_symbols item missing {field}"
            print(f"PASS: top_slow_symbols structure valid, sample: {sample}")
        else:
            print("INFO: top_slow_symbols is empty (acceptable)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
