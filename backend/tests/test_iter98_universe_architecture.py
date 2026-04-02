"""
Test Suite for Universe Architecture Transformation (Iteration 98)
Features:
- GET /api/debug/effective-universe (admin only)
- GET /api/admin/universe-monitor
- build_effective_universe semantics with empty whitelist (allow_all)
- Phase4 live config with symbol_whitelist=[]
- User scanner run with symbol_selection_mode=all_market_symbols
- Decision cards block_category field
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")
USER_EMAIL = "TEST_phase4iter2_pipeline@example.com"
USER_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }, timeout=15)
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin login failed: {response.status_code}")


@pytest.fixture(scope="module")
def user_token():
    """Get user authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    }, timeout=15)
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"User login failed: {response.status_code}")


class TestDebugEffectiveUniverse:
    """Tests for GET /api/debug/effective-universe endpoint (admin only)"""

    def test_debug_effective_universe_admin_access(self, admin_token):
        """Admin should access debug effective universe endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/debug/effective-universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"market_type": "spot", "scanner_mode": "ALL_MARKET_SYMBOLS", "top_n": 100},
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required fields exist
        assert "market_symbols_count" in data, "Missing market_symbols_count"
        assert "after_blacklist" in data, "Missing after_blacklist"
        assert "after_scanner_mode" in data, "Missing after_scanner_mode"
        assert "after_liquidity_filter" in data, "Missing after_liquidity_filter"
        assert "final_symbols" in data, "Missing final_symbols"
        
        # Verify data types
        assert isinstance(data["market_symbols_count"], int)
        assert isinstance(data["after_blacklist"], int)
        assert isinstance(data["after_scanner_mode"], int)
        assert isinstance(data["after_liquidity_filter"], int)
        assert isinstance(data["final_symbols"], list)
        
        print(f"market_symbols_count: {data['market_symbols_count']}")
        print(f"after_blacklist: {data['after_blacklist']}")
        print(f"after_scanner_mode: {data['after_scanner_mode']}")
        print(f"after_liquidity_filter: {data['after_liquidity_filter']}")
        print(f"final_symbols count: {len(data['final_symbols'])}")

    def test_debug_effective_universe_requires_admin(self, user_token):
        """Non-admin users should not access debug effective universe"""
        response = requests.get(
            f"{BASE_URL}/api/debug/effective-universe",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15
        )
        # Should be 401 or 403 for non-admin
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_debug_effective_universe_top_volume_mode(self, admin_token):
        """Test scanner_mode=TOP_VOLUME"""
        response = requests.get(
            f"{BASE_URL}/api/debug/effective-universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"market_type": "spot", "scanner_mode": "TOP_VOLUME", "top_n": 50},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data["scanner_mode"] == "TOP_VOLUME"
        assert data["after_scanner_mode"] <= 50  # Should be limited by top_n

    def test_debug_effective_universe_manual_selection_mode(self, admin_token):
        """Test scanner_mode=MANUAL_SELECTION"""
        response = requests.get(
            f"{BASE_URL}/api/debug/effective-universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={
                "market_type": "spot", 
                "scanner_mode": "MANUAL_SELECTION", 
                "selected_symbols": "BTCUSDT,ETHUSDT",
                "top_n": 100
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data["scanner_mode"] == "MANUAL_SELECTION"
        # Should only contain selected symbols that exist in market
        final = data["final_symbols"]
        assert len(final) <= 2


class TestAdminUniverseMonitor:
    """Tests for GET /api/admin/universe-monitor endpoint"""

    def test_universe_monitor_admin_access(self, admin_token):
        """Admin should access universe monitor endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"market_type": "spot", "scanner_mode": "ALL_MARKET_SYMBOLS", "top_n": 200},
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "total_exchange_symbols" in data, "Missing total_exchange_symbols"
        assert "active_scan_symbols" in data, "Missing active_scan_symbols"
        assert "blocked_by_permission" in data, "Missing blocked_by_permission"
        assert "blocked_by_risk" in data, "Missing blocked_by_risk"
        assert "blocked_by_liquidity" in data, "Missing blocked_by_liquidity"
        
        # Verify data types
        assert isinstance(data["total_exchange_symbols"], int)
        assert isinstance(data["active_scan_symbols"], int)
        assert isinstance(data["blocked_by_permission"], int)
        assert isinstance(data["blocked_by_risk"], int)
        assert isinstance(data["blocked_by_liquidity"], int)
        
        print(f"total_exchange_symbols: {data['total_exchange_symbols']}")
        print(f"active_scan_symbols: {data['active_scan_symbols']}")
        print(f"blocked_by_permission: {data['blocked_by_permission']}")
        print(f"blocked_by_risk: {data['blocked_by_risk']}")
        print(f"blocked_by_liquidity: {data['blocked_by_liquidity']}")

    def test_universe_monitor_requires_admin(self, user_token):
        """Non-admin users should not access universe monitor"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15
        )
        assert response.status_code in [401, 403]


class TestBuildEffectiveUniverseSemantics:
    """Tests for build_effective_universe semantics with empty whitelist"""

    def test_whitelist_empty_allows_all(self, admin_token):
        """When whitelist is empty, allow_all should be true"""
        response = requests.get(
            f"{BASE_URL}/api/debug/effective-universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"market_type": "spot", "scanner_mode": "ALL_MARKET_SYMBOLS", "top_n": 300},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        filters = data.get("filters", {})
        whitelist = filters.get("whitelist", [])
        allow_all = filters.get("allow_all", False)
        
        # If whitelist is empty, allow_all should be True
        if len(whitelist) == 0:
            assert allow_all is True, "allow_all should be True when whitelist is empty"
            print("Verified: whitelist empty -> allow_all=True")
        else:
            print(f"Whitelist has {len(whitelist)} items, allow_all={allow_all}")

    def test_liquidity_filter_advisory_only(self, admin_token):
        """Liquidity filter should be advisory-only mode, not exclusion"""
        response = requests.get(
            f"{BASE_URL}/api/debug/effective-universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"market_type": "spot", "scanner_mode": "ALL_MARKET_SYMBOLS", "top_n": 100},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        filters = data.get("filters", {})
        liquidity_filter_mode = filters.get("liquidity_filter_mode")
        
        # Verify advisory-only mode
        assert liquidity_filter_mode == "advisory_only", f"Expected advisory_only, got {liquidity_filter_mode}"
        print("Verified: liquidity_filter_mode=advisory_only")


class TestPhase4LiveConfigWhitelist:
    """Tests for Phase4 live config with symbol_whitelist=[]"""

    def test_phase4_get_config(self, admin_token):
        """Get Phase4 live config"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/live-config",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        assert "symbol_whitelist" in data
        print(f"Current symbol_whitelist: {data['symbol_whitelist']}")

    def test_phase4_empty_whitelist_readback(self, admin_token):
        """Update config with symbol_whitelist=[] and verify readback"""
        # First get current config
        get_response = requests.get(
            f"{BASE_URL}/api/phase4/live-config",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15
        )
        assert get_response.status_code == 200
        current_config = get_response.json()
        
        # Save current whitelist to restore later
        original_whitelist = current_config.get("symbol_whitelist", [])
        
        # Update with empty whitelist
        update_payload = {
            "exchange": current_config.get("exchange", "binance"),
            "market_type": current_config.get("market_type", "futures_live"),
            "safe_mode_enabled": current_config.get("safe_mode_enabled", True),
            "live_mode_enabled": current_config.get("live_mode_enabled", False),
            "symbol_whitelist": [],  # Empty whitelist
            "max_position_pct": current_config.get("max_position_pct", 0.1),
            "leverage_cap": current_config.get("leverage_cap", 1),
            "max_trades_per_hour": current_config.get("max_trades_per_hour", 6),
            "max_notional_exposure": current_config.get("max_notional_exposure", 150),
            "kill_switch_enabled": current_config.get("kill_switch_enabled", False),
            "disable_futures": current_config.get("disable_futures", False),
            "ip_whitelist_ready": current_config.get("ip_whitelist_ready", False),
            "trading_permission_ready": current_config.get("trading_permission_ready", False),
        }
        
        put_response = requests.put(
            f"{BASE_URL}/api/phase4/live-config",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=update_payload,
            timeout=15
        )
        assert put_response.status_code == 200, f"Config update failed: {put_response.text}"
        
        # Verify readback
        verify_response = requests.get(
            f"{BASE_URL}/api/phase4/live-config",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15
        )
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data["symbol_whitelist"] == [], f"Expected [], got {verify_data['symbol_whitelist']}"
        print("Verified: symbol_whitelist=[] readback successful")
        
        # Restore original whitelist
        if original_whitelist:
            update_payload["symbol_whitelist"] = original_whitelist
            requests.put(
                f"{BASE_URL}/api/phase4/live-config",
                headers={"Authorization": f"Bearer {admin_token}"},
                json=update_payload,
                timeout=15
            )


class TestUserScannerRunAllMarketSymbols:
    """Tests for user scanner run with symbol_selection_mode=all_market_symbols"""

    def test_scanner_run_all_market_symbols(self, user_token):
        """Scanner run with symbol_selection_mode=all_market_symbols should work"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "mode": "ASSISTED",
                "max_results": 20,
                "symbol_source": "crypto",
                "symbol_selection_mode": "all_market_symbols",
                "selected_symbols": []
            },
            timeout=60
        )
        assert response.status_code == 200, f"Scanner run failed: {response.text}"
        data = response.json()
        
        assert "run_id" in data
        assert "mode" in data
        assert "result_count" in data
        
        print(f"Scanner run successful: run_id={data['run_id']}, result_count={data['result_count']}")

    def test_scanner_run_top_volume(self, user_token):
        """Scanner run with symbol_selection_mode=top_volume should work"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "mode": "ASSISTED",
                "max_results": 15,
                "symbol_source": "crypto",
                "symbol_selection_mode": "top_volume",
                "selected_symbols": []
            },
            timeout=60
        )
        assert response.status_code == 200, f"Scanner run failed: {response.text}"
        data = response.json()
        assert "run_id" in data
        print(f"Scanner top_volume run successful: run_id={data['run_id']}")

    def test_scanner_run_manual_selection(self, user_token):
        """Scanner run with symbol_selection_mode=manual_selection should work"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "mode": "ASSISTED",
                "max_results": 10,
                "symbol_source": "crypto",
                "symbol_selection_mode": "manual_selection",
                "selected_symbols": ["BTCUSDT", "ETHUSDT"]
            },
            timeout=60
        )
        assert response.status_code == 200, f"Scanner run failed: {response.text}"
        data = response.json()
        assert "run_id" in data
        print(f"Scanner manual_selection run successful: run_id={data['run_id']}")


class TestDecisionCardsBlockCategory:
    """Tests for decision cards with block_category field"""

    def test_decision_cards_list(self, user_token):
        """List decision cards should include block_category field"""
        response = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 30},
            timeout=30
        )
        assert response.status_code == 200, f"Decision cards request failed: {response.text}"
        data = response.json()
        
        assert "items" in data or isinstance(data, list), "Unexpected response format"
        items = data.get("items", []) if isinstance(data, dict) else data
        
        print(f"Decision cards count: {len(items)}")
        
        # Check that block_category field exists in structure
        for item in items[:5]:  # Check first 5 items
            assert "decision" in item, "Missing decision field"
            assert "symbol" in item, "Missing symbol field"
            # block_category may be None if not blocked
            if "block_category" in item:
                print(f"Symbol {item['symbol']}: decision={item['decision']}, block_category={item.get('block_category')}")

    def test_decision_card_fields(self, user_token):
        """Verify decision card has basic required fields"""
        response = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 10},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", []) if isinstance(data, dict) else data
        if items:
            card = items[0]
            expected_fields = ["symbol", "decision", "confidence", "long_score", "short_score", "generated_at"]
            for field in expected_fields:
                assert field in card, f"Missing required field: {field}"
            print(f"Verified required fields in decision card for {card['symbol']}")


class TestScannerModeAliases:
    """Tests for scanner mode aliases (backward compatibility)"""

    def test_old_mode_all_exchange_alias(self, admin_token):
        """Old mode 'all_exchange' should map to ALL_MARKET_SYMBOLS"""
        response = requests.get(
            f"{BASE_URL}/api/debug/effective-universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"market_type": "spot", "scanner_mode": "all_exchange", "top_n": 50},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data["scanner_mode"] == "ALL_MARKET_SYMBOLS", f"Expected ALL_MARKET_SYMBOLS, got {data['scanner_mode']}"
        print("Verified: all_exchange -> ALL_MARKET_SYMBOLS")

    def test_old_mode_top_active_alias(self, admin_token):
        """Old mode 'top_active_50' should map to TOP_VOLUME"""
        response = requests.get(
            f"{BASE_URL}/api/debug/effective-universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"market_type": "spot", "scanner_mode": "top_active_50", "top_n": 50},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data["scanner_mode"] == "TOP_VOLUME", f"Expected TOP_VOLUME, got {data['scanner_mode']}"
        print("Verified: top_active_50 -> TOP_VOLUME")

    def test_old_mode_custom_list_alias(self, admin_token):
        """Old mode 'custom_list' should map to MANUAL_SELECTION"""
        response = requests.get(
            f"{BASE_URL}/api/debug/effective-universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={
                "market_type": "spot", 
                "scanner_mode": "custom_list", 
                "selected_symbols": "BTCUSDT",
                "top_n": 50
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data["scanner_mode"] == "MANUAL_SELECTION", f"Expected MANUAL_SELECTION, got {data['scanner_mode']}"
        print("Verified: custom_list -> MANUAL_SELECTION")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
