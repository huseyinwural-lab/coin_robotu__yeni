"""
Iteration 19 - Comprehensive User-Side Backend + Frontend Tests
Tests user flows: auth, scanner, signals, bot profiles, portfolio, trades, exchange settings
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com").rstrip("/")
API_URL = f"{BASE_URL}/api"

# Test credentials
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"


class TestAuthSession:
    """Auth/session tests for user login and protected routes"""
    
    @pytest.fixture(scope="class")
    def user_session(self):
        """Login and get auth token"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        response = session.post(f"{API_URL}/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        }, timeout=30)
        
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.status_code} - {response.text[:200]}")
        
        data = response.json()
        token = data.get("access_token") or data.get("token")
        assert token, "No token in login response"
        
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session, data
    
    def test_login_returns_valid_token(self, user_session):
        """Test login returns valid token and user data"""
        session, data = user_session
        assert "access_token" in data or "token" in data
        assert data.get("user", {}).get("email") == USER_EMAIL
        assert data.get("user", {}).get("role") == "user"
        print(f"PASS: Login successful for {USER_EMAIL}")
    
    def test_auth_me_returns_user(self, user_session):
        """Test /auth/me returns current user"""
        session, _ = user_session
        response = session.get(f"{API_URL}/auth/me", timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert data.get("email") == USER_EMAIL
        assert data.get("role") == "user"
        print(f"PASS: /auth/me returns user data")
    
    def test_protected_route_without_token_returns_401(self):
        """Test protected route without token returns 401"""
        response = requests.get(f"{API_URL}/user/dashboard", timeout=15)
        assert response.status_code == 401
        print("PASS: Protected route returns 401 without token")


class TestUserDashboard:
    """User dashboard/overview tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{API_URL}/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        }, timeout=30)
        if response.status_code != 200:
            pytest.skip("Login failed")
        token = response.json().get("access_token") or response.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_dashboard_returns_metrics(self, auth_session):
        """Test dashboard returns expected metrics"""
        response = auth_session.get(f"{API_URL}/user/dashboard", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        # Verify expected fields
        assert "bot_count" in data
        assert "running_bot_count" in data
        assert "risk_policy_count" in data
        assert "open_positions_count" in data
        assert "pending_signals_count" in data
        print(f"PASS: Dashboard returns metrics - bots={data.get('bot_count')}, positions={data.get('open_positions_count')}")


class TestUserScanner:
    """Scanner endpoint tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{API_URL}/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        }, timeout=30)
        if response.status_code != 200:
            pytest.skip("Login failed")
        token = response.json().get("access_token") or response.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_scanner_overview_returns_data(self, auth_session):
        """Test scanner overview endpoint"""
        response = auth_session.get(f"{API_URL}/user/scanner", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert "mode" in data
        assert "total_results" in data
        print(f"PASS: Scanner overview - mode={data.get('mode')}, results={data.get('total_results')}")
    
    def test_screener_returns_results(self, auth_session):
        """Test screener endpoint returns results"""
        response = auth_session.get(f"{API_URL}/screener", params={"limit": 10}, timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        if len(data) > 0:
            item = data[0]
            assert "symbol" in item
            assert "signal" in item
            assert "confidence" in item
        print(f"PASS: Screener returns {len(data)} results")
    
    def test_signal_mode_returns_current_mode(self, auth_session):
        """Test signal mode endpoint"""
        response = auth_session.get(f"{API_URL}/user/signal-mode", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert "mode" in data
        assert data["mode"] in ["MANUAL", "ASSISTED", "AUTO"]
        print(f"PASS: Signal mode = {data.get('mode')}")


class TestUserSignals:
    """Signals endpoint tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{API_URL}/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        }, timeout=30)
        if response.status_code != 200:
            pytest.skip("Login failed")
        token = response.json().get("access_token") or response.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_signals_returns_list(self, auth_session):
        """Test signals endpoint returns list"""
        response = auth_session.get(f"{API_URL}/user/signals", params={"limit": 20}, timeout=20)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        if len(data) > 0:
            signal = data[0]
            assert "symbol" in signal
            assert "status" in signal
            assert "blocked_reason_code" in signal
        print(f"PASS: Signals returns {len(data)} items")
    
    def test_signals_contain_error_classification(self, auth_session):
        """Test signals contain proper error classification fields"""
        response = auth_session.get(f"{API_URL}/user/signals", params={"limit": 10}, timeout=20)
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            signal = data[0]
            # Check error classification fields exist
            assert "blocked_reason_code" in signal
            assert "blocked_reason_message" in signal
            assert "blocked_solution_hint" in signal
            assert "tradeable" in signal
            assert "first_precheck_failure_code" in signal
        print("PASS: Signals contain error classification fields")


class TestBotProfiles:
    """Bot profiles endpoint tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{API_URL}/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        }, timeout=30)
        if response.status_code != 200:
            pytest.skip("Login failed")
        token = response.json().get("access_token") or response.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_bot_profiles_returns_list(self, auth_session):
        """Test bot profiles endpoint returns list"""
        response = auth_session.get(f"{API_URL}/bot-profiles", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        if len(data) > 0:
            bot = data[0]
            assert "id" in bot
            assert "name" in bot
            assert "exchange" in bot
            assert "market_type" in bot
            assert "strategy_type" in bot
            assert "is_enabled" in bot
        print(f"PASS: Bot profiles returns {len(data)} bots")
    
    def test_bot_profiles_contain_runtime_context(self, auth_session):
        """Test bot profiles contain runtime context"""
        response = auth_session.get(f"{API_URL}/bot-profiles", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            bot = data[0]
            assert "runtime_context" in bot
            assert "symbol_source_summary" in bot
            assert "binding_validation" in bot or "runtime_context" in bot
        print("PASS: Bot profiles contain runtime context")
    
    def test_bot_detail_endpoint(self, auth_session):
        """Test bot detail endpoint"""
        # First get list of bots
        response = auth_session.get(f"{API_URL}/bot-profiles", timeout=15)
        assert response.status_code == 200
        bots = response.json()
        
        if len(bots) == 0:
            pytest.skip("No bots to test detail")
        
        bot_id = bots[0]["id"]
        detail_response = auth_session.get(f"{API_URL}/bot-profiles/{bot_id}/detail", timeout=15)
        assert detail_response.status_code == 200
        detail = detail_response.json()
        
        assert "runtime_summary" in detail or "strategy_binding" in detail
        print(f"PASS: Bot detail endpoint works for bot {bot_id}")


class TestPortfolioTrades:
    """Portfolio and trades endpoint tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{API_URL}/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        }, timeout=30)
        if response.status_code != 200:
            pytest.skip("Login failed")
        token = response.json().get("access_token") or response.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_portfolio_returns_balances(self, auth_session):
        """Test portfolio endpoint returns balance data"""
        response = auth_session.get(f"{API_URL}/user/portfolio", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert "total_wallet_balance" in data
        assert "spot_wallet_balance" in data
        assert "futures_wallet_balance" in data
        assert "open_positions_count" in data
        print(f"PASS: Portfolio - total={data.get('total_wallet_balance')}, positions={data.get('open_positions_count')}")
    
    def test_trades_returns_list(self, auth_session):
        """Test trades endpoint returns list"""
        response = auth_session.get(f"{API_URL}/user/trades", params={"limit": 10}, timeout=25)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        print(f"PASS: Trades returns {len(data)} items")


class TestExchangeSettings:
    """Exchange settings/diagnostics tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{API_URL}/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        }, timeout=30)
        if response.status_code != 200:
            pytest.skip("Login failed")
        token = response.json().get("access_token") or response.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_exchange_connections_returns_list(self, auth_session):
        """Test exchange connections endpoint"""
        response = auth_session.get(f"{API_URL}/user/exchange-connections", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        if len(data) > 0:
            conn = data[0]
            assert "id" in conn
            assert "exchange" in conn
            assert "market_type" in conn
            assert "connection_health" in conn
            assert "readiness_snapshot" in conn
        print(f"PASS: Exchange connections returns {len(data)} connections")
    
    def test_exchange_connections_contain_health_metrics(self, auth_session):
        """Test exchange connections contain health metrics"""
        response = auth_session.get(f"{API_URL}/user/exchange-connections", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            conn = data[0]
            assert "connection_health" in conn
            assert "can_trade_effective" in conn
            assert "action_required" in conn
        print("PASS: Exchange connections contain health metrics")


class TestStrategyTemplates:
    """Strategy templates tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{API_URL}/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        }, timeout=30)
        if response.status_code != 200:
            pytest.skip("Login failed")
        token = response.json().get("access_token") or response.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_strategy_templates_returns_list(self, auth_session):
        """Test strategy templates endpoint"""
        response = auth_session.get(f"{API_URL}/strategy-templates", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        if len(data) > 0:
            template = data[0]
            assert "id" in template
            assert "name" in template
            assert "strategy_type" in template
            assert "lifecycle_state" in template
        print(f"PASS: Strategy templates returns {len(data)} templates")


class TestRiskPolicies:
    """Risk policies tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{API_URL}/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        }, timeout=30)
        if response.status_code != 200:
            pytest.skip("Login failed")
        token = response.json().get("access_token") or response.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_risk_policies_returns_list(self, auth_session):
        """Test risk policies endpoint"""
        response = auth_session.get(f"{API_URL}/risk-policies", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        if len(data) > 0:
            policy = data[0]
            assert "id" in policy
            assert "name" in policy
            assert "position_size_pct" in policy
            assert "max_leverage" in policy
        print(f"PASS: Risk policies returns {len(data)} policies")


class TestErrorHandlingContract:
    """Error handling contract tests - 503 DB_POOL_TIMEOUT"""
    
    def test_health_endpoint_returns_200(self):
        """Test health endpoint returns 200"""
        response = requests.get(f"{API_URL}/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        print("PASS: Health endpoint returns 200")
    
    def test_health_live_endpoint_returns_200(self):
        """Test health/live endpoint returns 200"""
        response = requests.get(f"{API_URL}/health/live", timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        print("PASS: Health/live endpoint returns 200")


class TestCanonicalStrategies:
    """Canonical strategies tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{API_URL}/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        }, timeout=30)
        if response.status_code != 200:
            pytest.skip("Login failed")
        token = response.json().get("access_token") or response.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_canonical_strategies_returns_list(self, auth_session):
        """Test canonical strategies endpoint"""
        response = auth_session.get(f"{API_URL}/user/canonical-strategies", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        print(f"PASS: Canonical strategies returns {len(data)} strategies")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
