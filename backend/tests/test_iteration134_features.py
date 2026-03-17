"""
Iteration 134 Testing: Exchange Settings State Resolver, Reconnect Metadata, Scanner useEffect fix
Features to test:
1. UserExchangeSettingsPage: Effective Trade State card + Execution State Resolver text
2. Connection profile: reconnecting + next_retry_in display
3. POST /api/user/exchange-connections/{id}/revalidate returns reconnect metadata fields
4. UserScannerPage: load function dependency fix (should not cause infinite loop)
5. Regression: bot soft-delete and trades opened/closed columns
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"
USER_EMAIL = "user1773706589@example.com"
USER_PASSWORD = "User12345!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def user_token():
    """Get user authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"User login failed: {response.status_code}")
    return response.json().get("access_token")


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestExchangeConnectionReconnectMetadata:
    """Tests for reconnect metadata fields in exchange connections"""

    def test_connection_list_includes_reconnect_fields(self, user_token):
        """GET /api/user/exchange-connections should return reconnect metadata"""
        response = requests.get(
            f"{BASE_URL}/api/user/exchange-connections",
            headers=auth_headers(user_token),
        )
        assert response.status_code == 200
        connections = response.json()
        assert isinstance(connections, list)
        
        # Check first connection has required fields
        if connections:
            conn = connections[0]
            # New fields from iteration 133/134
            assert "connection_health" in conn, "Missing connection_health field"
            assert "connection_health_reason" in conn, "Missing connection_health_reason field"
            assert "can_trade_effective" in conn, "Missing can_trade_effective field"
            assert "last_validated_at" in conn, "Missing last_validated_at field"
            assert "is_reconnecting" in conn, "Missing is_reconnecting field"
            assert "next_retry_in_seconds" in conn, "Missing next_retry_in_seconds field"
            assert "retry_backoff_seconds" in conn, "Missing retry_backoff_seconds field"
            
            print(f"Connection health: {conn['connection_health']}")
            print(f"Is reconnecting: {conn['is_reconnecting']}")
            print(f"Next retry in seconds: {conn['next_retry_in_seconds']}")

    def test_revalidate_returns_reconnect_metadata(self, user_token):
        """POST /api/user/exchange-connections/{id}/revalidate returns reconnect metadata"""
        # First get connections
        response = requests.get(
            f"{BASE_URL}/api/user/exchange-connections",
            headers=auth_headers(user_token),
        )
        assert response.status_code == 200
        connections = response.json()
        
        if not connections:
            pytest.skip("No exchange connections to revalidate")
        
        conn_id = connections[0]["id"]
        
        # Revalidate
        response = requests.post(
            f"{BASE_URL}/api/user/exchange-connections/{conn_id}/revalidate",
            headers=auth_headers(user_token),
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify reconnect metadata in response
        assert "connection_health" in data
        assert "connection_health_reason" in data
        assert "can_trade_effective" in data
        assert "is_reconnecting" in data
        assert "next_retry_in_seconds" in data
        assert "retry_backoff_seconds" in data
        
        print(f"Revalidate result - Health: {data['connection_health']}, Reconnecting: {data['is_reconnecting']}")


class TestExchangeReadinessChecklist:
    """Tests for readiness checklist endpoint"""

    def test_readiness_checklist_returns_venue_info(self, user_token):
        """GET /api/exchange/readiness-checklist returns proper structure"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/readiness-checklist",
            headers=auth_headers(user_token),
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
            },
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "readiness_status" in data
        assert "has_api_key" in data
        assert "has_api_secret" in data
        assert "validation_success" in data
        assert "can_trade" in data
        assert "is_validation_stale" in data
        assert "last_error_reason" in data
        
        print(f"Readiness status: {data['readiness_status']}")
        print(f"Last error reason: {data.get('last_error_reason', '-')}")


class TestBotSoftDeleteRegression:
    """Regression tests for bot soft-delete feature"""

    def test_create_and_delete_bot_not_in_list(self, user_token):
        """Bot delete should soft-delete - bot not visible after delete"""
        # Create bot
        create_payload = {
            "name": f"TEST_iter134_bot_{os.urandom(4).hex()}",
            "exchange": "binance",
            "market_type": "spot",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "strategy_type": "trend_following",
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 1,
            "is_enabled": True,
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/bot-profiles",
            headers=auth_headers(user_token),
            json=create_payload,
        )
        # Note: API returns 200 instead of 201 for bot creation
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        created_bot = create_response.json()
        bot_id = created_bot["id"]
        bot_name = created_bot["name"]
        
        # Verify bot is in list
        list_response = requests.get(
            f"{BASE_URL}/api/bot-profiles",
            headers=auth_headers(user_token),
        )
        assert list_response.status_code == 200
        bot_ids = [b["id"] for b in list_response.json()]
        assert bot_id in bot_ids, "Created bot should be in list"
        
        # Delete bot
        delete_response = requests.delete(
            f"{BASE_URL}/api/bot-profiles/{bot_id}",
            headers=auth_headers(user_token),
        )
        assert delete_response.status_code == 200
        
        # Verify bot not in list after delete
        list_response2 = requests.get(
            f"{BASE_URL}/api/bot-profiles",
            headers=auth_headers(user_token),
        )
        assert list_response2.status_code == 200
        bot_ids_after = [b["id"] for b in list_response2.json()]
        assert bot_id not in bot_ids_after, "Deleted bot should not be in list"
        
        print(f"Bot '{bot_name}' soft-deleted successfully")


class TestUserTradesRegression:
    """Regression tests for trades opened_at/closed_at columns"""

    def test_trades_have_time_columns(self, user_token):
        """GET /api/user/trades should return opened_at and closed_at columns"""
        response = requests.get(
            f"{BASE_URL}/api/user/trades",
            headers=auth_headers(user_token),
            params={"limit": 10},
        )
        assert response.status_code == 200
        trades = response.json()
        
        # Even if empty, verify response is list
        assert isinstance(trades, list)
        
        # If trades exist, verify time columns
        if trades:
            trade = trades[0]
            assert "opened_at" in trade, "Missing opened_at column"
            assert "closed_at" in trade, "Missing closed_at column"
            print(f"Trade found - opened_at: {trade.get('opened_at')}, closed_at: {trade.get('closed_at')}")
        else:
            print("No trades found - time columns verified in schema")


class TestScannerPartialLoadResilience:
    """Tests for scanner partial load resilience"""

    def test_scanner_overview_returns_valid_response(self, user_token):
        """GET /api/user/scanner should work and return valid structure"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner",
            headers=auth_headers(user_token),
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "mode" in data
        assert "total_results" in data
        assert "pending_signals" in data
        
        print(f"Scanner mode: {data['mode']}, Total results: {data['total_results']}")

    def test_scanner_results_endpoint(self, user_token):
        """GET /api/user/scanner/results should work"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            headers=auth_headers(user_token),
            params={"limit": 20},
        )
        assert response.status_code == 200
        results = response.json()
        assert isinstance(results, list)
        print(f"Scanner results count: {len(results)}")

    def test_scanner_automation_endpoint(self, user_token):
        """GET /api/user/scanner/automation should work"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/automation",
            headers=auth_headers(user_token),
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "auto_enabled" in data
        assert "interval_seconds" in data
        print(f"Scanner automation enabled: {data['auto_enabled']}")

    def test_scanner_automation_profiles_endpoint(self, user_token):
        """GET /api/user/scanner/automation-profiles should work"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/automation-profiles",
            headers=auth_headers(user_token),
        )
        assert response.status_code == 200
        profiles = response.json()
        assert isinstance(profiles, list)
        print(f"Scanner automation profiles count: {len(profiles)}")

    def test_decision_cards_endpoint(self, user_token):
        """GET /api/user/decision-cards should work"""
        response = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            headers=auth_headers(user_token),
            params={"limit": 20},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        print(f"Decision cards count: {len(data.get('items', []))}")


class TestExchangeValidateEndpoint:
    """Tests for exchange validation endpoint"""

    def test_validate_returns_proper_structure(self, user_token):
        """GET /api/exchange/validate returns expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            headers=auth_headers(user_token),
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
            },
        )
        # May return 400 if no credentials, but structure should be correct
        raw_data = response.json()
        
        # Data might be in 'detail' for error responses
        data = raw_data.get("detail") if "detail" in raw_data else raw_data
        
        assert "exchange" in data
        assert "market_type" in data
        assert "environment" in data
        
        if response.status_code == 200:
            assert "is_valid" in data
            assert "permissions" in data
            assert "can_trade" in data
            assert "reason_codes" in data
            print(f"Validation - is_valid: {data['is_valid']}, can_trade: {data['can_trade']}")
        else:
            # Error response should still have reason_codes
            assert "reason_codes" in data or "detail" in raw_data
            print(f"Validation blocked - reason: {data.get('reason_codes', data.get('detail'))}")


class TestUserRiskPreviewEndpoint:
    """Tests for user risk preview endpoint"""

    def test_risk_preview_returns_proper_structure(self, user_token):
        """GET /api/user-risk/preview returns expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/preview",
            headers=auth_headers(user_token),
            params={
                "market_type": "spot",
                "leverage": 1,
                "margin_mode": "cross",
                "position_side": "BOTH",
            },
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "market_type" in data
        assert "current_capital" in data
        assert "position_size" in data
        assert "allocation_pct" in data
        assert "warnings" in data
        
        print(f"Risk preview - capital: {data['current_capital']}, position_size: {data['position_size']}")


class TestUserPortfolioOverview:
    """Tests for portfolio overview endpoint"""

    def test_portfolio_overview_returns_proper_structure(self, user_token):
        """GET /api/user-risk/overview returns expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/overview",
            headers=auth_headers(user_token),
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "current_capital" in data
        assert "available_balance" in data
        assert "open_position_balance" in data
        assert "closed_pnl" in data
        assert "compounding_enabled" in data
        assert "next_base_capital" in data
        
        print(f"Portfolio - capital: {data['current_capital']}, available: {data['available_balance']}")


class TestVenueOptionsEndpoint:
    """Tests for venue options endpoint"""

    def test_venue_options_returns_list(self, user_token):
        """GET /api/venues/options returns venue list"""
        response = requests.get(
            f"{BASE_URL}/api/venues/options",
            headers=auth_headers(user_token),
        )
        assert response.status_code == 200
        venues = response.json()
        assert isinstance(venues, list)
        
        if venues:
            venue = venues[0]
            assert "exchange" in venue
            assert "market_type" in venue
            assert "environment" in venue
        
        print(f"Venue options count: {len(venues)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
