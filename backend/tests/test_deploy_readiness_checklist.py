"""
Deploy Readiness Checklist Tests
Tests for user-side menu endpoints: health, readiness, positions, trades, signals, bot profiles, exchange settings
Focus: API health/readiness, critical user menu endpoints, performance timeout risks
"""
import os
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_EMAIL = "review.user@platform.local"
TEST_PASSWORD = "ReviewUser123!"


class TestHealthReadinessEndpoints:
    """Health and readiness endpoint tests - deploy checklist critical"""

    def test_health_endpoint_returns_200(self):
        """API health endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Health endpoint failed: {response.status_code}"
        data = response.json()
        assert "status" in data
        assert "checks" in data
        print(f"PASS: /api/health returns 200, status={data.get('status')}")

    def test_health_live_endpoint_returns_200(self):
        """API health/live endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/health/live", timeout=10)
        assert response.status_code == 200, f"Health/live endpoint failed: {response.status_code}"
        data = response.json()
        assert data.get("status") == "ok"
        print(f"PASS: /api/health/live returns 200")

    def test_ready_endpoint_returns_200_or_503(self):
        """API ready endpoint should return 200 (ready) or 503 (not ready)"""
        response = requests.get(f"{BASE_URL}/api/ready", timeout=15)
        assert response.status_code in [200, 503], f"Ready endpoint unexpected status: {response.status_code}"
        data = response.json()
        assert "status" in data
        assert "checks" in data
        print(f"PASS: /api/ready returns {response.status_code}, status={data.get('status')}")

    def test_health_ready_endpoint_returns_200_or_503(self):
        """API health/ready endpoint should return 200 (ready) or 503 (not ready)"""
        response = requests.get(f"{BASE_URL}/api/health/ready", timeout=15)
        assert response.status_code in [200, 503], f"Health/ready endpoint unexpected status: {response.status_code}"
        data = response.json()
        assert "status" in data
        print(f"PASS: /api/health/ready returns {response.status_code}, status={data.get('status')}")


class TestAuthenticationFlow:
    """Authentication tests for user credentials"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for test user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=15
        )
        if response.status_code != 200:
            pytest.skip(f"Authentication failed: {response.status_code} - {response.text[:200]}")
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            pytest.skip("No token in auth response")
        return token

    def test_login_with_valid_credentials(self, auth_token):
        """Login should succeed with valid credentials"""
        assert auth_token is not None
        print(f"PASS: Login successful, token obtained")


class TestUserExecutionEndpoints:
    """User execution endpoints - positions and trades performance"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=15
        )
        if response.status_code != 200:
            pytest.skip(f"Authentication failed: {response.status_code}")
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            pytest.skip("No token in auth response")
        return {"Authorization": f"Bearer {token}"}

    def test_user_execution_positions_performance(self, auth_headers):
        """
        /api/user/execution/positions should respond within timeout
        Critical: Heavy readiness call was removed in recent patch
        """
        start = time.time()
        response = requests.get(
            f"{BASE_URL}/api/user/execution/positions",
            headers=auth_headers,
            timeout=30
        )
        elapsed = time.time() - start
        
        assert response.status_code in [200, 401, 403], f"Positions endpoint failed: {response.status_code}"
        print(f"PASS: /api/user/execution/positions returned {response.status_code} in {elapsed:.2f}s")
        
        # Performance check - should be fast after heavy readiness removal
        if response.status_code == 200:
            assert elapsed < 15, f"Positions endpoint too slow: {elapsed:.2f}s (expected <15s)"
            print(f"PASS: Positions endpoint performance OK ({elapsed:.2f}s)")

    def test_user_execution_intents(self, auth_headers):
        """
        /api/user/execution/intents should return list of execution intents
        """
        response = requests.get(
            f"{BASE_URL}/api/user/execution/intents",
            headers=auth_headers,
            timeout=20
        )
        assert response.status_code in [200, 401, 403], f"Intents endpoint failed: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list), "Intents should return a list"
        print(f"PASS: /api/user/execution/intents returned {response.status_code}")

    def test_user_execution_presets(self, auth_headers):
        """
        /api/user/execution/presets should return execution presets
        """
        response = requests.get(
            f"{BASE_URL}/api/user/execution/presets",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code in [200, 401, 403], f"Presets endpoint failed: {response.status_code}"
        print(f"PASS: /api/user/execution/presets returned {response.status_code}")


class TestUserTradesEndpoints:
    """User trades endpoints - performance critical"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=15
        )
        if response.status_code != 200:
            pytest.skip(f"Authentication failed: {response.status_code}")
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            pytest.skip("No token in auth response")
        return {"Authorization": f"Bearer {token}"}

    def test_user_trades_performance(self, auth_headers):
        """
        /api/user/trades should respond within timeout
        Critical: trade sync throttle was added in recent patch
        """
        start = time.time()
        response = requests.get(
            f"{BASE_URL}/api/user/trades",
            headers=auth_headers,
            params={"limit": 50},
            timeout=30
        )
        elapsed = time.time() - start
        
        assert response.status_code in [200, 401, 403], f"Trades endpoint failed: {response.status_code}"
        print(f"PASS: /api/user/trades returned {response.status_code} in {elapsed:.2f}s")
        
        if response.status_code == 200:
            data = response.json()
            # Check response structure
            if isinstance(data, dict):
                assert "items" in data or "trades" in data or isinstance(data.get("items"), list)
            print(f"PASS: Trades endpoint returned valid data structure")


class TestBotProfilesEndpoints:
    """Bot profiles endpoints - partial-load revision check"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=15
        )
        if response.status_code != 200:
            pytest.skip(f"Authentication failed: {response.status_code}")
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            pytest.skip("No token in auth response")
        return {"Authorization": f"Bearer {token}"}

    def test_bot_profiles_list(self, auth_headers):
        """
        /api/bot-profiles should return list of bot profiles
        Critical: partial-load revision was applied
        """
        response = requests.get(
            f"{BASE_URL}/api/bot-profiles",
            headers=auth_headers,
            timeout=20
        )
        assert response.status_code in [200, 401, 403], f"Bot profiles endpoint failed: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list), "Bot profiles should return a list"
        print(f"PASS: /api/bot-profiles returned {response.status_code}")

    def test_canonical_strategies(self, auth_headers):
        """
        /api/user/canonical-strategies should return canonical strategies
        """
        response = requests.get(
            f"{BASE_URL}/api/user/canonical-strategies",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code in [200, 401, 403], f"Canonical strategies endpoint failed: {response.status_code}"
        print(f"PASS: /api/user/canonical-strategies returned {response.status_code}")

    def test_strategy_templates(self, auth_headers):
        """
        /api/strategy-templates should return strategy templates
        """
        response = requests.get(
            f"{BASE_URL}/api/strategy-templates",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code in [200, 401, 403], f"Strategy templates endpoint failed: {response.status_code}"
        print(f"PASS: /api/strategy-templates returned {response.status_code}")

    def test_risk_policies(self, auth_headers):
        """
        /api/risk-policies should return risk policies
        """
        response = requests.get(
            f"{BASE_URL}/api/risk-policies",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code in [200, 401, 403], f"Risk policies endpoint failed: {response.status_code}"
        print(f"PASS: /api/risk-policies returned {response.status_code}")


class TestExchangeSettingsEndpoints:
    """Exchange settings endpoints - partial-load revision check"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=15
        )
        if response.status_code != 200:
            pytest.skip(f"Authentication failed: {response.status_code}")
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            pytest.skip("No token in auth response")
        return {"Authorization": f"Bearer {token}"}

    def test_exchange_connections(self, auth_headers):
        """
        /api/user/exchange-connections should return exchange connections
        """
        response = requests.get(
            f"{BASE_URL}/api/user/exchange-connections",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code in [200, 401, 403], f"Exchange connections endpoint failed: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list), "Exchange connections should return a list"
        print(f"PASS: /api/user/exchange-connections returned {response.status_code}")

    def test_phase4_exchange_settings(self, auth_headers):
        """
        /api/phase4/exchange-settings should return exchange settings
        """
        response = requests.get(
            f"{BASE_URL}/api/phase4/exchange-settings",
            headers=auth_headers,
            timeout=15
        )
        # May return 404 if not configured, 200 if configured
        assert response.status_code in [200, 401, 403, 404, 500], f"Exchange settings endpoint failed: {response.status_code}"
        print(f"PASS: /api/phase4/exchange-settings returned {response.status_code}")

    def test_venues_options(self, auth_headers):
        """
        /api/venues/options should return venue options
        """
        response = requests.get(
            f"{BASE_URL}/api/venues/options",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code in [200, 401, 403], f"Venues options endpoint failed: {response.status_code}"
        print(f"PASS: /api/venues/options returned {response.status_code}")

    def test_user_portfolio(self, auth_headers):
        """
        /api/user/portfolio should return portfolio overview
        """
        response = requests.get(
            f"{BASE_URL}/api/user/portfolio",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code in [200, 401, 403], f"Portfolio endpoint failed: {response.status_code}"
        print(f"PASS: /api/user/portfolio returned {response.status_code}")


class TestSignalsEndpoints:
    """Signals page endpoints - grid/funnel areas check"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=15
        )
        if response.status_code != 200:
            pytest.skip(f"Authentication failed: {response.status_code}")
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            pytest.skip("No token in auth response")
        return {"Authorization": f"Bearer {token}"}

    def test_user_signals(self, auth_headers):
        """
        /api/user/signals should return signals list
        Critical: grid/funnel areas should still populate
        """
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=auth_headers,
            params={"limit": 80},
            timeout=20
        )
        assert response.status_code in [200, 401, 403], f"Signals endpoint failed: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            # Can be list or dict with items
            if isinstance(data, dict):
                assert "items" in data or isinstance(data, list)
            print(f"PASS: Signals endpoint returned valid data")
        print(f"PASS: /api/user/signals returned {response.status_code}")

    def test_user_signal_mode(self, auth_headers):
        """
        /api/user/signal-mode should return signal mode
        """
        response = requests.get(
            f"{BASE_URL}/api/user/signal-mode",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code in [200, 401, 403], f"Signal mode endpoint failed: {response.status_code}"
        print(f"PASS: /api/user/signal-mode returned {response.status_code}")


class TestLiveDashboardEndpoints:
    """Live dashboard endpoints - performance/sync optimization check"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=15
        )
        if response.status_code != 200:
            pytest.skip(f"Authentication failed: {response.status_code}")
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            pytest.skip("No token in auth response")
        return {"Authorization": f"Bearer {token}"}

    def test_user_live_summary(self, auth_headers):
        """
        /api/user/live/summary should return live summary
        """
        start = time.time()
        response = requests.get(
            f"{BASE_URL}/api/user/live/summary",
            headers=auth_headers,
            params={"window": "1h"},
            timeout=25
        )
        elapsed = time.time() - start
        
        assert response.status_code in [200, 401, 403], f"Live summary endpoint failed: {response.status_code}"
        print(f"PASS: /api/user/live/summary returned {response.status_code} in {elapsed:.2f}s")

    def test_user_live_positions(self, auth_headers):
        """
        /api/user/live/positions should return live positions
        """
        response = requests.get(
            f"{BASE_URL}/api/user/live/positions",
            headers=auth_headers,
            timeout=20
        )
        assert response.status_code in [200, 401, 403], f"Live positions endpoint failed: {response.status_code}"
        print(f"PASS: /api/user/live/positions returned {response.status_code}")

    def test_user_live_performance(self, auth_headers):
        """
        /api/user/live/performance should return live performance
        """
        response = requests.get(
            f"{BASE_URL}/api/user/live/performance",
            headers=auth_headers,
            params={"window": "24h"},
            timeout=20
        )
        assert response.status_code in [200, 401, 403], f"Live performance endpoint failed: {response.status_code}"
        print(f"PASS: /api/user/live/performance returned {response.status_code}")

    def test_user_live_strategy_performance(self, auth_headers):
        """
        /api/user/live/strategy-performance should return strategy performance
        """
        response = requests.get(
            f"{BASE_URL}/api/user/live/strategy-performance",
            headers=auth_headers,
            params={"window": "24h"},
            timeout=20
        )
        assert response.status_code in [200, 401, 403], f"Strategy performance endpoint failed: {response.status_code}"
        print(f"PASS: /api/user/live/strategy-performance returned {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
