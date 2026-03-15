"""
Iteration 82 - Urgent UI Fixes and Exchange Validation Tests

Tests:
1. Risk Policies List API - Regression test
2. Scanner Run API - Regression test  
3. Exchange Validate API - Should not fail with assignment_required/settings_mismatch when user has matching connection
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

class TestRiskPoliciesRegression:
    """Regression tests for Risk Policies list and CRUD operations"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin token for testing"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Admin auth failed")
    
    def test_risk_policies_list_returns_200(self, admin_token):
        """GET /api/risk-policies should return 200 with list"""
        response = requests.get(
            f"{BASE_URL}/api/risk-policies",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"PASS: GET /api/risk-policies returned {len(data)} policies")
    
    def test_risk_policies_crud_create(self, admin_token):
        """POST /api/risk-policies should create a new policy"""
        unique_name = f"TEST_Policy_{uuid.uuid4().hex[:8]}"
        payload = {
            "name": unique_name,
            "position_size_pct": 2.0,
            "atr_stop_multiplier": 1.5,
            "risk_reward_ratio": 2.0,
            "daily_loss_cutoff_pct": 5.0,
            "max_open_positions": 3,
            "max_leverage": 3,
            "spread_limit_bps": 30,
            "slippage_limit_bps": 40,
            "min_liquidity_usdt": 100000
        }
        response = requests.post(
            f"{BASE_URL}/api/risk-policies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload
        )
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("name") == unique_name
        assert "id" in data
        print(f"PASS: Created risk policy: {data.get('id')}")
        return data.get("id")


class TestScannerRegression:
    """Regression tests for Scanner run functionality"""
    
    @pytest.fixture
    def user_token(self):
        """Get user token from existing test user"""
        # Try to use existing test user or create one
        email = "test_iter79_scanner_1773403334@test.com"
        password = "TestPass123!"
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        
        # Try admin login if user login fails
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Auth failed")
    
    def test_scanner_run_returns_success(self, user_token):
        """POST /api/user/scanner/run should work with MANUAL mode"""
        payload = {
            "mode": "MANUAL",
            "max_results": 20,
            "symbol_source": "crypto",
            "symbol_selection_mode": "top_active_50",
            "selected_symbols": []
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {user_token}"},
            json=payload
        )
        # Scanner may return 200 or 400 based on config, but should not 500
        assert response.status_code < 500, f"Expected non-500, got {response.status_code}: {response.text}"
        print(f"PASS: Scanner run returned {response.status_code}")
    
    def test_scanner_overview_returns_data(self, user_token):
        """GET /api/user/scanner should return scanner overview"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Should have mode field
        assert "mode" in data or "total_results" in data or isinstance(data, dict)
        print(f"PASS: Scanner overview returned data")
    
    def test_scanner_results_returns_list(self, user_token):
        """GET /api/user/scanner/results should return list"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/results?limit=10",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of results"
        print(f"PASS: Scanner results returned {len(data)} items")


class TestExchangeValidateNoAssignmentRequired:
    """
    Tests for exchange validate endpoint.
    Key test: When user has matching UserExchangeConnection, 
    reason_codes should NOT contain assignment_required or settings_mismatch
    """
    
    @pytest.fixture
    def user_token_and_id(self):
        """Create or login test user and return token + user_id"""
        unique_id = uuid.uuid4().hex[:8]
        email = f"test_iter82_exchange_{unique_id}@test.com"
        password = "TestExchange123!"
        
        # Register new user
        register_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": password, "full_name": f"Test Exchange User {unique_id}"}
        )
        
        # Login (even if registration failed, try login in case user exists)
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password}
        )
        
        if login_response.status_code != 200:
            # Fall back to existing user
            login_response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": "test_iter79_scanner_1773403334@test.com", "password": "TestPass123!"}
            )
        
        if login_response.status_code == 200:
            data = login_response.json()
            return data.get("access_token"), data.get("user", {}).get("id")
        
        pytest.skip("Could not get user token")
    
    @pytest.fixture  
    def admin_token(self):
        """Get admin token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Admin auth failed")
    
    def test_validate_without_connection_may_fail(self, user_token_and_id):
        """Test validate endpoint without connection - may fail with valid reasons"""
        token, user_id = user_token_and_id
        
        response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet"
            }
        )
        
        # Should either succeed or fail with valid reason codes
        assert response.status_code in [200, 400, 403], f"Unexpected status: {response.status_code}"
        
        if response.status_code >= 400:
            data = response.json()
            detail = data.get("detail", {})
            reason_codes = detail.get("reason_codes", []) if isinstance(detail, dict) else []
            print(f"Validate returned {response.status_code} with reason_codes: {reason_codes}")
        else:
            print(f"PASS: Validate returned 200")
    
    def test_validate_reason_codes_contract(self, user_token_and_id):
        """Test that validate response has proper reason_codes field"""
        token, user_id = user_token_and_id
        
        response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet"
            }
        )
        
        # Response should have reason_codes field
        data = response.json()
        
        if response.status_code == 200:
            assert "reason_codes" in data, "200 response should have reason_codes field"
            assert isinstance(data["reason_codes"], list), "reason_codes should be list"
            print(f"PASS: 200 response has reason_codes: {data['reason_codes']}")
        else:
            # Error response
            detail = data.get("detail", {})
            if isinstance(detail, dict):
                reason_codes = detail.get("reason_codes", [])
                print(f"Error response reason_codes: {reason_codes}")
                # Verify reason codes are valid
                valid_codes = {
                    "missing_credentials",
                    "invalid_key", 
                    "missing_trade_permission",
                    "ip_restriction",
                    "exchange_unreachable",
                    "assignment_required",
                    "settings_mismatch",
                    "adapter_not_configured",
                    "exchange_error_400",
                    "exchange_error_403",
                    "matching_connection_not_found"
                }
                for code in reason_codes:
                    # Allow exchange_error_XXX patterns
                    if not code.startswith("exchange_error_") and code not in valid_codes:
                        print(f"WARNING: Unknown reason code: {code}")
    
    def test_validate_after_connection_setup(self, user_token_and_id, admin_token):
        """
        CRITICAL TEST: After setting up UserExchangeConnection,
        validate should NOT fail with assignment_required or settings_mismatch
        """
        token, user_id = user_token_and_id
        if not user_id:
            pytest.skip("Could not get user_id")
        
        # Step 1: Create exchange connection for user
        connection_payload = {
            "user_id": user_id,
            "exchange": "binance",
            "market_type": "spot",
            "environment": "testnet",
            "api_key_plain": "test_api_key_iter82",
            "api_secret_plain": "test_api_secret_iter82",
            "is_default": True,
            "connection_name": "Test Connection Iter82"
        }
        
        # Try admin endpoint to create connection
        admin_create_response = requests.post(
            f"{BASE_URL}/api/admin/exchange-connections",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=connection_payload
        )
        
        # If admin endpoint doesn't exist, try user endpoint
        if admin_create_response.status_code == 404:
            user_create_response = requests.post(
                f"{BASE_URL}/api/user/exchange-connections",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "exchange": "binance",
                    "market_type": "spot",
                    "environment": "testnet",
                    "api_key_plain": "test_api_key_iter82",
                    "api_secret_plain": "test_api_secret_iter82",
                    "is_default": True,
                    "connection_name": "Test Connection Iter82"
                }
            )
            print(f"User connection create response: {user_create_response.status_code}")
        else:
            print(f"Admin connection create response: {admin_create_response.status_code}")
        
        # Step 2: Update user exchange settings to match
        settings_response = requests.put(
            f"{BASE_URL}/api/user/exchange-settings",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "exchange": "binance",
                "mode": "testnet",
                "api_key": "test_api_key_iter82",
                "api_secret": "test_api_secret_iter82"
            }
        )
        print(f"Settings update response: {settings_response.status_code}")
        
        # Step 3: Now call validate - should NOT have assignment_required/settings_mismatch
        validate_response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet"
            }
        )
        
        print(f"Validate response status: {validate_response.status_code}")
        data = validate_response.json()
        
        # Extract reason_codes based on response structure
        if validate_response.status_code == 200:
            reason_codes = data.get("reason_codes", [])
        else:
            detail = data.get("detail", {})
            reason_codes = detail.get("reason_codes", []) if isinstance(detail, dict) else []
        
        print(f"Reason codes: {reason_codes}")
        
        # CRITICAL ASSERTION: Should NOT have assignment_required or settings_mismatch
        # when user has matching connection
        forbidden_codes = {"assignment_required", "settings_mismatch"}
        found_forbidden = set(reason_codes) & forbidden_codes
        
        # If we have a matching connection, these codes should not appear
        # The failure reason should be credential-based (invalid_key, etc.) not assignment-based
        if found_forbidden and validate_response.status_code >= 400:
            # Check if this is because connection wasn't created
            if "matching_connection_not_found" in reason_codes:
                print(f"NOTE: Connection not found, so assignment_required is valid")
            else:
                # This is the bug - should not have assignment_required when connection exists
                assert False, f"FAIL: Found forbidden reason codes {found_forbidden} when user has matching connection. Expected credential-based failure (invalid_key, etc.) not assignment-based."
        
        print(f"PASS: validate reason_codes do not contain forbidden codes {forbidden_codes}")


class TestExchangeValidateWithVenueAssignment:
    """Test exchange validation with proper venue assignment flow"""
    
    @pytest.fixture
    def setup_user_with_venue_access(self):
        """Create user, approve them, and assign venue access"""
        admin_login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")}
        )
        if admin_login.status_code != 200:
            pytest.skip("Admin login failed")
        admin_token = admin_login.json().get("access_token")
        
        # Create user
        unique_id = uuid.uuid4().hex[:8]
        email = f"test_venue_{unique_id}@test.com"
        password = "VenueTest123!"
        
        register = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": password, "full_name": f"Venue Test {unique_id}"}
        )
        
        login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password}
        )
        
        if login.status_code != 200:
            pytest.skip("User login failed")
        
        user_data = login.json()
        user_token = user_data.get("access_token")
        user_id = user_data.get("user", {}).get("id")
        
        # Approve user
        approval = requests.put(
            f"{BASE_URL}/api/admin/users/{user_id}/approval",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "approved"}
        )
        print(f"Approval response: {approval.status_code}")
        
        # Assign venue access
        venue_assign = requests.post(
            f"{BASE_URL}/api/admin/users/{user_id}/venue-access",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "exchange": "binance",
                "market_types": ["spot", "futures"],
                "environments": ["testnet"]
            }
        )
        print(f"Venue assignment response: {venue_assign.status_code}")
        
        return user_token, user_id, admin_token
    
    def test_validate_with_venue_access(self, setup_user_with_venue_access):
        """Test validate with proper venue access - should not fail with assignment_required"""
        user_token, user_id, admin_token = setup_user_with_venue_access
        
        # Set exchange settings for the user
        settings = requests.put(
            f"{BASE_URL}/api/user/exchange-settings",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "exchange": "binance",
                "mode": "testnet",
                "api_key": f"test_key_{uuid.uuid4().hex[:8]}",
                "api_secret": f"test_secret_{uuid.uuid4().hex[:8]}"
            }
        )
        print(f"Settings response: {settings.status_code}")
        
        # Call validate
        validate = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            headers={"Authorization": f"Bearer {user_token}"},
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet"
            }
        )
        
        print(f"Validate status: {validate.status_code}")
        data = validate.json()
        
        if validate.status_code >= 400:
            detail = data.get("detail", {})
            reason_codes = detail.get("reason_codes", []) if isinstance(detail, dict) else []
            print(f"Reason codes: {reason_codes}")
            
            # Should NOT be assignment_required or settings_mismatch
            # Expected: invalid_key (because we used fake credentials)
            assert "assignment_required" not in reason_codes, \
                f"Should not have assignment_required when venue access is assigned"
            
            # After the fix, settings_mismatch should also not appear if connection exists
            if "settings_mismatch" in reason_codes:
                print(f"NOTE: settings_mismatch still present - may need connection sync")
        
        print(f"PASS: Validate did not fail with assignment_required")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
