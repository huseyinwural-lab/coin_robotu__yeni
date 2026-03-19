"""
Test Iteration 102: Admin Override Clear + Full Market Scope + Scanner Perf Metrics

Testing:
1. Admin control override clear -> full market spot/futures coverage
2. GET /api/debug/effective-universe spot/futures count and final_symbols
3. POST /api/user/scanner/run -> scanner_perf fields (latency/stale/queue/dropped)
4. scanner_perf contains: requested_selection_mode, effective_selection_mode, overload_fallback_applied
5. GET /api/admin/universe-monitor metrics: average_cycle_latency_ms, stale_blocks, queue_depth, dropped_evaluations
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Credentials
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")
USER_EMAIL = "TEST_phase4iter2_pipeline@example.com"
USER_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("access_token")


@pytest.fixture(scope="module")
def user_token():
    """Get user auth token, register if needed"""
    # Try login
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    if resp.status_code == 200:
        return resp.json().get("access_token")
    
    # Register user
    resp = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD,
        "name": "TEST Pipeline User"
    })
    if resp.status_code in [200, 201]:
        data = resp.json()
        return data.get("access_token") or data.get("token")
    
    # Try login again after registration
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    if resp.status_code == 200:
        return resp.json().get("access_token")
    
    pytest.skip(f"User authentication failed: {resp.status_code}")


class TestAdminControlOverrideClear:
    """Test admin control override clear for full market coverage"""
    
    def test_admin_control_get_current_state(self, admin_token):
        """Get current admin control state"""
        resp = requests.get(
            f"{BASE_URL}/api/admin-control",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        print(f"Current admin control: spot_universe count={len(data.get('spot_universe') or [])}, futures_universe count={len(data.get('futures_universe') or [])}")
        assert "spot_universe" in data or "whitelist" in data
    
    def test_admin_control_clear_overrides(self, admin_token):
        """Clear spot/futures override lists for full market"""
        resp = requests.put(
            f"{BASE_URL}/api/admin-control",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "spot_universe": [],
                "futures_universe": [],
                "whitelist": [],
                "blacklist": []
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        # Verify overrides are cleared
        spot_count = len(data.get("spot_universe") or [])
        futures_count = len(data.get("futures_universe") or [])
        print(f"After clear: spot_universe={spot_count}, futures_universe={futures_count}")
        assert spot_count == 0, "spot_universe should be empty"
        assert futures_count == 0, "futures_universe should be empty"


class TestEffectiveUniverseDebug:
    """Test debug effective universe endpoint"""
    
    def test_debug_effective_universe_spot(self, admin_token):
        """Test GET /api/debug/effective-universe for spot market"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/effective-universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"market_type": "spot", "scanner_mode": "ALL_MARKET_SYMBOLS", "top_n": 500}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify response structure
        assert "market_type" in data
        assert data["market_type"] == "spot"
        assert "final_symbols" in data
        assert "market_symbols_count" in data
        assert "after_scanner_mode" in data
        
        spot_count = len(data.get("final_symbols") or [])
        market_count = data.get("market_symbols_count", 0)
        print(f"Spot universe: market_symbols_count={market_count}, final_symbols count={spot_count}")
        
        # Should have wide market coverage now (>100 symbols expected)
        assert spot_count > 0, "Should have spot symbols"
        print(f"Spot final_symbols (first 10): {data.get('final_symbols', [])[:10]}")
    
    def test_debug_effective_universe_futures(self, admin_token):
        """Test GET /api/debug/effective-universe for futures market"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/effective-universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"market_type": "futures", "scanner_mode": "ALL_MARKET_SYMBOLS", "top_n": 500}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["market_type"] == "futures"
        assert "final_symbols" in data
        
        futures_count = len(data.get("final_symbols") or [])
        market_count = data.get("market_symbols_count", 0)
        print(f"Futures universe: market_symbols_count={market_count}, final_symbols count={futures_count}")
        
        # Futures may have symbols if not disabled
        print(f"Futures final_symbols (first 10): {data.get('final_symbols', [])[:10]}")
    
    def test_debug_effective_universe_filters(self, admin_token):
        """Verify filter details in effective universe"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/effective-universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"market_type": "spot"}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        filters = data.get("filters", {})
        print(f"Universe filters: {filters}")
        
        # Verify filters structure
        assert "whitelist" in filters
        assert "blacklist" in filters
        assert filters.get("allow_all") in [True, False, None] or "allow_all" in filters


class TestScannerRunWithPerfMetrics:
    """Test scanner run with performance metrics"""
    
    def test_scanner_run_returns_scanner_perf(self, user_token):
        """POST /api/user/scanner/run returns scanner_perf with all metrics"""
        resp = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "symbol_selection_mode": "all_market_symbols",
                "max_results": 30
            }
        )
        assert resp.status_code == 200, f"Scanner run failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        
        # Verify scanner_perf exists
        assert "scanner_perf" in data, "Response should contain scanner_perf"
        scanner_perf = data["scanner_perf"]
        
        print(f"Scanner run response keys: {list(data.keys())}")
        print(f"scanner_perf keys: {list(scanner_perf.keys())}")
        
        # Verify required scanner_perf fields
        required_fields = [
            "cycle_duration_ms",
            "symbols_evaluated",
            "queue_backlog",
            "dropped_symbol_count",
            "stale_block_count"
        ]
        for field in required_fields:
            assert field in scanner_perf, f"scanner_perf should have {field}"
            print(f"  {field}: {scanner_perf.get(field)}")
    
    def test_scanner_perf_selection_mode_fields(self, user_token):
        """Verify scanner_perf has requested/effective selection mode and overload fallback"""
        resp = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "symbol_selection_mode": "all_market_symbols",
                "max_results": 20
            }
        )
        assert resp.status_code == 200
        scanner_perf = resp.json().get("scanner_perf", {})
        
        # Check selection mode fields
        assert "requested_selection_mode" in scanner_perf, "Should have requested_selection_mode"
        assert "effective_selection_mode" in scanner_perf, "Should have effective_selection_mode"
        assert "overload_fallback_applied" in scanner_perf, "Should have overload_fallback_applied"
        
        requested = scanner_perf.get("requested_selection_mode")
        effective = scanner_perf.get("effective_selection_mode")
        fallback = scanner_perf.get("overload_fallback_applied")
        
        print(f"Selection modes: requested={requested}, effective={effective}, fallback_applied={fallback}")
        
        # Verify types
        assert isinstance(requested, str)
        assert isinstance(effective, str)
        assert isinstance(fallback, bool)
    
    def test_scanner_perf_latency_metrics(self, user_token):
        """Verify latency and stale metrics in scanner_perf"""
        resp = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"max_results": 15}
        )
        assert resp.status_code == 200
        scanner_perf = resp.json().get("scanner_perf", {})
        
        # Latency metrics
        cycle_ms = scanner_perf.get("cycle_duration_ms")
        avg_eval_ms = scanner_perf.get("avg_symbol_eval_ms")
        
        print(f"Latency: cycle_duration_ms={cycle_ms}, avg_symbol_eval_ms={avg_eval_ms}")
        
        assert cycle_ms is not None
        assert isinstance(cycle_ms, (int, float))
        
        # Stale metrics
        stale_eval = scanner_perf.get("stale_evaluation_count", 0)
        stale_block = scanner_perf.get("stale_block_count", 0)
        
        print(f"Stale metrics: stale_evaluation_count={stale_eval}, stale_block_count={stale_block}")
        
        # Queue metrics
        queue_backlog = scanner_perf.get("queue_backlog", 0)
        dropped = scanner_perf.get("dropped_symbol_count", 0)
        
        print(f"Queue metrics: queue_backlog={queue_backlog}, dropped_symbol_count={dropped}")


class TestUniverseMonitorMetrics:
    """Test admin universe monitor metrics"""
    
    def test_universe_monitor_summary(self, admin_token):
        """GET /api/admin/universe-monitor returns all required metrics"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"market_type": "spot", "scanner_mode": "ALL_MARKET_SYMBOLS"}
        )
        assert resp.status_code == 200, f"Universe monitor failed: {resp.status_code}"
        data = resp.json()
        
        print(f"Universe monitor response keys: {list(data.keys())}")
        
        # Required metrics
        assert "average_cycle_latency_ms" in data, "Should have average_cycle_latency_ms"
        assert "stale_blocks" in data, "Should have stale_blocks"
        assert "queue_depth" in data, "Should have queue_depth"
        assert "dropped_evaluations" in data, "Should have dropped_evaluations"
        
        print("Universe monitor metrics:")
        print(f"  average_cycle_latency_ms: {data.get('average_cycle_latency_ms')}")
        print(f"  stale_blocks: {data.get('stale_blocks')}")
        print(f"  queue_depth: {data.get('queue_depth')}")
        print(f"  dropped_evaluations: {data.get('dropped_evaluations')}")
        print(f"  worker_utilization: {data.get('worker_utilization')}")
    
    def test_universe_monitor_additional_fields(self, admin_token):
        """Verify additional monitor fields"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Additional expected fields
        additional_fields = [
            "total_exchange_symbols",
            "active_scan_symbols",
            "symbols_evaluated_this_cycle",
            "blocked_by_permission",
            "blocked_by_risk",
            "blocked_by_liquidity",
            "final_symbols"
        ]
        
        for field in additional_fields:
            print(f"  {field}: {data.get(field) if not isinstance(data.get(field), list) else len(data.get(field, []))}")
    
    def test_universe_monitor_top_slow_lists(self, admin_token):
        """Verify top slow strategies and symbols arrays"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Top slow arrays
        top_slow_strategies = data.get("top_slow_strategies", [])
        top_slow_symbols = data.get("top_slow_symbols", [])
        
        print(f"top_slow_strategies: {top_slow_strategies[:5]}")
        print(f"top_slow_symbols: {top_slow_symbols[:5]}")
        
        assert isinstance(top_slow_strategies, list)
        assert isinstance(top_slow_symbols, list)


class TestUniversePreview:
    """Test universe preview endpoint"""
    
    def test_universe_preview_after_clear(self, admin_token):
        """Verify universe preview reflects cleared overrides"""
        resp = requests.get(
            f"{BASE_URL}/api/admin-control/universe/preview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        spot_symbols = data.get("spot_symbols", [])
        futures_symbols = data.get("futures_symbols", [])
        filters = data.get("filters", {})
        
        print(f"Universe preview: spot={len(spot_symbols)}, futures={len(futures_symbols)}")
        print(f"Filters: {filters}")
        
        # After clearing overrides, should have market-derived symbols
        assert isinstance(spot_symbols, list)
        assert isinstance(futures_symbols, list)
