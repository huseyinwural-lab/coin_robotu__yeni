"""
Deploy Readiness Retest - Iteration 6
Testing fixes for:
1. /api/user/trades performance (was 59s)
2. /api/user/execution/positions performance
3. /api/health and /api/ready external preview
4. BotProfiles/ExchangeSettings page crash
5. Duplicate key warning in /user/exchange-settings route
"""
import os
import time
import pytest
import requests

BASE_URL = "http://127.0.0.1:8001"  # Internal URL for testing
TEST_EMAIL = "review.user@platform.local"
TEST_PASSWORD = "ReviewUser123!"

# Performance thresholds (in seconds)
TRADES_TIMEOUT_THRESHOLD = 15  # Was 59s, should be much faster now
POSITIONS_TIMEOUT_THRESHOLD = 10
HEALTH_TIMEOUT_THRESHOLD = 10


class TestHealthEndpoints:
    """Health endpoint tests"""

    def test_health_endpoint(self):
        """Test /api/health endpoint"""
        start = time.time()
        response = requests.get(f"{BASE_URL}/api/health", timeout=HEALTH_TIMEOUT_THRESHOLD)
        elapsed = time.time() - start
        print(f"/api/health response time: {elapsed:.2f}s, status: {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert elapsed < HEALTH_TIMEOUT_THRESHOLD, f"Response too slow: {elapsed:.2f}s"

    def test_ready_endpoint(self):
        """Test /api/ready endpoint"""
        start = time.time()
        response = requests.get(f"{BASE_URL}/api/ready", timeout=HEALTH_TIMEOUT_THRESHOLD + 5)
        elapsed = time.time() - start
        print(f"/api/ready response time: {elapsed:.2f}s, status: {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"


class TestAuthenticatedEndpoints:
    """Authenticated endpoint tests with performance focus"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token using correct endpoint"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",  # Correct endpoint
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=15
        )
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.status_code} - {response.text}")
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            pytest.skip("No token in login response")
        return token

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers"""
        return {"Authorization": f"Bearer {auth_token}"}

    def test_user_trades_performance(self, auth_headers):
        """CRITICAL: Test /api/user/trades performance - was 59s, should be <15s now"""
        start = time.time()
        response = requests.get(
            f"{BASE_URL}/api/user/trades",
            headers=auth_headers,
            timeout=TRADES_TIMEOUT_THRESHOLD + 5
        )
        elapsed = time.time() - start
        print(f"/api/user/trades response time: {elapsed:.2f}s, status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert elapsed < TRADES_TIMEOUT_THRESHOLD, f"CRITICAL: /api/user/trades still slow: {elapsed:.2f}s (threshold: {TRADES_TIMEOUT_THRESHOLD}s)"
        
        # Verify response structure
        data = response.json()
        print(f"/api/user/trades returned {len(data) if isinstance(data, list) else 'object'} items")

    def test_user_execution_positions_performance(self, auth_headers):
        """Test /api/user/execution/positions performance"""
        start = time.time()
        response = requests.get(
            f"{BASE_URL}/api/user/execution/positions?include_closed=false",
            headers=auth_headers,
            timeout=POSITIONS_TIMEOUT_THRESHOLD
        )
        elapsed = time.time() - start
        print(f"/api/user/execution/positions response time: {elapsed:.2f}s, status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert elapsed < POSITIONS_TIMEOUT_THRESHOLD, f"/api/user/execution/positions slow: {elapsed:.2f}s"

    def test_bot_profiles_endpoint(self, auth_headers):
        """Test /api/bot-profiles endpoint"""
        start = time.time()
        response = requests.get(
            f"{BASE_URL}/api/bot-profiles",
            headers=auth_headers,
            timeout=20
        )
        elapsed = time.time() - start
        print(f"/api/bot-profiles response time: {elapsed:.2f}s, status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_exchange_settings_endpoint(self, auth_headers):
        """Test /api/phase4/exchange-settings endpoint"""
        start = time.time()
        response = requests.get(
            f"{BASE_URL}/api/phase4/exchange-settings",
            headers=auth_headers,
            timeout=10
        )
        elapsed = time.time() - start
        print(f"/api/phase4/exchange-settings response time: {elapsed:.2f}s, status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
