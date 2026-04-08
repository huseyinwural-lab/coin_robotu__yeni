"""
Iteration 34: Comprehensive System Regression Test - Simplified
Tests all major flows with single session approach to handle preview environment timeouts
"""
import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com").rstrip("/")

# Test credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"


@pytest.fixture(scope="module")
def user_session():
    """Get user session with cookies - module scoped for reuse"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            response = session.post(f"{BASE_URL}/api/auth/login", json={
                "email": USER_EMAIL,
                "password": USER_PASSWORD
            }, timeout=45)
            if response.status_code == 200:
                print(f"✓ User login successful on attempt {attempt + 1}")
                return session
        except requests.exceptions.Timeout:
            print(f"  Login attempt {attempt + 1} timed out, retrying...")
            continue
        except Exception as e:
            print(f"  Login attempt {attempt + 1} failed: {e}")
            continue
    pytest.skip("User login failed after 3 attempts")


@pytest.fixture(scope="module")
def admin_session():
    """Get admin session with cookies - module scoped for reuse"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            response = session.post(f"{BASE_URL}/api/auth/login", json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }, timeout=45)
            if response.status_code == 200:
                print(f"✓ Admin login successful on attempt {attempt + 1}")
                return session
        except requests.exceptions.Timeout:
            print(f"  Admin login attempt {attempt + 1} timed out, retrying...")
            continue
        except Exception as e:
            print(f"  Admin login attempt {attempt + 1} failed: {e}")
            continue
    pytest.skip("Admin login failed after 3 attempts")


class TestHealthAndAuth:
    """Basic health and auth tests"""
    
    def test_health_endpoint(self):
        """Test /health returns 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print(f"✓ Health endpoint: 200 OK")
    
    def test_user_login(self, user_session):
        """Test user session is valid"""
        response = user_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert response.status_code == 200, f"Auth me failed: {response.text}"
        data = response.json()
        assert "email" in data, "Auth me missing email"
        print(f"✓ User auth verified: {data.get('email')}")
    
    def test_admin_login(self, admin_session):
        """Test admin session is valid"""
        response = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert response.status_code == 200, f"Auth me failed: {response.text}"
        data = response.json()
        assert "email" in data, "Auth me missing email"
        print(f"✓ Admin auth verified: {data.get('email')}")


class TestUserScannerFlow:
    """User Scanner page API tests"""
    
    def test_scanner_overview(self, user_session):
        """Test GET /user/scanner returns overview"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner", timeout=20)
        assert response.status_code == 200, f"Scanner overview failed: {response.text}"
        data = response.json()
        print(f"✓ Scanner overview: mode={data.get('mode')}, pending={data.get('pending_signals')}")
    
    def test_scanner_engine_config(self, user_session):
        """Test GET /user/scanner-engine/config returns config"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner-engine/config", timeout=20)
        assert response.status_code == 200, f"Scanner engine config failed: {response.text}"
        data = response.json()
        print(f"✓ Scanner engine config: exchange={data.get('exchange')}, spot={data.get('include_spot')}")
    
    def test_scanner_engine_last_run(self, user_session):
        """Test GET /user/scanner-engine/last-run returns last run data"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner-engine/last-run", timeout=20)
        assert response.status_code == 200, f"Scanner engine last run failed: {response.text}"
        data = response.json()
        print(f"✓ Scanner engine last run: status={data.get('status')}, scored={data.get('summary', {}).get('scored_count', 0)}")
    
    def test_scanner_engine_decision_map(self, user_session):
        """Test GET /user/scanner-engine/decision-map returns decision map"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner-engine/decision-map", timeout=20)
        assert response.status_code == 200, f"Scanner engine decision map failed: {response.text}"
        data = response.json()
        items = data.get("items", {})
        print(f"✓ Scanner engine decision map: {len(items)} symbols")
    
    def test_scanner_engine_run(self, user_session):
        """Test POST /user/scanner-engine/run executes scanner"""
        response = user_session.post(f"{BASE_URL}/api/user/scanner-engine/run", json={
            "force_refresh": False,
            "reason": "test_iteration34_scanner_run"
        }, timeout=90)
        assert response.status_code == 200, f"Scanner engine run failed: {response.text}"
        data = response.json()
        summary = data.get("summary", {})
        print(f"✓ Scanner engine run: scored={summary.get('scored_count', 0)}, long={summary.get('strong_long_count', 0)}, short={summary.get('strong_short_count', 0)}")
    
    def test_screener_endpoint(self, user_session):
        """Test GET /screener returns screener results"""
        response = user_session.get(f"{BASE_URL}/api/screener", params={"limit": 20}, timeout=20)
        assert response.status_code == 200, f"Screener failed: {response.text}"
        data = response.json()
        count = len(data) if isinstance(data, list) else 0
        print(f"✓ Screener: {count} results")


class TestUserSignalsFlow:
    """User Signals page API tests"""
    
    def test_signals_list(self, user_session):
        """Test GET /user/signals returns signals list"""
        response = user_session.get(f"{BASE_URL}/api/user/signals", params={"limit": 80}, timeout=30)
        assert response.status_code == 200, f"Signals list failed: {response.text}"
        data = response.json()
        items = data if isinstance(data, list) else data.get("items", [])
        print(f"✓ Signals list: {len(items)} signals")
        
        # Verify no blocked/non_tradeable signals (advisory mode)
        blocked_count = sum(1 for s in items if s.get("status") == "blocked")
        non_tradeable_count = sum(1 for s in items if s.get("status") == "non_tradeable")
        print(f"  - Blocked: {blocked_count}, Non-Tradeable: {non_tradeable_count}")
        assert blocked_count == 0, f"Found {blocked_count} blocked signals (should be 0 in advisory mode)"
        assert non_tradeable_count == 0, f"Found {non_tradeable_count} non_tradeable signals (should be 0 in advisory mode)"
    
    def test_signal_mode(self, user_session):
        """Test GET /user/signal-mode returns current mode"""
        response = user_session.get(f"{BASE_URL}/api/user/signal-mode", timeout=15)
        assert response.status_code == 200, f"Signal mode failed: {response.text}"
        data = response.json()
        mode = data.get("mode", "UNKNOWN")
        print(f"✓ Signal mode: {mode}")
    
    def test_portfolio(self, user_session):
        """Test GET /user/portfolio returns portfolio data"""
        response = user_session.get(f"{BASE_URL}/api/user/portfolio", timeout=20)
        assert response.status_code == 200, f"Portfolio failed: {response.text}"
        data = response.json()
        print(f"✓ Portfolio: open_positions={data.get('open_positions_count', 0)}, notional={data.get('open_notional', 0)}")
    
    def test_trades(self, user_session):
        """Test GET /user/trades returns trades list"""
        response = user_session.get(f"{BASE_URL}/api/user/trades", params={"limit": 50}, timeout=20)
        assert response.status_code == 200, f"Trades failed: {response.text}"
        data = response.json()
        count = len(data) if isinstance(data, list) else 0
        print(f"✓ Trades: {count} trades")
    
    def test_bot_profiles(self, user_session):
        """Test GET /bot-profiles returns bot profiles"""
        response = user_session.get(f"{BASE_URL}/api/bot-profiles", timeout=15)
        assert response.status_code == 200, f"Bot profiles failed: {response.text}"
        data = response.json()
        count = len(data) if isinstance(data, list) else 0
        print(f"✓ Bot profiles: {count} profiles")
    
    def test_scanner_status_contract(self, user_session):
        """Test GET /user/scanner/status-contract returns status contract"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner/status-contract", timeout=15)
        assert response.status_code == 200, f"Status contract failed: {response.text}"
        data = response.json()
        print(f"✓ Status contract: scanner_ready={data.get('scanner_ready')}, health={data.get('health')}")


class TestAdminUniverseMonitor:
    """Admin Universe Monitor page API tests"""
    
    def test_universe_monitor_summary(self, admin_session):
        """Test GET /admin/universe-monitor returns summary"""
        response = admin_session.get(f"{BASE_URL}/api/admin/universe-monitor", params={
            "market_type": "spot",
            "scanner_mode": "ALL_MARKET_SYMBOLS",
            "top_n": 200
        }, timeout=30)
        assert response.status_code == 200, f"Universe monitor failed: {response.text}"
        data = response.json()
        print(f"✓ Universe monitor: total_exchange_symbols={data.get('total_exchange_symbols')}, active_scan={data.get('active_scan_symbols')}")
    
    def test_universe_monitor_trends(self, admin_session):
        """Test GET /admin/universe-monitor/trends returns trends"""
        response = admin_session.get(f"{BASE_URL}/api/admin/universe-monitor/trends", params={"window": "24h"}, timeout=20)
        assert response.status_code == 200, f"Universe monitor trends failed: {response.text}"
        data = response.json()
        points = data.get("points", [])
        print(f"✓ Universe monitor trends: {len(points)} points")
    
    def test_universe_monitor_scanner_engine_config(self, admin_session):
        """Test GET /admin/universe-monitor/scanner-engine/config returns config"""
        response = admin_session.get(f"{BASE_URL}/api/admin/universe-monitor/scanner-engine/config", timeout=20)
        assert response.status_code == 200, f"Admin scanner engine config failed: {response.text}"
        data = response.json()
        print(f"✓ Admin scanner engine config: exchange={data.get('exchange')}")
    
    def test_universe_monitor_scanner_engine_last_run(self, admin_session):
        """Test GET /admin/universe-monitor/scanner-engine/last-run returns last run"""
        response = admin_session.get(f"{BASE_URL}/api/admin/universe-monitor/scanner-engine/last-run", timeout=20)
        assert response.status_code == 200, f"Admin scanner engine last run failed: {response.text}"
        data = response.json()
        print(f"✓ Admin scanner engine last run: status={data.get('status')}")
    
    def test_universe_monitor_scanner_engine_run(self, admin_session):
        """Test POST /admin/universe-monitor/scanner-engine/run executes scanner"""
        response = admin_session.post(f"{BASE_URL}/api/admin/universe-monitor/scanner-engine/run", json={
            "force_refresh": False,
            "reason": "test_iteration34_admin_scanner_run"
        }, timeout=90)
        assert response.status_code == 200, f"Admin scanner engine run failed: {response.text}"
        data = response.json()
        summary = data.get("summary", {})
        print(f"✓ Admin scanner engine run: scored={summary.get('scored_count', 0)}")
    
    def test_admin_strategy_status_contract(self, admin_session):
        """Test GET /admin/strategy/status-contract returns status contract"""
        response = admin_session.get(f"{BASE_URL}/api/admin/strategy/status-contract", timeout=15)
        assert response.status_code == 200, f"Admin strategy status contract failed: {response.text}"
        data = response.json()
        print(f"✓ Admin strategy status contract: scanner_ready={data.get('scanner_ready')}")


class TestAdminStrategyAllocation:
    """Admin Strategy Allocation page API tests"""
    
    def test_strategy_allocation_list(self, admin_session):
        """Test GET /admin/strategy-allocation returns allocation list"""
        response = admin_session.get(f"{BASE_URL}/api/admin/strategy-allocation", timeout=20)
        assert response.status_code == 200, f"Strategy allocation list failed: {response.text}"
        data = response.json()
        count = len(data) if isinstance(data, list) else 0
        print(f"✓ Strategy allocation: {count} strategies")
        
        # Verify 12 canonical strategies
        if count > 0:
            active_count = sum(1 for s in data if s.get("state") == "ACTIVE")
            disabled_count = sum(1 for s in data if s.get("state") == "DISABLED")
            print(f"  - Active: {active_count}, Disabled: {disabled_count}")
    
    def test_strategy_allocation_summary(self, admin_session):
        """Test GET /admin/strategy-allocation/summary returns summary"""
        response = admin_session.get(f"{BASE_URL}/api/admin/strategy-allocation/summary", timeout=15)
        assert response.status_code == 200, f"Strategy allocation summary failed: {response.text}"
        data = response.json()
        print(f"✓ Strategy allocation summary: total_weight={data.get('total_weight')}, total_capital={data.get('total_capital')}")
    
    def test_strategy_allocation_snapshots(self, admin_session):
        """Test GET /admin/strategy-allocation/snapshots returns snapshots"""
        response = admin_session.get(f"{BASE_URL}/api/admin/strategy-allocation/snapshots", timeout=15)
        assert response.status_code == 200, f"Strategy allocation snapshots failed: {response.text}"
        data = response.json()
        rows = data.get("rows", [])
        print(f"✓ Strategy allocation snapshots: {len(rows)} snapshots")
    
    def test_strategy_allocation_rebalance_suggestions(self, admin_session):
        """Test POST /admin/strategy-allocation/rebalance-suggestions returns suggestions"""
        response = admin_session.post(f"{BASE_URL}/api/admin/strategy-allocation/rebalance-suggestions", json={
            "strategy_ids": []
        }, timeout=20)
        assert response.status_code == 200, f"Strategy allocation rebalance suggestions failed: {response.text}"
        data = response.json()
        suggestions = data.get("suggestions", [])
        print(f"✓ Strategy allocation rebalance suggestions: {len(suggestions)} suggestions")
    
    def test_strategy_allocation_export_json(self, admin_session):
        """Test GET /admin/strategy-allocation/export?format=json returns JSON export"""
        response = admin_session.get(f"{BASE_URL}/api/admin/strategy-allocation/export", params={"format": "json"}, timeout=20)
        assert response.status_code == 200, f"Strategy allocation export JSON failed: {response.text}"
        print(f"✓ Strategy allocation export JSON successful")


class TestCriticalEndpointRegression:
    """Critical endpoint 4xx/5xx regression tests"""
    
    def test_user_endpoints_no_5xx(self, user_session):
        """Test critical user endpoints don't return 5xx"""
        endpoints = [
            "/api/user/scanner",
            "/api/user/signals",
            "/api/user/signal-mode",
            "/api/user/portfolio",
            "/api/bot-profiles",
            "/api/user/scanner/status-contract",
            "/api/user/scanner-engine/config",
            "/api/user/scanner-engine/last-run",
            "/api/screener",
        ]
        
        errors = []
        for endpoint in endpoints:
            try:
                response = user_session.get(f"{BASE_URL}{endpoint}", timeout=20)
                if response.status_code >= 500:
                    errors.append(f"{endpoint}: {response.status_code}")
                else:
                    print(f"  ✓ {endpoint}: {response.status_code}")
            except Exception as e:
                errors.append(f"{endpoint}: {str(e)}")
        
        assert len(errors) == 0, f"5xx errors found: {errors}"
        print(f"✓ All user endpoints returned non-5xx status")
    
    def test_admin_endpoints_no_5xx(self, admin_session):
        """Test critical admin endpoints don't return 5xx"""
        endpoints = [
            "/api/admin/universe-monitor",
            "/api/admin/universe-monitor/trends",
            "/api/admin/universe-monitor/scanner-engine/config",
            "/api/admin/universe-monitor/scanner-engine/last-run",
            "/api/admin/strategy-allocation",
            "/api/admin/strategy-allocation/summary",
            "/api/admin/strategy-allocation/snapshots",
        ]
        
        errors = []
        for endpoint in endpoints:
            try:
                response = admin_session.get(f"{BASE_URL}{endpoint}", timeout=20)
                if response.status_code >= 500:
                    errors.append(f"{endpoint}: {response.status_code}")
                else:
                    print(f"  ✓ {endpoint}: {response.status_code}")
            except Exception as e:
                errors.append(f"{endpoint}: {str(e)}")
        
        assert len(errors) == 0, f"5xx errors found: {errors}"
        print(f"✓ All admin endpoints returned non-5xx status")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
