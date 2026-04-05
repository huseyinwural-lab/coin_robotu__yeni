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

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_EMAIL = "review.user@platform.local"
TEST_PASSWORD = "ReviewUser123!"

# Performance thresholds (in seconds)
TRADES_TIMEOUT_THRESHOLD = 15  # Was 59s, should be much faster now
POSITIONS_TIMEOUT_THRESHOLD = 10
HEALTH_TIMEOUT_THRESHOLD = 10


class TestHealthEndpoints:
    """Health endpoint tests - external preview URL"""

    def test_health_endpoint(self):
        """Test /api/health endpoint"""
        start = time.time()
        try:
            response = requests.get(f"{BASE_URL}/api/health", timeout=HEALTH_TIMEOUT_THRESHOLD)
            elapsed = time.time() - start
            print(f"/api/health response time: {elapsed:.2f}s, status: {response.status_code}")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            assert elapsed < HEALTH_TIMEOUT_THRESHOLD, f"Response too slow: {elapsed:.2f}s"
        except requests.exceptions.Timeout:
            elapsed = time.time() - start
            pytest.fail(f"/api/health timed out after {elapsed:.2f}s")

    def test_health_ready_endpoint(self):
        """Test /api/health/ready endpoint"""
        start = time.time()
        try:
            response = requests.get(f"{BASE_URL}/api/health/ready", timeout=HEALTH_TIMEOUT_THRESHOLD)
            elapsed = time.time() - start
            print(f"/api/health/ready response time: {elapsed:.2f}s, status: {response.status_code}")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            assert elapsed < HEALTH_TIMEOUT_THRESHOLD, f"Response too slow: {elapsed:.2f}s"
        except requests.exceptions.Timeout:
            elapsed = time.time() - start
            pytest.fail(f"/api/health/ready timed out after {elapsed:.2f}s")

    def test_ready_endpoint(self):
        """Test /api/ready endpoint"""
        start = time.time()
        try:
            response = requests.get(f"{BASE_URL}/api/ready", timeout=HEALTH_TIMEOUT_THRESHOLD + 5)
            elapsed = time.time() - start
            print(f"/api/ready response time: {elapsed:.2f}s, status: {response.status_code}")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        except requests.exceptions.Timeout:
            elapsed = time.time() - start
            pytest.fail(f"/api/ready timed out after {elapsed:.2f}s")


class TestAuthenticatedEndpoints:
    """Authenticated endpoint tests with performance focus"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
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
        try:
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
            
        except requests.exceptions.Timeout:
            elapsed = time.time() - start
            pytest.fail(f"CRITICAL: /api/user/trades timed out after {elapsed:.2f}s - performance fix NOT working")

    def test_user_execution_positions_performance(self, auth_headers):
        """Test /api/user/execution/positions performance"""
        start = time.time()
        try:
            response = requests.get(
                f"{BASE_URL}/api/user/execution/positions",
                headers=auth_headers,
                timeout=POSITIONS_TIMEOUT_THRESHOLD
            )
            elapsed = time.time() - start
            print(f"/api/user/execution/positions response time: {elapsed:.2f}s, status: {response.status_code}")
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            assert elapsed < POSITIONS_TIMEOUT_THRESHOLD, f"/api/user/execution/positions slow: {elapsed:.2f}s"
            
        except requests.exceptions.Timeout:
            elapsed = time.time() - start
            pytest.fail(f"/api/user/execution/positions timed out after {elapsed:.2f}s")

    def test_bot_profiles_endpoint(self, auth_headers):
        """Test /api/bot-profiles endpoint - was slow at 14.7s"""
        start = time.time()
        try:
            response = requests.get(
                f"{BASE_URL}/api/bot-profiles",
                headers=auth_headers,
                timeout=20
            )
            elapsed = time.time() - start
            print(f"/api/bot-profiles response time: {elapsed:.2f}s, status: {response.status_code}")
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
        except requests.exceptions.Timeout:
            elapsed = time.time() - start
            pytest.fail(f"/api/bot-profiles timed out after {elapsed:.2f}s")

    def test_exchange_settings_endpoint(self, auth_headers):
        """Test /api/phase4/exchange-settings endpoint"""
        start = time.time()
        try:
            response = requests.get(
                f"{BASE_URL}/api/phase4/exchange-settings",
                headers=auth_headers,
                timeout=10
            )
            elapsed = time.time() - start
            print(f"/api/phase4/exchange-settings response time: {elapsed:.2f}s, status: {response.status_code}")
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
        except requests.exceptions.Timeout:
            elapsed = time.time() - start
            pytest.fail(f"/api/phase4/exchange-settings timed out after {elapsed:.2f}s")

    def test_user_exchange_connections(self, auth_headers):
        """Test /api/user/exchange-connections endpoint"""
        start = time.time()
        try:
            response = requests.get(
                f"{BASE_URL}/api/user/exchange-connections",
                headers=auth_headers,
                timeout=10
            )
            elapsed = time.time() - start
            print(f"/api/user/exchange-connections response time: {elapsed:.2f}s, status: {response.status_code}")
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
        except requests.exceptions.Timeout:
            elapsed = time.time() - start
            pytest.fail(f"/api/user/exchange-connections timed out after {elapsed:.2f}s")


class TestLiveDashboardEndpoints:
    """Live dashboard endpoint tests"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=15
        )
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.status_code}")
        data = response.json()
        return data.get("access_token") or data.get("token")

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers"""
        return {"Authorization": f"Bearer {auth_token}"}

    def test_user_live_summary(self, auth_headers):
        """Test /api/user/live/summary endpoint"""
        start = time.time()
        response = requests.get(
            f"{BASE_URL}/api/user/live/summary",
            headers=auth_headers,
            timeout=10
        )
        elapsed = time.time() - start
        print(f"/api/user/live/summary response time: {elapsed:.2f}s, status: {response.status_code}")
        assert response.status_code == 200

    def test_user_live_positions(self, auth_headers):
        """Test /api/user/live/positions endpoint"""
        start = time.time()
        response = requests.get(
            f"{BASE_URL}/api/user/live/positions",
            headers=auth_headers,
            timeout=10
        )
        elapsed = time.time() - start
        print(f"/api/user/live/positions response time: {elapsed:.2f}s, status: {response.status_code}")
        assert response.status_code == 200

    def test_user_live_performance(self, auth_headers):
        """Test /api/user/live/performance endpoint"""
        start = time.time()
        response = requests.get(
            f"{BASE_URL}/api/user/live/performance",
            headers=auth_headers,
            timeout=10
        )
        elapsed = time.time() - start
        print(f"/api/user/live/performance response time: {elapsed:.2f}s, status: {response.status_code}")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
