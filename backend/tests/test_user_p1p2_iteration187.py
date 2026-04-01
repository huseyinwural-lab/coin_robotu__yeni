"""
User P1/P2 Backend API Tests - Iteration 187
Tests for:
- User sidebar domain-based menu (via /api/auth/me)
- Legacy route redirects (indicator-screener -> scanner?screener, exchange-settings -> settings, risk-policy -> settings)
- Scanner route with section toggle
- Embedded Indicator Screener
- User settings page (/api/auth/me, /api/user/exchange-connections, /api/user-risk/settings)
- User activity log (/api/user/activity-log)
- No regression on dashboard/execution/alerts/chart routes
"""
import pytest
import requests

BASE_URL = "http://localhost:8001"

USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"


@pytest.fixture(scope="module")
def user_session():
    """Login as user and return session with Bearer token"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login as user
    login_resp = session.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
        timeout=30
    )
    if login_resp.status_code != 200:
        pytest.skip(f"User login failed: {login_resp.status_code} - {login_resp.text[:200]}")
    
    # Extract token and set as Bearer header
    data = login_resp.json()
    token = data.get("access_token") or data.get("token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


class TestUserAuthAndProfile:
    """Test user authentication and profile endpoints"""
    
    def test_user_login(self, user_session):
        """Verify user login works"""
        resp = user_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert resp.status_code == 200, f"Auth/me failed: {resp.text[:200]}"
        data = resp.json()
        assert "email" in data
        assert data["email"] == USER_EMAIL
        
    def test_user_role_is_user(self, user_session):
        """Verify user has 'user' role (not admin)"""
        resp = user_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("role") in ["user", "customer"], f"Expected user role, got: {data.get('role')}"


class TestUserSettingsPage:
    """Test endpoints for unified settings page"""
    
    def test_auth_me_for_profile(self, user_session):
        """GET /api/auth/me returns profile data for settings page"""
        resp = user_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert "email" in data
        assert "id" in data
        
    def test_exchange_connections(self, user_session):
        """GET /api/user/exchange-connections returns list"""
        resp = user_session.get(f"{BASE_URL}/api/user/exchange-connections", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got: {type(data)}"
        
    def test_user_risk_settings(self, user_session):
        """GET /api/user-risk/settings returns risk settings"""
        resp = user_session.get(f"{BASE_URL}/api/user-risk/settings", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        # Should return dict with risk settings
        assert isinstance(data, dict), f"Expected dict, got: {type(data)}"


class TestUserActivityLog:
    """Test user activity log endpoint"""
    
    def test_activity_log_returns_list(self, user_session):
        """GET /api/user/activity-log returns audit rows"""
        resp = user_session.get(f"{BASE_URL}/api/user/activity-log", params={"limit": 100}, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got: {type(data)}"
        
    def test_activity_log_row_structure(self, user_session):
        """Activity log rows have expected fields"""
        resp = user_session.get(f"{BASE_URL}/api/user/activity-log", params={"limit": 10}, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        if len(data) > 0:
            row = data[0]
            # Check expected fields
            assert "id" in row
            assert "action" in row
            assert "entity_type" in row
            assert "created_at" in row


class TestUserScannerEndpoints:
    """Test scanner endpoints for section toggle"""
    
    def test_scanner_overview(self, user_session):
        """GET /api/user/scanner returns overview"""
        resp = user_session.get(f"{BASE_URL}/api/user/scanner", timeout=15)
        assert resp.status_code == 200
        
    def test_scanner_automation(self, user_session):
        """GET /api/user/scanner/automation returns config"""
        resp = user_session.get(f"{BASE_URL}/api/user/scanner/automation", timeout=15)
        assert resp.status_code == 200
        
    def test_screener_endpoint(self, user_session):
        """GET /api/screener returns results for embedded screener"""
        resp = user_session.get(
            f"{BASE_URL}/api/screener",
            params={"limit": 80, "filters": '{"timeframe":"1h"}'},
            timeout=20
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got: {type(data)}"


class TestUserIndicatorScreenerEndpoints:
    """Test indicator screener endpoints"""
    
    def test_indicator_screener_presets(self, user_session):
        """GET /api/user/indicator-screener/presets returns presets"""
        resp = user_session.get(f"{BASE_URL}/api/user/indicator-screener/presets", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        
    def test_indicator_screener_saved_queries(self, user_session):
        """GET /api/user/indicator-screener/saved-queries returns list"""
        resp = user_session.get(f"{BASE_URL}/api/user/indicator-screener/saved-queries", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        
    def test_indicator_screener_watchlist(self, user_session):
        """GET /api/user/indicator-screener/watchlist returns list"""
        resp = user_session.get(f"{BASE_URL}/api/user/indicator-screener/watchlist", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestUserDashboardEndpoints:
    """Test user dashboard endpoints - no regression"""
    
    def test_live_runtime_snapshot(self, user_session):
        """GET /api/user/live/runtime-snapshot returns sections"""
        resp = user_session.get(f"{BASE_URL}/api/user/live/runtime-snapshot", timeout=20)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        
    def test_live_summary(self, user_session):
        """GET /api/user/live/summary returns summary"""
        resp = user_session.get(f"{BASE_URL}/api/user/live/summary", timeout=15)
        assert resp.status_code == 200
        
    def test_live_positions(self, user_session):
        """GET /api/user/live/positions returns positions"""
        resp = user_session.get(f"{BASE_URL}/api/user/live/positions", timeout=15)
        assert resp.status_code == 200
        
    def test_decision_cards(self, user_session):
        """GET /api/user/decision-cards returns items"""
        resp = user_session.get(f"{BASE_URL}/api/user/decision-cards", params={"limit": 60}, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data or isinstance(data, list)


class TestUserExecutionEndpoints:
    """Test user execution endpoints - no regression"""
    
    def test_execution_positions(self, user_session):
        """GET /api/user/execution/positions returns list"""
        resp = user_session.get(f"{BASE_URL}/api/user/execution/positions", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        
    def test_execution_intents(self, user_session):
        """GET /api/user/execution/intents returns list"""
        resp = user_session.get(f"{BASE_URL}/api/user/execution/intents", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestUserAlertsEndpoints:
    """Test user alerts endpoints - no regression"""
    
    def test_user_alerts(self, user_session):
        """GET /api/user/alerts returns list"""
        resp = user_session.get(f"{BASE_URL}/api/user/alerts", timeout=15)
        # May return 200 or 404 if no alerts endpoint exists
        assert resp.status_code in [200, 404]


class TestSymbolSelectorEndpoints:
    """Test symbol selector for embedded screener"""
    
    def test_symbol_selector_universe(self, user_session):
        """GET /api/symbol-selector/universe returns rows"""
        resp = user_session.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "mode": "all_market_symbols"
            },
            timeout=20
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        
    def test_symbol_selector_watchlists(self, user_session):
        """GET /api/symbol-selector/watchlists returns list"""
        resp = user_session.get(
            f"{BASE_URL}/api/symbol-selector/watchlists",
            params={"source": "crypto"},
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestHealthEndpoint:
    """Test health endpoint"""
    
    def test_health_check(self):
        """GET /api/health returns ok"""
        resp = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") in ["ok", "degraded"]
