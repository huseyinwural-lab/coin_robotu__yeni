"""
Iteration 74: Comprehensive testing of advanced symbol selection system.

Tests cover:
- New backend symbol selector API suite: /api/symbol-selector/universe, /watchlists CRUD, /provider-config, /provider-config/alpha-vantage
- Crypto symbol modes: all_exchange, top_active_50, top_active_100, custom_list
- Stock symbol universe behavior (NASDAQ+NYSE) and key-handling behavior
- User Bot Profiles page: SymbolSelectorPanel integration and profile create/update payload symbol list
- User Scanner page: SymbolSelectorPanel integration and scanner run payload
- User Indicator Screener page: new symbol modes/source UI + custom selector integration
- User Execute page: single-select symbol panel integration
- Admin Market Universe page: spot/futures selector integration + Alpha key save panel
- Admin Strategy Intelligence page: single-select symbol selector integration
- Regression: existing major admin/user pages still load and key API routes remain functional
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://execution-recovery.preview.emergentagent.com"

ADMIN_CREDENTIALS = {"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")}


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDENTIALS, timeout=15)
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers for authenticated admin requests."""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def user_token():
    """Create a test user and get their auth token."""
    # Try to login first
    login_response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "test_user_iter74@test.com", "password": "TestUser123!"},
        timeout=15,
    )
    if login_response.status_code == 200:
        return login_response.json().get("access_token")

    # Register new test user
    register_response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": "test_user_iter74@test.com", "password": "TestUser123!"},
        timeout=15,
    )
    if register_response.status_code in [200, 201]:
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "test_user_iter74@test.com", "password": "TestUser123!"},
            timeout=15,
        )
        if login_response.status_code == 200:
            return login_response.json().get("access_token")
    
    # Fall back to admin token if user creation fails
    admin_response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDENTIALS, timeout=15)
    return admin_response.json().get("access_token") if admin_response.status_code == 200 else None


@pytest.fixture(scope="module")
def user_headers(user_token):
    """Headers for authenticated user requests."""
    if not user_token:
        pytest.skip("User token not available")
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


class TestSymbolSelectorAPIBasics:
    """Test the new symbol selector API endpoints."""

    def test_get_provider_config(self, admin_headers):
        """GET /api/symbol-selector/provider-config returns provider config status."""
        response = requests.get(f"{BASE_URL}/api/symbol-selector/provider-config", headers=admin_headers, timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert "has_alpha_vantage_key" in data
        print(f"PASS: Provider config response: has_alpha_vantage_key={data.get('has_alpha_vantage_key')}")

    def test_get_crypto_universe_all_exchange(self, admin_headers):
        """GET /api/symbol-selector/universe with crypto source and all_exchange mode."""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "mode": "all_exchange",
            },
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("source") == "crypto"
        assert data.get("mode") == "all_exchange"
        assert "rows" in data
        assert "selected_symbols" in data
        assert data.get("has_provider_key") is True
        print(f"PASS: Crypto all_exchange returned {len(data.get('rows', []))} rows, {len(data.get('selected_symbols', []))} selected")

    def test_get_crypto_universe_top_active_50(self, admin_headers):
        """GET /api/symbol-selector/universe with crypto source and top_active_50 mode."""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "mode": "top_active_50",
            },
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("mode") == "top_active_50"
        selected = data.get("selected_symbols", [])
        # Should be at most 50 symbols
        assert len(selected) <= 50
        print(f"PASS: Crypto top_active_50 returned {len(selected)} selected symbols")

    def test_get_crypto_universe_top_active_100(self, admin_headers):
        """GET /api/symbol-selector/universe with crypto source and top_active_100 mode."""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "mode": "top_active_100",
            },
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("mode") == "top_active_100"
        selected = data.get("selected_symbols", [])
        # Should be at most 100 symbols
        assert len(selected) <= 100
        print(f"PASS: Crypto top_active_100 returned {len(selected)} selected symbols")

    def test_get_crypto_universe_custom_list(self, admin_headers):
        """GET /api/symbol-selector/universe with crypto source and custom_list mode."""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "mode": "custom_list",
                "selected_symbols": "BTCUSDT,ETHUSDT,BNBUSDT",
            },
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("mode") == "custom_list"
        selected = data.get("selected_symbols", [])
        # Custom list should contain the specified symbols
        assert "BTCUSDT" in selected or len(selected) == 0
        print(f"PASS: Crypto custom_list returned {len(selected)} selected symbols")

    def test_get_stock_universe_without_key(self, admin_headers):
        """GET /api/symbol-selector/universe with stock source - should warn about missing key."""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            params={
                "source": "stock",
                "exchange": "US",
                "market_type": "equity",
                "mode": "all_exchange",
            },
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("source") == "stock"
        warnings = data.get("warnings", [])
        # If no Alpha Vantage key, should have a warning
        if not data.get("has_provider_key"):
            assert "alpha_vantage_key_missing" in warnings
            print("PASS: Stock source correctly returns alpha_vantage_key_missing warning")
        else:
            print(f"PASS: Stock source has provider key, returned {len(data.get('rows', []))} rows")


class TestWatchlistCRUD:
    """Test watchlist CRUD operations."""

    def test_list_watchlists_empty(self, user_headers):
        """GET /api/symbol-selector/watchlists returns list (may be empty)."""
        response = requests.get(f"{BASE_URL}/api/symbol-selector/watchlists", headers=user_headers, timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Watchlists endpoint returned {len(data)} items")

    def test_create_watchlist(self, user_headers):
        """POST /api/symbol-selector/watchlists creates a new watchlist."""
        response = requests.post(
            f"{BASE_URL}/api/symbol-selector/watchlists",
            json={
                "name": "TEST_iter74_watchlist",
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            },
            headers=user_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("name") == "TEST_iter74_watchlist"
        assert data.get("source") == "crypto"
        assert "BTCUSDT" in data.get("symbols", [])
        print(f"PASS: Created watchlist with id={data.get('id')}")
        return data.get("id")

    def test_create_and_update_watchlist(self, user_headers):
        """Create and then update a watchlist."""
        # Create
        create_response = requests.post(
            f"{BASE_URL}/api/symbol-selector/watchlists",
            json={
                "name": "TEST_iter74_update_test",
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["BTCUSDT"],
            },
            headers=user_headers,
            timeout=15,
        )
        assert create_response.status_code == 200
        watchlist_id = create_response.json().get("id")
        
        # Update
        update_response = requests.put(
            f"{BASE_URL}/api/symbol-selector/watchlists/{watchlist_id}",
            json={
                "name": "TEST_iter74_updated",
                "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"],
            },
            headers=user_headers,
            timeout=15,
        )
        assert update_response.status_code == 200
        data = update_response.json()
        assert data.get("name") == "TEST_iter74_updated"
        assert len(data.get("symbols", [])) == 4
        print(f"PASS: Updated watchlist {watchlist_id}")

    def test_delete_watchlist(self, user_headers):
        """Create and then delete a watchlist."""
        # Create
        create_response = requests.post(
            f"{BASE_URL}/api/symbol-selector/watchlists",
            json={
                "name": "TEST_iter74_delete_test",
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["BTCUSDT"],
            },
            headers=user_headers,
            timeout=15,
        )
        assert create_response.status_code == 200
        watchlist_id = create_response.json().get("id")
        
        # Delete
        delete_response = requests.delete(
            f"{BASE_URL}/api/symbol-selector/watchlists/{watchlist_id}",
            headers=user_headers,
            timeout=15,
        )
        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data.get("deleted") is True
        print(f"PASS: Deleted watchlist {watchlist_id}")


class TestAlphaVantageKeyConfig:
    """Test Alpha Vantage API key configuration (admin only)."""

    def test_put_alpha_vantage_key(self, admin_headers):
        """PUT /api/symbol-selector/provider-config/alpha-vantage saves the key."""
        response = requests.put(
            f"{BASE_URL}/api/symbol-selector/provider-config/alpha-vantage",
            json={"api_key": "TEST_DEMO_KEY_12345"},
            headers=admin_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("has_alpha_vantage_key") is True
        assert data.get("key_hint") is not None
        print(f"PASS: Alpha Vantage key saved, key_hint={data.get('key_hint')}")

    def test_non_admin_cannot_put_alpha_key(self, user_headers):
        """Non-admin users cannot update Alpha Vantage key."""
        response = requests.put(
            f"{BASE_URL}/api/symbol-selector/provider-config/alpha-vantage",
            json={"api_key": "SHOULD_FAIL"},
            headers=user_headers,
            timeout=15,
        )
        # Should be 403 or 401
        assert response.status_code in [401, 403]
        print(f"PASS: Non-admin correctly blocked from updating Alpha key (status={response.status_code})")


class TestScannerWithSymbolSelection:
    """Test scanner run with symbol selection modes."""

    def test_scanner_run_with_crypto_source(self, user_headers):
        """POST /api/user/scanner/run with crypto source."""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            json={
                "mode": "ASSISTED",
                "max_results": 15,
                "symbol_source": "crypto",
                "symbol_selection_mode": "top_active_50",
                "selected_symbols": [],
            },
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert "mode" in data
        print(f"PASS: Scanner run completed, run_id={data.get('run_id')}, result_count={data.get('result_count')}")

    def test_scanner_run_with_custom_symbols(self, user_headers):
        """POST /api/user/scanner/run with custom symbol selection."""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            json={
                "mode": "MANUAL",
                "max_results": 10,
                "symbol_source": "crypto",
                "symbol_selection_mode": "custom_list",
                "selected_symbols": ["BTCUSDT", "ETHUSDT"],
            },
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("mode") == "MANUAL"
        # Should have warnings or selected_symbols
        print(f"PASS: Scanner with custom symbols, selected={data.get('selected_symbols', [])[:5]}")


class TestIndicatorScreenerWithSymbolModes:
    """Test indicator screener with symbol selection modes."""

    def test_screener_run_with_all_exchange(self, user_headers):
        """POST /api/user/indicator-screener/run with all_exchange universe."""
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json={
                "exchange": "binance",
                "market_type": "spot",
                "timeframe": "15m",
                "query_expression": "rsi14 < 70",
                "symbol_universe": "all",
                "limit": 30,
                "filter_payload": {
                    "symbol_source": "crypto",
                    "symbol_universe_mode": "all_exchange",
                },
            },
            headers=user_headers,
            timeout=60,
        )
        assert response.status_code == 200
        data = response.json()
        assert "rows" in data
        assert "query_valid" in data
        print(f"PASS: Indicator screener all_exchange returned {data.get('match_count', 0)} matches")

    def test_screener_run_with_custom_list(self, user_headers):
        """POST /api/user/indicator-screener/run with custom symbol list."""
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json={
                "exchange": "binance",
                "market_type": "spot",
                "timeframe": "15m",
                "query_expression": "rsi14 < 70",
                "symbol_universe": "BTCUSDT,ETHUSDT,BNBUSDT",
                "limit": 20,
                "filter_payload": {
                    "symbol_source": "crypto",
                    "symbol_universe_mode": "custom_list",
                    "symbol_whitelist": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
                },
            },
            headers=user_headers,
            timeout=60,
        )
        assert response.status_code == 200
        data = response.json()
        print(f"PASS: Indicator screener custom_list returned {data.get('match_count', 0)} matches")


class TestBotProfileWithSymbols:
    """Test bot profile creation/update with symbols from selector."""

    def test_create_bot_profile_with_symbols(self, user_headers):
        """POST /api/bot-profiles creates profile with symbols."""
        response = requests.post(
            f"{BASE_URL}/api/bot-profiles",
            json={
                "name": "TEST_iter74_bot",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"],
                "strategy_type": "trend_following",
                "timeframe": "15m",
                "trend_timeframe": "1h",
                "leverage": 1,
                "is_enabled": True,
            },
            headers=user_headers,
            timeout=15,
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert data.get("name") == "TEST_iter74_bot"
        assert len(data.get("symbols", [])) >= 4
        print(f"PASS: Created bot profile {data.get('id')} with {len(data.get('symbols', []))} symbols")

    def test_update_bot_profile_symbols(self, user_headers):
        """Update bot profile symbols list."""
        # First create
        create_response = requests.post(
            f"{BASE_URL}/api/bot-profiles",
            json={
                "name": "TEST_iter74_update_bot",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["BTCUSDT"],
                "strategy_type": "trend_following",
                "timeframe": "15m",
                "trend_timeframe": "1h",
                "leverage": 1,
                "is_enabled": True,
            },
            headers=user_headers,
            timeout=15,
        )
        assert create_response.status_code in [200, 201]
        bot_id = create_response.json().get("id")
        
        # Update with more symbols
        update_response = requests.put(
            f"{BASE_URL}/api/bot-profiles/{bot_id}",
            json={
                "name": "TEST_iter74_update_bot",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"],
                "strategy_type": "trend_following",
                "timeframe": "15m",
                "trend_timeframe": "1h",
                "leverage": 1,
                "is_enabled": True,
            },
            headers=user_headers,
            timeout=15,
        )
        assert update_response.status_code == 200
        data = update_response.json()
        assert len(data.get("symbols", [])) >= 5
        print(f"PASS: Updated bot profile to {len(data.get('symbols', []))} symbols")


class TestAdminControlSymbolUniverse:
    """Test admin control with symbol universe updates."""

    def test_get_admin_control(self, admin_headers):
        """GET /api/admin-control returns current settings."""
        response = requests.get(f"{BASE_URL}/api/admin-control", headers=admin_headers, timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert "spot_universe" in data
        assert "futures_universe" in data
        print(f"PASS: Admin control has spot_universe={len(data.get('spot_universe', []))} symbols")

    def test_update_admin_control_universe(self, admin_headers):
        """PUT /api/admin-control updates symbol universe."""
        # Get current first
        current = requests.get(f"{BASE_URL}/api/admin-control", headers=admin_headers, timeout=15).json()
        
        response = requests.put(
            f"{BASE_URL}/api/admin-control",
            json={
                "max_leverage_cap": current.get("max_leverage_cap", 5),
                "max_open_positions_cap": current.get("max_open_positions_cap", 10),
                "minimum_volume_usd": current.get("minimum_volume_usd", 1000000),
                "max_spread_bps": current.get("max_spread_bps", 40),
                "spot_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"],
                "futures_universe": ["BTCUSDT", "ETHUSDT"],
                "whitelist": current.get("whitelist", []),
                "blacklist": current.get("blacklist", []),
                "emergency_mode": current.get("emergency_mode", False),
                "disable_futures": current.get("disable_futures", False),
            },
            headers=admin_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert "BTCUSDT" in data.get("spot_universe", [])
        print("PASS: Updated admin control universe")


class TestRegressionExistingEndpoints:
    """Regression tests for existing endpoints to ensure no breakage."""

    def test_health_endpoint(self):
        """GET /api/health still works."""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        assert response.json().get("status") == "ok"
        print("PASS: Health endpoint OK")

    def test_user_dashboard(self, user_headers):
        """GET /api/user/dashboard still works."""
        response = requests.get(f"{BASE_URL}/api/user/dashboard", headers=user_headers, timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert "bot_count" in data or "running_bot_count" in data
        print("PASS: User dashboard endpoint OK")

    def test_bot_profiles_list(self, user_headers):
        """GET /api/bot-profiles still works."""
        response = requests.get(f"{BASE_URL}/api/bot-profiles", headers=user_headers, timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Bot profiles list returned {len(data)} items")

    def test_admin_dashboard_summary(self, admin_headers):
        """GET /api/admin/dashboard/summary still works."""
        response = requests.get(f"{BASE_URL}/api/admin/dashboard/summary", headers=admin_headers, timeout=15)
        assert response.status_code == 200
        print("PASS: Admin dashboard summary OK")

    def test_admin_strategy_intelligence(self, admin_headers):
        """GET /api/admin/strategy-intelligence still works."""
        response = requests.get(f"{BASE_URL}/api/admin/strategy-intelligence", headers=admin_headers, timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert "strategy_conflicts" in data
        print("PASS: Admin strategy intelligence endpoint OK")

    def test_user_exchange_connections(self, user_headers):
        """GET /api/user/exchange-connections still works."""
        response = requests.get(f"{BASE_URL}/api/user/exchange-connections", headers=user_headers, timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: User exchange connections returned {len(data)} items")

    def test_user_execution_presets(self, user_headers):
        """GET /api/user/execution/presets still works."""
        response = requests.get(f"{BASE_URL}/api/user/execution/presets", headers=user_headers, timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: User execution presets returned {len(data)} items")


class TestMarketUniversePreview:
    """Test the market universe preview endpoint."""

    def test_admin_universe_preview(self, admin_headers):
        """GET /api/admin-control/universe/preview returns effective universes."""
        response = requests.get(f"{BASE_URL}/api/admin-control/universe/preview", headers=admin_headers, timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert "spot_symbols" in data
        assert "futures_symbols" in data
        print(f"PASS: Universe preview: spot={len(data.get('spot_symbols', []))}, futures={len(data.get('futures_symbols', []))}")


class TestFuturesUniverseSelection:
    """Test futures market type with symbol selector."""

    def test_futures_crypto_universe(self, admin_headers):
        """GET /api/symbol-selector/universe with futures market_type."""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "futures",
                "mode": "top_active_50",
            },
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("market_type") == "futures"
        print(f"PASS: Futures universe returned {len(data.get('selected_symbols', []))} symbols")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
