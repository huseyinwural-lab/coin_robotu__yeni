"""
Test suite for Admin Market Data Keys API endpoints
Tests the new Binance read-only market data key management feature
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Admin credentials from review request
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"


class TestAdminMarketDataKeys:
    """Tests for /api/venues/admin/market-data-keys endpoints"""

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

    def test_get_market_data_keys_returns_200(self):
        """GET /api/venues/admin/market-data-keys returns 200 and expected summary fields"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        response = self.session.get(f"{BASE_URL}/api/venues/admin/market-data-keys")
        print(f"GET market-data-keys response: {response.status_code}")
        print(f"Response body: {response.text[:500]}")
        
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
        assert isinstance(data["users_with_live_distribution"], int), "users_with_live_distribution should be int"
        assert isinstance(data["active_user_count"], int), "active_user_count should be int"
        
        print(f"Market data keys summary: active_key={data['active_key']}, items_count={len(data['items'])}")

    def test_post_market_data_keys_invalid_key_returns_400(self):
        """POST /api/venues/admin/market-data-keys with invalid key returns controlled 400 error (not 500)"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        # Use clearly invalid/demo keys
        invalid_payload = {
            "api_key": "INVALID_TEST_API_KEY_12345",
            "api_secret": "INVALID_TEST_API_SECRET_67890",
            "base_url_override": "",
            "ip_route_note": "",
            "note": "test_invalid_key"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/market-data-keys",
            json=invalid_payload
        )
        print(f"POST market-data-keys with invalid key response: {response.status_code}")
        print(f"Response body: {response.text[:500]}")
        
        # Should return 400 (controlled error), NOT 500 (server error)
        assert response.status_code == 400, f"Expected 400 for invalid key, got {response.status_code}: {response.text}"
        
        # Verify error response has detail
        data = response.json()
        assert "detail" in data, "Error response should have 'detail' field"
        print(f"Error detail: {data.get('detail')}")

    def test_post_market_data_keys_missing_fields_returns_422(self):
        """POST /api/venues/admin/market-data-keys with missing required fields returns 422"""
        if not self.authenticated:
            pytest.skip("Admin authentication failed")
        
        # Missing api_secret
        incomplete_payload = {
            "api_key": "SOME_API_KEY"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/market-data-keys",
            json=incomplete_payload
        )
        print(f"POST market-data-keys with missing fields response: {response.status_code}")
        
        # Should return 422 for validation error
        assert response.status_code == 422, f"Expected 422 for missing fields, got {response.status_code}: {response.text}"


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
