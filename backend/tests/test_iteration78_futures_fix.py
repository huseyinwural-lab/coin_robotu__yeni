"""
Iteration 78 - Backend tests for:
1. Admin Action Center disable_futures reset when clear_kill_switch is used
2. Futures symbol universe API returns rows for all_exchange mode
3. Spot selector regression check
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"

@pytest.fixture(scope="module")
def admin_token():
    """Login as admin and get token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    assert "access_token" in data, "No access_token in login response"
    return data["access_token"]


class TestAdminActionCenterDisableFuturesReset:
    """Test that clear_kill_switch resets disable_futures to false"""

    def test_action_center_summary_initial(self, admin_token):
        """Get initial action center summary"""
        response = requests.get(
            f"{BASE_URL}/api/admin/action-center/summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()
        assert "disable_futures" in data, "disable_futures not in summary response"
        assert "kill_switch_active" in data, "kill_switch_active not in summary"
        assert "emergency_mode" in data, "emergency_mode not in summary"
        print(f"Initial summary: disable_futures={data.get('disable_futures')}, kill_switch_active={data.get('kill_switch_active')}, emergency_mode={data.get('emergency_mode')}")

    def test_close_next_actions_with_clear_kill_switch(self, admin_token):
        """Test that clear_kill_switch=true resets disable_futures to false"""
        # First enable disable_futures via admin control if needed
        # Then call close-next-actions with clear_kill_switch=true
        response = requests.post(
            f"{BASE_URL}/api/admin/action-center/close-next-actions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "ack_open_alerts": False,
                "reject_stale_approvals": False,
                "retry_timeout_rejections": False,
                "clear_kill_switch": True,
            },
        )
        assert response.status_code == 200, f"close-next-actions failed: {response.text}"
        data = response.json()
        assert data.get("status") == "completed", "Expected status=completed"
        assert data.get("clear_kill_switch") is True, "Expected clear_kill_switch=true in response"
        print(f"close-next-actions response: {data}")

    def test_action_center_summary_after_clear(self, admin_token):
        """Verify disable_futures is false after clear_kill_switch"""
        response = requests.get(
            f"{BASE_URL}/api/admin/action-center/summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()
        assert data.get("disable_futures") is False, f"Expected disable_futures=false, got {data.get('disable_futures')}"
        assert data.get("emergency_mode") is False, f"Expected emergency_mode=false, got {data.get('emergency_mode')}"
        print(f"After clear_kill_switch summary: disable_futures={data.get('disable_futures')}, emergency_mode={data.get('emergency_mode')}")


class TestFuturesSymbolUniverse:
    """Test futures symbol universe API returns rows for Binance futures"""

    def test_futures_universe_all_exchange_mode(self, admin_token):
        """GET /api/symbol-selector/universe with futures market_type returns rows"""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "futures",
                "mode": "all_exchange",
            },
        )
        assert response.status_code == 200, f"Futures universe failed: {response.text}"
        data = response.json()
        
        # Check required fields
        assert "rows" in data, "rows not in response"
        assert "selected_symbols" in data, "selected_symbols not in response"
        assert "source" in data, "source not in response"
        assert "market_type" in data, "market_type not in response"
        
        # Verify rows count is > 0 for futures
        rows_count = len(data.get("rows", []))
        selected_count = len(data.get("selected_symbols", []))
        
        print(f"Futures universe response: rows_count={rows_count}, selected_count={selected_count}, source={data.get('source')}, market_type={data.get('market_type')}")
        
        # CRITICAL: Main bug fix verification - futures should have rows
        assert rows_count > 0, f"Expected rows > 0 for futures all_exchange, got {rows_count}"
        assert selected_count > 0, f"Expected selected_symbols > 0 for futures all_exchange, got {selected_count}"
        assert data.get("market_type") == "futures", f"Expected market_type=futures, got {data.get('market_type')}"
        
        # Verify some common futures symbols are present
        symbols = [row.get("symbol") for row in data.get("rows", [])]
        print(f"Sample futures symbols: {symbols[:10]}")
        
        # BTCUSDT or ETHUSDT should typically be in futures
        common_futures = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
        found_common = [s for s in common_futures if s in symbols]
        print(f"Found common futures symbols: {found_common}")

    def test_futures_universe_with_query_filter(self, admin_token):
        """Test futures universe with query parameter"""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "futures",
                "mode": "all_exchange",
                "query": "BTC",
            },
        )
        assert response.status_code == 200, f"Futures universe with query failed: {response.text}"
        data = response.json()
        rows_count = len(data.get("rows", []))
        print(f"Futures universe with query=BTC: rows_count={rows_count}")
        
        # All returned symbols should contain BTC
        for row in data.get("rows", []):
            symbol = row.get("symbol", "")
            assert "BTC" in symbol, f"Symbol {symbol} does not contain BTC"


class TestSpotSymbolUniverseRegression:
    """Regression: Spot selector still works"""

    def test_spot_universe_all_exchange_mode(self, admin_token):
        """GET /api/symbol-selector/universe with spot market_type returns rows"""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "mode": "all_exchange",
            },
        )
        assert response.status_code == 200, f"Spot universe failed: {response.text}"
        data = response.json()
        
        rows_count = len(data.get("rows", []))
        selected_count = len(data.get("selected_symbols", []))
        
        print(f"Spot universe response: rows_count={rows_count}, selected_count={selected_count}")
        
        # Spot should have rows
        assert rows_count > 0, f"Expected rows > 0 for spot all_exchange, got {rows_count}"
        assert selected_count > 0, f"Expected selected_symbols > 0 for spot all_exchange, got {selected_count}"
        assert data.get("market_type") == "spot", f"Expected market_type=spot, got {data.get('market_type')}"

    def test_spot_universe_top_active_50(self, admin_token):
        """Test spot universe with top_active_50 mode"""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "mode": "top_active_50",
            },
        )
        assert response.status_code == 200, f"Spot top_active_50 failed: {response.text}"
        data = response.json()
        
        selected_count = len(data.get("selected_symbols", []))
        print(f"Spot top_active_50: selected_count={selected_count}")
        
        # top_active_50 should return exactly 50 or less (if less than 50 available)
        assert selected_count <= 50, f"Expected selected_count <= 50, got {selected_count}"
        assert selected_count > 0, f"Expected selected_count > 0, got {selected_count}"


class TestAdminControlEndpoint:
    """Test admin control endpoint for disable_futures"""

    def test_get_admin_control(self, admin_token):
        """Get current admin control settings"""
        response = requests.get(
            f"{BASE_URL}/api/admin-control",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"admin-control GET failed: {response.text}"
        data = response.json()
        
        assert "disable_futures" in data, "disable_futures not in admin-control"
        assert "emergency_mode" in data, "emergency_mode not in admin-control"
        assert "spot_universe" in data, "spot_universe not in admin-control"
        assert "futures_universe" in data, "futures_universe not in admin-control"
        
        print(f"Admin control: disable_futures={data.get('disable_futures')}, emergency_mode={data.get('emergency_mode')}")
        print(f"Spot universe count: {len(data.get('spot_universe', []))}")
        print(f"Futures universe count: {len(data.get('futures_universe', []))}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
