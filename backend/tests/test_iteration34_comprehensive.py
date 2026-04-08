"""
Iteration 34 - Comprehensive Backend API Tests
Tests critical APIs for:
- Admin/User login
- User Scanner page critical controls and run flow
- User Signals page critical controls and table
- Admin Universe Monitor scanner engine controls
- Admin Strategy Allocation table/edit/normalize controls
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


class TestAuthenticationFlows:
    """Authentication endpoint tests"""
    
    def test_admin_login_success(self):
        """Test admin login with valid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15
        )
        print(f"Admin login response status: {response.status_code}")
        print(f"Admin login response: {response.text[:500] if response.text else 'empty'}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "user" in data or "email" in data, "Response should contain user data"
        
    def test_user_login_success(self):
        """Test user login with valid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=15
        )
        print(f"User login response status: {response.status_code}")
        print(f"User login response: {response.text[:500] if response.text else 'empty'}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "user" in data or "email" in data, "Response should contain user data"
        
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "invalid@test.com", "password": "wrongpassword"},
            timeout=15
        )
        print(f"Invalid login response status: {response.status_code}")
        
        assert response.status_code in [401, 400, 403], f"Expected 401/400/403, got {response.status_code}"


@pytest.fixture(scope="class")
def admin_session():
    """Get authenticated admin session"""
    session = requests.Session()
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    
    # Extract token from response
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


@pytest.fixture(scope="class")
def user_session():
    """Get authenticated user session"""
    session = requests.Session()
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
        timeout=15
    )
    if response.status_code != 200:
        pytest.skip(f"User login failed: {response.status_code}")
    
    # Extract token from response
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


class TestUserSignalsAPI:
    """User Signals page API tests"""
    
    def test_get_user_signals(self, user_session):
        """Test GET /api/user/signals endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/user/signals",
            params={"limit": 80},
            timeout=15
        )
        print(f"User signals response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Response can be array or object with items
        assert isinstance(data, (list, dict)), "Response should be list or dict"
        
    def test_get_user_signal_mode(self, user_session):
        """Test GET /api/user/signal-mode endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/user/signal-mode",
            timeout=15
        )
        print(f"Signal mode response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "mode" in data, "Response should contain mode field"
        
    def test_get_user_portfolio(self, user_session):
        """Test GET /api/user/portfolio endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/user/portfolio",
            timeout=15
        )
        print(f"Portfolio response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_user_trades(self, user_session):
        """Test GET /api/user/trades endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/user/trades",
            params={"limit": 50},
            timeout=15
        )
        print(f"Trades response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_bot_profiles(self, user_session):
        """Test GET /api/bot-profiles endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/bot-profiles",
            timeout=15
        )
        print(f"Bot profiles response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_scanner_status_contract(self, user_session):
        """Test GET /api/user/scanner/status-contract endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/user/scanner/status-contract",
            timeout=15
        )
        print(f"Status contract response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_scanner_engine_decision_map(self, user_session):
        """Test GET /api/user/scanner-engine/decision-map endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/user/scanner-engine/decision-map",
            timeout=15
        )
        print(f"Decision map response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestUserScannerAPI:
    """User Scanner page API tests"""
    
    def test_get_scanner_overview(self, user_session):
        """Test GET /api/user/scanner endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/user/scanner",
            timeout=15
        )
        print(f"Scanner overview response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_screener_results(self, user_session):
        """Test GET /api/screener endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/screener",
            params={"limit": 120},
            timeout=15
        )
        print(f"Screener results response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_scanner_automation(self, user_session):
        """Test GET /api/user/scanner/automation endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/user/scanner/automation",
            timeout=15
        )
        print(f"Scanner automation response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_scanner_engine_config(self, user_session):
        """Test GET /api/user/scanner-engine/config endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/user/scanner-engine/config",
            timeout=15
        )
        print(f"Scanner engine config response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_scanner_engine_last_run(self, user_session):
        """Test GET /api/user/scanner-engine/last-run endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/user/scanner-engine/last-run",
            timeout=15
        )
        print(f"Scanner engine last run response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_post_scanner_engine_run(self, user_session):
        """Test POST /api/user/scanner-engine/run endpoint"""
        response = user_session.post(
            f"{BASE_URL}/api/user/scanner-engine/run",
            json={
                "force_refresh": False,
                "reason": "test_scanner_engine_run"
            },
            timeout=30
        )
        print(f"Scanner engine run response status: {response.status_code}")
        
        # Accept 200 or 202 (async) or 429 (rate limited)
        assert response.status_code in [200, 202, 429], f"Expected 200/202/429, got {response.status_code}: {response.text}"
        
    def test_get_scheduler_next_run(self, user_session):
        """Test GET /api/user/live/scheduler/next-run endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/scheduler/next-run",
            timeout=15
        )
        print(f"Scheduler next run response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestAdminUniverseMonitorAPI:
    """Admin Universe Monitor page API tests"""
    
    def test_get_universe_monitor(self, admin_session):
        """Test GET /api/admin/universe-monitor endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/universe-monitor",
            params={"market_type": "spot", "scanner_mode": "ALL_MARKET_SYMBOLS", "top_n": 200},
            timeout=15
        )
        print(f"Universe monitor response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_universe_monitor_trends(self, admin_session):
        """Test GET /api/admin/universe-monitor/trends endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/universe-monitor/trends",
            params={"window": "24h"},
            timeout=15
        )
        print(f"Universe monitor trends response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_universe_monitor_breakdown(self, admin_session):
        """Test GET /api/admin/universe-monitor/breakdown endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/universe-monitor/breakdown",
            params={"window": "24h"},
            timeout=15
        )
        print(f"Universe monitor breakdown response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_universe_monitor_heatmap(self, admin_session):
        """Test GET /api/admin/universe-monitor/freshness-heatmap endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/universe-monitor/freshness-heatmap",
            params={"window": "24h"},
            timeout=15
        )
        print(f"Universe monitor heatmap response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_universe_monitor_rollout_status(self, admin_session):
        """Test GET /api/admin/universe-monitor/rollout/status endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/universe-monitor/rollout/status",
            timeout=15
        )
        print(f"Universe monitor rollout status response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_universe_monitor_fallback_events(self, admin_session):
        """Test GET /api/admin/universe-monitor/fallback-events endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/universe-monitor/fallback-events",
            params={"limit": 80},
            timeout=15
        )
        print(f"Universe monitor fallback events response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_admin_universe_runtime_summary(self, admin_session):
        """Test GET /api/admin/universe/runtime-summary endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/universe/runtime-summary",
            params={"scanner_mode": "ALL_MARKET_SYMBOLS", "top_n": 200},
            timeout=15
        )
        print(f"Admin universe runtime summary response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_admin_strategy_status_contract(self, admin_session):
        """Test GET /api/admin/strategy/status-contract endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/strategy/status-contract",
            timeout=15
        )
        print(f"Admin strategy status contract response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_admin_scanner_engine_config(self, admin_session):
        """Test GET /api/admin/universe-monitor/scanner-engine/config endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/universe-monitor/scanner-engine/config",
            timeout=15
        )
        print(f"Admin scanner engine config response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_admin_scanner_engine_last_run(self, admin_session):
        """Test GET /api/admin/universe-monitor/scanner-engine/last-run endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/universe-monitor/scanner-engine/last-run",
            timeout=15
        )
        print(f"Admin scanner engine last run response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_admin_scanner_engine_jobs(self, admin_session):
        """Test GET /api/admin/universe-monitor/scanner-engine/bot/jobs endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/universe-monitor/scanner-engine/bot/jobs",
            params={"limit": 20},
            timeout=15
        )
        print(f"Admin scanner engine jobs response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestAdminStrategyAllocationAPI:
    """Admin Strategy Allocation page API tests"""
    
    def test_get_strategy_allocation(self, admin_session):
        """Test GET /api/admin/strategy-allocation endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            timeout=15
        )
        print(f"Strategy allocation response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
    def test_get_strategy_allocation_summary(self, admin_session):
        """Test GET /api/admin/strategy-allocation/summary endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            timeout=15
        )
        print(f"Strategy allocation summary response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_strategy_allocation_state_history(self, admin_session):
        """Test GET /api/admin/strategy-allocation/state-history endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/strategy-allocation/state-history",
            params={"limit": 40},
            timeout=15
        )
        print(f"Strategy allocation state history response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_strategy_allocation_approval_requests(self, admin_session):
        """Test GET /api/admin/strategy-allocation/approval-requests endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            timeout=15
        )
        print(f"Strategy allocation approval requests response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_strategy_allocation_snapshots(self, admin_session):
        """Test GET /api/admin/strategy-allocation/snapshots endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/strategy-allocation/snapshots",
            timeout=15
        )
        print(f"Strategy allocation snapshots response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_post_strategy_allocation_normalize(self, admin_session):
        """Test POST /api/admin/strategy-allocation/normalize endpoint"""
        response = admin_session.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            json={
                "reason_note": "test_normalize_iteration34",
                "expected_revisions": {}
            },
            timeout=15
        )
        print(f"Strategy allocation normalize response status: {response.status_code}")
        
        # Accept 200 or 409 (revision conflict) or 400 (validation error)
        assert response.status_code in [200, 400, 409], f"Expected 200/400/409, got {response.status_code}: {response.text}"
        
    def test_post_strategy_allocation_rebalance_suggestions(self, admin_session):
        """Test POST /api/admin/strategy-allocation/rebalance-suggestions endpoint"""
        response = admin_session.post(
            f"{BASE_URL}/api/admin/strategy-allocation/rebalance-suggestions",
            json={"strategy_ids": []},
            timeout=15
        )
        print(f"Strategy allocation rebalance suggestions response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_post_strategy_allocation_whatif_simulation(self, admin_session):
        """Test POST /api/admin/strategy-allocation/what-if-simulation endpoint"""
        response = admin_session.post(
            f"{BASE_URL}/api/admin/strategy-allocation/what-if-simulation",
            json={"strategy_ids": []},
            timeout=15
        )
        print(f"Strategy allocation what-if simulation response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestHealthAndBasicEndpoints:
    """Basic health and status endpoints"""
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        print(f"Health endpoint response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
    def test_strategy_templates(self, user_session):
        """Test GET /api/strategy-templates endpoint"""
        response = user_session.get(
            f"{BASE_URL}/api/strategy-templates",
            timeout=15
        )
        print(f"Strategy templates response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
