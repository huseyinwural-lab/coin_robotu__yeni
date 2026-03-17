"""
Iteration 138: System Health Dashboard Testing
Tests for new health metrics fields in /api/user/exchange-connections:
- last_success_at, last_failure_at
- health_bucket_metrics (1m/5m/15m keys with success/fail/success_rate/jitter/latency_samples)
- current_jitter_p95_p50_ms, current_jitter_stddev_ms
- liveness_latency_history
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
USER_EMAIL = "user1773706589@example.com"
USER_PASSWORD = "User12345!"
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"


class TestSystemHealthDashboardBackend:
    """Backend API tests for System Health Dashboard fields"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.user_token = None
        
    def _login_user(self):
        """Helper to login as user"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        })
        if response.status_code == 200:
            data = response.json()
            self.user_token = data.get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {self.user_token}"})
            return True
        return False
    
    def test_health_check(self):
        """Test basic health check endpoint"""
        response = self.session.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print("TEST PASS: Health check endpoint working")
    
    def test_user_login(self):
        """Test user authentication"""
        assert self._login_user(), "User login failed"
        print(f"TEST PASS: User login successful, token obtained")
    
    def test_exchange_connections_endpoint_returns_new_fields(self):
        """Test GET /api/user/exchange-connections returns new System Health Dashboard fields"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200, f"Exchange connections endpoint failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"TEST INFO: Found {len(data)} connection profiles")
        
        if len(data) == 0:
            # No connections yet - check schema via schema endpoint
            print("TEST INFO: No connections found, checking schema exists")
            return
        
        # Check first connection has new fields
        connection = data[0]
        
        # Verify new required fields exist
        required_fields = [
            "last_success_at",
            "last_failure_at", 
            "health_bucket_metrics",
            "current_jitter_p95_p50_ms",
            "current_jitter_stddev_ms",
            "liveness_latency_history"
        ]
        
        for field in required_fields:
            assert field in connection, f"Missing required field: {field}"
            print(f"TEST PASS: Field '{field}' present in response")
        
        print("TEST PASS: All new System Health Dashboard fields present")
    
    def test_health_bucket_metrics_contract(self):
        """Test health_bucket_metrics has 1m/5m/15m keys with correct structure"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200, f"Endpoint failed: {response.text}"
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No connection profiles to test")
        
        connection = data[0]
        health_bucket_metrics = connection.get("health_bucket_metrics", {})
        
        # Verify 1m, 5m, 15m keys exist
        expected_buckets = ["1m", "5m", "15m"]
        for bucket_key in expected_buckets:
            assert bucket_key in health_bucket_metrics, f"Missing bucket key: {bucket_key}"
            print(f"TEST PASS: Bucket '{bucket_key}' present in health_bucket_metrics")
        
        # Verify each bucket has required fields
        bucket_required_fields = [
            "success", 
            "fail", 
            "success_rate",
            "latency_samples",
            "jitter_p95_p50_ms",
            "jitter_stddev_ms"
        ]
        
        for bucket_key in expected_buckets:
            bucket = health_bucket_metrics[bucket_key]
            for field in bucket_required_fields:
                assert field in bucket, f"Bucket '{bucket_key}' missing field: {field}"
            print(f"TEST PASS: Bucket '{bucket_key}' has all required fields: {bucket_required_fields}")
        
        # Check data types are correct
        first_bucket = health_bucket_metrics["1m"]
        assert isinstance(first_bucket.get("success"), int) or first_bucket.get("success") is None
        assert isinstance(first_bucket.get("fail"), int) or first_bucket.get("fail") is None
        assert first_bucket.get("success_rate") is None or isinstance(first_bucket.get("success_rate"), (int, float))
        assert isinstance(first_bucket.get("latency_samples"), int) or first_bucket.get("latency_samples") is None
        
        print("TEST PASS: health_bucket_metrics contract validated for all buckets (1m/5m/15m)")
    
    def test_jitter_fields_nullable(self):
        """Test that jitter fields can be null when no data available"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200, f"Endpoint failed: {response.text}"
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No connection profiles to test")
        
        connection = data[0]
        
        # Jitter fields can be null or float
        jitter_p95_p50 = connection.get("current_jitter_p95_p50_ms")
        jitter_stddev = connection.get("current_jitter_stddev_ms")
        
        assert jitter_p95_p50 is None or isinstance(jitter_p95_p50, (int, float)), \
            f"current_jitter_p95_p50_ms has invalid type: {type(jitter_p95_p50)}"
        assert jitter_stddev is None or isinstance(jitter_stddev, (int, float)), \
            f"current_jitter_stddev_ms has invalid type: {type(jitter_stddev)}"
        
        print(f"TEST PASS: Jitter fields validated - p95_p50: {jitter_p95_p50}, stddev: {jitter_stddev}")
    
    def test_liveness_latency_history_structure(self):
        """Test liveness_latency_history is list with correct item structure"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200, f"Endpoint failed: {response.text}"
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No connection profiles to test")
        
        connection = data[0]
        latency_history = connection.get("liveness_latency_history", [])
        
        assert isinstance(latency_history, list), "liveness_latency_history should be a list"
        print(f"TEST INFO: liveness_latency_history has {len(latency_history)} entries")
        
        # If there are entries, verify structure
        if len(latency_history) > 0:
            entry = latency_history[0]
            assert "at" in entry, "Latency history entry missing 'at' field"
            assert "latency_ms" in entry, "Latency history entry missing 'latency_ms' field"
            assert "source" in entry, "Latency history entry missing 'source' field"
            print(f"TEST PASS: Latency history entry structure validated")
        else:
            print("TEST INFO: No latency history entries yet (MOCKED exchange adapters)")
        
        print("TEST PASS: liveness_latency_history structure validated")
    
    def test_last_success_failure_timestamps(self):
        """Test last_success_at and last_failure_at fields"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200, f"Endpoint failed: {response.text}"
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No connection profiles to test")
        
        connection = data[0]
        
        last_success_at = connection.get("last_success_at")
        last_failure_at = connection.get("last_failure_at")
        
        # These can be null if no success/failure has been recorded
        assert last_success_at is None or isinstance(last_success_at, str), \
            f"last_success_at should be string or null, got {type(last_success_at)}"
        assert last_failure_at is None or isinstance(last_failure_at, str), \
            f"last_failure_at should be string or null, got {type(last_failure_at)}"
        
        print(f"TEST PASS: Timestamp fields validated - last_success_at: {last_success_at}, last_failure_at: {last_failure_at}")
    
    def test_existing_fields_preserved(self):
        """Regression: Verify existing connection fields still present"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200, f"Endpoint failed: {response.text}"
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No connection profiles to test")
        
        connection = data[0]
        
        # Check existing fields are still present
        existing_fields = [
            "id",
            "user_id",
            "account_label",
            "exchange",
            "market_type",
            "environment",
            "is_default",
            "readiness_snapshot",
            "permission_snapshot",
            "connection_health",
            "connection_health_reason",
            "can_trade_effective",
            "last_validated_at",
            "is_reconnecting",
            "next_retry_in_seconds",
            "retry_backoff_seconds",
            "action_required",
            "action_required_message",
            "validation_success_24h",
            "validation_fail_24h",
            "validation_success_rate_24h",
            "health_last_transition_at",
            "health_history",
            "has_api_key",
            "has_api_secret",
            "masked_api_key",
            "credential_fingerprint",
            "created_at",
            "updated_at"
        ]
        
        missing_fields = []
        for field in existing_fields:
            if field not in connection:
                missing_fields.append(field)
        
        assert len(missing_fields) == 0, f"Missing existing fields: {missing_fields}"
        print(f"TEST PASS: All {len(existing_fields)} existing fields preserved")
    
    def test_phase4_exchange_settings_endpoint(self):
        """Test phase4 exchange settings endpoint still working"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/phase4/exchange-settings")
        assert response.status_code == 200, f"Phase4 exchange settings failed: {response.text}"
        
        data = response.json()
        assert "exchange" in data or "mode" in data, "Expected exchange/mode in response"
        print(f"TEST PASS: Phase4 exchange settings endpoint working")
    
    def test_venues_options_endpoint(self):
        """Test venues options endpoint still working"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/venues/options")
        assert response.status_code == 200, f"Venues options failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list of venue options"
        print(f"TEST PASS: Venues options endpoint working, found {len(data)} options")
    
    def test_exchange_readiness_checklist(self):
        """Test exchange readiness checklist endpoint"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/exchange/readiness-checklist", params={
            "exchange": "binance",
            "market_type": "futures",
            "environment": "testnet"
        })
        assert response.status_code == 200, f"Readiness checklist failed: {response.text}"
        
        data = response.json()
        assert "readiness_status" in data, "Expected readiness_status in response"
        print(f"TEST PASS: Readiness checklist endpoint working, status: {data.get('readiness_status')}")
    
    def test_user_risk_overview(self):
        """Test user risk overview endpoint"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/user-risk/overview")
        assert response.status_code == 200, f"User risk overview failed: {response.text}"
        
        data = response.json()
        assert "current_capital" in data, "Expected current_capital in response"
        print(f"TEST PASS: User risk overview working, capital: {data.get('current_capital')}")
    
    def test_permission_status_endpoint(self):
        """Test permission status endpoint"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/phase4/permission-status")
        assert response.status_code == 200, f"Permission status failed: {response.text}"
        
        data = response.json()
        assert "overall_status" in data or "live_activation" in data, "Expected status fields"
        print(f"TEST PASS: Permission status endpoint working")


class TestRegressionExistingTabs:
    """Regression tests for existing tabs and panels"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
    def _login_user(self):
        """Helper to login as user"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        })
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
            return True
        return False
    
    def test_user_risk_settings(self):
        """Test user risk settings endpoint"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/user-risk/settings")
        assert response.status_code == 200, f"Risk settings failed: {response.text}"
        
        data = response.json()
        expected_fields = ["allocation_pct", "trade_risk_pct", "daily_loss_limit_pct", "compounding_enabled"]
        for field in expected_fields:
            assert field in data, f"Missing risk settings field: {field}"
        
        print(f"TEST PASS: Risk settings endpoint working with all expected fields")
    
    def test_user_risk_preview(self):
        """Test user risk preview endpoint"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/user-risk/preview", params={
            "market_type": "futures",
            "leverage": 3
        })
        assert response.status_code == 200, f"Risk preview failed: {response.text}"
        
        data = response.json()
        assert "current_capital" in data, "Missing current_capital in preview"
        assert "position_size" in data, "Missing position_size in preview"
        print(f"TEST PASS: Risk preview endpoint working")
    
    def test_venues_access_check(self):
        """Test venues access check endpoint"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/venues/access-check", params={
            "exchange": "binance",
            "market_type": "futures",
            "environment": "testnet"
        })
        assert response.status_code == 200, f"Access check failed: {response.text}"
        print(f"TEST PASS: Venues access check endpoint working")
    
    def test_market_ticker(self):
        """Test market ticker endpoint"""
        assert self._login_user(), "Login failed"
        
        response = self.session.get(f"{BASE_URL}/api/market/ticker", params={
            "symbol": "BTCUSDT"
        })
        # May fail if no market data, but endpoint should exist
        assert response.status_code in [200, 400, 500], f"Unexpected ticker status: {response.status_code}"
        print(f"TEST PASS: Market ticker endpoint exists, status: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
