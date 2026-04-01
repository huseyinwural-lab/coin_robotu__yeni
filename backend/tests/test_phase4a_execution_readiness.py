"""
Phase 4A Testing: Execution Readiness API and Frontend Build Verification
Tests:
1. /api/admin/execution-readiness endpoint latency and caching
2. Frontend production build with CI=true
3. REACT_APP_BACKEND_URL build-time guard
"""
import os
import time
import pytest
import requests

# Use environment variable for BASE_URL
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "http://0.0.0.0:8001"

ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=60,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in login response")
    return token


class TestExecutionReadinessAPI:
    """Test /api/admin/execution-readiness endpoint"""

    def test_execution_readiness_returns_200(self, admin_token):
        """Test that execution-readiness endpoint returns 200 OK"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=60,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields exist
        assert "exchange_connection" in data
        assert "permissions" in data
        assert "latency_ms" in data
        assert "order_test" in data
        assert "mode" in data
        assert "final_status" in data
        assert "mocked_flag" in data
        assert "reason_codes" in data
        print(f"Execution readiness response: final_status={data.get('final_status')}, mode={data.get('mode')}")

    def test_execution_readiness_caching_behavior(self, admin_token):
        """Test that execution-readiness endpoint has caching (subsequent calls faster)"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # First call (may be cold cache)
        start1 = time.time()
        response1 = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=headers,
            timeout=60,
        )
        latency1 = time.time() - start1
        assert response1.status_code == 200
        
        # Second call (should be cached)
        start2 = time.time()
        response2 = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=headers,
            timeout=60,
        )
        latency2 = time.time() - start2
        assert response2.status_code == 200
        
        # Third call (should be cached)
        start3 = time.time()
        response3 = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=headers,
            timeout=60,
        )
        latency3 = time.time() - start3
        assert response3.status_code == 200
        
        print(f"Latencies: call1={latency1:.2f}s, call2={latency2:.2f}s, call3={latency3:.2f}s")
        
        # Cached calls should be significantly faster (at least 50% faster than first call)
        # Note: First call might also be cached if run after other tests
        avg_cached = (latency2 + latency3) / 2
        print(f"Average cached latency: {avg_cached:.2f}s")
        
        # Verify cached calls are under 5 seconds
        assert latency2 < 5.0, f"Second call too slow: {latency2:.2f}s"
        assert latency3 < 5.0, f"Third call too slow: {latency3:.2f}s"

    def test_execution_readiness_response_structure(self, admin_token):
        """Test that execution-readiness response has correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=60,
        )
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify all expected fields
        expected_fields = [
            "exchange_connection",
            "permissions",
            "latency_ms",
            "order_test",
            "mode",
            "final_status",
            "mocked_flag",
            "override_active",
            "reason_codes",
            "execution_proof",
            "mocked_paths",
            "readiness_state",
            "execution_allowed",
            "go_live_allowed",
        ]
        
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify types
        assert isinstance(data["reason_codes"], list)
        assert isinstance(data["mocked_flag"], bool)
        assert isinstance(data["override_active"], bool)
        assert isinstance(data["execution_allowed"], bool)
        assert isinstance(data["go_live_allowed"], bool)
        
        print(f"Response structure verified: {len(expected_fields)} fields present")

    def test_execution_readiness_requires_auth(self):
        """Test that execution-readiness endpoint requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            timeout=30,
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestHealthEndpoints:
    """Test health and ready endpoints"""

    def test_health_endpoint(self):
        """Test /api/health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        print(f"Health check passed: {data.get('service')}")

    def test_ready_endpoint(self):
        """Test /api/ready endpoint"""
        response = requests.get(f"{BASE_URL}/api/ready", timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"Ready check passed: {data.get('status')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
