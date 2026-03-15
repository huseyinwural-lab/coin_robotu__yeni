"""
Iteration 56 - Platform Kapanış Paketi Faz-1 (Admin finalization) Tests
Tests for Admin Positions Monitor, Portfolio Risk, Execution Queue pages
Tests operational state handling (loading/empty/error) and filter/summary visibility
"""

import os
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
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


class TestAdminAuthentication:
    """Admin authentication flow"""

    def test_admin_login(self):
        """Test admin login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login/admin", json={
            "email": os.environ.get("TEST_ADMIN_EMAIL", ""),
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "")
        }, timeout=20)
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "access_token missing in response"
        assert len(data["access_token"]) > 0, "access_token should not be empty"


@pytest.fixture
def admin_headers():
    """Get admin auth headers"""
    response = requests.post(f"{BASE_URL}/api/auth/login/admin", json={
        "email": os.environ.get("TEST_ADMIN_EMAIL", ""),
        "password": os.environ.get("TEST_ADMIN_PASSWORD", "")
    }, timeout=20)
    if response.status_code == 200:
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    pytest.skip("Could not authenticate admin")


class TestAdminPositionsMonitor:
    """Admin Positions Monitor endpoint tests"""

    def test_positions_monitor_returns_200(self, admin_headers):
        """GET /api/admin/positions-monitor should return 200"""
        response = requests.get(f"{BASE_URL}/api/admin/positions-monitor", headers=admin_headers)
        assert response.status_code == 200, f"positions-monitor failed: {response.text}"

    def test_positions_monitor_response_structure(self, admin_headers):
        """positions-monitor response should have required fields"""
        response = requests.get(f"{BASE_URL}/api/admin/positions-monitor", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "generated_at" in data, "generated_at field missing"
        assert "open_positions" in data, "open_positions field missing"
        assert "cluster_exposure" in data, "cluster_exposure field missing"
        assert "risk_level" in data, "risk_level field missing"
        assert "forced_liquidation_risk" in data, "forced_liquidation_risk field missing"
        
        # Validate types
        assert isinstance(data["open_positions"], list), "open_positions should be a list"
        assert isinstance(data["cluster_exposure"], dict), "cluster_exposure should be a dict"
        assert data["risk_level"] in ["LOW", "MEDIUM", "HIGH"], f"Invalid risk_level: {data['risk_level']}"
        assert isinstance(data["forced_liquidation_risk"], (int, float)), "forced_liquidation_risk should be numeric"

    def test_positions_monitor_open_positions_fields(self, admin_headers):
        """Each open position should have required fields"""
        response = requests.get(f"{BASE_URL}/api/admin/positions-monitor", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        # If there are open positions, validate their structure
        if len(data["open_positions"]) > 0:
            position = data["open_positions"][0]
            expected_fields = ["position_id", "symbol", "size", "entry_price", "current_price", "unrealized_pnl", "leverage"]
            for field in expected_fields:
                assert field in position, f"Missing field {field} in open position"


class TestAdminPortfolioRisk:
    """Admin Portfolio Risk endpoint tests"""

    def test_portfolio_risk_limits_returns_200(self, admin_headers):
        """GET /api/admin/portfolio-risk/limits should return 200"""
        response = requests.get(f"{BASE_URL}/api/admin/portfolio-risk/limits", headers=admin_headers)
        assert response.status_code == 200, f"portfolio-risk/limits failed: {response.text}"

    def test_portfolio_risk_limits_structure(self, admin_headers):
        """portfolio-risk/limits should have all limit fields"""
        response = requests.get(f"{BASE_URL}/api/admin/portfolio-risk/limits", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        expected_fields = [
            "max_portfolio_leverage",
            "max_symbol_exposure",
            "max_cluster_exposure",
            "max_strategy_exposure",
            "max_single_trade_risk",
            "max_intraday_drawdown",
            "max_total_drawdown"
        ]
        for field in expected_fields:
            assert field in data, f"Missing limit field: {field}"
            assert isinstance(data[field], (int, float)), f"{field} should be numeric"

    def test_portfolio_risk_clusters_returns_200(self, admin_headers):
        """GET /api/admin/portfolio-risk/clusters should return 200"""
        response = requests.get(f"{BASE_URL}/api/admin/portfolio-risk/clusters", headers=admin_headers)
        assert response.status_code == 200, f"portfolio-risk/clusters failed: {response.text}"

    def test_portfolio_risk_clusters_structure(self, admin_headers):
        """Each cluster should have required fields"""
        response = requests.get(f"{BASE_URL}/api/admin/portfolio-risk/clusters", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list), "clusters should be a list"
        if len(data) > 0:
            cluster = data[0]
            expected_fields = ["cluster_id", "symbols", "cluster_type", "correlation_score", "risk_weight"]
            for field in expected_fields:
                assert field in cluster, f"Missing cluster field: {field}"

    def test_portfolio_risk_dashboard_returns_200(self, admin_headers):
        """GET /api/admin/portfolio-risk should return 200"""
        response = requests.get(f"{BASE_URL}/api/admin/portfolio-risk", headers=admin_headers)
        assert response.status_code == 200, f"portfolio-risk dashboard failed: {response.text}"

    def test_portfolio_risk_dashboard_structure(self, admin_headers):
        """portfolio-risk dashboard should have exposure and alert fields"""
        response = requests.get(f"{BASE_URL}/api/admin/portfolio-risk", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "timestamp" in data, "timestamp field missing"
        assert "total_exposure" in data, "total_exposure field missing"
        assert "cluster_exposure" in data, "cluster_exposure field missing"
        assert "strategy_exposure" in data, "strategy_exposure field missing"


class TestAdminExecutionQueue:
    """Admin Execution Queue endpoint tests"""

    def test_execution_queue_all_filter_returns_200(self, admin_headers):
        """GET /api/admin/execution-queue?status_filter=all should return 200"""
        response = requests.get(f"{BASE_URL}/api/admin/execution-queue", 
                               params={"status_filter": "all", "limit": 200},
                               headers=admin_headers)
        assert response.status_code == 200, f"execution-queue all failed: {response.text}"

    def test_execution_queue_queued_filter(self, admin_headers):
        """GET /api/admin/execution-queue?status_filter=QUEUED should return 200"""
        response = requests.get(f"{BASE_URL}/api/admin/execution-queue",
                               params={"status_filter": "QUEUED", "limit": 100},
                               headers=admin_headers)
        assert response.status_code == 200

    def test_execution_queue_released_filter(self, admin_headers):
        """GET /api/admin/execution-queue?status_filter=RELEASED should return 200"""
        response = requests.get(f"{BASE_URL}/api/admin/execution-queue",
                               params={"status_filter": "RELEASED", "limit": 100},
                               headers=admin_headers)
        assert response.status_code == 200

    def test_execution_queue_rejected_filter(self, admin_headers):
        """GET /api/admin/execution-queue?status_filter=REJECTED should return 200"""
        response = requests.get(f"{BASE_URL}/api/admin/execution-queue",
                               params={"status_filter": "REJECTED", "limit": 100},
                               headers=admin_headers)
        assert response.status_code == 200

    def test_execution_queue_cancelled_filter(self, admin_headers):
        """GET /api/admin/execution-queue?status_filter=CANCELLED should return 200"""
        response = requests.get(f"{BASE_URL}/api/admin/execution-queue",
                               params={"status_filter": "CANCELLED", "limit": 100},
                               headers=admin_headers)
        assert response.status_code == 200

    def test_execution_queue_item_structure(self, admin_headers):
        """Each execution queue item should have required fields"""
        response = requests.get(f"{BASE_URL}/api/admin/execution-queue",
                               params={"status_filter": "all", "limit": 10},
                               headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list), "execution-queue should return a list"
        if len(data) > 0:
            item = data[0]
            expected_fields = ["id", "user_id", "symbol", "market_type", "side", "notional", "status", "created_at"]
            for field in expected_fields:
                assert field in item, f"Missing queue item field: {field}"

    def test_execution_queue_risk_flags_field(self, admin_headers):
        """Execution queue items should have risk_flags field"""
        response = requests.get(f"{BASE_URL}/api/admin/execution-queue",
                               params={"status_filter": "all", "limit": 10},
                               headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            item = data[0]
            assert "risk_flags" in item, "risk_flags field missing"
            assert isinstance(item["risk_flags"], list), "risk_flags should be a list"

    def test_execution_queue_intent_type_field(self, admin_headers):
        """Execution queue items should have intent_type field"""
        response = requests.get(f"{BASE_URL}/api/admin/execution-queue",
                               params={"status_filter": "all", "limit": 10},
                               headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            item = data[0]
            assert "intent_type" in item, "intent_type field missing"


class TestAdminEndpointSecurity:
    """Security tests for admin endpoints"""

    def test_positions_monitor_requires_auth(self):
        """positions-monitor should require authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/positions-monitor")
        assert response.status_code in [401, 403], "positions-monitor should require auth"

    def test_portfolio_risk_requires_auth(self):
        """portfolio-risk should require authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/portfolio-risk")
        assert response.status_code in [401, 403], "portfolio-risk should require auth"

    def test_execution_queue_requires_auth(self):
        """execution-queue should require authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/execution-queue")
        assert response.status_code in [401, 403], "execution-queue should require auth"
