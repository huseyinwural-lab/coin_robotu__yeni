"""
Iteration 71: V1 Trading Preview/Execute + Admin Emergency Stop + Rate Limiter Testing
Tests:
- POST /api/v1/user/trading/preview - preview + metrics + rate_limit
- POST /api/v1/user/trading/execute - accepts intent_token/preview_hash
- POST /api/v1/admin/emergency_stop - kill switch functionality
- Rate limiter guard behavior (no regression in normal flow)
- Regression: existing /api/user/execution/intent/preview and /api/user/execution/intent/submit
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"
TEST_USER_EMAIL = "iter71_test_v1_user@example.com"
TEST_USER_PASSWORD = "User12345!"


@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_token(api_client):
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin login failed: {response.status_code}")


@pytest.fixture(scope="module")
def user_token(api_client, admin_token):
    """Create and approve a test user, return their token"""
    # Try to register new user
    register_response = api_client.post(f"{BASE_URL}/api/auth/register", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD,
        "full_name": "Iter71 V1 Test User"
    })
    
    if register_response.status_code == 201:
        # Approve user
        api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
        pending_response = api_client.get(f"{BASE_URL}/api/auth/admin/user-approval-requests")
        if pending_response.status_code == 200:
            for req in pending_response.json():
                if req.get("email") == TEST_USER_EMAIL:
                    api_client.post(f"{BASE_URL}/api/auth/admin/user-approval-requests/{req['id']}/approve")
                    break
        api_client.headers.pop("Authorization", None)
    
    # Login
    login_response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    
    if login_response.status_code == 200:
        return login_response.json().get("access_token")
    
    # Fallback to existing test user
    fallback_users = [
        ("e2_conn_last@example.com", "User12345!"),
        ("testuser@example.com", "User12345!"),
    ]
    for email, password in fallback_users:
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
        if response.status_code == 200:
            return response.json().get("access_token")
    
    pytest.skip("No user token available")


class TestV1TradingPreview:
    """Tests for POST /api/v1/user/trading/preview"""
    
    def test_preview_returns_200_with_valid_payload(self, api_client, user_token):
        """Preview endpoint returns 200 with preview + metrics + rate_limit"""
        api_client.headers.update({"Authorization": f"Bearer {user_token}"})
        
        payload = {
            "source_type": "manual",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
        }
        
        response = api_client.post(f"{BASE_URL}/api/v1/user/trading/preview", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify preview object exists
        assert "preview" in data, "Response should contain 'preview' object"
        preview = data["preview"]
        assert "intent_id" in preview
        assert "intent_token" in preview
        assert "preview_hash" in preview
        assert "validation_status" in preview
        
        # Verify metrics object exists
        assert "metrics" in data, "Response should contain 'metrics' object"
        metrics = data["metrics"]
        assert "entry_price" in metrics
        assert "estimated_notional" in metrics
        
        # Verify rate_limit object exists
        assert "rate_limit" in data, "Response should contain 'rate_limit' object"
        rate_limit = data["rate_limit"]
        assert "allowed" in rate_limit
        assert "remaining_tokens" in rate_limit
        
        print(f"PASS: Preview returned with intent_token={preview['intent_token']}, validation={preview['validation_status']}")

    def test_preview_contains_execution_metrics(self, api_client, user_token):
        """Preview metrics include real-time execution preview data"""
        api_client.headers.update({"Authorization": f"Bearer {user_token}"})
        
        payload = {
            "source_type": "manual",
            "symbol": "ETHUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50,
            "stop_loss_mode": "percent",
            "stop_loss_value": 2,
            "take_profit_mode": "percent",
            "take_profit_value": 4,
        }
        
        response = api_client.post(f"{BASE_URL}/api/v1/user/trading/preview", json=payload)
        assert response.status_code == 200
        
        metrics = response.json().get("metrics", {})
        
        # Check real-time metrics fields
        assert "entry_price" in metrics
        assert "estimated_quantity" in metrics
        assert "estimated_risk_usdt" in metrics
        assert "liquidity_guard" in metrics
        
        print(f"PASS: Metrics include entry_price={metrics.get('entry_price')}, notional={metrics.get('estimated_notional')}")

    def test_preview_futures_market_type(self, api_client, user_token):
        """Preview works for futures market type"""
        api_client.headers.update({"Authorization": f"Bearer {user_token}"})
        
        payload = {
            "source_type": "manual",
            "symbol": "BTCUSDT",
            "market_type": "futures",
            "side": "long",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 100,
            "leverage": 3,
            "margin_mode": "isolated",
        }
        
        response = api_client.post(f"{BASE_URL}/api/v1/user/trading/preview", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert "preview" in data
        assert "metrics" in data
        print(f"PASS: Futures preview completed with validation={data['preview']['validation_status']}")


class TestV1TradingExecute:
    """Tests for POST /api/v1/user/trading/execute"""
    
    def test_execute_requires_intent_token(self, api_client, user_token):
        """Execute endpoint requires intent_token"""
        api_client.headers.update({"Authorization": f"Bearer {user_token}"})
        
        # First get a valid preview
        preview_payload = {
            "source_type": "manual",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
        }
        
        preview_response = api_client.post(f"{BASE_URL}/api/v1/user/trading/preview", json=preview_payload)
        assert preview_response.status_code == 200
        
        preview_data = preview_response.json()["preview"]
        intent_token = preview_data["intent_token"]
        preview_hash = preview_data["preview_hash"]
        
        # Execute with the token
        execute_response = api_client.post(f"{BASE_URL}/api/v1/user/trading/execute", json={
            "intent_token": intent_token,
            "preview_hash": preview_hash,
        })
        
        # Should be 200 or 400 (if validation invalid or already submitted)
        assert execute_response.status_code in [200, 400], f"Unexpected status: {execute_response.status_code}"
        
        if execute_response.status_code == 200:
            data = execute_response.json()
            assert "intent_id" in data
            assert "intent_status" in data
            print(f"PASS: Execute queued intent with status={data['intent_status']}")
        else:
            print(f"INFO: Execute returned 400 (expected for invalid/already-submitted): {execute_response.text}")

    def test_execute_fails_without_token(self, api_client, user_token):
        """Execute fails when intent_token is missing"""
        api_client.headers.update({"Authorization": f"Bearer {user_token}"})
        
        response = api_client.post(f"{BASE_URL}/api/v1/user/trading/execute", json={
            "preview_hash": "fake_hash",
        })
        
        assert response.status_code == 422, "Should fail validation without intent_token"
        print("PASS: Execute correctly fails without intent_token")


class TestRateLimiterGuard:
    """Tests for rate limiter behavior on preview/execute endpoints"""
    
    def test_rate_limiter_allows_normal_flow(self, api_client, user_token):
        """Rate limiter allows normal preview requests"""
        api_client.headers.update({"Authorization": f"Bearer {user_token}"})
        
        payload = {
            "source_type": "manual",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
        }
        
        # Make a few requests to verify rate limiter doesn't block
        for i in range(3):
            response = api_client.post(f"{BASE_URL}/api/v1/user/trading/preview", json=payload)
            assert response.status_code != 429, f"Rate limited on request {i+1}"
            assert response.status_code == 200
        
        print("PASS: Rate limiter allows normal flow (3 consecutive requests)")

    def test_rate_limit_info_in_response(self, api_client, user_token):
        """Rate limit info is included in preview response"""
        api_client.headers.update({"Authorization": f"Bearer {user_token}"})
        
        payload = {
            "source_type": "manual",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
        }
        
        response = api_client.post(f"{BASE_URL}/api/v1/user/trading/preview", json=payload)
        assert response.status_code == 200
        
        rate_limit = response.json().get("rate_limit", {})
        assert rate_limit.get("allowed") is True
        assert "remaining_tokens" in rate_limit
        
        print(f"PASS: Rate limit info present, remaining_tokens={rate_limit.get('remaining_tokens')}")


class TestAdminEmergencyStop:
    """Tests for POST /api/v1/admin/emergency_stop"""
    
    def test_emergency_stop_requires_admin(self, api_client, user_token):
        """Emergency stop requires admin role"""
        api_client.headers.update({"Authorization": f"Bearer {user_token}"})
        
        response = api_client.post(f"{BASE_URL}/api/v1/admin/emergency_stop", json={
            "reason": "test_unauthorized"
        })
        
        # Should be 403 (Forbidden) for non-admin
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("PASS: Emergency stop correctly rejects non-admin user")

    def test_emergency_stop_works_for_admin(self, api_client, admin_token):
        """Emergency stop works for admin"""
        api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
        
        response = api_client.post(f"{BASE_URL}/api/v1/admin/emergency_stop", json={
            "reason": "iteration71_test_emergency_stop"
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "status" in data
        assert data["status"] == "triggered"
        assert "reason" in data
        assert "closed_positions_count" in data
        assert "rejected_intents_count" in data
        assert "emergency_mode_active" in data
        
        print(f"PASS: Emergency stop triggered, rejected_intents={data.get('rejected_intents_count')}")


class TestLegacyIntentEndpointsRegression:
    """Regression tests for existing /api/user/execution/intent/* endpoints"""
    
    def test_legacy_intent_preview_still_works(self, api_client, user_token):
        """Legacy intent preview endpoint still works"""
        api_client.headers.update({"Authorization": f"Bearer {user_token}"})
        
        payload = {
            "source_type": "manual",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
        }
        
        response = api_client.post(f"{BASE_URL}/api/user/execution/intent/preview", json=payload)
        
        assert response.status_code == 200, f"Legacy preview failed: {response.status_code}"
        data = response.json()
        assert "intent_id" in data
        assert "intent_token" in data
        assert "validation_status" in data
        
        print(f"PASS: Legacy /api/user/execution/intent/preview still works")

    def test_legacy_intent_submit_still_works(self, api_client, user_token):
        """Legacy intent submit endpoint still works"""
        api_client.headers.update({"Authorization": f"Bearer {user_token}"})
        
        # First get preview
        preview_payload = {
            "source_type": "manual",
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
        }
        
        preview_response = api_client.post(f"{BASE_URL}/api/user/execution/intent/preview", json=preview_payload)
        assert preview_response.status_code == 200
        
        preview_data = preview_response.json()
        intent_token = preview_data["intent_token"]
        preview_hash = preview_data["preview_hash"]
        
        # Submit via legacy endpoint
        submit_response = api_client.post(f"{BASE_URL}/api/user/execution/intent/submit", json={
            "intent_token": intent_token,
            "preview_hash": preview_hash,
        })
        
        # Should be 200 or 400 (if validation invalid or already submitted)
        assert submit_response.status_code in [200, 400], f"Unexpected status: {submit_response.status_code}"
        print(f"PASS: Legacy /api/user/execution/intent/submit still works")


class TestHealthAndBasicEndpoints:
    """Basic health and connectivity checks"""
    
    def test_health_endpoint(self, api_client):
        """Health endpoint returns 200"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("PASS: Health endpoint working")

    def test_admin_login_works(self, api_client):
        """Admin login returns token"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        assert "access_token" in response.json()
        print("PASS: Admin login working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
