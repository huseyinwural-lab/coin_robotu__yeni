"""
Iteration 35 - Final Pre-Deployment Validation
Tests: Auth, User Scanner/Signals/Trades, Admin Universe Monitor & Strategy Allocation
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"


class TestAuthEndpoints:
    """Authentication endpoint tests"""

    def test_admin_login_success(self):
        """Test admin login returns token and correct role"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Missing access_token"
        assert data.get("role") in ["super_admin", "admin"], f"Unexpected role: {data.get('role')}"
        print(f"✓ Admin login success: role={data.get('role')}")

    def test_user_login_success(self):
        """Test user login returns token and correct role"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=30
        )
        assert response.status_code == 200, f"User login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Missing access_token"
        assert data.get("role") == "user", f"Unexpected role: {data.get('role')}"
        print(f"✓ User login success: role={data.get('role')}")

    def test_invalid_login_returns_401(self):
        """Test invalid credentials return 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": "invalid@test.com", "password": "wrongpassword"},
            timeout=30
        )
        assert response.status_code in [401, 400], f"Expected 401/400, got {response.status_code}"
        print("✓ Invalid login correctly returns 401/400")

    def test_auth_me_with_token(self):
        """Test /auth/me returns user info with valid token"""
        # First login
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=30
        )
        assert login_resp.status_code == 200
        token = login_resp.json().get("access_token")
        
        # Then check /me
        me_resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        assert me_resp.status_code == 200, f"/auth/me failed: {me_resp.text}"
        data = me_resp.json()
        assert data.get("email") == USER_EMAIL
        print(f"✓ /auth/me returns correct user: {data.get('email')}")


class TestUserScannerEndpoints:
    """User scanner-related endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get user token for authenticated requests"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=30
        )
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_scanner_engine_last_run(self):
        """Test /user/scanner-engine/last-run returns scanner results"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner-engine/last-run",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Scanner last-run failed: {response.text}"
        data = response.json()
        assert "status" in data
        print(f"✓ Scanner last-run: status={data.get('status')}, results={len(data.get('results', []))}")

    def test_scanner_engine_config(self):
        """Test /user/scanner-engine/config returns configuration"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner-engine/config",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Scanner config failed: {response.text}"
        data = response.json()
        assert "exchange" in data or "include_spot" in data
        print(f"✓ Scanner config: keys={list(data.keys())[:5]}")

    def test_scanner_overview(self):
        """Test /user/scanner returns overview"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Scanner overview failed: {response.text}"
        data = response.json()
        print(f"✓ Scanner overview: mode={data.get('mode')}, total_results={data.get('total_results')}")


class TestUserSignalsEndpoints:
    """User signals-related endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get user token for authenticated requests"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=30
        )
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_user_signals_list(self):
        """Test /user/signals returns signal list"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=self.headers,
            params={"limit": 50},
            timeout=30
        )
        assert response.status_code == 200, f"Signals list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ User signals: count={len(data)}")

    def test_user_signal_mode(self):
        """Test /user/signal-mode returns current mode"""
        response = requests.get(
            f"{BASE_URL}/api/user/signal-mode",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Signal mode failed: {response.text}"
        data = response.json()
        assert "mode" in data
        print(f"✓ Signal mode: {data.get('mode')}")

    def test_user_portfolio(self):
        """Test /user/portfolio returns portfolio data"""
        response = requests.get(
            f"{BASE_URL}/api/user/portfolio",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Portfolio failed: {response.text}"
        data = response.json()
        print(f"✓ Portfolio: keys={list(data.keys())[:5]}")

    def test_user_trades(self):
        """Test /user/trades returns trade list"""
        response = requests.get(
            f"{BASE_URL}/api/user/trades",
            headers=self.headers,
            params={"limit": 50},
            timeout=30
        )
        assert response.status_code == 200, f"Trades failed: {response.text}"
        data = response.json()
        print(f"✓ User trades: count={len(data) if isinstance(data, list) else 'N/A'}")


class TestAdminUniverseMonitorEndpoints:
    """Admin universe monitor endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for authenticated requests"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_universe_monitor_trends(self):
        """Test /admin/universe-monitor/trends returns trend data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/trends",
            headers=self.headers,
            params={"window": "24h"},
            timeout=30
        )
        assert response.status_code == 200, f"Universe trends failed: {response.text}"
        data = response.json()
        print(f"✓ Universe trends: keys={list(data.keys())[:5]}")

    def test_universe_monitor_fallback_events(self):
        """Test /admin/universe-monitor/fallback-events returns events"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/fallback-events",
            headers=self.headers,
            params={"limit": 10},
            timeout=30
        )
        assert response.status_code == 200, f"Fallback events failed: {response.text}"
        data = response.json()
        print(f"✓ Fallback events: items={len(data.get('items', []))}")


class TestAdminStrategyAllocationEndpoints:
    """Admin strategy allocation endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for authenticated requests"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_strategy_allocation_list(self):
        """Test /admin/strategy-allocation returns allocation list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Strategy allocation failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Strategy allocation: count={len(data)}")

    def test_strategy_allocation_summary(self):
        """Test /admin/strategy-allocation/summary returns summary"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Allocation summary failed: {response.text}"
        data = response.json()
        print(f"✓ Allocation summary: total_weight={data.get('total_weight')}")


class TestHealthAndScreener:
    """Health check and screener tests"""

    def test_health_endpoint(self):
        """Test /health returns OK"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print("✓ Health endpoint OK")

    def test_screener_endpoint(self):
        """Test /screener returns results"""
        # Get user token first
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=30
        )
        assert login_resp.status_code == 200
        token = login_resp.json().get("access_token")
        
        response = requests.get(
            f"{BASE_URL}/api/screener",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 20},
            timeout=30
        )
        assert response.status_code == 200, f"Screener failed: {response.text}"
        data = response.json()
        print(f"✓ Screener: results={len(data) if isinstance(data, list) else 'N/A'}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
