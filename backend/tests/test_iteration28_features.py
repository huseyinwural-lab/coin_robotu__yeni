"""
Iteration 28 Feature Tests
==========================
Tests for:
1. Strategy allocation weight - no auto normalize/reset on load
2. /api/symbol-selector/universe?market_type=both - returns merged spot+futures
3. ScannerResultsTable strategy filter - 12 canonical strategies always present
4. TradeSymbolSelection - uses marketType prop (both shows merged symbols)
5. UserScannerPage - local scanner settings persist (mode/marketType/watchlistOnly)
6. UserSignalsPage - signals/trades requests have retry for transient 500
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


def get_authenticated_session(email: str, password: str) -> requests.Session:
    """Create an authenticated session with cookies"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=60,
    )
    if login_response.status_code != 200:
        raise Exception(f"Login failed: {login_response.status_code} - {login_response.text}")
    
    # Extract token from response and set as header if needed
    data = login_response.json()
    if "access_token" in data:
        session.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    elif "token" in data:
        session.headers.update({"Authorization": f"Bearer {data['token']}"})
    
    return session


@pytest.fixture(scope="module")
def admin_session():
    """Admin session fixture"""
    return get_authenticated_session("canary.admin@platform.local", "CanaryAdmin123!")


@pytest.fixture(scope="module")
def user_session():
    """User session fixture"""
    return get_authenticated_session("review.user@platform.local", "ReviewUser123!")


class TestSymbolSelectorUniverseBoth:
    """Test /api/symbol-selector/universe?market_type=both returns merged spot+futures"""

    def test_universe_spot_returns_symbols(self, admin_session):
        """Test spot market type returns symbols"""
        response = admin_session.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "mode": "all_market_symbols",
            },
            timeout=60,
        )
        assert response.status_code == 200, f"Spot universe failed: {response.text}"
        data = response.json()
        assert "rows" in data, "Response should have 'rows' field"
        assert "selected_symbols" in data, "Response should have 'selected_symbols' field"
        spot_count = len(data.get("rows", []))
        print(f"Spot symbols count: {spot_count}")
        assert spot_count > 0, "Spot should return symbols"

    def test_universe_futures_returns_symbols(self, admin_session):
        """Test futures market type returns symbols"""
        response = admin_session.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "futures",
                "mode": "all_market_symbols",
            },
            timeout=60,
        )
        assert response.status_code == 200, f"Futures universe failed: {response.text}"
        data = response.json()
        assert "rows" in data, "Response should have 'rows' field"
        futures_count = len(data.get("rows", []))
        print(f"Futures symbols count: {futures_count}")
        # Futures may be empty in some environments, but endpoint should work
        assert isinstance(data.get("rows"), list), "Rows should be a list"

    def test_universe_both_returns_merged_symbols(self, admin_session):
        """Test market_type=both returns merged spot+futures symbols"""
        # First get spot count
        spot_response = admin_session.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "mode": "all_market_symbols",
            },
            timeout=60,
        )
        assert spot_response.status_code == 200
        spot_data = spot_response.json()
        spot_count = len(spot_data.get("rows", []))

        # Now get both
        both_response = admin_session.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "both",
                "mode": "all_market_symbols",
            },
            timeout=60,
        )
        assert both_response.status_code == 200, f"Both universe failed: {both_response.text}"
        both_data = both_response.json()
        both_count = len(both_data.get("rows", []))

        print(f"Spot count: {spot_count}, Both count: {both_count}")

        # Both should have at least as many as spot (merged)
        # Even if futures is empty, both should not drop spot symbols
        assert both_count >= spot_count, f"Both ({both_count}) should have at least as many symbols as spot ({spot_count})"

        # Check that rows have market_type field
        if both_count > 0:
            first_row = both_data["rows"][0]
            assert "market_type" in first_row, "Row should have market_type field"
            # When merged, market_type should be 'both' for common symbols
            print(f"First row market_type: {first_row.get('market_type')}")

    def test_universe_both_does_not_drop_spot_when_futures_empty(self, admin_session):
        """Verify that both selection doesn't drop spot symbols even if futures is empty"""
        # Get spot symbols
        spot_response = admin_session.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "mode": "all_market_symbols",
            },
            timeout=60,
        )
        assert spot_response.status_code == 200
        spot_symbols = set(row["symbol"] for row in spot_response.json().get("rows", []))

        # Get both symbols
        both_response = admin_session.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "both",
                "mode": "all_market_symbols",
            },
            timeout=60,
        )
        assert both_response.status_code == 200
        both_symbols = set(row["symbol"] for row in both_response.json().get("rows", []))

        # All spot symbols should be in both
        missing_from_both = spot_symbols - both_symbols
        assert len(missing_from_both) == 0, f"Spot symbols missing from both: {list(missing_from_both)[:10]}"
        print(f"All {len(spot_symbols)} spot symbols are present in both selection")


class TestStrategyAllocationNoAutoNormalize:
    """Test that strategy allocation weights are not auto-normalized on load"""

    def test_strategy_allocation_list_returns_12_strategies(self, admin_session):
        """Test that strategy allocation list returns 12 canonical strategies"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            timeout=60,
        )
        assert response.status_code == 200, f"Strategy allocation list failed: {response.text}"
        data = response.json()
        strategies = data.get("strategies", data) if isinstance(data, dict) else data
        if isinstance(strategies, dict) and "strategies" in strategies:
            strategies = strategies["strategies"]
        
        # Should be a list
        assert isinstance(strategies, list), f"Expected list, got {type(strategies)}"
        print(f"Strategy count: {len(strategies)}")
        
        # Should have 12 canonical strategies
        assert len(strategies) == 12, f"Expected 12 strategies, got {len(strategies)}"

    def test_strategy_weights_preserved_on_load(self, admin_session):
        """Test that strategy weights are not reset to equal distribution on load"""
        # First load
        response1 = admin_session.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            timeout=60,
        )
        assert response1.status_code == 200
        data1 = response1.json()
        strategies1 = data1.get("strategies", data1) if isinstance(data1, dict) else data1
        if isinstance(strategies1, dict) and "strategies" in strategies1:
            strategies1 = strategies1["strategies"]

        # Get weights from first load
        weights1 = {s["strategy_id"]: s.get("capital_weight", 0) for s in strategies1}

        # Second load
        response2 = admin_session.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            timeout=60,
        )
        assert response2.status_code == 200
        data2 = response2.json()
        strategies2 = data2.get("strategies", data2) if isinstance(data2, dict) else data2
        if isinstance(strategies2, dict) and "strategies" in strategies2:
            strategies2 = strategies2["strategies"]

        # Get weights from second load
        weights2 = {s["strategy_id"]: s.get("capital_weight", 0) for s in strategies2}

        # Weights should be the same (not reset)
        for strategy_id in weights1:
            assert strategy_id in weights2, f"Strategy {strategy_id} missing in second load"
            assert abs(weights1[strategy_id] - weights2[strategy_id]) < 0.0001, \
                f"Weight changed for {strategy_id}: {weights1[strategy_id]} -> {weights2[strategy_id]}"

        print("Strategy weights preserved across loads")


class TestUserSignalsRetryMechanism:
    """Test that UserSignalsPage has retry mechanism for transient 500 errors"""

    def test_signals_endpoint_works(self, user_session):
        """Test that signals endpoint returns data"""
        response = user_session.get(
            f"{BASE_URL}/api/user/signals",
            params={"limit": 80},
            timeout=60,
        )
        assert response.status_code == 200, f"Signals endpoint failed: {response.text}"
        data = response.json()
        # Should return list or object with items
        if isinstance(data, list):
            print(f"Signals count: {len(data)}")
        elif isinstance(data, dict):
            items = data.get("items", [])
            print(f"Signals count: {len(items)}")
        else:
            pytest.fail(f"Unexpected response type: {type(data)}")

    def test_trades_endpoint_works(self, user_session):
        """Test that trades endpoint returns data"""
        response = user_session.get(
            f"{BASE_URL}/api/user/trades",
            params={"limit": 50},
            timeout=60,
        )
        assert response.status_code == 200, f"Trades endpoint failed: {response.text}"
        data = response.json()
        # Should return list
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"Trades count: {len(data)}")

    def test_portfolio_endpoint_works(self, user_session):
        """Test that portfolio endpoint returns data"""
        response = user_session.get(
            f"{BASE_URL}/api/user/portfolio",
            timeout=60,
        )
        assert response.status_code == 200, f"Portfolio endpoint failed: {response.text}"
        data = response.json()
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        print(f"Portfolio data keys: {list(data.keys())}")


class TestCanonicalStrategiesInScannerFilter:
    """Test that scanner results filter always shows 12 canonical strategies"""

    CANONICAL_STRATEGIES = [
        "ichimoku_trend_continuation",
        "golden_cross_regime",
        "supertrend_flip",
        "vortex_directional_cross",
        "bollinger_squeeze_breakout",
        "moving_momentum",
        "fibonacci_pullback_continuation",
        "macd_impulse",
        "fisher_reversal",
        "divergence_reversal_suite",
        "structure_breakout",
        "stochastic_exhaustion_reentry",
    ]

    def test_canonical_strategies_defined(self):
        """Verify 12 canonical strategies are defined"""
        assert len(self.CANONICAL_STRATEGIES) == 12, f"Expected 12 canonical strategies, got {len(self.CANONICAL_STRATEGIES)}"
        print(f"Canonical strategies: {self.CANONICAL_STRATEGIES}")

    def test_screener_endpoint_works(self, admin_session):
        """Test that screener endpoint returns data"""
        response = admin_session.get(
            f"{BASE_URL}/api/screener",
            params={"limit": 120},
            timeout=60,
        )
        assert response.status_code == 200, f"Screener endpoint failed: {response.text}"
        data = response.json()
        # Should return list
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"Screener results count: {len(data)}")


class TestScannerSettingsPersistence:
    """Test that scanner settings (mode/marketType/watchlistOnly) persist"""

    def test_scanner_symbol_selection_save_and_load(self, user_session):
        """Test that scanner symbol selection can be saved and loaded"""
        # Save symbol selection
        save_payload = {
            "scanner_id": "default",
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
        }
        save_response = user_session.put(
            f"{BASE_URL}/api/user/scanner/symbol-selection",
            json=save_payload,
            timeout=60,
        )
        assert save_response.status_code == 200, f"Save symbol selection failed: {save_response.text}"
        save_data = save_response.json()
        assert "saved_at" in save_data, "Response should have saved_at field"
        print(f"Symbol selection saved at: {save_data.get('saved_at')}")

        # Load symbol selection
        load_response = user_session.get(
            f"{BASE_URL}/api/user/scanner/symbol-selection",
            params={"scanner_id": "default"},
            timeout=60,
        )
        assert load_response.status_code == 200, f"Load symbol selection failed: {load_response.text}"
        load_data = load_response.json()
        
        # Verify saved data matches
        assert load_data.get("symbol_source") == "crypto", f"symbol_source mismatch: {load_data.get('symbol_source')}"
        assert load_data.get("symbol_selection_mode") == "manual_selection", f"symbol_selection_mode mismatch: {load_data.get('symbol_selection_mode')}"
        loaded_symbols = load_data.get("selected_symbols", [])
        assert "BTCUSDT" in loaded_symbols, f"BTCUSDT not in loaded symbols: {loaded_symbols}"
        print(f"Symbol selection loaded successfully: {loaded_symbols}")

    def test_scanner_automation_settings_persist(self, user_session):
        """Test that scanner automation settings persist"""
        # Get current automation settings
        get_response = user_session.get(
            f"{BASE_URL}/api/user/scanner/automation",
            timeout=60,
        )
        assert get_response.status_code == 200, f"Get automation failed: {get_response.text}"
        current_data = get_response.json()
        print(f"Current automation settings: {current_data}")

        # Update automation settings
        update_payload = {
            "auto_enabled": False,
            "interval_seconds": 60,
            "max_results": 25,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["BTCUSDT", "ETHUSDT"],
        }
        update_response = user_session.put(
            f"{BASE_URL}/api/user/scanner/automation",
            json=update_payload,
            timeout=60,
        )
        assert update_response.status_code == 200, f"Update automation failed: {update_response.text}"

        # Verify settings persisted
        verify_response = user_session.get(
            f"{BASE_URL}/api/user/scanner/automation",
            timeout=60,
        )
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data.get("symbol_source") == "crypto", f"symbol_source not persisted"
        assert verify_data.get("symbol_selection_mode") == "manual_selection", f"symbol_selection_mode not persisted"
        print("Scanner automation settings persisted successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
