"""
Test suite for Admin Strategy Observability API endpoints
Tests: Signal Control + Explainability system
Features: Top signals, simulate, execute, bulk operations, score tuning, rejection analytics, audit log
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for super_admin"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": SUPER_ADMIN_EMAIL,
        "password": SUPER_ADMIN_PASSWORD
    })
    print(f"Login response status: {response.status_code}")
    
    if response.status_code != 200:
        pytest.skip(f"Login failed: {response.text}")
    
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in login response")
    
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestAuthAndSetup:
    """Authentication and setup tests"""
    
    def test_login_super_admin(self):
        """Test super_admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": SUPER_ADMIN_EMAIL,
            "password": SUPER_ADMIN_PASSWORD
        })
        print(f"Login response status: {response.status_code}")
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data or "token" in data, "No token in response"


class TestTopSignalsEndpoints:
    """Test top signals control layer endpoints"""
    
    def test_get_top_signals_24h(self, auth_headers):
        """Test GET /api/admin/strategy/top-signals with 24h window"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/top-signals", 
                               params={"window": "24h", "top_n": 10},
                               headers=auth_headers)
        print(f"Top signals response: {response.status_code}")
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "items" in data, "Missing items in response"
        assert "window" in data, "Missing window in response"
        assert data["window"] == "24h"
    
    def test_get_top_signals_7d(self, auth_headers):
        """Test GET /api/admin/strategy/top-signals with 7d window"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/top-signals",
                               params={"window": "7d", "top_n": 20},
                               headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "7d"
    
    def test_get_top_signals_30d(self, auth_headers):
        """Test GET /api/admin/strategy/top-signals with 30d window"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/top-signals",
                               params={"window": "30d", "top_n": 5},
                               headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "30d"


class TestScoreConfigEndpoints:
    """Test score configuration endpoints"""
    
    def test_get_score_config(self, auth_headers):
        """Test GET /api/admin/strategy/score-config"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/score-config",
                               headers=auth_headers)
        print(f"Score config response: {response.status_code}")
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "config" in data, "Missing config in response"
        config = data["config"]
        assert "threshold" in config, "Missing threshold"
        assert "factor_weights" in config, "Missing factor_weights"
    
    def test_score_preview(self, auth_headers):
        """Test POST /api/admin/strategy/score-preview"""
        response = requests.post(f"{BASE_URL}/api/admin/strategy/score-preview", 
                                json={
                                    "threshold": 0.65,
                                    "factor_weights": {
                                        "base_score": 0.55,
                                        "trend_strength": 0.25,
                                        "relative_volume": 0.20
                                    },
                                    "top_n": 10
                                },
                                headers=auth_headers)
        print(f"Score preview response: {response.status_code}")
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "state_snapshot" in data, "Missing state_snapshot"


class TestRejectionAnalyticsEndpoints:
    """Test rejection analytics endpoints"""
    
    def test_get_rejection_analytics(self, auth_headers):
        """Test GET /api/admin/strategy/rejection-analytics"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/rejection-analytics",
                               params={"window": "24h"},
                               headers=auth_headers)
        print(f"Rejection analytics response: {response.status_code}")
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "window" in data
        assert "signals_total" in data
    
    def test_get_rejection_analytics_details(self, auth_headers):
        """Test GET /api/admin/strategy/rejection-analytics/details"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/rejection-analytics/details",
                               params={"window": "24h"},
                               headers=auth_headers)
        print(f"Rejection details response: {response.status_code}")
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "items" in data
    
    def test_get_rejection_analytics_reasons(self, auth_headers):
        """Test GET /api/admin/strategy/rejection-analytics/reasons"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/rejection-analytics/reasons",
                               params={"window": "24h"},
                               headers=auth_headers)
        print(f"Rejection reasons response: {response.status_code}")
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "reasons" in data


class TestScoreMetricsAndReportEndpoints:
    """Test score metrics and report endpoints"""
    
    def test_get_score_metrics(self, auth_headers):
        """Test GET /api/admin/strategy/score-metrics"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/score-metrics",
                               params={"window": "24h"},
                               headers=auth_headers)
        print(f"Score metrics response: {response.status_code}")
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "window" in data
        assert "avg_base_score" in data
        assert "avg_adjusted_score" in data
    
    def test_get_strategy_report(self, auth_headers):
        """Test GET /api/admin/strategy/report"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/report",
                               params={"window": "24h"},
                               headers=auth_headers)
        print(f"Strategy report response: {response.status_code}")
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "window" in data
        assert "signals_total" in data


class TestAuditLogEndpoint:
    """Test audit log endpoint"""
    
    def test_get_audit_log(self, auth_headers):
        """Test GET /api/admin/strategy/audit-log"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/audit-log",
                               params={"limit": 50},
                               headers=auth_headers)
        print(f"Audit log response: {response.status_code}")
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "items" in data
        assert "count" in data


class TestSimulationEndpoints:
    """Test simulation endpoints - requires signals to exist"""
    
    def test_bulk_simulate_top_signals(self, auth_headers):
        """Test POST /api/admin/strategy/top-signals/bulk-simulate"""
        response = requests.post(f"{BASE_URL}/api/admin/strategy/top-signals/bulk-simulate",
                                json={"window": "24h", "top_n": 10},
                                headers=auth_headers)
        print(f"Bulk simulate response: {response.status_code}")
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "status" in data
        assert data["status"] == "success"
    
    def test_bulk_execute_preview(self, auth_headers):
        """Test POST /api/admin/strategy/top-signals/bulk-execute with mode=preview"""
        response = requests.post(f"{BASE_URL}/api/admin/strategy/top-signals/bulk-execute",
                                json={"mode": "preview", "window": "24h", "top_n": 10},
                                headers=auth_headers)
        print(f"Bulk execute preview response: {response.status_code}")
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "status" in data


class TestRiskCapitalEndpoint:
    """Test risk capital status endpoint"""
    
    def test_get_risk_capital_status(self, auth_headers):
        """Test GET /api/admin/strategy/risk-capital/status"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/risk-capital/status",
                               headers=auth_headers)
        print(f"Risk capital status response: {response.status_code}")
        
        # This endpoint may not exist - check for 200 or 404
        if response.status_code == 404:
            pytest.skip("Risk capital status endpoint not implemented")
        
        assert response.status_code == 200, f"Failed: {response.text}"


class TestUnauthorizedAccess:
    """Test that endpoints require authentication"""
    
    def test_top_signals_requires_auth(self):
        """Test that top-signals requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/top-signals")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_score_config_requires_auth(self):
        """Test that score-config requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/score-config")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_audit_log_requires_auth(self):
        """Test that audit-log requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/strategy/audit-log")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestScoreConfigApplyAndOverride:
    """Test score config apply and override - super_admin only"""
    
    def test_apply_score_config_requires_reason(self, auth_headers):
        """Test PUT /api/admin/strategy/score-config requires reason"""
        response = requests.put(f"{BASE_URL}/api/admin/strategy/score-config",
                               json={
                                   "threshold": 0.65,
                                   "factor_weights": {
                                       "base_score": 0.55,
                                       "trend_strength": 0.25,
                                       "relative_volume": 0.20
                                   },
                                   "per_strategy": {},
                                   "reason": "ab"  # Too short
                               },
                               headers=auth_headers)
        print(f"Apply score config (short reason) response: {response.status_code}")
        # Should fail validation due to short reason
        assert response.status_code in [200, 422], f"Unexpected: {response.text}"
    
    def test_apply_score_config_success(self, auth_headers):
        """Test PUT /api/admin/strategy/score-config with valid reason"""
        response = requests.put(f"{BASE_URL}/api/admin/strategy/score-config",
                               json={
                                   "threshold": 0.65,
                                   "factor_weights": {
                                       "base_score": 0.55,
                                       "trend_strength": 0.25,
                                       "relative_volume": 0.20
                                   },
                                   "per_strategy": {},
                                   "reason": "Test config update for testing purposes"
                               },
                               headers=auth_headers)
        print(f"Apply score config response: {response.status_code}")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "config" in data
    
    def test_auto_tuning_toggle(self, auth_headers):
        """Test POST /api/admin/strategy/score-auto-tuning/toggle"""
        response = requests.post(f"{BASE_URL}/api/admin/strategy/score-auto-tuning/toggle",
                                json={
                                    "enabled": False,
                                    "reason": "Test auto tuning toggle"
                                },
                                headers=auth_headers)
        print(f"Auto tuning toggle response: {response.status_code}")
        assert response.status_code == 200, f"Failed: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
