"""
Iteration 35 - GO/NO-GO Final Test
Tests:
1. Auth login admin/user
2. User signals/scanner render APIs
3. Admin universe-monitor and strategy-allocation render APIs
4. API: /api/user/signal-mode, /api/user/scanner/automation, /api/admin/strategy-allocation, /api/admin/universe-monitor/trends
5. UI AUTO badges visibility
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com").rstrip("/")

# Test credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"


class TestAuthLogin:
    """Test authentication for admin and user"""
    
    def test_admin_login(self):
        """Test admin login returns access_token and role=super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Missing access_token in admin login response"
        assert data.get("role") == "super_admin" or data.get("user", {}).get("role") == "super_admin", f"Expected super_admin role, got: {data}"
        print(f"✓ Admin login successful - role: {data.get('role', data.get('user', {}).get('role'))}")
    
    def test_user_login(self):
        """Test user login returns access_token and role=user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=30
        )
        assert response.status_code == 200, f"User login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Missing access_token in user login response"
        print(f"✓ User login successful - role: {data.get('role', data.get('user', {}).get('role'))}")
    
    def test_invalid_login(self):
        """Test invalid credentials return 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": "invalid@test.com", "password": "wrongpassword"},
            timeout=30
        )
        assert response.status_code == 401, f"Expected 401 for invalid login, got: {response.status_code}"
        print("✓ Invalid login correctly returns 401")


class TestUserSignalsAPIs:
    """Test user signals and scanner APIs"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get user auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=30
        )
        assert response.status_code == 200, f"User login failed: {response.text}"
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_user_signal_mode(self):
        """Test GET /api/user/signal-mode returns mode"""
        response = requests.get(
            f"{BASE_URL}/api/user/signal-mode",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Signal mode failed: {response.text}"
        data = response.json()
        assert "mode" in data, f"Missing mode in response: {data}"
        print(f"✓ Signal mode API working - mode: {data.get('mode')}")
    
    def test_user_scanner_automation(self):
        """Test GET /api/user/scanner/automation returns automation config"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/automation",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Scanner automation failed: {response.text}"
        data = response.json()
        assert "auto_enabled" in data, f"Missing auto_enabled in response: {data}"
        print(f"✓ Scanner automation API working - auto_enabled: {data.get('auto_enabled')}")
    
    def test_user_signals_list(self):
        """Test GET /api/user/signals returns signals list"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=self.headers,
            params={"limit": 50},
            timeout=30
        )
        assert response.status_code == 200, f"Signals list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got: {type(data)}"
        print(f"✓ User signals API working - count: {len(data)}")
    
    def test_user_scanner_overview(self):
        """Test GET /api/user/scanner returns scanner overview"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Scanner overview failed: {response.text}"
        data = response.json()
        assert "mode" in data, f"Missing mode in scanner overview: {data}"
        print(f"✓ Scanner overview API working - mode: {data.get('mode')}")
    
    def test_user_scanner_engine_config(self):
        """Test GET /api/user/scanner-engine/config returns config"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner-engine/config",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Scanner engine config failed: {response.text}"
        data = response.json()
        assert "signal_mode" in data or "exchange" in data, f"Missing expected fields: {data}"
        print(f"✓ Scanner engine config API working - keys: {len(data)}")
    
    def test_user_scanner_engine_last_run(self):
        """Test GET /api/user/scanner-engine/last-run returns last run data"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner-engine/last-run",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Scanner engine last run failed: {response.text}"
        data = response.json()
        assert "status" in data, f"Missing status in last run: {data}"
        print(f"✓ Scanner engine last run API working - status: {data.get('status')}")
    
    def test_user_scanner_engine_decision_map(self):
        """Test GET /api/user/scanner-engine/decision-map returns decision map"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner-engine/decision-map",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Decision map failed: {response.text}"
        data = response.json()
        assert "items" in data or "count" in data, f"Missing expected fields: {data}"
        print(f"✓ Decision map API working - count: {data.get('count', len(data.get('items', {})))}")


class TestAdminAPIs:
    """Test admin universe-monitor and strategy-allocation APIs"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_admin_strategy_allocation(self):
        """Test GET /api/admin/strategy-allocation returns allocations"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Strategy allocation failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got: {type(data)}"
        print(f"✓ Strategy allocation API working - count: {len(data)}")
    
    def test_admin_universe_monitor_trends(self):
        """Test GET /api/admin/universe-monitor/trends returns trends"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/trends",
            headers=self.headers,
            params={"window": "24h"},
            timeout=30
        )
        assert response.status_code == 200, f"Universe monitor trends failed: {response.text}"
        data = response.json()
        assert "points" in data or "latest" in data or isinstance(data, dict), f"Unexpected response: {data}"
        print(f"✓ Universe monitor trends API working - keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
    
    def test_admin_universe_monitor(self):
        """Test GET /api/admin/universe-monitor returns monitor data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor",
            headers=self.headers,
            params={"market_type": "spot", "scanner_mode": "ALL_MARKET_SYMBOLS", "top_n": 50},
            timeout=30
        )
        assert response.status_code == 200, f"Universe monitor failed: {response.text}"
        data = response.json()
        assert isinstance(data, dict), f"Expected dict, got: {type(data)}"
        print(f"✓ Universe monitor API working - keys: {len(data)}")
    
    def test_admin_universe_monitor_scanner_engine_config(self):
        """Test GET /api/admin/universe-monitor/scanner-engine/config returns config"""
        response = requests.get(
            f"{BASE_URL}/api/admin/universe-monitor/scanner-engine/config",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Scanner engine config failed: {response.text}"
        data = response.json()
        assert isinstance(data, dict), f"Expected dict, got: {type(data)}"
        print(f"✓ Admin scanner engine config API working - keys: {len(data)}")
    
    def test_admin_strategy_allocation_summary(self):
        """Test GET /api/admin/strategy-allocation/summary returns summary"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Strategy allocation summary failed: {response.text}"
        data = response.json()
        assert isinstance(data, dict), f"Expected dict, got: {type(data)}"
        print(f"✓ Strategy allocation summary API working - keys: {len(data)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
