"""
Iteration 20 - User-Side Comprehensive Backend Tests
Tests: Auth/login timeout, User Signals, Scanner, BotProfiles, Portfolio/Trades endpoints
Focus: Timeout behavior, error-state handling, endpoint stability
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com").rstrip("/")
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

# Timeout configurations for testing
LOGIN_TIMEOUT_SECONDS = 30
API_TIMEOUT_SECONDS = 25


class TestHealthEndpoints:
    """Health check endpoints - should respond quickly"""
    
    def test_health_endpoint(self):
        """Test /api/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["ok", "degraded"]
        print(f"Health check: {data['status']}")
    
    def test_health_live_endpoint(self):
        """Test /api/health/live returns 200"""
        response = requests.get(f"{BASE_URL}/api/health/live", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        print("Health live check: OK")


class TestAuthLoginTimeout:
    """Auth/login timeout behavior tests"""
    
    def test_login_success_within_timeout(self):
        """Login should complete within 30 seconds"""
        start_time = time.time()
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=LOGIN_TIMEOUT_SECONDS
        )
        elapsed = time.time() - start_time
        
        assert response.status_code == 200, f"Login failed with status {response.status_code}: {response.text}"
        assert elapsed < LOGIN_TIMEOUT_SECONDS, f"Login took {elapsed:.2f}s, exceeds {LOGIN_TIMEOUT_SECONDS}s timeout"
        
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        print(f"Login successful in {elapsed:.2f}s")
        return data["access_token"]
    
    def test_login_invalid_credentials(self):
        """Invalid credentials should return 401 quickly"""
        start_time = time.time()
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": "invalid@test.com", "password": "wrongpassword"},
            timeout=15
        )
        elapsed = time.time() - start_time
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        assert elapsed < 15, f"Invalid login took {elapsed:.2f}s, should be faster"
        print(f"Invalid login rejected in {elapsed:.2f}s")
    
    def test_auth_me_endpoint(self):
        """Test /api/auth/me with valid token"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=LOGIN_TIMEOUT_SECONDS
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        
        # Then check /me
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=API_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        print(f"Auth me: {data.get('email')}")


class TestUserSignalsEndpoints:
    """User Signals page endpoints - slow-loading hint + hard-timeout error-state"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=LOGIN_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_user_signals_endpoint(self):
        """Test /api/user/signals returns data within timeout"""
        start_time = time.time()
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=self.headers,
            params={"limit": 80},
            timeout=API_TIMEOUT_SECONDS
        )
        elapsed = time.time() - start_time
        
        assert response.status_code == 200, f"Signals failed: {response.status_code}"
        assert elapsed < API_TIMEOUT_SECONDS, f"Signals took {elapsed:.2f}s"
        print(f"User signals: {response.status_code} in {elapsed:.2f}s")
    
    def test_user_portfolio_endpoint(self):
        """Test /api/user/portfolio returns data"""
        start_time = time.time()
        response = requests.get(
            f"{BASE_URL}/api/user/portfolio",
            headers=self.headers,
            timeout=API_TIMEOUT_SECONDS
        )
        elapsed = time.time() - start_time
        
        assert response.status_code == 200, f"Portfolio failed: {response.status_code}"
        print(f"User portfolio: {response.status_code} in {elapsed:.2f}s")
    
    def test_user_trades_endpoint(self):
        """Test /api/user/trades returns data - critical for stability"""
        start_time = time.time()
        response = requests.get(
            f"{BASE_URL}/api/user/trades",
            headers=self.headers,
            params={"limit": 50},
            timeout=API_TIMEOUT_SECONDS
        )
        elapsed = time.time() - start_time
        
        assert response.status_code == 200, f"Trades failed: {response.status_code}"
        print(f"User trades: {response.status_code} in {elapsed:.2f}s")
    
    def test_user_signal_mode_endpoint(self):
        """Test /api/user/signal-mode returns data"""
        response = requests.get(
            f"{BASE_URL}/api/user/signal-mode",
            headers=self.headers,
            timeout=API_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        print(f"Signal mode: {data.get('mode')}")


class TestScannerEndpoints:
    """Scanner/Signals/BotProfiles error class and endpoint visibility"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=LOGIN_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_user_scanner_endpoint(self):
        """Test /api/user/scanner returns data"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner",
            headers=self.headers,
            timeout=API_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        print(f"User scanner: {response.status_code}")
    
    def test_screener_endpoint(self):
        """Test /api/screener returns data"""
        response = requests.get(
            f"{BASE_URL}/api/screener",
            headers=self.headers,
            params={"limit": 120},
            timeout=API_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        print(f"Screener: {response.status_code}")
    
    def test_scanner_status_contract_endpoint(self):
        """Test /api/user/scanner/status-contract returns data"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/status-contract",
            headers=self.headers,
            timeout=API_TIMEOUT_SECONDS
        )
        # May return 404 if not configured, but should not error
        assert response.status_code in [200, 404]
        print(f"Scanner status contract: {response.status_code}")


class TestBotProfilesEndpoints:
    """BotProfiles error class and endpoint visibility"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=LOGIN_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_bot_profiles_list(self):
        """Test /api/bot-profiles returns list"""
        response = requests.get(
            f"{BASE_URL}/api/bot-profiles",
            headers=self.headers,
            timeout=API_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Bot profiles: {len(data)} items")
    
    def test_strategy_templates_endpoint(self):
        """Test /api/strategy-templates returns data"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-templates",
            headers=self.headers,
            timeout=API_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        print(f"Strategy templates: {response.status_code}")
    
    def test_risk_policies_endpoint(self):
        """Test /api/risk-policies returns data"""
        response = requests.get(
            f"{BASE_URL}/api/risk-policies",
            headers=self.headers,
            timeout=API_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        print(f"Risk policies: {response.status_code}")
    
    def test_user_canonical_strategies_endpoint(self):
        """Test /api/user/canonical-strategies returns data"""
        response = requests.get(
            f"{BASE_URL}/api/user/canonical-strategies",
            headers=self.headers,
            timeout=API_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        print(f"Canonical strategies: {response.status_code}")
    
    def test_user_exchange_connections_endpoint(self):
        """Test /api/user/exchange-connections returns data"""
        response = requests.get(
            f"{BASE_URL}/api/user/exchange-connections",
            headers=self.headers,
            timeout=API_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Exchange connections: {len(data)} items")


class TestExecutionIntentEndpoints:
    """Precheck/submit sim flows and user-side critical flows"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=LOGIN_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_execution_intent_preview(self):
        """Test /api/user/execution/intent/preview with SIM mode payload"""
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "take_profit_mode": "percent",
            "take_profit_value": 2,
            "stop_loss_mode": "percent",
            "stop_loss_value": 1,
            "execution_mode": "sim"
        }
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=self.headers,
            json=payload,
            timeout=API_TIMEOUT_SECONDS
        )
        # May return 400 if validation fails, but should not 500
        assert response.status_code in [200, 400, 422]
        print(f"Execution intent preview: {response.status_code}")
    
    def test_user_execution_intents_list(self):
        """Test /api/user/execution/intents returns list"""
        response = requests.get(
            f"{BASE_URL}/api/user/execution/intents",
            headers=self.headers,
            params={"limit": 50},
            timeout=API_TIMEOUT_SECONDS
        )
        assert response.status_code == 200
        print(f"Execution intents: {response.status_code}")


class TestErrorClassification:
    """Test error classification for infra_error, auth_error, trade_blocker"""
    
    def test_unauthorized_returns_401(self):
        """Requests without token should return 401"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            timeout=10
        )
        assert response.status_code == 401
        print("Unauthorized correctly returns 401")
    
    def test_invalid_token_returns_401(self):
        """Invalid token should return 401"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers={"Authorization": "Bearer invalid_token_here"},
            timeout=10
        )
        assert response.status_code == 401
        print("Invalid token correctly returns 401")
    
    def test_nonexistent_endpoint_returns_404(self):
        """Non-existent endpoint should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/nonexistent/endpoint",
            timeout=10
        )
        assert response.status_code == 404
        print("Non-existent endpoint correctly returns 404")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
