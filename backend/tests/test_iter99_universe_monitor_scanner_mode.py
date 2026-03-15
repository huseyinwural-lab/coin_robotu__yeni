"""
Iteration 99 - Universe Monitor, Scanner Mode, Debug/Effective Universe Tests
Features:
1. GET /api/debug/effective-universe (admin only) returns required keys
2. GET /api/admin/universe-monitor returns required metrics
3. PUT/GET /api/phase4/live-config supports symbol_whitelist=[] (allow all)
4. POST /api/user/scanner/run with symbol_selection_mode=all_market_symbols
5. GET /api/user/decision-cards includes block_category field
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_CREDENTIALS = {"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")}
USER_CREDENTIALS = {"email": "TEST_phase4iter2_pipeline@example.com", "password": "TestPassword123!"}


@pytest.fixture(scope="module")
def admin_session():
    """Create admin session with auth token"""
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDENTIALS)
    if response.status_code == 200:
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
    return session


@pytest.fixture(scope="module")
def user_session():
    """Create user session with auth token"""
    session = requests.Session()
    
    # Try to create user first (may already exist)
    try:
        requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": USER_CREDENTIALS["email"],
            "password": USER_CREDENTIALS["password"],
            "full_name": "Test Phase4 User"
        })
    except Exception:
        pass
    
    response = session.post(f"{BASE_URL}/api/auth/login", json=USER_CREDENTIALS)
    if response.status_code == 200:
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
    return session


class TestDebugEffectiveUniverse:
    """GET /api/debug/effective-universe admin endpoint tests"""
    
    def test_debug_effective_universe_returns_200_for_admin(self, admin_session):
        """Admin should access debug effective universe endpoint"""
        response = admin_session.get(f"{BASE_URL}/api/debug/effective-universe", params={
            "market_type": "spot",
            "scanner_mode": "ALL_MARKET_SYMBOLS",
            "top_n": 100
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Check required keys are present
        required_keys = [
            "market_type", "scanner_mode", "market_symbols_count",
            "after_blacklist", "after_scanner_mode", "final_symbols",
            "generated_at", "filters"
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"
        
        # Validate types
        assert isinstance(data["final_symbols"], list)
        assert isinstance(data["market_symbols_count"], int)
        assert isinstance(data["filters"], dict)
        print(f"Debug effective universe: market_symbols={data['market_symbols_count']}, final_symbols={len(data['final_symbols'])}")
    
    def test_debug_effective_universe_requires_admin(self, user_session):
        """Non-admin should NOT access debug effective universe"""
        response = user_session.get(f"{BASE_URL}/api/debug/effective-universe")
        # Should return 401/403 for non-admin
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_debug_effective_universe_scanner_modes(self, admin_session):
        """Test different scanner modes"""
        for mode in ["ALL_MARKET_SYMBOLS", "TOP_VOLUME", "MANUAL_SELECTION"]:
            response = admin_session.get(f"{BASE_URL}/api/debug/effective-universe", params={
                "scanner_mode": mode, "top_n": 50
            })
            assert response.status_code == 200, f"Mode {mode} failed: {response.status_code}"
            data = response.json()
            assert data["scanner_mode"] in ["ALL_MARKET_SYMBOLS", "TOP_VOLUME", "MANUAL_SELECTION"]
            print(f"Scanner mode {mode}: final_symbols={len(data['final_symbols'])}")


class TestAdminUniverseMonitor:
    """GET /api/admin/universe-monitor endpoint tests"""
    
    def test_universe_monitor_returns_200_for_admin(self, admin_session):
        """Admin should access universe monitor endpoint"""
        response = admin_session.get(f"{BASE_URL}/api/admin/universe-monitor", params={
            "market_type": "spot",
            "scanner_mode": "ALL_MARKET_SYMBOLS",
            "top_n": 200
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Check required metrics keys
        required_keys = [
            "market_type", "scanner_mode", "total_exchange_symbols",
            "active_scan_symbols", "blocked_by_permission", "blocked_by_risk",
            "blocked_by_liquidity", "generated_at"
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"
        
        # Validate types
        assert isinstance(data["total_exchange_symbols"], int)
        assert isinstance(data["active_scan_symbols"], int)
        assert isinstance(data["blocked_by_permission"], int)
        assert isinstance(data["blocked_by_risk"], int)
        assert isinstance(data["blocked_by_liquidity"], int)
        
        print(f"Universe monitor: total={data['total_exchange_symbols']}, active={data['active_scan_symbols']}, "
              f"blocked_perm={data['blocked_by_permission']}, blocked_risk={data['blocked_by_risk']}, "
              f"blocked_liq={data['blocked_by_liquidity']}")
    
    def test_universe_monitor_requires_admin(self, user_session):
        """Non-admin should NOT access universe monitor"""
        response = user_session.get(f"{BASE_URL}/api/admin/universe-monitor")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestPhase4LiveConfigWhitelist:
    """PUT/GET /api/phase4/live-config symbol_whitelist tests"""
    
    def test_get_live_config(self, admin_session):
        """Get current live config"""
        response = admin_session.get(f"{BASE_URL}/api/phase4/live-config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # symbol_whitelist should be a list
        assert "symbol_whitelist" in data
        assert isinstance(data["symbol_whitelist"], list)
        print(f"Current symbol_whitelist: {data.get('symbol_whitelist')}")
    
    def test_put_live_config_empty_whitelist(self, admin_session):
        """Empty symbol_whitelist should be accepted (allow all behavior)"""
        # First get current config
        get_response = admin_session.get(f"{BASE_URL}/api/phase4/live-config")
        assert get_response.status_code == 200
        current_config = get_response.json()
        
        # Update with empty whitelist
        update_payload = {
            **current_config,
            "symbol_whitelist": []  # Empty = allow all
        }
        response = admin_session.put(f"{BASE_URL}/api/phase4/live-config", json=update_payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify empty whitelist was saved
        verify_response = admin_session.get(f"{BASE_URL}/api/phase4/live-config")
        assert verify_response.status_code == 200
        verified = verify_response.json()
        assert verified.get("symbol_whitelist") == [], f"Expected [], got {verified.get('symbol_whitelist')}"
        print("Empty whitelist (allow all) test passed")
    
    def test_put_live_config_with_symbols(self, admin_session):
        """symbol_whitelist with specific symbols should work"""
        get_response = admin_session.get(f"{BASE_URL}/api/phase4/live-config")
        assert get_response.status_code == 200
        current_config = get_response.json()
        
        # Update with specific symbols
        update_payload = {
            **current_config,
            "symbol_whitelist": ["BTCUSDT", "ETHUSDT"]
        }
        response = admin_session.put(f"{BASE_URL}/api/phase4/live-config", json=update_payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify
        verify_response = admin_session.get(f"{BASE_URL}/api/phase4/live-config")
        verified = verify_response.json()
        assert "BTCUSDT" in verified.get("symbol_whitelist", [])
        print(f"Whitelist with symbols test passed: {verified.get('symbol_whitelist')}")
        
        # Reset to empty for future tests
        update_payload["symbol_whitelist"] = []
        admin_session.put(f"{BASE_URL}/api/phase4/live-config", json=update_payload)


class TestUserScannerWithMode:
    """POST /api/user/scanner/run with symbol_selection_mode tests"""
    
    def test_scanner_run_all_market_symbols_mode(self, user_session):
        """Scanner run with symbol_selection_mode=all_market_symbols should return 200"""
        response = user_session.post(f"{BASE_URL}/api/user/scanner/run", json={
            "symbol_selection_mode": "all_market_symbols",
            "max_results": 10
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Should have run_id and result_count
        assert "run_id" in data
        assert "result_count" in data or "actionable_count" in data
        print(f"Scanner run: run_id={data.get('run_id')}, results={data.get('result_count', data.get('actionable_count'))}")
    
    def test_scanner_run_top_volume_mode(self, user_session):
        """Scanner run with symbol_selection_mode=top_volume"""
        response = user_session.post(f"{BASE_URL}/api/user/scanner/run", json={
            "symbol_selection_mode": "top_volume",
            "max_results": 10
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_scanner_run_manual_selection_mode(self, user_session):
        """Scanner run with symbol_selection_mode=manual_selection"""
        response = user_session.post(f"{BASE_URL}/api/user/scanner/run", json={
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["BTCUSDT", "ETHUSDT"],
            "max_results": 10
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestDecisionCardsBlockCategory:
    """GET /api/user/decision-cards block_category field tests"""
    
    def test_decision_cards_includes_block_category(self, user_session):
        """Decision cards should include block_category field"""
        # First run scanner to generate some data
        user_session.post(f"{BASE_URL}/api/user/scanner/run", json={
            "symbol_selection_mode": "all_market_symbols",
            "max_results": 5
        })
        
        response = user_session.get(f"{BASE_URL}/api/user/decision-cards", params={"limit": 10})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Check structure
        items = data.get("items") or data
        if isinstance(items, list) and len(items) > 0:
            sample = items[0]
            # block_category can be null or a string value
            assert "block_category" in sample, f"Missing block_category in decision card. Keys: {list(sample.keys())}"
            
            # Validate block_category value if present
            valid_categories = [None, "symbol_permission_block", "data_unavailable", "cooldown_block", "risk_block", "gate_block"]
            block_cat = sample.get("block_category")
            assert block_cat in valid_categories or block_cat is None, f"Unexpected block_category: {block_cat}"
            print(f"Decision card includes block_category: {block_cat}")
        else:
            print("No decision cards available - skipping block_category validation (scanner may not have generated cards)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
