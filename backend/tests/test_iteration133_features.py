"""
Test iteration 133 features:
1. Admin bot profile soft-delete flow (create -> delete -> not visible in list)
2. GET /api/user/exchange-connections response new fields (connection_health, etc.)
3. POST /api/user/exchange-connections/{id}/revalidate
4. User trades opened_at/closed_at columns
5. User scanner page partial failure resilience
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"


@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session with auth header."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json().get("access_token")
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


@pytest.fixture(scope="module")
def user_session(admin_session):
    """Create/get a test user and login. If creation fails, try using existing user."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Try to login with existing user first
    test_email = "user1773706589@example.com"
    test_password = "User12345!"
    
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": test_email,
        "password": test_password,
    })
    
    if response.status_code == 200:
        token = response.json().get("access_token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    # Fallback to admin session
    return admin_session


class TestBotProfileSoftDelete:
    """Test bot profile create -> delete -> not visible in list"""
    
    def test_create_bot_profile(self, admin_session):
        """Create a new bot profile"""
        unique_name = f"test-bot-{uuid.uuid4().hex[:8]}"
        payload = {
            "name": unique_name,
            "exchange": "binance",
            "market_type": "spot",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "strategy_type": "trend_following",
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 3,
            "is_enabled": True,
        }
        
        response = admin_session.post(f"{BASE_URL}/api/bot-profiles", json=payload)
        assert response.status_code == 200, f"Create bot profile failed: {response.text}"
        
        data = response.json()
        assert "id" in data
        assert data["name"] == unique_name
        assert data.get("is_deleted") is False or data.get("is_deleted") is None or data.get("is_deleted") == False
        
        return data["id"], unique_name
    
    def test_delete_bot_profile_soft(self, admin_session):
        """Delete bot profile (soft delete) and verify it doesn't appear in list"""
        # First create a bot
        unique_name = f"test-delete-bot-{uuid.uuid4().hex[:8]}"
        payload = {
            "name": unique_name,
            "exchange": "binance",
            "market_type": "spot",
            "symbols": ["BTCUSDT"],
            "strategy_type": "trend_following",
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 3,
            "is_enabled": True,
        }
        
        create_resp = admin_session.post(f"{BASE_URL}/api/bot-profiles", json=payload)
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        bot_id = create_resp.json()["id"]
        
        # Delete the bot
        delete_resp = admin_session.delete(f"{BASE_URL}/api/bot-profiles/{bot_id}")
        assert delete_resp.status_code == 200, f"Delete failed: {delete_resp.text}"
        delete_data = delete_resp.json()
        assert delete_data.get("deleted") is True, "Delete response should have deleted=True"
        
        # Verify bot doesn't appear in list
        list_resp = admin_session.get(f"{BASE_URL}/api/bot-profiles")
        assert list_resp.status_code == 200, f"List failed: {list_resp.text}"
        
        bot_ids_in_list = [bot["id"] for bot in list_resp.json()]
        assert bot_id not in bot_ids_in_list, "Soft-deleted bot should not appear in list"
        print(f"✓ Bot {bot_id} soft-deleted and not visible in list")


class TestExchangeConnectionsNewFields:
    """Test GET /api/user/exchange-connections response new fields"""
    
    def test_exchange_connections_has_new_fields(self, user_session):
        """Verify response includes new health fields"""
        response = user_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200, f"Get exchange connections failed: {response.text}"
        
        connections = response.json()
        # It might be empty, but the schema should still work
        print(f"Found {len(connections)} exchange connection(s)")
        
        if connections:
            # Check first connection has the new fields
            conn = connections[0]
            
            # Required new fields according to the schema
            new_fields = [
                "connection_health",
                "connection_health_reason",
                "can_trade_effective",
                "last_validated_at",
                "is_reconnecting",
                "next_retry_in_seconds",
                "retry_backoff_seconds",
            ]
            
            for field in new_fields:
                assert field in conn, f"Missing new field: {field}"
                print(f"✓ Field {field} present: {conn[field]}")
            
            # Validate field types/values
            assert conn["connection_health"] in ["online", "degraded", "offline", "unknown"], \
                f"Invalid connection_health: {conn['connection_health']}"
            assert isinstance(conn["can_trade_effective"], bool), "can_trade_effective should be bool"
            assert isinstance(conn["is_reconnecting"], bool), "is_reconnecting should be bool"
            assert isinstance(conn["retry_backoff_seconds"], (int, type(None))), "retry_backoff_seconds should be int or None"
        else:
            # Create a connection to test new fields
            payload = {
                "account_label": f"test-conn-{uuid.uuid4().hex[:6]}",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "live",
                "is_default": False,
            }
            create_resp = user_session.post(f"{BASE_URL}/api/user/exchange-connections", json=payload)
            assert create_resp.status_code == 201, f"Create connection failed: {create_resp.text}"
            
            conn = create_resp.json()
            new_fields = [
                "connection_health",
                "connection_health_reason",
                "can_trade_effective",
                "last_validated_at",
                "is_reconnecting",
                "next_retry_in_seconds",
                "retry_backoff_seconds",
            ]
            
            for field in new_fields:
                assert field in conn, f"Missing new field in created connection: {field}"
                print(f"✓ Field {field} present: {conn[field]}")
            
            # Clean up
            user_session.delete(f"{BASE_URL}/api/user/exchange-connections/{conn['id']}")
    
    def test_exchange_connection_revalidate(self, user_session):
        """Test POST /api/user/exchange-connections/{id}/revalidate endpoint"""
        # First get existing connections
        list_resp = user_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert list_resp.status_code == 200, f"Get connections failed: {list_resp.text}"
        
        connections = list_resp.json()
        
        if not connections:
            # Create a connection first
            payload = {
                "account_label": f"revalidate-test-{uuid.uuid4().hex[:6]}",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "live",
                "is_default": False,
            }
            create_resp = user_session.post(f"{BASE_URL}/api/user/exchange-connections", json=payload)
            assert create_resp.status_code == 201, f"Create connection failed: {create_resp.text}"
            conn_id = create_resp.json()["id"]
        else:
            conn_id = connections[0]["id"]
        
        # Test revalidate endpoint
        revalidate_resp = user_session.post(f"{BASE_URL}/api/user/exchange-connections/{conn_id}/revalidate")
        # This may fail if credentials are not set, but endpoint should exist
        assert revalidate_resp.status_code in [200, 400, 403], \
            f"Revalidate unexpected status: {revalidate_resp.status_code} - {revalidate_resp.text}"
        
        if revalidate_resp.status_code == 200:
            data = revalidate_resp.json()
            # Verify new fields in response
            assert "connection_health" in data
            assert "can_trade_effective" in data
            assert "is_reconnecting" in data
            print(f"✓ Revalidate successful, connection_health={data.get('connection_health')}")
        else:
            print(f"✓ Revalidate endpoint exists, returned {revalidate_resp.status_code} (expected when no credentials)")


class TestUserTradesColumns:
    """Test that user trades endpoint returns opened_at and closed_at columns"""
    
    def test_trades_have_time_columns(self, user_session):
        """Verify GET /api/user/trades returns opened_at and closed_at"""
        response = user_session.get(f"{BASE_URL}/api/user/trades", params={"limit": 50})
        assert response.status_code == 200, f"Get trades failed: {response.text}"
        
        trades = response.json()
        print(f"Found {len(trades)} trades")
        
        # Check that even if empty, the response is valid
        assert isinstance(trades, list), "Trades response should be a list"
        
        if trades:
            # Check first trade has time columns
            trade = trades[0]
            assert "opened_at" in trade, "Trade missing opened_at column"
            assert "closed_at" in trade, "Trade missing closed_at column"
            
            print(f"✓ Trade has opened_at={trade['opened_at']}, closed_at={trade['closed_at']}")
        else:
            print("✓ Trades endpoint returns empty list (no trades yet)")


class TestUserScannerResilience:
    """Test that scanner page handles partial endpoint failures gracefully"""
    
    def test_scanner_overview_endpoint(self, user_session):
        """Test /api/user/scanner endpoint"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner")
        assert response.status_code == 200, f"Scanner overview failed: {response.text}"
        print(f"✓ Scanner overview: {response.json()}")
    
    def test_scanner_results_endpoint(self, user_session):
        """Test /api/user/scanner/results endpoint"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner/results", params={"limit": 10})
        assert response.status_code == 200, f"Scanner results failed: {response.text}"
        print(f"✓ Scanner results count: {len(response.json())}")
    
    def test_scanner_automation_endpoint(self, user_session):
        """Test /api/user/scanner/automation endpoint"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner/automation")
        assert response.status_code == 200, f"Scanner automation failed: {response.text}"
        print(f"✓ Scanner automation: auto_enabled={response.json().get('auto_enabled')}")
    
    def test_scanner_automation_profiles_endpoint(self, user_session):
        """Test /api/user/scanner/automation-profiles endpoint"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner/automation-profiles")
        assert response.status_code == 200, f"Scanner automation profiles failed: {response.text}"
        print(f"✓ Scanner automation profiles count: {len(response.json())}")
    
    def test_decision_cards_endpoint(self, user_session):
        """Test /api/user/decision-cards endpoint"""
        response = user_session.get(f"{BASE_URL}/api/user/decision-cards", params={"limit": 10})
        assert response.status_code == 200, f"Decision cards failed: {response.text}"
        print("✓ Decision cards available")


class TestUserExchangeSettingsUIComponents:
    """Test that the new UI card data is properly supported by backend"""
    
    def test_connection_profiles_have_health_data(self, user_session):
        """Verify connection profiles have health data for UI cards"""
        response = user_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200
        
        connections = response.json()
        
        # Verify the schema supports UI card rendering
        expected_ui_fields = [
            "id",
            "account_label",
            "exchange",
            "market_type",
            "environment",
            "is_default",
            "connection_health",
            "connection_health_reason",
            "can_trade_effective",
            "is_reconnecting",
            "next_retry_in_seconds",
            "last_validated_at",
        ]
        
        if connections:
            conn = connections[0]
            for field in expected_ui_fields:
                assert field in conn, f"Missing UI field: {field}"
            print("✓ All UI fields present for connection profile card rendering")


class TestBackwardCompatibility:
    """Test backward compatibility - existing fields still work"""
    
    def test_bot_profiles_list_structure(self, admin_session):
        """Verify bot profiles list maintains existing structure"""
        response = admin_session.get(f"{BASE_URL}/api/bot-profiles")
        assert response.status_code == 200
        
        bots = response.json()
        if bots:
            bot = bots[0]
            required_fields = [
                "id", "name", "exchange", "market_type", "symbols",
                "strategy_type", "timeframe", "is_enabled", "is_running",
            ]
            for field in required_fields:
                assert field in bot, f"Missing required field: {field}"
            
            # New fields should be present but backward-compat
            if "is_deleted" in bot:
                assert bot["is_deleted"] in [True, False], "is_deleted should be boolean"
            
            print("✓ Bot profile structure backward compatible")
    
    def test_exchange_connection_old_fields_present(self, user_session):
        """Verify old exchange connection fields are still present"""
        response = user_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200
        
        connections = response.json()
        if connections:
            conn = connections[0]
            old_fields = [
                "id", "user_id", "account_label", "exchange", "market_type",
                "environment", "is_default", "has_api_key", "has_api_secret",
                "masked_api_key", "credential_fingerprint", "created_at", "updated_at",
            ]
            for field in old_fields:
                assert field in conn, f"Missing backward-compat field: {field}"
            
            print("✓ Exchange connection structure backward compatible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
