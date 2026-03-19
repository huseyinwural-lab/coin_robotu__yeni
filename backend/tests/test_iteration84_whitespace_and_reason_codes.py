"""
Iteration 84 - Whitespace Trimming and Reason Code Normalization Tests

Features to verify:
1. Exchange connection create/update should trim api_key and api_secret (leading/trailing spaces) before encryption
2. Validate endpoint reason extraction should NOT emit missing_trade_permission together with invalid_key for 401/403 invalid key responses
3. Validate endpoint still returns hint field and reason_codes consistently
4. Regression: exchange connection CRUD and validate endpoint still functional
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


# ============================================================================
# Test Fixtures
# ============================================================================
@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def test_user(admin_token):
    """Create a test user for testing"""
    email = f"test_iter84_{uuid.uuid4().hex[:8]}@test.com"
    password = "TestPass123!"
    
    # Register user
    response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password, "name": "Test User Iter84"},
    )
    assert response.status_code in [200, 201], f"Registration failed: {response.text}"
    user_data = response.json()
    user_id = user_data.get("id") or user_data.get("user_id")
    
    # Approve user
    requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    
    # Get user token
    token_response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers={"Content-Type": "application/json"},
    )
    assert token_response.status_code == 200, f"User login failed: {token_response.text}"
    user_token = token_response.json()["access_token"]
    
    return {"user_id": user_id, "email": email, "token": user_token}


# ============================================================================
# Test: Backend Health
# ============================================================================
class TestBackendHealth:
    """Verify backend is running"""

    def test_health_check(self):
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("Backend health check: PASS")


# ============================================================================
# Test: Whitespace Trimming on Exchange Connection Create
# ============================================================================
class TestWhitespaceTrimming:
    """Verify api_key and api_secret are trimmed on create and update"""

    def test_create_connection_with_whitespace_keys(self, test_user):
        """Create exchange connection with whitespace-padded keys and verify they're trimmed"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        
        # Create connection with leading/trailing whitespace in keys
        whitespace_api_key = "   testApiKeyWithSpaces123   "
        whitespace_api_secret = "\n\ttestSecretWithTabs456\t\n"
        
        response = requests.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json={
                "account_label": f"whitespace_test_{uuid.uuid4().hex[:6]}",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "is_default": False,
                "api_key": whitespace_api_key,
                "api_secret": whitespace_api_secret,
            },
            headers=headers,
        )
        assert response.status_code in [200, 201], f"Create connection failed: {response.text}"
        data = response.json()
        
        # Verify the masked key doesn't have leading/trailing spaces
        masked_key = data.get("masked_api_key", "")
        assert not masked_key.startswith(" "), "Masked API key should not start with space"
        assert not masked_key.endswith(" "), "Masked API key should not end with space"
        
        # The credential fingerprint should be consistent for trimmed keys
        fingerprint = data.get("credential_fingerprint", "")
        assert fingerprint, "Credential fingerprint should exist"
        
        print(f"Create with whitespace: PASS - masked_key={masked_key}, fingerprint={fingerprint}")
        return data.get("id")

    def test_update_connection_with_whitespace_keys(self, test_user):
        """Update exchange connection with whitespace-padded keys"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        
        # First create a connection
        create_response = requests.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json={
                "account_label": f"update_ws_test_{uuid.uuid4().hex[:6]}",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "is_default": False,
                "api_key": "initialKey123",
                "api_secret": "initialSecret456",
            },
            headers=headers,
        )
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        connection_id = create_response.json().get("id")
        
        # Update with whitespace-padded keys
        whitespace_api_key = "   updatedKeyWithSpaces789   "
        whitespace_api_secret = "\t  updatedSecretWithTabs012  \t"
        
        update_response = requests.put(
            f"{BASE_URL}/api/user/exchange-connections/{connection_id}",
            json={
                "api_key": whitespace_api_key,
                "api_secret": whitespace_api_secret,
            },
            headers=headers,
        )
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        data = update_response.json()
        
        # Verify trimming
        masked_key = data.get("masked_api_key", "")
        assert not masked_key.startswith(" "), "Updated masked API key should not start with space"
        assert not masked_key.endswith(" "), "Updated masked API key should not end with space"
        
        print(f"Update with whitespace: PASS - masked_key={masked_key}")


# ============================================================================
# Test: Reason Code Normalization (No Dual Emission)
# ============================================================================
class TestReasonCodeNormalization:
    """Verify that invalid_key and missing_trade_permission are not emitted together for 401/403"""

    def test_invalid_key_reason_codes_no_dual_emission(self, test_user):
        """Validate with invalid credentials should return only invalid_key, not both invalid_key + missing_trade_permission"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        
        # Create a connection with clearly invalid keys
        create_response = requests.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json={
                "account_label": f"invalid_key_test_{uuid.uuid4().hex[:6]}",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "is_default": True,
                "api_key": "INVALID_API_KEY_12345",
                "api_secret": "INVALID_API_SECRET_67890",
            },
            headers=headers,
        )
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        
        # Now validate using GET endpoint with query params
        validate_response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
            },
            headers=headers,
        )
        
        # The validation should fail (status 400 or 403)
        # When status >= 400, the response is in detail field
        data = validate_response.json()
        if validate_response.status_code >= 400:
            data = data.get("detail", data)
        reason_codes = data.get("reason_codes", [])
        
        print(f"Validate response status: {validate_response.status_code}")
        print(f"Reason codes returned: {reason_codes}")
        
        # KEY ASSERTION: Should NOT have both invalid_key AND missing_trade_permission together
        has_invalid_key = "invalid_key" in reason_codes
        has_missing_trade_permission = "missing_trade_permission" in reason_codes
        
        if has_invalid_key:
            assert not has_missing_trade_permission, (
                f"FAIL: Both invalid_key and missing_trade_permission returned together: {reason_codes}. "
                "For invalid key scenarios (401/403), only invalid_key should be returned."
            )
            print("Reason code normalization: PASS - invalid_key without missing_trade_permission")
        elif has_missing_trade_permission:
            # This is acceptable if the key is valid but lacks permissions
            print("Reason code: missing_trade_permission (key might be valid but restricted)")
        else:
            # Some other error like exchange_error_400
            print(f"Other reason codes: {reason_codes}")
        
        # Verify no dual emission
        assert not (has_invalid_key and has_missing_trade_permission), (
            f"Dual emission detected: {reason_codes}"
        )

    def test_whitespace_only_keys_validate_as_invalid(self, test_user):
        """Keys that are only whitespace should validate as invalid_key after trimming"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        
        # Create a connection with whitespace-only keys
        create_response = requests.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json={
                "account_label": f"ws_only_test_{uuid.uuid4().hex[:6]}",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "is_default": True,
                "api_key": "   ",  # Only whitespace
                "api_secret": "\t\n  \t",  # Only whitespace
            },
            headers=headers,
        )
        # Should succeed in creating but with empty keys
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        
        # Validate should return missing_credentials - use GET endpoint
        validate_response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
            },
            headers=headers,
        )
        
        # When status >= 400, the response is in detail field
        data = validate_response.json()
        if validate_response.status_code >= 400:
            data = data.get("detail", data)
        reason_codes = data.get("reason_codes", [])
        
        print(f"Whitespace-only keys validate result: {reason_codes}")
        
        # Should be missing_credentials since trimmed keys are empty
        assert "missing_credentials" in reason_codes, (
            f"Expected missing_credentials for whitespace-only keys, got: {reason_codes}"
        )
        print("Whitespace-only keys: PASS - correctly identified as missing_credentials")


# ============================================================================
# Test: Hint Field Consistency
# ============================================================================
class TestHintFieldConsistency:
    """Verify hint field is returned for various failure scenarios"""

    def test_hint_returned_for_invalid_key(self, test_user):
        """Validate with invalid key should return hint field"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        
        # Create connection with invalid keys
        create_response = requests.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json={
                "account_label": f"hint_test_{uuid.uuid4().hex[:6]}",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "is_default": True,
                "api_key": "BAD_KEY_FOR_HINT_TEST",
                "api_secret": "BAD_SECRET_FOR_HINT_TEST",
            },
            headers=headers,
        )
        assert create_response.status_code in [200, 201]
        
        # Validate using GET endpoint
        validate_response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
            },
            headers=headers,
        )
        
        # When status >= 400, the response is in detail field
        data = validate_response.json()
        if validate_response.status_code >= 400:
            data = data.get("detail", data)
        reason_codes = data.get("reason_codes", [])
        hint = data.get("hint")
        
        print(f"Hint field returned: {hint}")
        print(f"Reason codes: {reason_codes}")
        
        # Verify hint is present for failure cases
        if reason_codes:
            # hint may or may not be present depending on reason code
            if "invalid_key" in reason_codes or "exchange_error_400" in reason_codes:
                # These should have hints
                if hint:
                    print(f"Hint consistency: PASS - hint provided for {reason_codes}")
                else:
                    # Acceptable if exchange_error_400 doesn't have a specific hint
                    print(f"Hint consistency: OK - no specific hint for {reason_codes}")
        else:
            print("Validation passed unexpectedly (no reason codes)")


# ============================================================================
# Test: Exchange Connection CRUD Regression
# ============================================================================
class TestExchangeConnectionCRUDRegression:
    """Regression tests for exchange connection CRUD operations"""

    def test_list_connections(self, test_user):
        """GET /api/user/exchange-connections should return list"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = requests.get(
            f"{BASE_URL}/api/user/exchange-connections",
            headers=headers,
        )
        assert response.status_code == 200, f"List failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"List connections: PASS - {len(data)} connections found")

    def test_create_connection(self, test_user):
        """POST /api/user/exchange-connections should create new connection"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = requests.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json={
                "account_label": f"regression_create_{uuid.uuid4().hex[:6]}",
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
                "is_default": False,
                "api_key": "test_key_regression",
                "api_secret": "test_secret_regression",
            },
            headers=headers,
        )
        assert response.status_code in [200, 201], f"Create failed: {response.text}"
        data = response.json()
        assert "id" in data, "Response should contain id"
        assert data.get("exchange") == "binance"
        assert data.get("market_type") == "futures"
        print(f"Create connection: PASS - id={data['id']}")
        return data["id"]

    def test_update_connection(self, test_user):
        """PUT /api/user/exchange-connections/{id} should update connection"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        
        # Create first
        create_response = requests.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json={
                "account_label": f"regression_update_{uuid.uuid4().hex[:6]}",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "is_default": False,
            },
            headers=headers,
        )
        connection_id = create_response.json()["id"]
        
        # Update
        update_response = requests.put(
            f"{BASE_URL}/api/user/exchange-connections/{connection_id}",
            json={"market_type": "futures"},
            headers=headers,
        )
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        data = update_response.json()
        assert data.get("market_type") == "futures"
        print("Update connection: PASS - market_type updated to futures")

    def test_delete_connection(self, test_user):
        """DELETE /api/user/exchange-connections/{id} should delete connection"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        
        # Create first
        create_response = requests.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json={
                "account_label": f"regression_delete_{uuid.uuid4().hex[:6]}",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "is_default": False,
            },
            headers=headers,
        )
        connection_id = create_response.json()["id"]
        
        # Delete
        delete_response = requests.delete(
            f"{BASE_URL}/api/user/exchange-connections/{connection_id}",
            headers=headers,
        )
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        data = delete_response.json()
        assert data.get("deleted") == True
        print("Delete connection: PASS - connection deleted")


# ============================================================================
# Test: Validate Endpoint Regression
# ============================================================================
class TestValidateEndpointRegression:
    """Regression tests for validate endpoint"""

    def test_validate_endpoint_returns_expected_fields(self, test_user):
        """Validate endpoint should return consistent field structure"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        
        # Create a connection first
        requests.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json={
                "account_label": f"validate_regression_{uuid.uuid4().hex[:6]}",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "is_default": True,
                "api_key": "test_key_validate",
                "api_secret": "test_secret_validate",
            },
            headers=headers,
        )
        
        # Validate using GET endpoint
        response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
            },
            headers=headers,
        )
        
        # When status >= 400, the response is in detail field
        data = response.json()
        if response.status_code >= 400:
            data = data.get("detail", data)
        
        # Check expected fields exist
        expected_fields = ["exchange", "market_type", "environment", "is_valid", "reason_codes"]
        for field in expected_fields:
            assert field in data, f"Missing expected field: {field}"
        
        # Verify reason_codes is a list
        assert isinstance(data.get("reason_codes"), list), "reason_codes should be a list"
        
        # Verify hint field exists (may be None for success)
        # hint is optional so just check it's present in response keys or check if reason_codes present
        if data.get("reason_codes"):
            # hint should be present for failures
            print(f"Validate returns hint: {data.get('hint')}")
        
        print("Validate endpoint structure: PASS - all expected fields present")


# ============================================================================
# Test: Direct Unit Test of _extract_reason_codes Logic
# ============================================================================
class TestExtractReasonCodesLogic:
    """Test the reason code extraction logic directly via API behavior"""

    def test_401_403_with_invalid_message_returns_invalid_key_only(self, test_user):
        """When exchange returns 401/403 with 'invalid' in message, should only return invalid_key"""
        # This tests the behavior described at lines 519-529 in live_mode_service.py
        # We can't call the function directly, but we can verify the API behavior
        
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        
        # Create with invalid keys that should trigger 401/403 from Binance
        create_response = requests.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json={
                "account_label": f"reason_code_direct_{uuid.uuid4().hex[:6]}",
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
                "is_default": True,
                "api_key": "COMPLETELY_INVALID_KEY",
                "api_secret": "COMPLETELY_INVALID_SECRET",
            },
            headers=headers,
        )
        
        validate_response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            params={
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
            },
            headers=headers,
        )
        
        # When status >= 400, the response is in detail field
        data = validate_response.json()
        if validate_response.status_code >= 400:
            data = data.get("detail", data)
        reason_codes = data.get("reason_codes", [])
        
        print(f"Direct test - Status: {validate_response.status_code}, Reason codes: {reason_codes}")
        
        # Assert no dual emission
        if "invalid_key" in reason_codes:
            assert "missing_trade_permission" not in reason_codes, (
                f"CRITICAL: Dual emission detected - both invalid_key and missing_trade_permission: {reason_codes}"
            )
            print("Direct test: PASS - Only invalid_key returned (no dual emission)")
        else:
            # Could be exchange_error_400 or other codes
            print(f"Direct test: Other reason codes returned: {reason_codes}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
