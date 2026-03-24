"""
Iteration 136 Tests: Exchange Settings telemetry/action-required + backend health history metrics

Features tested:
1. GET /api/user/exchange-connections new fields: action_required, action_required_message,
   validation_success_24h, validation_fail_24h, validation_success_rate_24h,
   health_last_transition_at, health_history
2. Health loop + manual revalidate producing at least 1 health_history record
3. Regression: bot soft-delete, scanner load, trades time columns
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://identity-control-1.preview.emergentagent.com"


class TestAuthSetup:
    """Authentication fixtures"""

    @pytest.fixture(scope="class")
    def user_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "user1773706589@example.com", "password": "User12345!"},
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip("User authentication failed")
        return response.json().get("access_token")

    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@platform.local", "password": "Admin12345!"},
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip("Admin authentication failed")
        return response.json().get("access_token")


class TestExchangeConnectionsNewFields(TestAuthSetup):
    """Test new telemetry fields in GET /api/user/exchange-connections"""

    def test_exchange_connections_returns_action_required_field(self, user_token):
        """action_required field must be present"""
        response = requests.get(
            f"{BASE_URL}/api/user/exchange-connections",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        if len(data) > 0:
            conn = data[0]
            assert "action_required" in conn, "action_required field missing"
            assert isinstance(conn["action_required"], bool), "action_required should be boolean"
        print(f"PASS: action_required field present in {len(data)} connection(s)")

    def test_exchange_connections_returns_action_required_message_field(self, user_token):
        """action_required_message field must be present"""
        response = requests.get(
            f"{BASE_URL}/api/user/exchange-connections",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            conn = data[0]
            assert "action_required_message" in conn, "action_required_message field missing"
        print("PASS: action_required_message field present")

    def test_exchange_connections_returns_validation_24h_metrics(self, user_token):
        """validation_success_24h, validation_fail_24h, validation_success_rate_24h fields must be present"""
        response = requests.get(
            f"{BASE_URL}/api/user/exchange-connections",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            conn = data[0]
            assert "validation_success_24h" in conn, "validation_success_24h field missing"
            assert "validation_fail_24h" in conn, "validation_fail_24h field missing"
            assert "validation_success_rate_24h" in conn, "validation_success_rate_24h field missing"
            assert isinstance(conn["validation_success_24h"], int), "validation_success_24h should be int"
            assert isinstance(conn["validation_fail_24h"], int), "validation_fail_24h should be int"
            # validation_success_rate_24h can be None or float
            print(f"PASS: 24h validation metrics - success={conn['validation_success_24h']}, fail={conn['validation_fail_24h']}, rate={conn['validation_success_rate_24h']}")

    def test_exchange_connections_returns_health_last_transition_at(self, user_token):
        """health_last_transition_at field must be present"""
        response = requests.get(
            f"{BASE_URL}/api/user/exchange-connections",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            conn = data[0]
            assert "health_last_transition_at" in conn, "health_last_transition_at field missing"
            print(f"PASS: health_last_transition_at = {conn['health_last_transition_at']}")

    def test_exchange_connections_returns_health_history(self, user_token):
        """health_history field must be present and be a list"""
        response = requests.get(
            f"{BASE_URL}/api/user/exchange-connections",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            conn = data[0]
            assert "health_history" in conn, "health_history field missing"
            assert isinstance(conn["health_history"], list), "health_history should be a list"
            print(f"PASS: health_history has {len(conn['health_history'])} record(s)")


class TestHealthHistoryAccumulation(TestAuthSetup):
    """Test health loop + manual revalidate producing at least 1 health_history record"""

    def test_revalidate_produces_health_history(self, user_token):
        """After revalidate, health_history should have at least 1 record"""
        # First get connections to find a connection ID
        response = requests.get(
            f"{BASE_URL}/api/user/exchange-connections",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        if len(data) == 0:
            pytest.skip("No connection profiles to revalidate")

        conn_id = data[0]["id"]

        # Revalidate
        revalidate_response = requests.post(
            f"{BASE_URL}/api/user/exchange-connections/{conn_id}/revalidate",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15,
        )
        assert revalidate_response.status_code == 200
        revalidate_data = revalidate_response.json()

        # Check health_history has at least 1 record
        assert "health_history" in revalidate_data, "health_history field missing in revalidate response"
        assert isinstance(revalidate_data["health_history"], list), "health_history should be a list"
        assert len(revalidate_data["health_history"]) >= 1, "health_history should have at least 1 record"

        # Verify record structure
        record = revalidate_data["health_history"][0]
        assert "at" in record, "health_history record missing 'at' field"
        assert "health" in record, "health_history record missing 'health' field"
        assert "reason" in record, "health_history record missing 'reason' field"
        assert "source" in record, "health_history record missing 'source' field"
        assert "validation_success" in record, "health_history record missing 'validation_success' field"
        assert "can_trade" in record, "health_history record missing 'can_trade' field"

        print(f"PASS: Revalidate returned health_history with {len(revalidate_data['health_history'])} record(s)")
        print(f"  Latest record: health={record['health']}, reason={record['reason']}, source={record['source']}")


class TestBotSoftDeleteRegression(TestAuthSetup):
    """Regression test: bot soft-delete functionality"""

    def test_bot_create_and_soft_delete(self, user_token):
        """Bot creation and soft-delete should work correctly"""
        # Create a bot
        create_response = requests.post(
            f"{BASE_URL}/api/bot-profiles",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "name": "TEST_iter136_regression_bot",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["BTCUSDT"],
                "strategy_type": "trend_following",
                "timeframe": "15m",
                "trend_timeframe": "1h",
                "leverage": 3,
                "is_enabled": True,
            },
            timeout=15,
        )
        assert create_response.status_code in [200, 201], f"Bot creation failed: {create_response.text}"
        bot_data = create_response.json()
        bot_id = bot_data["id"]
        print(f"PASS: Created bot {bot_id}")

        # Delete the bot (soft delete)
        delete_response = requests.delete(
            f"{BASE_URL}/api/bot-profiles/{bot_id}",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15,
        )
        assert delete_response.status_code in [200, 204], f"Bot delete failed: {delete_response.text}"
        print(f"PASS: Soft-deleted bot {bot_id}")

        # Verify bot is soft deleted (not in active list or has is_deleted flag)
        list_response = requests.get(
            f"{BASE_URL}/api/bot-profiles",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15,
        )
        assert list_response.status_code == 200
        bots = list_response.json()
        # The soft-deleted bot should not appear in the list
        active_bot_ids = [b["id"] for b in bots if not b.get("is_deleted", False)]
        assert bot_id not in active_bot_ids, "Soft-deleted bot should not appear in active bot list"
        print("PASS: Soft-deleted bot not in active list")


class TestScannerLoadRegression(TestAuthSetup):
    """Regression test: scanner page load functionality"""

    def test_scanner_overview_loads(self, user_token):
        """Scanner overview endpoint should load"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15,
        )
        assert response.status_code == 200, f"Scanner overview failed: {response.text}"
        data = response.json()
        assert "mode" in data or "latest_run_id" in data, "Scanner overview missing expected fields"
        print("PASS: Scanner overview loads successfully")

    def test_scanner_results_loads(self, user_token):
        """Scanner results endpoint should load"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 20},
            timeout=15,
        )
        assert response.status_code == 200, f"Scanner results failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Scanner results should be a list"
        print(f"PASS: Scanner results loads successfully ({len(data)} results)")

    def test_scanner_automation_loads(self, user_token):
        """Scanner automation endpoint should load"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/automation",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15,
        )
        assert response.status_code == 200, f"Scanner automation failed: {response.text}"
        print("PASS: Scanner automation loads successfully")


class TestTradesTimeColumnsRegression(TestAuthSetup):
    """Regression test: trades time columns (opened_at, closed_at)"""

    def test_trades_returns_time_columns(self, user_token):
        """Trades endpoint should return opened_at and closed_at columns"""
        response = requests.get(
            f"{BASE_URL}/api/user/trades",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 20},
            timeout=15,
        )
        assert response.status_code == 200, f"Trades endpoint failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Trades should be a list"

        # If there are trades, verify time columns exist
        if len(data) > 0:
            trade = data[0]
            # Check schema has time column keys (values can be null)
            assert "opened_at" in trade, "opened_at column missing from trade"
            assert "closed_at" in trade, "closed_at column missing from trade"
            print(f"PASS: Trades has time columns - opened_at={trade.get('opened_at')}, closed_at={trade.get('closed_at')}")
        else:
            print("PASS: Trades endpoint works, no trades to verify columns (0 trades)")


class TestHealthLoopBackendRunning(TestAuthSetup):
    """Test that health loop is running on backend without issues"""

    def test_health_endpoint_available(self, user_token):
        """Health endpoint should be available"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok", f"Health check failed: {data}"
        print("PASS: Backend health check OK")

    def test_exchange_connections_liveness_fields_stable(self, user_token):
        """Exchange connections should return stable liveness fields without errors"""
        response = requests.get(
            f"{BASE_URL}/api/user/exchange-connections",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            conn = data[0]
            # Check that liveness fields exist and have proper types
            assert "is_reconnecting" in conn, "is_reconnecting field missing"
            assert "next_retry_in_seconds" in conn, "next_retry_in_seconds field missing"
            assert "retry_backoff_seconds" in conn, "retry_backoff_seconds field missing"
            assert isinstance(conn["is_reconnecting"], bool), "is_reconnecting should be boolean"
            print(f"PASS: Liveness fields stable - is_reconnecting={conn['is_reconnecting']}, next_retry_in={conn['next_retry_in_seconds']}")


class TestSchemaFieldsPresence:
    """Test that schemas.py UserExchangeConnectionResponse has all new fields"""

    def test_schema_has_action_required_fields(self):
        """Schema should have action_required and action_required_message"""
        try:
            from schemas import UserExchangeConnectionResponse
        except ImportError:
            import sys
            sys.path.insert(0, "/app/backend")
            from schemas import UserExchangeConnectionResponse
        
        fields = UserExchangeConnectionResponse.model_fields
        assert "action_required" in fields, "action_required not in schema"
        assert "action_required_message" in fields, "action_required_message not in schema"
        print("PASS: Schema has action_required fields")

    def test_schema_has_24h_validation_fields(self):
        """Schema should have validation_success_24h, validation_fail_24h, validation_success_rate_24h"""
        try:
            from schemas import UserExchangeConnectionResponse
        except ImportError:
            import sys
            sys.path.insert(0, "/app/backend")
            from schemas import UserExchangeConnectionResponse
        
        fields = UserExchangeConnectionResponse.model_fields
        assert "validation_success_24h" in fields, "validation_success_24h not in schema"
        assert "validation_fail_24h" in fields, "validation_fail_24h not in schema"
        assert "validation_success_rate_24h" in fields, "validation_success_rate_24h not in schema"
        print("PASS: Schema has 24h validation metric fields")

    def test_schema_has_health_history_fields(self):
        """Schema should have health_last_transition_at and health_history"""
        try:
            from schemas import UserExchangeConnectionResponse
        except ImportError:
            import sys
            sys.path.insert(0, "/app/backend")
            from schemas import UserExchangeConnectionResponse
        
        fields = UserExchangeConnectionResponse.model_fields
        assert "health_last_transition_at" in fields, "health_last_transition_at not in schema"
        assert "health_history" in fields, "health_history not in schema"
        print("PASS: Schema has health_history fields")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
