"""
Test suite for Admin Market Data Keys API endpoints
Tests the exchange+market selection feature for market data key management
Supports: binance, bybit, okx exchanges with spot/futures markets
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Admin credentials from review request
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"


class TestAdminMarketDataKeys:
    """Tests for /api/venues/admin/market-data-keys endpoints with exchange+market selection"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with admin authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Authenticate as admin
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if login_response.status_code == 200:
            token = login_response.json().get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
            self.authenticated = True
        else:
            self.authenticated = False
            print(f"Admin login failed: {login_response.status_code} - {login_response.text}")

    def test_admin_login_works(self):
        """Test that admin login works with provided credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        print(f"Admin login response: {response.status_code}")
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in login response"
        assert "user" in data, "No user in login response"
        assert data["user"]["email"] == ADMIN_EMAIL
        print(f"Admin login successful for {ADMIN_EMAIL}")

    def test_get_market_data_keys_returns_200_with_exchange_market_fields(self):
        """GET /api/venues/admin/market-data-keys returns 200 with provider, exchange, market fields"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        response = self.session.get(f"{BASE_URL}/api/venues/admin/market-data-keys")
        print(f"GET market-data-keys response: {response.status_code}")
        print(f"Response body: {response.text[:800]}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify expected summary fields
        assert "active_key" in data, "Missing 'active_key' field"
        assert "items" in data, "Missing 'items' field"
        assert "users_with_live_distribution" in data, "Missing 'users_with_live_distribution' field"
        assert "active_user_count" in data, "Missing 'active_user_count' field"
        
        # Verify types
        assert isinstance(data["active_key"], bool), "active_key should be boolean"
        assert isinstance(data["items"], list), "items should be a list"
        
        # If there are items, verify they contain provider, exchange, market fields
        if data["items"]:
            first_item = data["items"][0]
            assert "provider" in first_item, "Item should have 'provider' field"
            assert "exchange" in first_item, "Item should have 'exchange' field"
            assert "market" in first_item, "Item should have 'market' field"
            print(f"First item: provider={first_item['provider']}, exchange={first_item['exchange']}, market={first_item['market']}")
        
        print(f"Market data keys summary: active_key={data['active_key']}, items_count={len(data['items'])}")

    def test_post_bybit_spot_demo_key_returns_200(self):
        """POST /api/venues/admin/market-data-keys with bybit/spot demo key returns 200 (validation skipped for non-binance)"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        # Bybit spot demo key - validation is skipped for non-binance exchanges
        bybit_payload = {
            "exchange": "bybit",
            "market": "spot",
            "api_key": "DEMO_BYBIT_API_KEY_12345",
            "api_secret": "DEMO_BYBIT_API_SECRET_67890",
            "base_url_override": "",
            "ip_route_note": "",
            "note": "test_bybit_spot_demo"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/market-data-keys",
            json=bybit_payload
        )
        print(f"POST bybit/spot demo key response: {response.status_code}")
        print(f"Response body: {response.text[:800]}")
        
        # Should return 200 because validation is skipped for non-binance exchanges
        assert response.status_code == 200, f"Expected 200 for bybit/spot demo key, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "active_key" in data, "Response should have 'active_key' field"
        assert "items" in data, "Response should have 'items' field"
        
        # Verify the bybit/spot key appears in the items list
        bybit_items = [item for item in data["items"] if item.get("exchange") == "bybit" and item.get("market") == "spot"]
        assert len(bybit_items) > 0, "Bybit/spot key should appear in items list"
        
        bybit_item = bybit_items[0]
        assert bybit_item["exchange"] == "bybit", "Exchange should be 'bybit'"
        assert bybit_item["market"] == "spot", "Market should be 'spot'"
        assert bybit_item["status"] == "active", "Status should be 'active'"
        print(f"Bybit/spot key saved successfully: provider={bybit_item['provider']}, status={bybit_item['status']}")

    def test_post_invalid_binance_futures_key_returns_400(self):
        """POST /api/venues/admin/market-data-keys with invalid binance/futures key returns controlled 400"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        # Invalid Binance futures key - should fail validation
        invalid_payload = {
            "exchange": "binance",
            "market": "futures",
            "api_key": "INVALID_BINANCE_FUTURES_KEY_12345",
            "api_secret": "INVALID_BINANCE_FUTURES_SECRET_67890",
            "base_url_override": "",
            "ip_route_note": "",
            "note": "test_invalid_binance_futures"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/market-data-keys",
            json=invalid_payload
        )
        print(f"POST invalid binance/futures key response: {response.status_code}")
        print(f"Response body: {response.text[:500]}")
        
        # Should return 400 (controlled error), NOT 500 (server error)
        assert response.status_code == 400, f"Expected 400 for invalid binance key, got {response.status_code}: {response.text}"
        
        # Verify error response has detail
        data = response.json()
        assert "detail" in data, "Error response should have 'detail' field"
        print(f"Error detail: {data.get('detail')}")

    def test_post_invalid_binance_spot_key_returns_400(self):
        """POST /api/venues/admin/market-data-keys with invalid binance/spot key returns controlled 400"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        # Invalid Binance spot key - should fail validation
        invalid_payload = {
            "exchange": "binance",
            "market": "spot",
            "api_key": "INVALID_BINANCE_SPOT_KEY_12345",
            "api_secret": "INVALID_BINANCE_SPOT_SECRET_67890",
            "base_url_override": "",
            "ip_route_note": "",
            "note": "test_invalid_binance_spot"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/market-data-keys",
            json=invalid_payload
        )
        print(f"POST invalid binance/spot key response: {response.status_code}")
        print(f"Response body: {response.text[:500]}")
        
        # Should return 400 (controlled error), NOT 500 (server error)
        assert response.status_code == 400, f"Expected 400 for invalid binance key, got {response.status_code}: {response.text}"
        
        # Verify error response has detail
        data = response.json()
        assert "detail" in data, "Error response should have 'detail' field"
        print(f"Error detail: {data.get('detail')}")

    def test_post_market_data_keys_missing_exchange_returns_422(self):
        """POST /api/venues/admin/market-data-keys with missing exchange field returns 422"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        # Missing exchange field
        incomplete_payload = {
            "market": "spot",
            "api_key": "SOME_API_KEY",
            "api_secret": "SOME_API_SECRET"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/market-data-keys",
            json=incomplete_payload
        )
        print(f"POST market-data-keys with missing exchange response: {response.status_code}")
        
        # Should return 422 for validation error
        assert response.status_code == 422, f"Expected 422 for missing exchange, got {response.status_code}: {response.text}"

    def test_post_market_data_keys_missing_market_returns_422(self):
        """POST /api/venues/admin/market-data-keys with missing market field returns 422"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        # Missing market field
        incomplete_payload = {
            "exchange": "binance",
            "api_key": "SOME_API_KEY",
            "api_secret": "SOME_API_SECRET"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/market-data-keys",
            json=incomplete_payload
        )
        print(f"POST market-data-keys with missing market response: {response.status_code}")
        
        # Should return 422 for validation error
        assert response.status_code == 422, f"Expected 422 for missing market, got {response.status_code}: {response.text}"

    def test_post_okx_futures_demo_key_returns_200(self):
        """POST /api/venues/admin/market-data-keys with okx/futures demo key returns 200 (validation skipped for non-binance)"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        # OKX futures demo key - validation is skipped for non-binance exchanges
        okx_payload = {
            "exchange": "okx",
            "market": "futures",
            "api_key": "DEMO_OKX_API_KEY_12345",
            "api_secret": "DEMO_OKX_API_SECRET_67890",
            "base_url_override": "",
            "ip_route_note": "",
            "note": "test_okx_futures_demo"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/market-data-keys",
            json=okx_payload
        )
        print(f"POST okx/futures demo key response: {response.status_code}")
        print(f"Response body: {response.text[:800]}")
        
        # Should return 200 because validation is skipped for non-binance exchanges
        assert response.status_code == 200, f"Expected 200 for okx/futures demo key, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "active_key" in data, "Response should have 'active_key' field"
        assert "items" in data, "Response should have 'items' field"
        
        # Verify the okx/futures key appears in the items list
        okx_items = [item for item in data["items"] if item.get("exchange") == "okx" and item.get("market") == "futures"]
        assert len(okx_items) > 0, "OKX/futures key should appear in items list"
        
        okx_item = okx_items[0]
        assert okx_item["exchange"] == "okx", "Exchange should be 'okx'"
        assert okx_item["market"] == "futures", "Market should be 'futures'"
        print(f"OKX/futures key saved successfully: provider={okx_item['provider']}, status={okx_item['status']}")


class TestAdminExchangesPageBackwardCompatibility:
    """Tests for existing admin venues CRUD pages backward compatibility"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with admin authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Authenticate as admin
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if login_response.status_code == 200:
            token = login_response.json().get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
            self.authenticated = True
        else:
            self.authenticated = False

    def test_admin_exchanges_list_returns_200(self):
        """GET /api/venues/admin/exchanges returns 200"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        response = self.session.get(f"{BASE_URL}/api/venues/admin/exchanges")
        print(f"GET admin/exchanges response: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} exchanges")

    def test_admin_capabilities_list_returns_200(self):
        """GET /api/venues/admin/capabilities returns 200"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        response = self.session.get(f"{BASE_URL}/api/venues/admin/capabilities")
        print(f"GET admin/capabilities response: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} capabilities")

    def test_admin_allowed_markets_list_returns_200(self):
        """GET /api/venues/admin/allowed-markets returns 200"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        response = self.session.get(f"{BASE_URL}/api/venues/admin/allowed-markets")
        print(f"GET admin/allowed-markets response: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} allowed markets")

    def test_admin_user_assignments_list_returns_200(self):
        """GET /api/venues/admin/user-assignments returns 200"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        response = self.session.get(f"{BASE_URL}/api/venues/admin/user-assignments")
        print(f"GET admin/user-assignments response: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} user assignments")

    def test_admin_health_summary_returns_200(self):
        """GET /api/venues/admin/health-summary returns 200"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        response = self.session.get(f"{BASE_URL}/api/venues/admin/health-summary")
        print(f"GET admin/health-summary response: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "exchange_health" in data or "market_availability" in data, "Health summary should have expected fields"
        print(f"Health summary keys: {list(data.keys())}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
