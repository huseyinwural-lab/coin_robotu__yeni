"""
Iteration 117: User Live Dashboard Pagination + Controlled Live Scanner Tests
- Tests pagination (limit/offset) for positions, trades, strategies endpoints
- Tests scanner runtime run endpoint with assisted mode
- Tests live-readiness endpoint for max_positions, daily_loss_limit_pct, symbol_integrity
"""
import os
import uuid
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    """Resolve BASE_URL from environment or frontend .env"""
    env_base = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if env_base:
        return env_base
    frontend_env = Path("/app/frontend/.env")
    if frontend_env.exists():
        for line in frontend_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


@pytest.fixture(scope="module")
def admin_headers():
    """Get admin authentication headers"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def user_headers(admin_headers):
    """Create and approve a new user, return auth headers"""
    email = f"iter117_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestIter117Pass!"
    
    # Register new user
    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert register.status_code == 200, f"Registration failed: {register.text}"
    user_id = register.json()["id"]
    
    # Approve user
    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=20,
    )
    assert approve.status_code == 200, f"User approval failed: {approve.text}"
    
    # Login
    login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert login.status_code == 200, f"User login failed: {login.text}"
    token = login.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


# ========== User Live Dashboard Pagination Tests ==========

class TestUserLivePositionsPagination:
    """Tests for /api/user/live/positions limit/offset pagination"""
    
    def test_positions_pagination_contract(self, user_headers):
        """GET /api/user/live/positions should return limit, offset, total_positions_count"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/positions",
            params={"limit": 3, "offset": 0},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Request failed: {response.text}"
        payload = response.json()
        
        # Pagination fields
        assert "limit" in payload, "Missing 'limit' in response"
        assert "offset" in payload, "Missing 'offset' in response"
        assert "total_positions_count" in payload, "Missing 'total_positions_count' in response"
        assert "positions_count" in payload, "Missing 'positions_count' in response"
        assert "positions" in payload, "Missing 'positions' in response"
        
        # Values check
        assert payload["limit"] == 3
        assert payload["offset"] == 0
        assert isinstance(payload["positions"], list)
        assert payload["positions_count"] <= 3
        print(f"Positions pagination OK: limit={payload['limit']}, offset={payload['offset']}, total={payload['total_positions_count']}")
    
    def test_positions_pagination_with_offset(self, user_headers):
        """Test positions endpoint with non-zero offset"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/positions",
            params={"limit": 5, "offset": 2},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["limit"] == 5
        assert payload["offset"] == 2
        print(f"Positions offset test OK: offset={payload['offset']}")


class TestUserLiveTradesPagination:
    """Tests for /api/user/live/trades limit/offset pagination"""
    
    def test_trades_pagination_contract(self, user_headers):
        """GET /api/user/live/trades should return limit, offset, total_trades_count"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/trades",
            params={"window": "24h", "limit": 5, "offset": 0},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Request failed: {response.text}"
        payload = response.json()
        
        # Pagination fields
        assert "limit" in payload, "Missing 'limit' in response"
        assert "offset" in payload, "Missing 'offset' in response"
        assert "total_trades_count" in payload, "Missing 'total_trades_count' in response"
        assert "trades_count" in payload, "Missing 'trades_count' in response"
        assert "items" in payload, "Missing 'items' in response"
        
        # Values check
        assert payload["limit"] == 5
        assert payload["offset"] == 0
        assert isinstance(payload["items"], list)
        assert payload["trades_count"] <= 5
        print(f"Trades pagination OK: limit={payload['limit']}, offset={payload['offset']}, total={payload['total_trades_count']}")
    
    def test_trades_pagination_with_offset(self, user_headers):
        """Test trades endpoint with non-zero offset"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/trades",
            params={"window": "24h", "limit": 10, "offset": 5},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["limit"] == 10
        assert payload["offset"] == 5
        print(f"Trades offset test OK: offset={payload['offset']}")


class TestUserLiveStrategiesPagination:
    """Tests for /api/user/live/strategies limit/offset pagination"""
    
    def test_strategies_pagination_contract(self, user_headers):
        """GET /api/user/live/strategies should return limit, offset, total_strategy_count"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/strategies",
            params={"window": "24h", "limit": 2, "offset": 0},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Request failed: {response.text}"
        payload = response.json()
        
        # Pagination fields
        assert "limit" in payload, "Missing 'limit' in response"
        assert "offset" in payload, "Missing 'offset' in response"
        assert "total_strategy_count" in payload, "Missing 'total_strategy_count' in response"
        assert "strategy_count" in payload, "Missing 'strategy_count' in response"
        assert "items" in payload, "Missing 'items' in response"
        
        # Values check
        assert payload["limit"] == 2
        assert payload["offset"] == 0
        assert isinstance(payload["items"], list)
        assert payload["strategy_count"] <= 2
        print(f"Strategies pagination OK: limit={payload['limit']}, offset={payload['offset']}, total={payload['total_strategy_count']}")
    
    def test_strategies_pagination_with_offset(self, user_headers):
        """Test strategies endpoint with non-zero offset"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/strategies",
            params={"window": "24h", "limit": 5, "offset": 1},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["limit"] == 5
        assert payload["offset"] == 1
        print(f"Strategies offset test OK: offset={payload['offset']}")


# ========== User Live Dashboard Regression Tests ==========

class TestUserLiveDashboardRegression:
    """Regression tests for existing user-live endpoints (should return 200)"""
    
    def test_summary_endpoint(self, user_headers):
        """GET /api/user/live/summary should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/summary",
            params={"window": "1h"},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Summary failed: {response.text}"
        payload = response.json()
        assert "window" in payload
        assert "generated_at" in payload
        print("Summary endpoint OK")
    
    def test_performance_endpoint(self, user_headers):
        """GET /api/user/live/performance should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/performance",
            params={"window": "24h"},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Performance failed: {response.text}"
        payload = response.json()
        assert "window" in payload
        print("Performance endpoint OK")
    
    def test_risk_endpoint(self, user_headers):
        """GET /api/user/live/risk should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/risk",
            params={"window": "24h"},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Risk failed: {response.text}"
        payload = response.json()
        assert "window" in payload
        print("Risk endpoint OK")
    
    def test_execution_quality_endpoint(self, user_headers):
        """GET /api/user/live/execution-quality should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/execution-quality",
            params={"window": "24h"},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Execution quality failed: {response.text}"
        payload = response.json()
        assert "window" in payload
        print("Execution quality endpoint OK")
    
    def test_daily_report_endpoint(self, user_headers):
        """GET /api/user/live/daily-report should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/daily-report",
            params={"window": "24h"},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Daily report failed: {response.text}"
        payload = response.json()
        assert "date" in payload
        print("Daily report endpoint OK")
    
    def test_daily_report_export_json(self, user_headers):
        """GET /api/user/live/daily-report/export?format=json should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/daily-report/export",
            params={"format": "json", "window": "24h"},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Daily report export json failed: {response.text}"
        print("Daily report export JSON OK")
    
    def test_daily_report_export_csv(self, user_headers):
        """GET /api/user/live/daily-report/export?format=csv should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/user/live/daily-report/export",
            params={"format": "csv", "window": "24h"},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Daily report export csv failed: {response.text}"
        assert "text/csv" in response.headers.get("content-type", "")
        print("Daily report export CSV OK")


# ========== Scanner Runtime Tests ==========

class TestScannerRuntimeRun:
    """Tests for controlled live scanner run scenarios"""
    
    def test_scanner_run_assisted_mode(self, user_headers):
        """POST /api/user/scanner/runtime/run with assisted mode and selected symbols"""
        # Use 10-20 symbols for controlled live test
        test_symbols = "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOTUSDT,AVAXUSDT,LINKUSDT,MATICUSDT"
        
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/runtime/run",
            params={
                "symbol_selection_mode": "manual_selection",
                "max_results": 20,
                "selected_symbols": test_symbols,
            },
            headers=user_headers,
            timeout=60,
        )
        assert response.status_code == 200, f"Scanner run failed: {response.text}"
        payload = response.json()
        
        # Verify run succeeded
        assert "run_id" in payload, "Missing run_id in response"
        assert "user_id" in payload, "Missing user_id in response"
        assert "decisions" in payload, "Missing decisions in response"
        assert "generated_at" in payload, "Missing generated_at in response"
        
        print(f"Scanner run OK: run_id={payload.get('run_id')}, decisions={len(payload.get('decisions', []))}")
    
    def test_scanner_run_all_market_symbols(self, user_headers):
        """POST /api/user/scanner/runtime/run with all_market_symbols mode"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/runtime/run",
            params={
                "symbol_selection_mode": "all_market_symbols",
                "max_results": 50,
            },
            headers=user_headers,
            timeout=60,
        )
        assert response.status_code == 200, f"Scanner run all_market failed: {response.text}"
        payload = response.json()
        assert "run_id" in payload
        print(f"Scanner run all_market_symbols OK: run_id={payload.get('run_id')}")
    
    def test_scanner_snapshot(self, user_headers):
        """GET /api/user/scanner/runtime/snapshot should return cached runtime snapshot"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/runtime/snapshot",
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Snapshot failed: {response.text}"
        # May be empty dict if no scan run yet
        print("Scanner snapshot endpoint OK")


# ========== Live Readiness Tests ==========

class TestLiveReadinessEndpoint:
    """Tests for /api/user/scanner/runtime/live-readiness endpoint"""
    
    def test_live_readiness_max_positions(self, user_headers):
        """live-readiness should contain max_positions=3"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/runtime/live-readiness",
            params={"window": "24h"},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Live readiness failed: {response.text}"
        payload = response.json()
        
        # Check max_risk_guard
        max_risk_guard = payload.get("max_risk_guard", {})
        assert max_risk_guard.get("max_positions") == 3, f"Expected max_positions=3, got {max_risk_guard.get('max_positions')}"
        print("Live readiness max_positions=3 OK")
    
    def test_live_readiness_daily_loss_limit(self, user_headers):
        """live-readiness should contain daily_loss_limit_pct=1.0"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/runtime/live-readiness",
            params={"window": "24h"},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        
        # Check max_risk_guard
        max_risk_guard = payload.get("max_risk_guard", {})
        assert max_risk_guard.get("daily_loss_limit_pct") == 1.0, f"Expected daily_loss_limit_pct=1.0, got {max_risk_guard.get('daily_loss_limit_pct')}"
        print("Live readiness daily_loss_limit_pct=1.0 OK")
    
    def test_live_readiness_symbol_integrity(self, user_headers):
        """live-readiness should contain symbol_integrity with ok field"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/runtime/live-readiness",
            params={"window": "24h"},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        
        # Check symbol_integrity
        symbol_integrity = payload.get("symbol_integrity", {})
        assert "ok" in symbol_integrity, f"Missing 'ok' field in symbol_integrity: {symbol_integrity}"
        assert isinstance(symbol_integrity.get("ok"), bool), "symbol_integrity.ok should be bool"
        print(f"Live readiness symbol_integrity.ok={symbol_integrity.get('ok')} OK")
    
    def test_live_readiness_full_structure(self, user_headers):
        """Verify full live-readiness response structure"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/runtime/live-readiness",
            params={"window": "24h"},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        
        # Required top-level fields
        required_fields = [
            "window",
            "generated_at",
            "symbol_integrity",
            "max_risk_guard",
            "execution_quality",
            "scanner_activity",
            "market_regime",
            "strategy_diversity",
            "emergency_stop",
            "first_live_test_params",
        ]
        for field in required_fields:
            assert field in payload, f"Missing required field: {field}"
        
        print("Live readiness full structure OK")


# ========== Scanner Daily Report Tests ==========

class TestScannerDailyReport:
    """Tests for scanner daily report endpoints"""
    
    def test_scanner_daily_report(self, user_headers):
        """GET /api/user/scanner/runtime/daily-report should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/runtime/daily-report",
            params={"window": "24h"},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Scanner daily report failed: {response.text}"
        payload = response.json()
        assert "date" in payload
        assert "window" in payload
        assert "scan" in payload
        assert "execution" in payload
        assert "risk" in payload
        print("Scanner daily report OK")
    
    def test_scanner_daily_report_export_csv(self, user_headers):
        """GET /api/user/scanner/runtime/daily-report/export?format=csv should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/runtime/daily-report/export",
            params={"format": "csv", "window": "24h"},
            headers=user_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Scanner daily report export csv failed: {response.text}"
        assert "text/csv" in response.headers.get("content-type", "")
        print("Scanner daily report export CSV OK")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
