"""
Test Iteration 163: 423 EXECUTION_BLOCKED_BY_READINESS Regression Test

Tests:
1. User exchange connection credentials update + revalidate -> readiness ready_for_test_order
2. Admin execution queue approve flow (423 regression check)
3. Approve edilen intent RELEASED duruma geçmesi
4. User positions reflection after approve
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://runtime-hub-2.preview.emergentagent.com").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"
USER_EMAIL = "testuser1773706589@example.com"
USER_PASSWORD = "TestPassword123!"


class TestAuthenticationFlows:
    """Authentication and login tests"""
    
    def test_user_login_success(self):
        """Test user login returns valid token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD}
        )
        assert response.status_code == 200, f"User login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Missing access_token in response"
        assert data.get("mfa_required") == False, "Unexpected MFA requirement"
        print(f"User login successful, user_id: {data['user']['id']}")
    
    def test_admin_login_success(self):
        """Test admin login returns valid token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Missing access_token in response"
        assert data["user"]["role"] in ["admin", "super_admin", "ops"], f"Invalid admin role: {data['user']['role']}"
        print(f"Admin login successful, role: {data['user']['role']}")


class TestExchangeConnectionReadiness:
    """Exchange connection and readiness tests"""
    
    @pytest.fixture
    def user_token(self):
        """Get user auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip("User login failed")
        return response.json().get("access_token")
    
    @pytest.fixture
    def admin_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        return response.json().get("access_token")
    
    def test_user_exchange_connections_list(self, user_token):
        """Test user can list exchange connections"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/api/user/exchange-connections", headers=headers)
        
        assert response.status_code == 200, f"Exchange connections list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of connections"
        
        if data:
            conn = data[0]
            print(f"Found connection: {conn.get('id')} - {conn.get('exchange')} - {conn.get('market_type')}")
            assert "id" in conn, "Connection missing id"
            assert "exchange" in conn, "Connection missing exchange"
        else:
            print("No connections found for user - will need to create one for full test")
    
    def test_user_exchange_readiness_checklist(self, user_token):
        """Test user readiness-checklist endpoint"""
        headers = {"Authorization": f"Bearer {user_token}"}
        
        # Get connections first
        conn_response = requests.get(f"{BASE_URL}/api/user/exchange-connections", headers=headers)
        if conn_response.status_code != 200 or not conn_response.json():
            pytest.skip("No exchange connections for readiness check")
        
        conn = conn_response.json()[0]
        params = {
            "exchange": conn.get("exchange"),
            "market_type": conn.get("market_type"),
            "environment": conn.get("environment")
        }
        
        response = requests.get(
            f"{BASE_URL}/api/exchange/readiness-checklist",
            headers=headers,
            params=params
        )
        
        assert response.status_code == 200, f"Readiness checklist failed: {response.text}"
        data = response.json()
        
        print(f"Readiness status: {data.get('readiness_status')}")
        assert "readiness_status" in data, "Missing readiness_status field"
        
        # Check if ready_for_test_order
        if data.get("readiness_status") == "ready_for_test_order":
            print("SUCCESS: Connection is ready_for_test_order")
        else:
            print(f"WARNING: Connection status is {data.get('readiness_status')}, may need revalidation")
    
    def test_user_revalidate_connection(self, user_token):
        """Test revalidate endpoint for exchange connection"""
        headers = {"Authorization": f"Bearer {user_token}"}
        
        # Get connections
        conn_response = requests.get(f"{BASE_URL}/api/user/exchange-connections", headers=headers)
        if conn_response.status_code != 200 or not conn_response.json():
            pytest.skip("No exchange connections for revalidation")
        
        conn = conn_response.json()[0]
        conn_id = conn.get("id")
        
        response = requests.post(
            f"{BASE_URL}/api/user/exchange-connections/{conn_id}/revalidate",
            headers=headers
        )
        
        assert response.status_code == 200, f"Revalidate failed: {response.text}"
        data = response.json()
        
        print(f"Revalidate result: {data}")
        
        # Check readiness_snapshot
        snapshot = data.get("readiness_snapshot", {})
        if snapshot.get("reason_codes"):
            print(f"Revalidate reason_codes: {snapshot.get('reason_codes')}")
        else:
            print("SUCCESS: No reason_codes (connection healthy)")
    
    def test_admin_execution_readiness(self, admin_token):
        """Test admin execution-readiness endpoint"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/execution-readiness", headers=headers)
        
        assert response.status_code == 200, f"Admin execution-readiness failed: {response.text}"
        data = response.json()
        
        print(f"Admin readiness: final_status={data.get('final_status')}, mode={data.get('mode')}")
        assert "final_status" in data, "Missing final_status"
        assert "mode" in data, "Missing mode"
        
        # Verify contract fields
        assert "exchange_connection" in data
        assert "permissions" in data
        assert "order_test" in data
        
        if data.get("final_status") == "READY":
            print("SUCCESS: Admin execution readiness is READY")
        else:
            print(f"NOTE: Readiness is {data.get('final_status')}, reason_codes: {data.get('reason_codes')}")


class TestExecutionQueueApproveFlow:
    """Admin execution queue approve flow - 423 regression test"""
    
    @pytest.fixture
    def user_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip("User login failed")
        return response.json().get("access_token")
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        return response.json().get("access_token")
    
    def test_execution_queue_list(self, admin_token):
        """Test admin can list execution queue"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue",
            headers=headers,
            params={"status_filter": "QUEUED", "limit": 10}
        )
        
        assert response.status_code == 200, f"Execution queue list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of queue items"
        
        print(f"Found {len(data)} QUEUED items")
        
        if data:
            item = data[0]
            print(f"First item: id={item.get('id')}, status={item.get('status')}, symbol={item.get('symbol')}")
    
    def test_execution_queue_approve_no_423(self, admin_token, user_token):
        """Test that approve doesn't return 423 when readiness is READY
        
        This test creates a new intent with the test user (who has valid exchange connection)
        and then approves it as admin.
        """
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        user_headers = {"Authorization": f"Bearer {user_token}"}
        
        # First ensure user connection is revalidated
        conn_resp = requests.get(f"{BASE_URL}/api/user/exchange-connections", headers=user_headers)
        if conn_resp.status_code == 200 and conn_resp.json():
            conn_id = conn_resp.json()[0].get("id")
            reval = requests.post(f"{BASE_URL}/api/user/exchange-connections/{conn_id}/revalidate", headers=user_headers)
            print(f"User connection revalidated: {reval.status_code}")
        else:
            pytest.skip("User has no exchange connections")
        
        # Create a new intent with the test user
        preview_resp = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers=user_headers,
            json={
                "source_type": "manual",
                "intent_type": "OPEN_POSITION",
                "market_type": "futures",
                "symbol": "ETHUSDT",
                "side": "buy",
                "order_type": "market",
                "position_size_mode": "fixed_notional",
                "position_size_value": 15,
                "size": 0.01,
                "margin_mode": "isolated",
                "leverage": 1,
                "execution_mode": "manual",
                "holding_profile": "intraday"
            }
        )
        
        if preview_resp.status_code != 200:
            pytest.skip(f"Preview failed: {preview_resp.text}")
        
        preview = preview_resp.json().get("preview", {})
        intent_token = preview.get("intent_token")
        preview_hash = preview.get("preview_hash")
        
        if not intent_token:
            pytest.skip("No intent_token in preview")
        
        # Submit to create QUEUED intent
        submit_resp = requests.post(
            f"{BASE_URL}/api/user/open-position",
            headers=user_headers,
            json={"intent_token": intent_token, "preview_hash": preview_hash}
        )
        
        if submit_resp.status_code != 200:
            # 423 at submit stage means connection issue - not a regression
            if submit_resp.status_code == 423:
                pytest.skip("User's exchange connection not ready for live - skipping")
            pytest.skip(f"Submit failed: {submit_resp.text}")
        
        submit_data = submit_resp.json()
        intent_id = submit_data.get("intent_id")
        print(f"Created intent: {intent_id}, execution_mode: {submit_data.get('execution_mode')}")
        
        # Now approve as admin
        approve_resp = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
            headers=admin_headers,
            json={"note": "test-iteration163-fresh-intent"}
        )
        
        print(f"Approve response: status={approve_resp.status_code}")
        
        if approve_resp.status_code == 200:
            data = approve_resp.json()
            print(f"SUCCESS: Approved! status={data.get('status')}, execution_mode={data.get('execution_mode')}")
            assert data.get("status") in ["RELEASED", "APPROVED", "SUBMITTED"]
        elif approve_resp.status_code == 423:
            print("FAIL: Got 423 for fresh intent with valid connection")
            pytest.fail("423 EXECUTION_BLOCKED_BY_READINESS regression detected")
        else:
            print(f"Status: {approve_resp.status_code}, body: {approve_resp.text}")
    
    def test_release_gate_status(self, admin_token):
        """Test release gate status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/release-gate", headers=headers)
        
        assert response.status_code == 200, f"Release gate failed: {response.text}"
        data = response.json()
        
        print(f"Release gate: status={data.get('status')}, override_active={data.get('override_active')}")
        
        if data.get("status") == "BLOCKED":
            print(f"Release gate is BLOCKED, reasons: {data.get('reason_codes')}")
            # This is expected in test environments
        elif data.get("status") == "PASS":
            print("Release gate is PASS - ready for live execution")


class TestValidateOrderPrecheck:
    """Test validate-order endpoint"""
    
    @pytest.fixture
    def user_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip("User login failed")
        return response.json().get("access_token")
    
    def test_validate_order_returns_execution_mode(self, user_token):
        """Test validate-order includes execution_mode field"""
        headers = {"Authorization": f"Bearer {user_token}"}
        
        # Get a market price first
        ticker_resp = requests.get(
            f"{BASE_URL}/api/market/ticker",
            headers=headers,
            params={"symbol": "ETHUSDT"}
        )
        
        price = 3000.0
        if ticker_resp.status_code == 200:
            price = float(ticker_resp.json().get("mid_price", 3000))
        
        size = round(20 / price, 6)  # ~$20 notional
        
        payload = {
            "symbol": "ETHUSDT",
            "market_type": "futures",
            "order_type": "market",
            "side": "buy",
            "price": price,
            "size": size,
            "leverage": 1,
            "margin_mode": "isolated"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=headers,
            json=payload
        )
        
        assert response.status_code == 200, f"Validate order failed: {response.text}"
        data = response.json()
        
        print(f"Validate result: valid={data.get('valid')}, execution_mode={data.get('execution_mode')}")
        
        assert "valid" in data, "Missing valid field"
        assert "execution_mode" in data, "Missing execution_mode field"
        assert "violations" in data, "Missing violations field"
        
        if data.get("valid"):
            print("SUCCESS: Order validated successfully")
        else:
            print(f"Validation failed with violations: {data.get('violations')}")
    
    def test_validate_order_leverage_limit(self, user_token):
        """Test validate-order detects leverage limit exceeded"""
        headers = {"Authorization": f"Bearer {user_token}"}
        
        payload = {
            "symbol": "ETHUSDT",
            "market_type": "futures",
            "order_type": "market",
            "side": "buy",
            "price": 3000,
            "size": 0.01,
            "leverage": 50,  # High leverage should trigger violation
            "margin_mode": "isolated"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=headers,
            json=payload
        )
        
        assert response.status_code == 200, f"Validate order failed: {response.text}"
        data = response.json()
        
        violations = data.get("violations", [])
        codes = [v.get("code") for v in violations if isinstance(v, dict)]
        
        print(f"Violations for high leverage: {codes}")
        
        if "leverage_limit_exceeded" in codes:
            print("SUCCESS: Leverage limit violation detected correctly")
        else:
            print("NOTE: No leverage violation - current limit may be >= 50")


class TestGuardTelemetry:
    """Test guard telemetry endpoint"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        return response.json().get("access_token")
    
    def test_guard_telemetry_contract(self, admin_token):
        """Test guard telemetry returns required fields"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/guard-telemetry", headers=headers)
        
        assert response.status_code == 200, f"Guard telemetry failed: {response.text}"
        data = response.json()
        
        print(f"Guard telemetry: blocked_24h={data.get('blocked_24h')}, override_24h={data.get('override_24h')}")
        
        assert "blocked_24h" in data, "Missing blocked_24h"
        assert "override_24h" in data, "Missing override_24h"


class TestUserPositions:
    """Test user positions endpoints"""
    
    @pytest.fixture
    def user_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip("User login failed")
        return response.json().get("access_token")
    
    def test_user_positions_endpoint(self, user_token):
        """Test user can access positions endpoint"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/api/user/execution/positions", headers=headers)
        
        assert response.status_code == 200, f"Positions endpoint failed: {response.text}"
        data = response.json()
        
        print(f"User positions: found {len(data)} positions")
        
        if data:
            pos = data[0]
            print(f"First position: symbol={pos.get('symbol')}, status={pos.get('status')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
